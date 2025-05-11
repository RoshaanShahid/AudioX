import json
import random

from django.shortcuts import render, redirect
from django.http import JsonResponse, QueryDict
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.core.validators import validate_email
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db.utils import IntegrityError

from ..models import User
from .utils import _get_full_context


def signup(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        username = request.POST.get('username')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm-password')
        entered_otp = request.POST.get('otp')
        bio = request.POST.get('bio', '')

        errors = {}
        if not full_name: errors['full_name'] = "Full name is required."
        if not username: errors['username'] = "Username is required."
        if not email: errors['email'] = "Email is required."
        if not password: errors['password'] = "Password is required."
        if not confirm_password: errors['confirm-password'] = "Password confirmation is required."
        if not entered_otp: errors['otp'] = "OTP is required."

        if password and confirm_password and password != confirm_password:
            errors['confirm-password'] = "Passwords don't match."

        if email:
            try:
                validate_email(email)
            except ValidationError:
                errors['email'] = 'Invalid email address format.'
        else:
            pass

        if email and 'email' not in errors and User.objects.filter(email=email).exists():
            errors['email'] = "Email already exists."
        if username and 'username' not in errors and User.objects.filter(username=username).exists():
            errors['username'] = "Username already exists."

        if entered_otp:
            stored_otp = request.session.get('otp')
            stored_email_for_otp = request.session.get('otp_email')
            if not stored_otp or not stored_email_for_otp:
                errors['otp'] = "OTP session expired or not found. Please request a new OTP."
            elif email and email != stored_email_for_otp:
                errors['otp'] = "OTP verification failed (email mismatch). Please request a new OTP."
            elif entered_otp != stored_otp:
                errors['otp'] = "Incorrect OTP entered."

        if errors:
            return JsonResponse({'status': 'error', 'message': "Please correct the errors below.", 'errors': errors}, status=400)

        try:
            del request.session['otp']
            del request.session['otp_email']
        except KeyError:
            pass # OTP already cleared or not set

        if not phone_number:
            phone_number = ''
        if not bio:
            bio = ''

        try:
            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
                username=username,
                phone_number=phone_number,
                bio=bio
            )
            user.subscription_type = 'FR'
            user.save(update_fields=['subscription_type'])
            return JsonResponse({'status': 'success', 'message': 'Account created successfully! You can now log in.'})

        except IntegrityError as ie:
            error_field = 'username' if 'username' in str(ie).lower() else 'email'
            return JsonResponse({'status': 'error', 'message': f'{error_field.capitalize()} already exists (database constraint).', 'errors': {error_field: f'{error_field.capitalize()} already exists.'}}, status=400)
        except ValueError as ve:
            return JsonResponse({'status': 'error', 'message': str(ve)}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"An unexpected error occurred during account creation. Please try again later or contact support."}, status=500)

    context = _get_full_context(request)
    return render(request, 'auth/signup.html', context)


def send_otp(request, purpose='signup'):
    if request.method == 'POST':
        email = None
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                email = data.get('email')
                purpose_from_json = data.get('purpose', purpose)
                if purpose_from_json in ['signup', 'login']:
                    purpose = purpose_from_json
            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
        else:
            email = request.POST.get('email')

        if not email:
            return JsonResponse({'status': 'error', 'message': 'Email address is required.'}, status=400)
        try:
            validate_email(email)
        except ValidationError:
            return JsonResponse({'status': 'error', 'message': 'Invalid email address format.'}, status=400)

        session_otp_key = ''
        session_email_key = ''
        subject = ''
        message_body = ''
        log_purpose = ''

        if purpose == 'signup':
            if User.objects.filter(email=email).exists():
                return JsonResponse({'status': 'error', 'message': 'This email address is already registered.'}, status=400)
            session_otp_key = 'otp'
            session_email_key = 'otp_email'
            subject = 'Your OTP for AudioX Signup'
            message_body = 'Your One-Time Password (OTP) for AudioX signup is: {otp}\n\nThis OTP is valid for 5 minutes.'
            log_purpose = 'Signup'
        elif purpose == 'login':
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return JsonResponse({'status': 'success', 'message': 'If an account with that email exists and requires 2FA, an OTP has been sent.'})

            session_otp_key = 'login_otp'
            session_email_key = 'login_email_pending_2fa'
            subject = 'Your AudioX Login Verification Code'
            message_body = 'Your One-Time Password (OTP) for AudioX login is: {otp}\n\nThis OTP is valid for 5 minutes.'
            log_purpose = 'Login 2FA'
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid OTP purpose specified.'}, status=400)

        otp = str(random.randint(100000, 999999))
        request.session[session_otp_key] = otp
        request.session[session_email_key] = email
        request.session.set_expiry(300)

        try:
            send_mail(
                subject,
                message_body.format(otp=otp),
                settings.EMAIL_HOST_USER,
                [email],
                fail_silently=False,
            )
            success_message = 'OTP successfully sent to your email.' if purpose == 'signup' else 'A verification code has been sent to your email.'
            return JsonResponse({'status': 'success', 'message': success_message})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': 'Failed to send OTP email. Please check server logs or contact support.'}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


def login(request):
    if request.method == 'POST':
        login_identifier = request.POST.get('loginIdentifier')
        password = request.POST.get('password')

        if not login_identifier or not password:
            return JsonResponse({'status': 'error', 'message': "Email/Username and password are required."}, status=400)

        user = authenticate(request, username=login_identifier, password=password)

        if user is not None:
            for key in ['2fa_user_email', '2fa_user_id', 'login_otp', 'login_email_pending_2fa']:
                request.session.pop(key, None)

            if user.is_2fa_enabled:
                json_data_for_otp = json.dumps({'email': user.email, 'purpose': 'login'})
                original_method = request.method
                original_content_type = request.content_type
                original_body = request.body
                request.method = 'POST'
                request.content_type = 'application/json'
                request.body = json_data_for_otp.encode('utf-8')

                otp_response = None
                try:
                    otp_response = send_otp(request, purpose='login')
                finally:
                    request.method = original_method
                    request.content_type = original_content_type
                    request.body = original_body

                if otp_response and otp_response.status_code == 200:
                    try:
                        otp_data = json.loads(otp_response.content)
                        if otp_data.get('status') == 'success':
                            request.session['2fa_user_email'] = user.email
                            request.session['2fa_user_id'] = user.pk
                            request.session.set_expiry(300)
                            return JsonResponse({'status': '2fa_required', 'email': user.email})
                        else:
                            return JsonResponse({'status': 'error', 'message': otp_data.get('message', 'Failed to send OTP.')}, status=500)
                    except json.JSONDecodeError:
                        return JsonResponse({'status': 'error', 'message': 'Error processing OTP request.'}, status=500)
                else:
                    status_code = otp_response.status_code if otp_response else 500
                    error_message = 'Failed to initiate 2FA verification.'
                    try:
                        if otp_response:
                            error_data = json.loads(otp_response.content)
                            if error_data.get('message'): error_message = error_data['message']
                    except json.JSONDecodeError: pass
                    return JsonResponse({'status': 'error', 'message': error_message}, status=status_code)
            else:
                auth_login(request, user)
                home_url = reverse('AudioXApp:home')
                return JsonResponse({'status': 'success', 'redirect_url': home_url})
        else:
            return JsonResponse({'status': 'error', 'message': "Incorrect email/username or password."}, status=401)

    context = _get_full_context(request)
    return render(request, 'auth/login.html', context)


@require_POST
def verify_login_otp(request):
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    if not is_ajax:
        return JsonResponse({'status': 'error', 'message': 'Invalid request type.'}, status=400)

    try:
        data = json.loads(request.body)
        entered_otp = data.get('otp')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)

    if not entered_otp:
        return JsonResponse({'status': 'error', 'message': 'OTP is required.'}, status=400)

    stored_otp = request.session.get('login_otp')
    user_email = request.session.get('2fa_user_email')
    user_id = request.session.get('2fa_user_id')

    if not stored_otp or not user_email or not user_id:
        return JsonResponse({'status': 'error', 'message': 'Verification session expired or invalid. Please try logging in again.'}, status=400)

    if entered_otp == stored_otp:
        try:
            user = User.objects.get(pk=user_id, email=user_email)
            auth_login(request, user)
            for key in ['login_otp', 'login_email_pending_2fa', '2fa_user_email', '2fa_user_id']:
                request.session.pop(key, None)
            redirect_url = reverse('AudioXApp:home')
            return JsonResponse({'status': 'success', 'message': 'Verification successful!', 'redirect_url': redirect_url})
        except User.DoesNotExist:
            for key in ['login_otp', 'login_email_pending_2fa', '2fa_user_email', '2fa_user_id']:
               request.session.pop(key, None)
            return JsonResponse({'status': 'error', 'message': 'User verification failed. Please try logging in again.'}, status=400)
        except Exception as e:
           for key in ['login_otp', 'login_email_pending_2fa', '2fa_user_email', '2fa_user_id']:
                request.session.pop(key, None)
           return JsonResponse({'status': 'error', 'message': 'An error occurred during login. Please try again.'}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid verification code.'}, status=400)


@login_required
def logout_view(request):
    try:
        username = request.user.username
        auth_logout(request)
        messages.success(request, f"User '{username}' has been successfully logged out.")
        return redirect('AudioXApp:home')
    except AttributeError:
        auth_logout(request)
        messages.success(request, "You have been successfully logged out.")
        return redirect('AudioXApp:home')
    except Exception as e:
        messages.error(request, "An error occurred during logout. Please try again.")
        return redirect('AudioXApp:home')


def forgot_password_view(request):
    context = _get_full_context(request)
    return render(request, 'auth/forgotpassword.html', context)

def handle_forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        if not email:
            messages.error(request, 'Please enter an email address.')
            context = _get_full_context(request)
            return render(request, 'auth/forgotpassword.html', context)
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.success(request, 'If an account with that email exists, an OTP has been sent.')
            return redirect('AudioXApp:verify_otp')

        otp = str(random.randint(100000, 999999))
        request.session['reset_otp'] = otp
        request.session['reset_email'] = email
        request.session.set_expiry(300)
        try:
            send_mail(
                'Password Reset OTP for AudioX',
                f'Your OTP for password reset is: {otp}. It is valid for 5 minutes.',
                settings.EMAIL_HOST_USER,
                [email],
                fail_silently=False
            )
            messages.success(request, 'If an account with that email exists, an OTP has been sent.')
            return redirect('AudioXApp:verify_otp')
        except Exception as e:
            messages.error(request, 'There was an error sending the OTP email. Please try again later.')
            context = _get_full_context(request)
            return render(request, 'auth/forgotpassword.html', context)
    context = _get_full_context(request)
    return render(request, 'auth/forgotpassword.html', context)

def verify_otp_view(request):
    context = _get_full_context(request)
    if 'reset_email' not in request.session:
        messages.warning(request, 'Password reset session expired or invalid. Please request a new OTP.')
        return redirect('AudioXApp:forgot_password')

    reset_email = request.session.get('reset_email')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp')
        stored_otp = request.session.get('reset_otp')

        if not entered_otp:
            messages.error(request, 'Please enter the OTP.')
            return render(request, 'auth/verify_otp.html', context)

        if stored_otp is None:
            messages.error(request, 'OTP has expired. Please request a new one.')
            request.session.pop('reset_email', None)
            return redirect('AudioXApp:forgot_password')

        if entered_otp == stored_otp:
            request.session['reset_otp_verified'] = True
            request.session.pop('reset_otp', None)
            request.session.set_expiry(600)
            return redirect('AudioXApp:reset_password')
        else:
            messages.error(request, 'Incorrect OTP entered.')
            return render(request, 'auth/verify_otp.html', context)

    return render(request, 'auth/verify_otp.html', context)

def reset_password_view(request):
    context = _get_full_context(request)
    reset_email = request.session.get('reset_email')
    is_verified = request.session.get('reset_otp_verified')

    if not is_verified or not reset_email:
        messages.error(request, 'Invalid password reset request or session expired. Please start again.')
        for key in ['reset_email', 'reset_otp_verified', 'reset_otp']:
            request.session.pop(key, None)
        return redirect('AudioXApp:forgot_password')

    if request.method == 'POST':
        new_password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if not new_password or not confirm_password:
            messages.error(request, 'Please enter and confirm your new password.')
            return render(request, 'auth/reset_password.html', context)
        if new_password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'auth/reset_password.html', context)

        try:
            user = User.objects.get(email=reset_email)
            user.set_password(new_password)
            user.save()

            for key in ['reset_email', 'reset_otp_verified', 'reset_otp']:
                request.session.pop(key, None)

            messages.success(request, 'Your password has been reset successfully. You can now log in.')
            return redirect('AudioXApp:login')

        except User.DoesNotExist:
            messages.error(request, 'User not found. Please start the password reset process again.')
            for key in ['reset_email', 'reset_otp_verified', 'reset_otp']:
                request.session.pop(key, None)
            return redirect('AudioXApp:forgot_password')
        except Exception as e:
            messages.error(request, 'An unexpected error occurred while resetting your password.')
            return render(request, 'auth/reset_password.html', context)

    return render(request, "auth/reset_password.html", context)
