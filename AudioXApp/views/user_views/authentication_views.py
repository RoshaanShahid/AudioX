# AudioXApp/views/user_views/authentication_views.py

import json
import random
import logging # It's good practice to have logging

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

from ...models import User # Relative import: ...models because we are in views/user_views/
from ..utils import _get_full_context # Relative import: ..utils because utils.py is in views/

logger = logging.getLogger(__name__)

# --- Authentication Views ---

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
        phone_number = request.POST.get('phone') # Assuming 'phone' is the field name
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm-password')
        entered_otp = request.POST.get('otp')
        bio = request.POST.get('bio', '') # Default to empty string if not provided

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

        if email and 'email' not in errors and User.objects.filter(email__iexact=email).exists(): # Use iexact for case-insensitive check
            errors['email'] = "Email already exists."
        if username and 'username' not in errors and User.objects.filter(username__iexact=username).exists(): # Use iexact
            errors['username'] = "Username already exists."

        if entered_otp:
            stored_otp = request.session.get('otp') # Assuming 'otp' is the session key for signup OTP
            stored_email_for_otp = request.session.get('otp_email') # Assuming 'otp_email' is for signup
            if not stored_otp or not stored_email_for_otp:
                errors['otp'] = "OTP session expired or not found. Please request a new OTP."
            elif email and email.lower() != stored_email_for_otp.lower(): # Case-insensitive email check
                errors['otp'] = "OTP verification failed (email mismatch). Please request a new OTP for the correct email."
            elif entered_otp != stored_otp:
                errors['otp'] = "Incorrect OTP entered."

        if errors:
            return JsonResponse({'status': 'error', 'message': "Please correct the errors below.", 'errors': errors}, status=400)

        # Clear OTP from session after successful validation or if there were no other errors
        try:
            if 'otp' in request.session: del request.session['otp']
            if 'otp_email' in request.session: del request.session['otp_email']
        except KeyError:
            pass # Should not happen if keys were checked above, but good practice

        # Ensure phone_number and bio have default values if empty
        if not phone_number: phone_number = ''
        if not bio: bio = ''

        try:
            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
                username=username,
                phone_number=phone_number,
                bio=bio
            )
            # Default subscription type, if applicable
            user.subscription_type = 'FR' # Assuming 'FR' is the code for Free
            user.save(update_fields=['subscription_type'])
            
            logger.info(f"New user signed up: {user.username} ({user.email})")
            return JsonResponse({'status': 'success', 'message': 'Account created successfully! You can now log in.'})

        except IntegrityError as ie:
            logger.warning(f"IntegrityError during signup for email {email} or username {username}: {ie}")
            error_field = 'username' if 'username' in str(ie).lower() else 'email'
            return JsonResponse({'status': 'error', 'message': f'{error_field.capitalize()} already exists (database constraint).', 'errors': {error_field: f'{error_field.capitalize()} already exists.'}}, status=400)
        except ValueError as ve: # From User.objects.create_user if required fields are missing
            logger.warning(f"ValueError during signup for email {email}: {ve}")
            return JsonResponse({'status': 'error', 'message': str(ve)}, status=400)
        except Exception as e:
            logger.error(f"Unexpected error during signup for email {email}: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': f"An unexpected error occurred during account creation. Please try again later or contact support."}, status=500)

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
        else: # Fallback for form data if needed, though AJAX JSON is typical for this
            email = request.POST.get('email')
            purpose = request.POST.get('purpose', 'signup') # Default purpose

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
            if User.objects.filter(email__iexact=email).exists():
                return JsonResponse({'status': 'error', 'message': 'This email address is already registered.'}, status=400)
            session_otp_key = 'otp' # For signup
            session_email_key = 'otp_email' # For signup
            subject = 'Your OTP for AudioX Signup'
            message_body_template = 'Your One-Time Password (OTP) for AudioX signup is: {otp}\n\nThis OTP is valid for 5 minutes.'
        
        elif purpose == 'login': # For 2FA login
            try:
                user = User.objects.get(email__iexact=email)
                if not user.is_2fa_enabled: # Check if 2FA is actually enabled for this user
                    return JsonResponse({'status': 'error', 'message': '2FA is not enabled for this account.'}, status=400)
            except User.DoesNotExist:
                # Don't reveal if user exists or not for 2FA login OTP request to prevent enumeration
                return JsonResponse({'status': 'success', 'message': 'If an account with that email exists and requires 2FA, an OTP has been sent.'})
            session_otp_key = 'login_otp'
            session_email_key = 'login_email_pending_2fa' # To store email for which 2FA is pending
            subject = 'Your AudioX Login Verification Code'
            message_body_template = 'Your One-Time Password (OTP) for AudioX login is: {otp}\n\nThis OTP is valid for 5 minutes.'

        elif purpose == 'password_reset':
            try:
                User.objects.get(email__iexact=email) # Check if user exists
            except User.DoesNotExist:
                # Don't reveal if user exists for password reset to prevent enumeration
                return JsonResponse({'status': 'success', 'message': 'If your email address is registered, you will receive a password reset code.'})
            
            session_otp_key = 'password_reset_otp'
            session_email_key = 'password_reset_email'
            subject = 'Your AudioX Password Reset Code'
            message_body_template = 'Your One-Time Password (OTP) to reset your AudioX password is: {otp}\n\nThis OTP is valid for 5 minutes. If you did not request this, please ignore this email.'

        otp_value = str(random.randint(100000, 999999))
        request.session[session_otp_key] = otp_value
        request.session[session_email_key] = email # Store the email for which OTP was sent
        request.session.set_expiry(300) # OTP valid for 5 minutes

        try:
            send_mail(
                subject,
                message_body_template.format(otp=otp_value),
                settings.EMAIL_HOST_USER,
                [email],
                fail_silently=False,
            )
            logger.info(f"OTP sent to {email} for purpose: {purpose}")
            success_message = f'An OTP has been sent to {email}.'
            if purpose == 'password_reset' or (purpose == 'login' and not User.objects.filter(email__iexact=email).exists()):
                 success_message = 'If your email address is registered, you will receive a code.' # More generic for password reset / non-existent user 2FA
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

        user = authenticate(request, username=login_identifier, password=password)

        if user is not None:
            # Clear any previous 2FA session data
            for key in ['2fa_user_email', '2fa_user_id', 'login_otp', 'login_email_pending_2fa']:
                request.session.pop(key, None)

            if user.is_2fa_enabled:
                # Prepare to call send_otp internally for 2FA
                json_data_for_otp = json.dumps({'email': user.email, 'purpose': 'login'})
                
                # Temporarily modify request for send_otp call
                original_method = request.method
                original_content_type = request.content_type
                original_body = request.body
                
                request.method = 'POST' # send_otp expects POST
                request.content_type = 'application/json'
                request.body = json_data_for_otp.encode('utf-8')
                
                otp_response = None
                try:
                    otp_response = send_otp(request) # Call send_otp
                finally: # Restore original request attributes
                    request.method = original_method
                    request.content_type = original_content_type
                    request.body = original_body

                if otp_response and otp_response.status_code == 200:
                    try:
                        otp_data = json.loads(otp_response.content)
                        if otp_data.get('status') == 'success':
                            request.session['2fa_user_email'] = user.email # Store email for verification step
                            request.session['2fa_user_id'] = user.pk # Store user PK for verification step
                            request.session.set_expiry(300) # Keep session alive for OTP entry
                            logger.info(f"2FA OTP sent for user {user.email}")
                            return JsonResponse({'status': '2fa_required', 'email': user.email})
                        else: # OTP sending failed (e.g., email issue, or user doesn't exist if logic was different)
                            return JsonResponse({'status': 'error', 'message': otp_data.get('message', 'Failed to send OTP for 2FA.')}, status=500)
                    except json.JSONDecodeError:
                        logger.error("Error decoding JSON response from internal send_otp call for 2FA.")
                        return JsonResponse({'status': 'error', 'message': 'Error processing 2FA OTP request.'}, status=500)
                else: # send_otp itself returned an error
                    status_code = otp_response.status_code if otp_response else 500
                    error_message = 'Failed to initiate 2FA verification.'
                    try: # Try to get a more specific message from send_otp's response
                        if otp_response:
                            error_data = json.loads(otp_response.content)
                            if error_data.get('message'): error_message = error_data['message']
                    except (json.JSONDecodeError, AttributeError): pass # Ignore if can't parse
                    return JsonResponse({'status': 'error', 'message': error_message}, status=status_code)
            else: # 2FA not enabled, log in directly
                auth_login(request, user)
                logger.info(f"User {user.username} logged in successfully (no 2FA).")
                home_url = reverse('AudioXApp:home') # Or user dashboard
                return JsonResponse({'status': 'success', 'redirect_url': home_url})
        else: # Authentication failed
            return JsonResponse({'status': 'error', 'message': "Incorrect email/username or password."}, status=401)

    context = _get_full_context(request)
    return render(request, 'auth/login.html', context)


@require_POST
def verify_login_otp(request):
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    if not is_ajax: # Should be AJAX
        return JsonResponse({'status': 'error', 'message': 'Invalid request type. AJAX POST required.'}, status=400)

    try:
        data = json.loads(request.body)
        entered_otp = data.get('otp')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)

    if not entered_otp:
        return JsonResponse({'status': 'error', 'message': 'OTP is required.'}, status=400)

    stored_otp = request.session.get('login_otp')
    user_email_for_2fa = request.session.get('2fa_user_email') # Email of user pending 2FA
    user_id_for_2fa = request.session.get('2fa_user_id') # PK of user pending 2FA

    if not stored_otp or not user_email_for_2fa or not user_id_for_2fa:
        return JsonResponse({'status': 'error', 'message': 'Verification session expired or invalid. Please try logging in again.'}, status=400)

    if entered_otp == stored_otp:
        try:
            user = User.objects.get(pk=user_id_for_2fa, email__iexact=user_email_for_2fa) # Verify user still exists
            auth_login(request, user) # Log the user in
            # Clear all 2FA related session data
            for key in ['login_otp', 'login_email_pending_2fa', '2fa_user_email', '2fa_user_id']:
                request.session.pop(key, None)
            
            logger.info(f"User {user.username} completed 2FA and logged in.")
            redirect_url = reverse('AudioXApp:home') # Or user dashboard
            return JsonResponse({'status': 'success', 'message': 'Verification successful! Logging you in...', 'redirect_url': redirect_url})
        except User.DoesNotExist:
            logger.warning(f"User for 2FA verification not found: email {user_email_for_2fa}, id {user_id_for_2fa}")
            for key in ['login_otp', 'login_email_pending_2fa', '2fa_user_email', '2fa_user_id']: request.session.pop(key, None)
            return JsonResponse({'status': 'error', 'message': 'User verification failed. Please try logging in again.'}, status=400)
        except Exception as e:
            logger.error(f"Error during 2FA login for user {user_email_for_2fa}: {e}", exc_info=True)
            for key in ['login_otp', 'login_email_pending_2fa', '2fa_user_email', '2fa_user_id']: request.session.pop(key, None)
            return JsonResponse({'status': 'error', 'message': 'An error occurred during login. Please try again.'}, status=500)
    else: # Incorrect OTP
        return JsonResponse({'status': 'error', 'message': 'Invalid verification code.'}, status=400)


# --- Forgot Password Views ---

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

    if not stored_otp or not stored_email or stored_email.lower() != email.lower(): # Case-insensitive email check
        return JsonResponse({'status': 'error', 'message': 'OTP session expired or email mismatch. Please request a new OTP.'}, status=400)

    if entered_otp == stored_otp:
        # Mark email and OTP as verified for the next step
        request.session['password_reset_verified_email'] = email 
        request.session['password_reset_verified_otp'] = entered_otp 
        request.session.set_expiry(300) # Extend session for password reset form (5 mins)
        logger.info(f"Password reset OTP verified for {email}")
        return JsonResponse({'status': 'success', 'message': 'OTP verified successfully. Proceed to reset your password.'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid OTP entered.'}, status=400)


def reset_password_form(request):
    email = request.GET.get('email') # Get from query params as a simple way to pass info
    otp = request.GET.get('otp')     # Get from query params

    verified_email_in_session = request.session.get('password_reset_verified_email')
    verified_otp_in_session = request.session.get('password_reset_verified_otp')

    # Validate that the email and OTP from query params match what's verified in session
    if not email or not otp or \
       not verified_email_in_session or not verified_otp_in_session or \
       email.lower() != verified_email_in_session.lower() or otp != verified_otp_in_session:
        messages.error(request, "Invalid or expired password reset link/session. Please start the password reset process again.")
        return redirect('AudioXApp:forgot_password')

    context = _get_full_context(request)
    context.update({'email': email, 'otp': otp}) # Pass to template for hidden fields
    return render(request, 'auth/resetpassword.html', context)


@require_POST
def reset_password_confirm(request):
    try:
        data = json.loads(request.body)
        email = data.get('email')
        otp = data.get('otp') # This is the OTP confirmed in the previous step
        new_password = data.get('new_password')
        confirm_new_password = data.get('confirm_new_password')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)

    errors = {}
    if not email: errors['email'] = "Email is missing." # Should be submitted from hidden field
    if not otp: errors['otp'] = "OTP/Token is missing." # Should be submitted from hidden field
    if not new_password: errors['new_password'] = "New password is required."
    if not confirm_new_password: errors['confirm_new_password'] = "Please confirm your new password."

    if new_password and confirm_new_password and new_password != confirm_new_password:
        errors['confirm_new_password'] = "Passwords do not match."
    
    # Basic password length validation (Django's User model handles more complex validation on set_password)
    if new_password and len(new_password) < 8: # Example minimum length
        errors['new_password'] = "Password must be at least 8 characters long."

    # Verify against session again
    verified_email_in_session = request.session.get('password_reset_verified_email')
    verified_otp_in_session = request.session.get('password_reset_verified_otp')

    if not verified_email_in_session or not verified_otp_in_session or \
       email.lower() != verified_email_in_session.lower() or otp != verified_otp_in_session:
        logger.warning(f"Password reset attempt with mismatched session data for email {email}.")
        return JsonResponse({'status': 'error', 'message': 'Invalid or expired password reset session. Please start over.'}, status=403)

    if errors:
        return JsonResponse({'status': 'error', 'message': 'Please correct the errors.', 'errors': errors}, status=400)

    try:
        user = User.objects.get(email__iexact=email) # Case-insensitive email fetch
        user.set_password(new_password) # Hashes the password
        user.save()

        # Clear all password reset session variables
        for key in ['password_reset_otp', 'password_reset_email', 'password_reset_verified_email', 'password_reset_verified_otp']:
            request.session.pop(key, None)
        
        logger.info(f"Password successfully reset for user {user.email}")
        return JsonResponse({'status': 'success', 'message': 'Your password has been reset successfully. You can now login.'})
    except User.DoesNotExist:
        logger.error(f"User not found during password reset confirmation for email {email}, though OTP was verified.")
        return JsonResponse({'status': 'error', 'message': 'User not found. Password reset failed.'}, status=404) # Should not happen if OTP verified correctly
    except Exception as e:
        logger.error(f"Unexpected error during password reset confirmation for email {email}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred. Please try again.'}, status=500)


# --- Logout View ---

@login_required # Ensures user is logged in to log out
def logout_view(request):
    """Logs out the current user and redirects to the home page."""
    try:
        username_display = request.user.username # Get username before logout for message
        auth_logout(request) # Django's built-in logout
        messages.success(request, f"User '{username_display}' has been successfully logged out.")
        logger.info(f"User {username_display} logged out.")
    except AttributeError: # If request.user is somehow not set (e.g., AnonymousUser)
        auth_logout(request) # Still attempt logout
        messages.success(request, "You have been successfully logged out.")
        logger.info("Anonymous user session logged out.")
    except Exception as e:
        logger.error(f"Error during logout: {e}", exc_info=True)
        messages.error(request, "An error occurred during logout. Please try again.")
    return redirect('AudioXApp:home')