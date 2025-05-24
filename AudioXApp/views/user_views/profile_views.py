# AudioXApp/views/user_views/profile_views.py

import json
import re # For phone number validation in update_profile
import logging

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.core.files.storage import default_storage
from django.utils import timezone
from django.urls import reverse
from django.core.validators import validate_email


from ...models import User # Relative import
from ..utils import _get_full_context # Relative import

logger = logging.getLogger(__name__)

# --- Profile Views ---

@login_required
def myprofile(request):
    """Renders the user's profile page."""
    context = _get_full_context(request)
    # The _get_full_context should ideally populate ban reason if user is banned.
    # If not, you might need to fetch it here or adjust _get_full_context.
    # Example: if context.get('is_banned') and not context.get('ban_reason_display'):
    #    context['ban_reason_display'] = "No specific reason provided."
    return render(request, 'user/myprofile.html', context)

@login_required
@require_POST # This view now handles both multipart (for pic) and JSON (for text fields)
@csrf_protect
def update_profile(request):
    """Handles updating user profile information via AJAX."""
    user = request.user

    if request.content_type.startswith('multipart/form-data'):
        # Handle profile picture upload
        if 'profile_pic' in request.FILES:
            if user.profile_pic and hasattr(user.profile_pic, 'name') and user.profile_pic.name: # Check if there's an old pic
                try:
                    if default_storage.exists(user.profile_pic.name):
                        default_storage.delete(user.profile_pic.name)
                except Exception as e_del:
                    logger.error(f"Error deleting old profile picture for user {user.username}: {e_del}", exc_info=True)
                    # Continue with upload even if old pic deletion fails

            user.profile_pic = request.FILES['profile_pic']
            try:
                user.save(update_fields=['profile_pic'])
                # Add a timestamp to the URL to bypass browser cache for the new image
                pic_url = user.profile_pic.url + f'?t={timezone.now().timestamp()}'
                return JsonResponse({'status': 'success', 'message': 'Profile picture updated successfully.', 'profile_pic_url': pic_url})
            except Exception as e_save:
                logger.error(f"Error saving new profile picture for user {user.username}: {e_save}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': 'Error saving profile picture.'}, status=500)
        else: # No profile_pic in FILES but request is multipart
            return JsonResponse({'status': 'error', 'message': 'No profile picture file found in request for multipart upload.'}, status=400)

    elif request.content_type == 'application/json':
        # Handle other profile fields update (text-based data)
        try:
            data = json.loads(request.body)
            fields_to_update = []
            error_messages = {} # To collect errors for specific fields

            if 'username' in data:
                username = data['username'].strip()
                if not username:
                    error_messages['username'] = 'Username cannot be empty.'
                elif len(username) < 3:
                    error_messages['username'] = 'Username must be at least 3 characters long.'
                elif user.username != username: # Only check for existence if username is actually changing
                    if User.objects.exclude(pk=user.pk).filter(username__iexact=username).exists():
                        error_messages['username'] = 'Username already exists.'
                    else:
                        user.username = username
                        fields_to_update.append('username')

            if 'full_name' in data:
                full_name = data['full_name'].strip()
                if not full_name:
                    error_messages['full_name'] = 'Full Name cannot be empty.'
                elif user.full_name != full_name:
                    user.full_name = full_name
                    fields_to_update.append('full_name')
            
            # Email update logic (ensure it's handled carefully, might require re-verification)
            # For simplicity, if email change is allowed directly:
            if 'email' in data:
                email = data['email'].strip()
                if not email:
                    error_messages['email'] = 'Email cannot be empty.'
                else:
                    try:
                        validate_email(email)
                        if user.email.lower() != email.lower(): # Case-insensitive check if email changed
                            if User.objects.exclude(pk=user.pk).filter(email__iexact=email).exists():
                                error_messages['email'] = 'Email already exists.'
                            else:
                                user.email = email # Consider implications: does this need re-verification?
                                fields_to_update.append('email')
                    except ValidationError:
                        error_messages['email'] = 'Invalid email address format.'


            if 'phone_number' in data:
                phone_number = data['phone_number'].strip()
                if phone_number: # If a phone number is provided
                    # Basic validation for Pakistani phone numbers: +923xxxxxxxxx
                    phone_regex = r"^\+923\d{9}$" 
                    if not re.match(phone_regex, phone_number):
                        error_messages['phone_number'] = 'Invalid phone number format. Use +923xxxxxxxxx.'
                    else:
                        if user.phone_number != phone_number:
                            user.phone_number = phone_number
                            fields_to_update.append('phone_number')
                else: # If phone number is submitted as empty, clear it
                    if user.phone_number != '': # Only update if it's different
                        user.phone_number = ''
                        fields_to_update.append('phone_number')

            if 'bio' in data:
                bio = data['bio'].strip()
                if user.bio != bio:
                    user.bio = bio
                    fields_to_update.append('bio')

            if data.get('remove_profile_pic') is True: # Check for explicit removal flag
                if user.profile_pic and hasattr(user.profile_pic, 'name') and user.profile_pic.name:
                    try:
                        if default_storage.exists(user.profile_pic.name):
                            default_storage.delete(user.profile_pic.name)
                        user.profile_pic = None # Clear the field
                        fields_to_update.append('profile_pic')
                    except Exception as e_del_json:
                        logger.error(f"Error removing profile picture via JSON for user {user.username}: {e_del_json}", exc_info=True)
                        error_messages['profile_pic'] = 'Error removing profile picture.'
            
            if 'is_2fa_enabled' in data:
                new_2fa_status = data.get('is_2fa_enabled')
                if isinstance(new_2fa_status, bool):
                    if user.is_2fa_enabled != new_2fa_status:
                        user.is_2fa_enabled = new_2fa_status
                        fields_to_update.append('is_2fa_enabled')
                else:
                    error_messages['is_2fa_enabled'] = 'Invalid value for 2FA status (must be true or false).'


            if error_messages:
                # Construct a general message if multiple errors, or use specific if only one
                general_error_message = "Please correct the errors below."
                if len(error_messages) == 1 and 'profile_pic' in error_messages and 'Error removing profile picture' in error_messages['profile_pic']:
                     general_error_message = error_messages['profile_pic']
                elif len(error_messages) == 1: # If only one error, use its message
                    general_error_message = list(error_messages.values())[0]

                return JsonResponse({'status': 'error', 'message': general_error_message, 'errors': error_messages}, status=400)

            if fields_to_update:
                try:
                    user.save(update_fields=list(set(fields_to_update))) # Use set to avoid duplicate fields
                    message = "Profile updated successfully."
                    # More specific messages for certain single updates
                    if 'is_2fa_enabled' in fields_to_update and len(fields_to_update) == 1:
                        message = f"Two-Factor Authentication {'enabled' if user.is_2fa_enabled else 'disabled'}."
                    elif 'profile_pic' in fields_to_update and data.get('remove_profile_pic') is True and len(fields_to_update) == 1:
                        message = "Profile picture removed successfully."
                    
                    logger.info(f"Profile updated for user {user.username}. Fields: {fields_to_update}")
                    return JsonResponse({'status': 'success', 'message': message})
                except IntegrityError as e: # Catch potential unique constraint violations (e.g., username, email)
                    logger.warning(f"IntegrityError updating profile for {user.username}: {e}", exc_info=True)
                    error_message = 'A data conflict occurred. Please check your input.'
                    # Be more specific if possible
                    if 'username' in str(e).lower(): error_message = 'Username already exists.'
                    elif 'email' in str(e).lower(): error_message = 'Email already exists.'
                    return JsonResponse({'status': 'error', 'message': error_message, 'errors': {'general': error_message}}, status=400)
                except Exception as e_save_json:
                    logger.error(f"Error saving profile (JSON) for user {user.username}: {e_save_json}", exc_info=True)
                    return JsonResponse({'status': 'error', 'message': 'Error saving profile.'}, status=500)
            else:
                return JsonResponse({'status': 'success', 'message': 'No changes detected.'})

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid request data format (expected JSON).'}, status=400)
        except Exception as e_main: # Catch-all for other unexpected errors
            logger.error(f"Unexpected error in update_profile (JSON part) for user {user.username}: {e_main}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request format (Content-Type).'}, status=415)


@login_required
@csrf_protect # Ensure CSRF protection
def change_password(request):
    """Handles user password change via AJAX."""
    # Check if it's an AJAX request and POST method
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Important to keep the user logged in
            logger.info(f"Password changed successfully for user {user.username}")
            return JsonResponse({'status': 'success', 'message': 'Password updated successfully!'})
        else:
            # Prepare a more user-friendly error dictionary
            errors = {}
            for field, error_list in form.errors.items():
                # Customize messages if needed
                if field == 'old_password' and 'Invalid password' in error_list[0]:
                    errors[field] = 'Incorrect current password.'
                elif field == 'new_password2':
                    if "The two password fields didn’t match." in error_list[0]:
                        errors[field] = "New passwords didn't match."
                    elif "password is too common" in error_list[0].lower():
                        errors[field] = "This password is too common."
                    elif "password is too short" in error_list[0].lower():
                        min_length_validator = next((v for v in settings.AUTH_PASSWORD_VALIDATORS if 'OPTIONS' in v and 'min_length' in v['OPTIONS']), None)
                        min_length = min_length_validator['OPTIONS']['min_length'] if min_length_validator else 8
                        errors[field] = f"Password must be at least {min_length} characters."
                    elif "entirely numeric" in error_list[0].lower():
                         errors[field] = "Password can't be entirely numeric."
                    else:
                        errors[field] = error_list[0] # Default Django message
                else:
                    errors[field] = error_list[0] # Take the first error message for the field
            
            logger.warning(f"Password change failed for user {request.user.username}. Errors: {errors}")
            return JsonResponse({'status': 'error', 'message': 'Please correct the errors below.', 'errors': errors}, status=400)
    else:
        # If not AJAX POST, it's an invalid request for this endpoint
        return JsonResponse({'status': 'error', 'message': 'Invalid request method or type.'}, status=400)


@login_required
@csrf_protect # Protect both GET and POST
def complete_profile(request):
    user = request.user
    context = _get_full_context(request)

    # Determine the 'next' URL
    next_destination_after_save = request.GET.get('next')
    if not next_destination_after_save: # Check session if not in GET
        next_destination_after_save = request.session.get('next_url_after_profile_completion')
        if next_destination_after_save and not next_destination_after_save.startswith('/'):
            try: # Try to reverse if it's a name, otherwise use as is or default
                next_destination_after_save = reverse(next_destination_after_save)
            except: # If reversing fails, it might be an absolute path or invalid
                next_destination_after_save = reverse('AudioXApp:home') # Fallback
    if not next_destination_after_save: # Default if still not found
        next_destination_after_save = reverse('AudioXApp:home')

    # Check if profile is already complete based on your criteria
    profile_is_complete = bool(
        user.full_name and user.full_name.strip() and
        user.phone_number and user.phone_number.startswith('+92') and 
        len(user.phone_number) == 13 and user.phone_number[3:].isdigit()
        # Add other checks like bio if it's mandatory for "completion"
        # and user.bio and user.bio.strip() 
    )

    if profile_is_complete and request.method == 'GET':
        # If profile is complete and it's a GET request, redirect away
        if 'profile_incomplete' in request.session: del request.session['profile_incomplete']
        if 'next_url_after_profile_completion' in request.session: del request.session['next_url_after_profile_completion']
        messages.info(request, "Your profile is already complete.")
        return redirect(next_destination_after_save)

    if request.method == 'POST':
        if request.content_type == 'application/json': # Expecting JSON for this form
            try:
                data = json.loads(request.body)
                full_name = data.get('full_name', '').strip()
                phone_number_full = data.get('phone_number', '').strip() # Assuming full number like +92... is submitted

                errors = {}
                if not full_name:
                    errors['full_name'] = 'Full name cannot be empty.'
                
                if not phone_number_full:
                    errors['phone_number'] = 'Phone number cannot be empty.'
                elif not (phone_number_full.startswith('+92') and len(phone_number_full) == 13 and phone_number_full[3:].isdigit()):
                    errors['phone_number'] = 'Please enter a valid phone number in the format +923xxxxxxxxx.'
                elif User.objects.exclude(pk=user.pk).filter(phone_number=phone_number_full).exists():
                    errors['phone_number'] = 'This phone number is already registered with another account.'

                if errors:
                    return JsonResponse({'status': 'error', 'message': 'Please correct the errors.', 'errors': errors}, status=400)

                # Update user profile
                user.full_name = full_name
                user.phone_number = phone_number_full
                # user.bio = data.get('bio', user.bio) # If bio is also part of completion form
                user.save(update_fields=['full_name', 'phone_number']) # Add 'bio' if included

                # Clear session flags related to profile completion
                if 'profile_incomplete' in request.session: del request.session['profile_incomplete']
                if 'next_url_after_profile_completion' in request.session: del request.session['next_url_after_profile_completion']
                
                logger.info(f"Profile completed for user {user.username}")
                messages.success(request, "Your profile has been updated successfully!") # For display on next page
                return JsonResponse({
                    'status': 'success',
                    'message': 'Your profile has been updated successfully!',
                    'redirect_url': next_destination_after_save
                })

            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
            except Exception as e:
                logger.error(f"Error completing profile for {user.username}: {e}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)
        else: # Not JSON
            return JsonResponse({'status': 'error', 'message': 'Invalid request content type. Expected application/json.'}, status=415)

    # For GET request, prepare context for the form
    user_phone_number_only = ''
    if user.phone_number and user.phone_number.startswith('+92') and len(user.phone_number) == 13:
        user_phone_number_only = user.phone_number[3:] # Extract number part for easier display/editing

    context['user_phone_number_only'] = user_phone_number_only
    context['user_full_phone_number'] = user.phone_number # For hidden field or initial value
    context['next_destination_on_success'] = next_destination_after_save # Pass to template if needed

    return render(request, 'auth/complete_profile.html', context)