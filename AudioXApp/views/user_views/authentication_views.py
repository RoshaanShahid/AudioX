# AudioXApp/views/user_views/authentication_views.py

import json
import random
import logging

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.core.validators import validate_email
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db.utils import IntegrityError
from django.db.models import Q # Import Q for complex lookups

from ...models import User
from ..utils import _get_full_context

logger = logging.getLogger(__name__)

def signup(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        username = request.POST.get('username')
        email = request.POST.get('email')
        phone_number_from_form = request.POST.get('phone') # This is '+92xxxxxxxxx'
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm-password')
        entered_otp = request.POST.get('otp')
        # Bio is not collected on your signup.html, so it will be None by default in the model

        errors = {}
        if not full_name: errors['full_name'] = "Full name is required."
        if not username: errors['username'] = "Username is required."
        if not email: errors['email'] = "Email is required."
        if not phone_number_from_form: errors['phone'] = "Phone number is required." # Error for the form field
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

        if email and 'email' not in errors and User.objects.filter(email__iexact=email).exists():
            errors['email'] = "Email already exists."
        if username and 'username' not in errors and User.objects.filter(username__iexact=username).exists():
            errors['username'] = "Username already exists."
        
        # Phone number validation (basic check, model might have more)
        if phone_number_from_form and not (phone_number_from_form.startswith('+92') and len(phone_number_from_form) == 13 and phone_number_from_form[3:].isdigit()):
             errors['phone'] = 'Invalid phone number format from form.'


        if entered_otp:
            stored_otp = request.session.get('otp')
            stored_email_for_otp = request.session.get('otp_email')
            if not stored_otp or not stored_email_for_otp:
                errors['otp'] = "OTP session expired or not found. Please request a new OTP."
            elif email and email.lower() != stored_email_for_otp.lower():
                errors['otp'] = "OTP verification failed (email mismatch). Please request a new OTP for the correct email."
            elif entered_otp != stored_otp:
                errors['otp'] = "Incorrect OTP entered."

        if errors:
            return JsonResponse({'status': 'error', 'message': "Please correct the errors below.", 'errors': errors}, status=400)

        try:
            if 'otp' in request.session: del request.session['otp']
            if 'otp_email' in request.session: del request.session['otp_email']
        except KeyError:
            pass

        # Ensure phone_number is saved as submitted (it's required on form)
        # Bio will be None as it's not on the form and model defaults to None
        phone_to_save = phone_number_from_form # It's required, so should have a value

        try:
            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
                username=username,
                phone_number=phone_to_save, # Will be saved as provided
                bio=None # Explicitly None as it's not on signup form
            )
            # user.requires_extra_details_post_social_signup will be False (default)
            user.subscription_type = 'FR'
            user.save(update_fields=['subscription_type'])

            logger.info(f"New user signed up via form: {user.username} ({user.email})")
            return JsonResponse({'status': 'success', 'message': 'Account created successfully! You can now log in.'})
        except IntegrityError as ie:
            logger.warning(f"IntegrityError during form signup for email {email} or username {username}: {ie}")
            error_field = 'username' if 'username' in str(ie).lower() else 'email'
            return JsonResponse({'status': 'error', 'message': f'{error_field.capitalize()} already exists (database constraint).', 'errors': {error_field: f'{error_field.capitalize()} already exists.'}}, status=400)
        except ValueError as ve:
            logger.warning(f"ValueError during form signup for email {email}: {ve}")
            return JsonResponse({'status': 'error', 'message': str(ve)}, status=400)
        except Exception as e:
            logger.error(f"Unexpected error during form signup for email {email}: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': f"An unexpected error occurred. Please try again later."}, status=500)

    context = _get_full_context(request)
    return render(request, 'auth/signup.html', context)


def send_otp(request):
    if request.method == 'POST':
        email = None
        purpose = None

        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                email = data.get('email')
                purpose = data.get('purpose')
            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
        else:
            email = request.POST.get('email')
            purpose = request.POST.get('purpose', 'signup')

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

        if purpose in ['login', 'password_reset']:
            try:
                user_check = User.objects.get(email__iexact=email)
                if hasattr(user_check, 'is_banned_by_admin') and (user_check.is_banned_by_admin or not user_check.is_active):
                    logger.warning(f"OTP request for banned/inactive user: {email} (Purpose: {purpose})")
                    # Still send generic success to not reveal account status for banned users
                    if purpose == 'login':
                        return JsonResponse({'status': 'success', 'message': 'If an account with that email exists and requires 2FA, an OTP has been sent.'})
                    elif purpose == 'password_reset':
                        return JsonResponse({'status': 'success', 'message': 'If your email address is registered and active, you will receive a password reset code.'})
            except User.DoesNotExist:
                pass # Will be handled by generic messages below to not reveal account existence

        if purpose == 'signup':
            if User.objects.filter(email__iexact=email).exists():
                return JsonResponse({'status': 'error', 'message': 'This email address is already registered.'}, status=400)
            session_otp_key = 'otp'
            session_email_key = 'otp_email'
            subject = 'Your OTP for AudioX Signup'
            message_body_template = 'Your One-Time Password (OTP) for AudioX signup is: {otp}\n\nThis OTP is valid for 5 minutes.'

        elif purpose == 'login':
            try:
                user = User.objects.get(email__iexact=email)
                if not user.is_2fa_enabled: # Only send OTP if 2FA is enabled
                    return JsonResponse({'status': 'error', 'message': '2FA is not enabled for this account.'}, status=400)
            except User.DoesNotExist:
                # Generic message to not reveal if account exists or if 2FA is not enabled
                return JsonResponse({'status': 'success', 'message': 'If an account with that email exists and requires 2FA, an OTP has been sent.'})
            session_otp_key = 'login_otp'
            session_email_key = 'login_email_pending_2fa'
            subject = 'Your AudioX Login Verification Code'
            message_body_template = 'Your One-Time Password (OTP) for AudioX login is: {otp}\n\nThis OTP is valid for 5 minutes.'

        elif purpose == 'password_reset':
            try:
                User.objects.get(email__iexact=email) # Check if user exists
            except User.DoesNotExist:
                # Generic message to not reveal account existence
                return JsonResponse({'status': 'success', 'message': 'If your email address is registered, you will receive a password reset code.'})
            session_otp_key = 'password_reset_otp'
            session_email_key = 'password_reset_email'
            subject = 'Your AudioX Password Reset Code'
            message_body_template = 'Your One-Time Password (OTP) to reset your AudioX password is: {otp}\n\nThis OTP is valid for 5 minutes. If you did not request this, please ignore this email.'

        otp_value = str(random.randint(100000, 999999))
        request.session[session_otp_key] = otp_value
        request.session[session_email_key] = email
        request.session.set_expiry(300) # 5 minutes

        try:
            send_mail(
                subject, message_body_template.format(otp=otp_value),
                settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False,
            )
            logger.info(f"OTP sent to {email} for purpose: {purpose}")
            success_message = f'An OTP has been sent to {email}.'
            
            # For login/password_reset, use generic messages if user didn't exist to avoid account enumeration
            user_actually_exists = User.objects.filter(email__iexact=email).exists()
            if purpose == 'login' and not user_actually_exists:
                success_message = 'If an account with that email exists and requires 2FA, an OTP has been sent.'
            elif purpose == 'password_reset' and not user_actually_exists:
                success_message = 'If your email address is registered, you will receive a password reset code.'

            return JsonResponse({'status': 'success', 'message': success_message})
        except Exception as e_mail:
            logger.error(f"Failed to send OTP email to {email} for purpose {purpose}: {e_mail}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': 'Failed to send OTP email. Please try again later.'}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


def login(request):
    if request.method == 'POST':
        login_identifier = request.POST.get('loginIdentifier')
        password = request.POST.get('password')

        if not login_identifier or not password:
            return JsonResponse({'status': 'error', 'message': "Email/Username and password are required."}, status=400)

        try:
            user_obj = User.objects.get(Q(email__iexact=login_identifier) | Q(username__iexact=login_identifier))
        except User.DoesNotExist:
            user_obj = None

        if user_obj:
            if hasattr(user_obj, 'is_banned_by_admin') and (user_obj.is_banned_by_admin or not user_obj.is_active):
                ban_reason = user_obj.platform_ban_reason if user_obj.is_banned_by_admin and user_obj.platform_ban_reason else "Your account is currently disabled or has been blocked by an administrator."
                logger.warning(f"Login attempt by banned/inactive user: {user_obj.username}. Reason: {ban_reason}")
                auth_logout(request)
                return JsonResponse({'status': 'error', 'message': ban_reason, 'is_banned': True,}, status=403)

            user = authenticate(request, username=user_obj.email, password=password)

            if user is not None: # Password is correct
                for key in ['2fa_user_email', '2fa_user_id', 'login_otp', 'login_email_pending_2fa']:
                    request.session.pop(key, None)

                # --- MODIFIED PROFILE INCOMPLETENESS CHECK (APPLIES BEFORE 2FA or direct login) ---
                profile_phone_is_missing = (user.phone_number is None or user.phone_number.strip() == '')
                # full_name check is optional here as allauth usually populates it from Google.
                # Your signup form requires it, so normal users will have it.
                # profile_full_name_is_missing = (user.full_name is None or user.full_name.strip() == '')

                needs_social_completion_flow = getattr(user, 'requires_extra_details_post_social_signup', False)

                if needs_social_completion_flow and profile_phone_is_missing:
                    request.session['profile_incomplete'] = True # For middleware
                    logger.info(f"User {user.username} (social signup) requires phone number completion. Prompting for profile completion.")
                    # Even if 2FA is enabled, profile completion takes precedence here as per your logic for social users
                    return JsonResponse({'status': 'profile_incomplete', 'redirect_url': reverse('AudioXApp:complete_profile')})
                else:
                    # If not a social user needing completion, or if their phone is filled, clear any lingering session flag
                    if 'profile_incomplete' in request.session:
                        if not (needs_social_completion_flow and profile_phone_is_missing):
                            request.session.pop('profile_incomplete', None)
                # --- END MODIFIED CHECK ---

                if user.is_2fa_enabled: # Now proceed to 2FA if applicable AND profile is complete for social users
                    json_data_for_otp = json.dumps({'email': user.email, 'purpose': 'login'})
                    original_method = request.method
                    original_content_type = request.content_type
                    original_body = request.body
                    request.method = 'POST'
                    request.content_type = 'application/json'
                    request.body = json_data_for_otp.encode('utf-8')
                    otp_response = None
                    try:
                        otp_response = send_otp(request)
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
                                logger.info(f"2FA OTP sent for user {user.email} (after profile check).")
                                return JsonResponse({'status': '2fa_required', 'email': user.email})
                            else:
                                return JsonResponse({'status': 'error', 'message': otp_data.get('message', 'Failed to send OTP for 2FA.')}, status=500)
                        except json.JSONDecodeError:
                            logger.error("Error decoding JSON response from internal send_otp call for 2FA.")
                            return JsonResponse({'status': 'error', 'message': 'Error processing 2FA OTP request.'}, status=500)
                    else:
                        status_code = otp_response.status_code if otp_response else 500
                        error_message = 'Failed to initiate 2FA verification.'
                        try:
                            if otp_response: error_data = json.loads(otp_response.content); error_message = error_data.get('message', error_message)
                        except: pass
                        return JsonResponse({'status': 'error', 'message': error_message}, status=status_code)
                else: # 2FA not enabled, and profile completion not required for this user, log in directly
                    auth_login(request, user)
                    logger.info(f"User {user.username} logged in successfully (no 2FA, profile complete/not required).")
                    home_url = reverse('AudioXApp:home')
                    return JsonResponse({'status': 'success', 'redirect_url': home_url})
            else: # Password incorrect
                logger.warning(f"Incorrect password for user: {login_identifier}")
                return JsonResponse({'status': 'error', 'message': "Incorrect email/username or password."}, status=401)
        else: # User not found
            logger.warning(f"Login attempt for non-existent user: {login_identifier}")
            return JsonResponse({'status': 'error', 'message': "Incorrect email/username or password."}, status=401)

    context = _get_full_context(request)
    return render(request, 'auth/login.html', context)


@require_POST
def verify_login_otp(request):
    # ... (initial checks for AJAX, JSON data, OTP presence are fine) ...
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
            user = User.objects.get(pk=user_id_for_2fa, email__iexact=user_email_for_2fa)
            if hasattr(user, 'is_banned_by_admin') and (user.is_banned_by_admin or not user.is_active):
                ban_reason = user.platform_ban_reason if user.is_banned_by_admin and user.platform_ban_reason else "Your account is currently disabled or blocked."
                logger.warning(f"Login attempt during 2FA OTP verification by banned/inactive user: {user.username}")
                auth_logout(request)
                for key in ['login_otp', 'login_email_pending_2fa', '2fa_user_email', '2fa_user_id']: request.session.pop(key, None)
                return JsonResponse({'status': 'error', 'message': ban_reason, 'is_banned': True}, status=403)

            auth_login(request, user) # Log the user in
            for key in ['login_otp', 'login_email_pending_2fa', '2fa_user_email', '2fa_user_id']:
                request.session.pop(key, None)
            
            logger.info(f"User {user.username} completed 2FA and logged in.")

            # --- RE-APPLY THE SAME PROFILE INCOMPLETENESS CHECK AS IN LOGIN VIEW ---
            # This is because the login view might have been bypassed if 2FA was the first step shown after password.
            # However, our login view logic now checks profile completion *before* 2FA trigger if applicable.
            # So, this check here might be redundant if the login view always handles it first.
            # But, keeping it provides a safeguard. If the user was already in a 2FA flow and their
            # profile somehow became "incomplete" for social users, this would catch it.
            # Given the current flow, it's less likely to be hit if login() did its job.

            profile_phone_is_missing = (user.phone_number is None or user.phone_number.strip() == '')
            needs_social_completion_flow = getattr(user, 'requires_extra_details_post_social_signup', False)

            if needs_social_completion_flow and profile_phone_is_missing:
                request.session['profile_incomplete'] = True # For middleware
                logger.info(f"User {user.username} (social signup, post-2FA) still requires phone number completion.")
                return JsonResponse({'status': 'profile_incomplete', 'redirect_url': reverse('AudioXApp:complete_profile')})
            else:
                # If this point is reached, profile is complete or not required for social user.
                # Ensure the session flag is cleared if it was somehow set.
                if 'profile_incomplete' in request.session:
                    if not (needs_social_completion_flow and profile_phone_is_missing):
                        request.session.pop('profile_incomplete', None)
            # --- END MODIFIED CHECK ---
            
            redirect_url = reverse('AudioXApp:home')
            return JsonResponse({'status': 'success', 'message': 'Verification successful! Logging you in...', 'redirect_url': redirect_url})
        except User.DoesNotExist:
            logger.warning(f"User for 2FA verification not found: email {user_email_for_2fa}, id {user_id_for_2fa}")
            for key in ['login_otp', 'login_email_pending_2fa', '2fa_user_email', '2fa_user_id']: request.session.pop(key, None)
            return JsonResponse({'status': 'error', 'message': 'User verification failed. Please try logging in again.'}, status=400)
        except Exception as e:
            logger.error(f"Error during 2FA login for user {user_email_for_2fa}: {e}", exc_info=True)
            for key in ['login_otp', 'login_email_pending_2fa', '2fa_user_email', '2fa_user_id']: request.session.pop(key, None)
            return JsonResponse({'status': 'error', 'message': 'An error occurred during login. Please try again.'}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid verification code.'}, status=400)


# --- forgot_password_request, verify_password_reset_otp, reset_password_form, reset_password_confirm, logout_view functions remain the same ---
def forgot_password_request(request):
    context = _get_full_context(request)
    return render(request, 'auth/forgotpassword.html', context)


@require_POST
def verify_password_reset_otp(request):
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

    if not stored_otp or not stored_email or stored_email.lower() != email.lower():
        return JsonResponse({'status': 'error', 'message': 'OTP session expired or email mismatch. Please request a new OTP.'}, status=400)

    if entered_otp == stored_otp:
        request.session['password_reset_verified_email'] = email
        request.session['password_reset_verified_otp'] = entered_otp
        request.session.set_expiry(300) # 5 minutes
        logger.info(f"Password reset OTP verified for {email}")
        return JsonResponse({'status': 'success', 'message': 'OTP verified successfully. Proceed to reset your password.'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid OTP entered.'}, status=400)


def reset_password_form(request):
    email = request.GET.get('email')
    otp = request.GET.get('otp')

    verified_email_in_session = request.session.get('password_reset_verified_email')
    verified_otp_in_session = request.session.get('password_reset_verified_otp')

    if not email or not otp or \
       not verified_email_in_session or not verified_otp_in_session or \
       email.lower() != verified_email_in_session.lower() or otp != verified_otp_in_session:
        messages.error(request, "Invalid or expired password reset link/session. Please start the password reset process again.")
        return redirect('AudioXApp:forgot_password')

    context = _get_full_context(request)
    context.update({'email': email, 'otp': otp})
    return render(request, 'auth/resetpassword.html', context)


@require_POST
def reset_password_confirm(request):
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
    
    if new_password and len(new_password) < 8: # Example minimum length
        errors['new_password'] = "Password must be at least 8 characters long."

    verified_email_in_session = request.session.get('password_reset_verified_email')
    verified_otp_in_session = request.session.get('password_reset_verified_otp')

    if not verified_email_in_session or not verified_otp_in_session or \
       email.lower() != verified_email_in_session.lower() or otp != verified_otp_in_session:
        logger.warning(f"Password reset attempt with mismatched session data for email {email}.")
        return JsonResponse({'status': 'error', 'message': 'Invalid or expired password reset session. Please start over.'}, status=403)

    if errors:
        return JsonResponse({'status': 'error', 'message': 'Please correct the errors.', 'errors': errors}, status=400)

    try:
        user = User.objects.get(email__iexact=email)
        if hasattr(user, 'is_banned_by_admin') and (user.is_banned_by_admin or not user.is_active):
            ban_reason = user.platform_ban_reason if user.is_banned_by_admin and user.platform_ban_reason else "Your account is currently disabled or blocked."
            logger.warning(f"Password reset attempt for banned/inactive user: {user.username}")
            return JsonResponse({'status': 'error', 'message': ban_reason, 'is_banned': True}, status=403)

        user.set_password(new_password)
        user.save()

        for key in ['password_reset_otp', 'password_reset_email', 'password_reset_verified_email', 'password_reset_verified_otp']:
            request.session.pop(key, None)
        
        logger.info(f"Password successfully reset for user {user.email}")
        return JsonResponse({'status': 'success', 'message': 'Your password has been reset successfully. You can now login.'})
    except User.DoesNotExist:
        logger.error(f"User not found during password reset confirmation for email {email}, though OTP was verified.")
        return JsonResponse({'status': 'error', 'message': 'User not found. Password reset failed.'}, status=404)
    except Exception as e:
        logger.error(f"Unexpected error during password reset confirmation for email {email}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred. Please try again.'}, status=500)


@login_required
def logout_view(request):
    try:
        username_display = request.user.username 
        auth_logout(request)
        messages.success(request, f"User '{username_display}' has been successfully logged out.")
        logger.info(f"User {username_display} logged out.")
    except AttributeError: 
        auth_logout(request)
        messages.success(request, "You have been successfully logged out.")
        logger.info("Anonymous user session logged out.")
    except Exception as e:
        logger.error(f"Error during logout: {e}", exc_info=True)
        messages.error(request, "An error occurred during logout. Please try again.")
    return redirect('AudioXApp:home')