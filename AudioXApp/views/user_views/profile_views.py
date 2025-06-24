"""
============================================================================
USER PROFILE VIEWS
============================================================================
Handles user profile management including profile updates, password changes,
and account settings with proper validation and security measures.

Author: AudioX Development Team
Version: 2.0
Last Updated: 2024
============================================================================
"""

# ============================================================================
# IMPORTS AND DEPENDENCIES
# ============================================================================
import json
import re
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
from ...models import User
from ..utils import _get_full_context

# ============================================================================
# CONFIGURATION AND SETUP
# ============================================================================

# Configure logging
logger = logging.getLogger(__name__)

# ============================================================================
# MAIN PROFILE VIEWS
# ============================================================================

@login_required
def myprofile(request):
    """
    Renders the main user profile page with account settings.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Rendered profile template with user context
    """
    logger.info(f"User {request.user.username} accessed profile page")
    context = _get_full_context(request)
    return render(request, 'user/myprofile.html', context)

# ============================================================================
# PROFILE UPDATE FUNCTIONALITY
# ============================================================================

@login_required
@require_POST 
@csrf_protect
def update_profile(request):
    """
    Handles profile updates via AJAX requests.
    Supports both file uploads (profile pictures) and JSON data updates.
    Note: Email updates are disabled for security reasons.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse: Success/error status with appropriate messages
    """
    user = request.user
    logger.info(f"Profile update request from user: {user.username}")
    
    # ============================================================================
    # HANDLE PROFILE PICTURE UPLOADS
    # ============================================================================
    if request.content_type.startswith('multipart/form-data'):
        if 'profile_pic' in request.FILES:
            logger.info(f"Processing profile picture upload for user: {user.username}")
            
            # Remove old profile picture if exists
            if user.profile_pic and hasattr(user.profile_pic, 'name') and user.profile_pic.name:
                try:
                    if default_storage.exists(user.profile_pic.name):
                        default_storage.delete(user.profile_pic.name)
                        logger.info(f"Deleted old profile picture for user: {user.username}")
                except Exception as e_del:
                    logger.error(f"Error deleting old profile picture for user {user.username}: {e_del}", exc_info=True)
            
            # Save new profile picture
            user.profile_pic = request.FILES['profile_pic']
            try:
                user.save(update_fields=['profile_pic'])
                pic_url = user.profile_pic.url + f'?t={timezone.now().timestamp()}'
                logger.info(f"Successfully updated profile picture for user: {user.username}")
                return JsonResponse({
                    'status': 'success', 
                    'message': 'Profile picture updated successfully.', 
                    'profile_pic_url': pic_url
                })
            except Exception as e_save:
                logger.error(f"Error saving new profile picture for user {user.username}: {e_save}", exc_info=True)
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Error saving profile picture.'
                }, status=500)
        else:
            logger.warning(f"No profile picture file found in multipart request from user: {user.username}")
            return JsonResponse({
                'status': 'error', 
                'message': 'No profile picture file found in request for multipart upload.'
            }, status=400)

    # ============================================================================
    # HANDLE JSON DATA UPDATES
    # ============================================================================
    elif request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
            fields_to_update = []
            error_messages = {}
            
            logger.info(f"Processing JSON profile update for user: {user.username}, fields: {list(data.keys())}")

            # ============================================================================
            # USERNAME VALIDATION AND UPDATE
            # ============================================================================
            if 'username' in data:
                username = data['username'].strip()
                if not username:
                    error_messages['username'] = 'Username cannot be empty.'
                elif len(username) < 3:
                    error_messages['username'] = 'Username must be at least 3 characters long.'
                elif user.username != username:
                    if User.objects.exclude(pk=user.pk).filter(username__iexact=username).exists():
                        error_messages['username'] = 'Username already exists.'
                    else:
                        user.username = username
                        fields_to_update.append('username')

            # ============================================================================
            # FULL NAME VALIDATION AND UPDATE
            # ============================================================================
            if 'full_name' in data:
                full_name = data['full_name'].strip()
                if not full_name:
                    error_messages['full_name'] = 'Full Name cannot be empty.'
                elif user.full_name != full_name:
                    user.full_name = full_name
                    fields_to_update.append('full_name')
            
            # ============================================================================
            # EMAIL UPDATE DISABLED FOR SECURITY
            # ============================================================================
            if 'email' in data:
                logger.warning(f"Email update attempt blocked for user {user.username} - email updates disabled for security")
                error_messages['email'] = 'Email address cannot be changed for security reasons.'

            # ============================================================================
            # PHONE NUMBER VALIDATION AND UPDATE
            # ============================================================================
            if 'phone_number' in data:
                phone_number = data['phone_number'].strip()
                if phone_number:
                    phone_regex = r"^\+923\d{9}$"
                    if not re.match(phone_regex, phone_number):
                        error_messages['phone_number'] = 'Invalid phone number format. Use +923xxxxxxxxx.'
                    else:
                        if user.phone_number != phone_number:
                            user.phone_number = phone_number
                            fields_to_update.append('phone_number')
                else:
                    # Allow empty phone number (optional field)
                    if user.phone_number is not None and user.phone_number != '':
                        user.phone_number = None
                        fields_to_update.append('phone_number')

            # ============================================================================
            # BIO UPDATE
            # ============================================================================
            if 'bio' in data:
                bio = data['bio'].strip()
                if user.bio != bio:
                    user.bio = bio if bio else None
                    fields_to_update.append('bio')

            # ============================================================================
            # PROFILE PICTURE REMOVAL
            # ============================================================================
            if data.get('remove_profile_pic') is True:
                logger.info(f"Processing profile picture removal for user: {user.username}")
                if user.profile_pic and hasattr(user.profile_pic, 'name') and user.profile_pic.name:
                    try:
                        if default_storage.exists(user.profile_pic.name):
                            default_storage.delete(user.profile_pic.name)
                        user.profile_pic = None
                        fields_to_update.append('profile_pic')
                        logger.info(f"Successfully removed profile picture for user: {user.username}")
                    except Exception as e_del_json:
                        logger.error(f"Error removing profile picture via JSON for user {user.username}: {e_del_json}", exc_info=True)
                        error_messages['profile_pic'] = 'Error removing profile picture.'
            
            # ============================================================================
            # TWO-FACTOR AUTHENTICATION UPDATE
            # ============================================================================
            if 'is_2fa_enabled' in data:
                new_2fa_status = data.get('is_2fa_enabled')
                if isinstance(new_2fa_status, bool):
                    if user.is_2fa_enabled != new_2fa_status:
                        user.is_2fa_enabled = new_2fa_status
                        fields_to_update.append('is_2fa_enabled')
                        logger.info(f"2FA status changed for user {user.username}: {new_2fa_status}")
                else:
                    error_messages['is_2fa_enabled'] = 'Invalid value for 2FA status (must be true or false).'

            # ============================================================================
            # VALIDATION ERROR HANDLING
            # ============================================================================
            if error_messages:
                general_error_message = "Please correct the errors below."
                if len(error_messages) == 1:
                    general_error_message = list(error_messages.values())[0]
                logger.warning(f"Profile update validation errors for user {user.username}: {error_messages}")
                return JsonResponse({
                    'status': 'error', 
                    'message': general_error_message, 
                    'errors': error_messages
                }, status=400)

            # ============================================================================
            # SAVE PROFILE UPDATES
            # ============================================================================
            if fields_to_update:
                try:
                    user.save(update_fields=list(set(fields_to_update)))
                    
                    # Generate appropriate success message
                    message = "Profile updated successfully."
                    if 'is_2fa_enabled' in fields_to_update and len(fields_to_update) == 1:
                        message = f"Two-Factor Authentication {'enabled' if user.is_2fa_enabled else 'disabled'}."
                    elif 'profile_pic' in fields_to_update and data.get('remove_profile_pic') is True and len(fields_to_update) == 1:
                        message = "Profile picture removed successfully."
                    
                    logger.info(f"Profile updated successfully for user {user.username}. Fields: {fields_to_update}")
                    return JsonResponse({
                        'status': 'success', 
                        'message': message
                    })
                    
                except IntegrityError as e:
                    logger.warning(f"IntegrityError updating profile for {user.username}: {e}", exc_info=True)
                    error_message = 'A data conflict occurred. Please check your input.'
                    if 'username' in str(e).lower():
                        error_message = 'Username already exists.'
                    elif 'email' in str(e).lower():
                        error_message = 'Email already exists.'
                    return JsonResponse({
                        'status': 'error', 
                        'message': error_message, 
                        'errors': {'general': error_message}
                    }, status=400)
                    
                except Exception as e_save_json:
                    logger.error(f"Error saving profile (JSON) for user {user.username}: {e_save_json}", exc_info=True)
                    return JsonResponse({
                        'status': 'error', 
                        'message': 'Error saving profile.'
                    }, status=500)
            else:
                logger.info(f"No changes detected in profile update for user: {user.username}")
                return JsonResponse({
                    'status': 'success', 
                    'message': 'No changes detected.'
                })
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON data in profile update request from user: {user.username}")
            return JsonResponse({
                'status': 'error', 
                'message': 'Invalid request data format (expected JSON).'
            }, status=400)
            
        except Exception as e_main:
            logger.error(f"Unexpected error in update_profile (JSON part) for user {user.username}: {e_main}", exc_info=True)
            return JsonResponse({
                'status': 'error', 
                'message': 'An unexpected error occurred.'
            }, status=500)
    else:
        logger.error(f"Invalid content type in profile update request from user: {user.username}")
        return JsonResponse({
            'status': 'error', 
            'message': 'Invalid request format (Content-Type).'
        }, status=415)

# ============================================================================
# PASSWORD CHANGE FUNCTIONALITY
# ============================================================================

@login_required
@csrf_protect
def change_password(request):
    """
    Handles password change requests via AJAX.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        JsonResponse: Success/error status with appropriate messages
    """
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.method == 'POST':
        logger.info(f"Password change request from user: {request.user.username}")
        
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            logger.info(f"Password changed successfully for user {user.username}")
            return JsonResponse({
                'status': 'success', 
                'message': 'Password updated successfully!'
            })
        else:
            # Process form errors with user-friendly messages
            errors = {}
            for field, error_list in form.errors.items():
                if field == 'old_password' and 'Invalid password' in error_list[0]:
                    errors[field] = 'Incorrect current password.'
                elif field == 'new_password2':
                    if "The two password fields didn't match." in error_list[0]:
                        errors[field] = "New passwords didn't match."
                    elif "password is too common" in error_list[0].lower():
                        errors[field] = "This password is too common."
                    elif "password is too short" in error_list[0].lower():
                        errors[field] = "Password must be at least 8 characters."
                    elif "entirely numeric" in error_list[0].lower():
                        errors[field] = "Password can't be entirely numeric."
                    else:
                        errors[field] = error_list[0]
                else:
                    errors[field] = error_list[0]
            
            logger.warning(f"Password change failed for user {request.user.username}. Errors: {errors}")
            return JsonResponse({
                'status': 'error', 
                'message': 'Please correct the errors below.', 
                'errors': errors
            }, status=400)
    else:
        logger.error(f"Invalid password change request from user: {request.user.username}")
        return JsonResponse({
            'status': 'error', 
            'message': 'Invalid request method or type.'
        }, status=400)

# ============================================================================
# PROFILE COMPLETION FUNCTIONALITY
# ============================================================================

@login_required
@csrf_protect
def complete_profile(request):
    """
    Handles profile completion flow for users who signed up via social authentication.
    Ensures required fields like phone number and full name are provided.
    
    Args:
        request: Django HTTP request object
        
    Returns:
        Rendered template or redirect based on completion status
    """
    user = request.user
    context = _get_full_context(request)
    next_destination_after_save = request.GET.get('next') or request.session.get('next_url_after_profile_completion') or reverse('AudioXApp:home')
    needs_completion_flow_flag = getattr(user, 'requires_extra_details_post_social_signup', False)
    phone_is_missing = (user.phone_number is None or user.phone_number.strip() == '')
    full_name_is_effectively_missing = (user.full_name is None or user.full_name.strip() == '')

    logger.info(f"Profile completion request from user: {user.username}, needs_completion: {needs_completion_flow_flag}")

    # ============================================================================
    # HANDLE GET REQUESTS (DISPLAY FORM)
    # ============================================================================
    if request.method == 'GET':
        if not needs_completion_flow_flag and not phone_is_missing and not full_name_is_effectively_missing:
            logger.info(f"User {user.username} profile already complete, redirecting")
            request.session.pop('profile_incomplete', None)
            request.session.pop('next_url_after_profile_completion', None)
            messages.info(request, "Your profile is already complete.")
            return redirect(next_destination_after_save)
        elif needs_completion_flow_flag and not phone_is_missing and not full_name_is_effectively_missing:
            logger.info(f"User {user.username} profile completion flag cleared, redirecting")
            user.requires_extra_details_post_social_signup = False
            user.save(update_fields=['requires_extra_details_post_social_signup'])
            request.session.pop('profile_incomplete', None)
            request.session.pop('next_url_after_profile_completion', None)
            messages.success(request, "Your profile details seem complete and have been verified.")
            return redirect(next_destination_after_save)

    # ============================================================================
    # HANDLE POST REQUESTS (FORM SUBMISSION)
    # ============================================================================
    if request.method == 'POST':
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                full_name_from_form = data.get('full_name', user.full_name or '').strip()
                phone_number_full = data.get('phone_number', '').strip()
                errors = {}
                
                # Validate required fields
                if not full_name_from_form:
                    errors['full_name'] = 'Full name cannot be empty.'
                if not phone_number_full:
                    errors['phone_number'] = 'Phone number cannot be empty for profile completion.'
                elif not (phone_number_full.startswith('+92') and len(phone_number_full) == 13 and phone_number_full[3:].isdigit()):
                    errors['phone_number'] = 'Please enter a valid phone number in the format +923xxxxxxxxx.'
                elif User.objects.exclude(pk=user.pk).filter(phone_number=phone_number_full).exists():
                    errors['phone_number'] = 'This phone number is already registered with another account.'

                if errors:
                    logger.warning(f"Profile completion validation errors for user {user.username}: {errors}")
                    return JsonResponse({
                        'status': 'error', 
                        'message': 'Please correct the errors.', 
                        'errors': errors
                    }, status=400)

                # Save profile completion data
                user.full_name = full_name_from_form
                user.phone_number = phone_number_full
                user.requires_extra_details_post_social_signup = False
                fields_to_save = ['full_name', 'phone_number', 'requires_extra_details_post_social_signup']
                user.save(update_fields=fields_to_save)
                request.session.pop('profile_incomplete', None)
                
                logger.info(f"Profile completion successful for user {user.username}")
                messages.success(request, "Your profile has been updated successfully!")
                return JsonResponse({
                    'status': 'success', 
                    'message': 'Your profile has been updated successfully!', 
                    'redirect_url': next_destination_after_save
                })
                
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in profile completion request from user: {user.username}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Invalid JSON data.'
                }, status=400)
                
            except IntegrityError as ie:
                logger.error(f"IntegrityError completing profile for {user.username}: {ie}", exc_info=True)
                error_message = 'A data conflict occurred. This phone number might already be in use.'
                errors = {}
                if 'phone_number' in str(ie).lower():
                    errors['phone_number'] = 'This phone number is already registered.'
                return JsonResponse({
                    'status': 'error', 
                    'message': error_message, 
                    'errors': errors or {'general': error_message}
                }, status=400)
                
            except Exception as e:
                logger.error(f"Error completing profile for {user.username}: {e}", exc_info=True)
                return JsonResponse({
                    'status': 'error', 
                    'message': 'An unexpected error occurred.'
                }, status=500)
        else:
            logger.error(f"Invalid content type in profile completion request from user: {user.username}")
            return JsonResponse({
                'status': 'error', 
                'message': 'Invalid request content type. Expected application/json.'
            }, status=415)

    # ============================================================================
    # PREPARE CONTEXT FOR TEMPLATE RENDERING
    # ============================================================================
    context['user_full_name_from_social'] = user.full_name or ""
    user_phone_number_only = ''
    if user.phone_number and user.phone_number.startswith('+92') and len(user.phone_number) == 13:
        user_phone_number_only = user.phone_number[3:]
    context['user_phone_number_only'] = user_phone_number_only
    context['next_destination_on_success'] = next_destination_after_save
    
    logger.info(f"Rendering profile completion form for user: {user.username}")
    return render(request, 'auth/complete_profile.html', context)
