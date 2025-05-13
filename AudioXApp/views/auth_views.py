import json
import random
import logging # Import the logging module

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET # For GET requests to render pages
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.core.validators import validate_email
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db.utils import IntegrityError
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm # For password validation
from django.contrib.auth.tokens import default_token_generator # For more secure tokens (optional for now, sticking to OTP)


from ..models import User
from .utils import _get_full_context # Assuming this utility exists

# Get an instance of a logger
logger = logging.getLogger(__name__)

def signup(request):
    """
    Handles user signup.
    - Validates form data including OTP.
    - Creates a new user if validation passes.
    - Returns JSON responses for AJAX requests.
    """
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
        
        if email and 'email' not in errors and User.objects.filter(email=email).exists():
            errors['email'] = "Email already exists."
        if username and 'username' not in errors and User.objects.filter(username=username).exists():
            errors['username'] = "Username already exists."

        if entered_otp:
            stored_otp = request.session.get('otp') # For signup
            stored_email_for_otp = request.session.get('otp_email') # For signup
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
            pass 

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
            logger.error(f"IntegrityError during signup for {username}/{email}: {ie}")
            error_field = 'username' if 'username' in str(ie).lower() else 'email'
            return JsonResponse({'status': 'error', 'message': f'{error_field.capitalize()} already exists (database constraint).', 'errors': {error_field: f'{error_field.capitalize()} already exists.'}}, status=400)
        except ValueError as ve: 
            logger.error(f"ValueError during signup for {username}/{email}: {ve}")
            return JsonResponse({'status': 'error', 'message': str(ve)}, status=400)
        except Exception as e:
            logger.error(f"Unexpected error during signup for {username}/{email}: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': f"An unexpected error occurred during account creation. Please try again later or contact support."}, status=500)

    context = _get_full_context(request)
    return render(request, 'auth/signup.html', context)


def send_otp(request): # Removed purpose from signature, will get from JSON
    """
    Sends an OTP to the provided email for a specified purpose (signup, login 2FA, or password_reset).
    - Validates email format.
    - Checks for existing user if purpose is signup or if user must exist for password_reset.
    - Generates, stores OTP in session, and emails it.
    - Returns JSON responses.
    """
    if request.method == 'POST':
        email = None
        purpose = None # Initialize purpose

        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                email = data.get('email')
                purpose = data.get('purpose') # Get purpose from JSON
            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
        else: # Fallback for form data if not JSON (though frontend uses JSON)
            email = request.POST.get('email')
            purpose = request.POST.get('purpose', 'signup') # Default purpose if not specified

        if not email:
            return JsonResponse({'status': 'error', 'message': 'Email address is required.'}, status=400)
        if not purpose or purpose not in ['signup', 'login', 'password_reset']:
             return JsonResponse({'status': 'error', 'message': 'Invalid or missing OTP purpose.'}, status=400)

        try:
            validate_email(email)
        except ValidationError:
            return JsonResponse({'status': 'error', 'message': 'Invalid email address format.'}, status=400)

        session_otp_key = ''
        session_email_key = ''
        subject = ''
        message_body_template = ''

        if purpose == 'signup':
            if User.objects.filter(email=email).exists():
                return JsonResponse({'status': 'error', 'message': 'This email address is already registered.'}, status=400)
            session_otp_key = 'otp' 
            session_email_key = 'otp_email' 
            subject = 'Your OTP for AudioX Signup'
            message_body_template = 'Your One-Time Password (OTP) for AudioX signup is: {otp}\n\nThis OTP is valid for 5 minutes.'
        
        elif purpose == 'login':
            try:
                user = User.objects.get(email=email)
                if not user.is_2fa_enabled:
                    return JsonResponse({'status': 'error', 'message': '2FA is not enabled for this account.'}, status=400)
            except User.DoesNotExist:
                # Generic message to prevent user enumeration for login 2FA OTP send.
                # The main login view handles "user does not exist" before this.
                return JsonResponse({'status': 'success', 'message': 'If an account with that email exists and requires 2FA, an OTP has been sent.'})
            session_otp_key = 'login_otp'
            session_email_key = 'login_email_pending_2fa'
            subject = 'Your AudioX Login Verification Code'
            message_body_template = 'Your One-Time Password (OTP) for AudioX login is: {otp}\n\nThis OTP is valid for 5 minutes.'
        
        elif purpose == 'password_reset':
            try:
                user = User.objects.get(email=email) # User must exist to reset password
            except User.DoesNotExist:
                 # To prevent user enumeration, send a generic success-like message.
                 # The frontend will proceed to OTP entry, but verification will fail if no OTP was actually stored.
                logger.info(f"Password reset OTP requested for non-existent email: {email}")
                return JsonResponse({'status': 'success', 'message': 'If your email address is registered, you will receive a password reset code.'})

            session_otp_key = 'password_reset_otp'
            session_email_key = 'password_reset_email'
            subject = 'Your AudioX Password Reset Code'
            message_body_template = 'Your One-Time Password (OTP) to reset your AudioX password is: {otp}\n\nThis OTP is valid for 5 minutes. If you did not request this, please ignore this email.'

        otp_value = str(random.randint(100000, 999999))
        request.session[session_otp_key] = otp_value
        request.session[session_email_key] = email
        request.session.set_expiry(300) # OTP valid for 5 minutes

        try:
            send_mail(
                subject,
                message_body_template.format(otp=otp_value),
                settings.EMAIL_HOST_USER,
                [email],
                fail_silently=False,
            )
            success_message = f'An OTP has been sent to {email}.'
            return JsonResponse({'status': 'success', 'message': success_message})

        except Exception as e:
            logger.error(f"Failed to send OTP email for {purpose} to {email}: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': 'Failed to send OTP email. Please try again later.'}, status=500)
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
                    otp_response = send_otp(request) # Purpose is now derived from JSON
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
                            return JsonResponse({'status': 'error', 'message': otp_data.get('message', 'Failed to send OTP for 2FA.')}, status=500)
                    except json.JSONDecodeError:
                        return JsonResponse({'status': 'error', 'message': 'Error processing 2FA OTP request.'}, status=500)
                else:
                    status_code = otp_response.status_code if otp_response else 500
                    error_message = 'Failed to initiate 2FA verification.'
                    try:
                        if otp_response: 
                            error_data = json.loads(otp_response.content)
                            if error_data.get('message'): error_message = error_data['message'] # Corrected: was error
                    except (json.JSONDecodeError, AttributeError): pass 
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
        return JsonResponse({'status': 'error', 'message': 'Invalid request type. AJAX POST required.'}, status=400)

    try:
        data = json.loads(request.body)
        entered_otp = data.get('otp')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)

    if not entered_otp:
        return JsonResponse({'status': 'error', 'message': 'OTP is required.'}, status=400)

    stored_otp = request.session.get('login_otp')
    user_email_for_2fa = request.session.get('2fa_user_email') 
    user_id_for_2fa = request.session.get('2fa_user_id') 

    if not stored_otp or not user_email_for_2fa or not user_id_for_2fa:
        return JsonResponse({'status': 'error', 'message': 'Verification session expired or invalid. Please try logging in again.'}, status=400)

    if entered_otp == stored_otp:
        try:
            user = User.objects.get(pk=user_id_for_2fa, email=user_email_for_2fa)
            auth_login(request, user) 
            for key in ['login_otp', 'login_email_pending_2fa', '2fa_user_email', '2fa_user_id']:
                request.session.pop(key, None)
            redirect_url = reverse('AudioXApp:home')
            return JsonResponse({'status': 'success', 'message': 'Verification successful! Logging you in...', 'redirect_url': redirect_url})
        except User.DoesNotExist:
            for key in ['login_otp', 'login_email_pending_2fa', '2fa_user_email', '2fa_user_id']:
                request.session.pop(key, None)
            return JsonResponse({'status': 'error', 'message': 'User verification failed. Please try logging in again.'}, status=400)
        except Exception as e:
            logger.error(f"Error during final login step of 2FA: {e}", exc_info=True)
            for key in ['login_otp', 'login_email_pending_2fa', '2fa_user_email', '2fa_user_id']:
                request.session.pop(key, None) 
            return JsonResponse({'status': 'error', 'message': 'An error occurred during login. Please try again.'}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid verification code.'}, status=400)

# --- Forgot Password Views ---

def forgot_password_request(request):
    """
    Renders the forgot password page (email entry).
    The actual OTP sending is handled by the existing 'send_otp' view with purpose='password_reset'.
    """
    context = _get_full_context(request)
    return render(request, 'auth/forgotpassword.html', context)

@require_POST
def verify_password_reset_otp(request):
    """
    Verifies the OTP entered for password reset.
    If successful, it sets a session flag and prepares data for the reset_password_form view.
    """
    try:
        data = json.loads(request.body)
        email = data.get('email')
        entered_otp = data.get('otp')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)

    if not email or not entered_otp:
        return JsonResponse({'status': 'error', 'message': 'Email and OTP are required.'}, status=400)

    stored_otp = request.session.get('password_reset_otp')
    stored_email = request.session.get('password_reset_email')

    if not stored_otp or not stored_email or stored_email != email:
        return JsonResponse({'status': 'error', 'message': 'OTP session expired or email mismatch. Please request a new OTP.'}, status=400)

    if entered_otp == stored_otp:
        request.session['password_reset_verified_email'] = email
        request.session['password_reset_verified_otp'] = entered_otp 
        request.session.set_expiry(300) 
        
        return JsonResponse({'status': 'success', 'message': 'OTP verified successfully. Proceed to reset your password.'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid OTP entered.'}, status=400)


def reset_password_form(request):
    """
    Renders the page where the user can enter their new password.
    This view expects 'email' and 'otp' (the verified OTP) as GET parameters.
    """
    email = request.GET.get('email')
    otp = request.GET.get('otp') 

    verified_email_in_session = request.session.get('password_reset_verified_email')
    verified_otp_in_session = request.session.get('password_reset_verified_otp')

    if not email or not otp or email != verified_email_in_session or otp != verified_otp_in_session:
        messages.error(request, "Invalid or expired password reset link/session. Please try again.")
        return redirect('AudioXApp:forgot_password') 

    # Corrected context creation
    context = _get_full_context(request)
    context.update({'email': email, 'otp': otp})
    return render(request, 'auth/resetpassword.html', context)


@require_POST
def reset_password_confirm(request):
    """
    Processes the new password submission.
    Requires email, the verified OTP (or a more secure token), and new passwords.
    """
    try:
        data = json.loads(request.body)
        email = data.get('email')
        otp = data.get('otp') 
        new_password = data.get('new_password')
        confirm_new_password = data.get('confirm_new_password')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)

    errors = {}
    if not email: errors['email'] = "Email is missing." 
    if not otp: errors['otp'] = "OTP/Token is missing." 
    if not new_password: errors['new_password'] = "New password is required."
    if not confirm_new_password: errors['confirm_new_password'] = "Please confirm your new password."

    if new_password and confirm_new_password and new_password != confirm_new_password:
        errors['confirm_new_password'] = "Passwords do not match."
    
    if new_password and len(new_password) < 8: 
        errors['new_password'] = "Password must be at least 8 characters long."

    verified_email_in_session = request.session.get('password_reset_verified_email')
    verified_otp_in_session = request.session.get('password_reset_verified_otp')

    if not verified_email_in_session or not verified_otp_in_session or \
       email != verified_email_in_session or otp != verified_otp_in_session:
        logger.warning(f"Password reset attempt for {email} failed session validation.")
        return JsonResponse({'status': 'error', 'message': 'Invalid or expired password reset session. Please start over.'}, status=403)

    if errors:
        return JsonResponse({'status': 'error', 'message': 'Please correct the errors.', 'errors': errors}, status=400)

    try:
        user = User.objects.get(email=email)
        user.set_password(new_password)
        user.save()
        
        for key in ['password_reset_otp', 'password_reset_email', 'password_reset_verified_email', 'password_reset_verified_otp']:
            request.session.pop(key, None)
        
        return JsonResponse({'status': 'success', 'message': 'Your password has been reset successfully. You can now login.'})
    except User.DoesNotExist:
        logger.error(f"User not found during password reset confirm for email: {email}")
        return JsonResponse({'status': 'error', 'message': 'User not found. Password reset failed.'}, status=404)
    except Exception as e:
        logger.error(f"Error during password reset confirm for {email}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred. Please try again.'}, status=500)


@login_required
def logout_view(request):
    try:
        username = request.user.username 
        auth_logout(request)
        messages.success(request, f"User '{username}' has been successfully logged out.")
    except AttributeError: 
        auth_logout(request) 
        messages.success(request, "You have been successfully logged out.")
    except Exception as e:
        logger.error(f"Error during logout: {e}", exc_info=True)
        messages.error(request, "An error occurred during logout. Please try again.")
    return redirect('AudioXApp:home')
