# AudioXApp/views/user_views/profile_views.py

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

logger = logging.getLogger(__name__)

# --- User Profile Page ---

@login_required
def myprofile(request):
    context = _get_full_context(request)
    return render(request, 'user/myprofile.html', context)

# --- Update Profile (AJAX) ---

@login_required
@require_POST 
@csrf_protect
def update_profile(request):
    user = request.user
    if request.content_type.startswith('multipart/form-data'):
        if 'profile_pic' in request.FILES:
            if user.profile_pic and hasattr(user.profile_pic, 'name') and user.profile_pic.name: 
                try:
                    if default_storage.exists(user.profile_pic.name):
                        default_storage.delete(user.profile_pic.name)
                except Exception as e_del:
                    logger.error(f"Error deleting old profile picture for user {user.username}: {e_del}", exc_info=True)
            user.profile_pic = request.FILES['profile_pic']
            try:
                user.save(update_fields=['profile_pic'])
                pic_url = user.profile_pic.url + f'?t={timezone.now().timestamp()}'
                return JsonResponse({'status': 'success', 'message': 'Profile picture updated successfully.', 'profile_pic_url': pic_url})
            except Exception as e_save:
                logger.error(f"Error saving new profile picture for user {user.username}: {e_save}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': 'Error saving profile picture.'}, status=500)
        else: 
            return JsonResponse({'status': 'error', 'message': 'No profile picture file found in request for multipart upload.'}, status=400)

    elif request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
            fields_to_update = []
            error_messages = {} 

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

            if 'full_name' in data:
                full_name = data['full_name'].strip()
                if not full_name:
                    error_messages['full_name'] = 'Full Name cannot be empty.'
                elif user.full_name != full_name:
                    user.full_name = full_name
                    fields_to_update.append('full_name')
            
            if 'email' in data:
                email = data['email'].strip()
                if not email:
                    error_messages['email'] = 'Email cannot be empty.'
                else:
                    try:
                        validate_email(email)
                        if user.email.lower() != email.lower(): 
                            if User.objects.exclude(pk=user.pk).filter(email__iexact=email).exists():
                                error_messages['email'] = 'Email already exists.'
                            else:
                                user.email = email 
                                fields_to_update.append('email')
                    except ValidationError:
                        error_messages['email'] = 'Invalid email address format.'

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
                    if user.phone_number is not None and user.phone_number != '': 
                        user.phone_number = None
                        fields_to_update.append('phone_number')

            if 'bio' in data:
                bio = data['bio'].strip()
                if user.bio != bio:
                    user.bio = bio if bio else None
                    fields_to_update.append('bio')

            if data.get('remove_profile_pic') is True: 
                if user.profile_pic and hasattr(user.profile_pic, 'name') and user.profile_pic.name:
                    try:
                        if default_storage.exists(user.profile_pic.name):
                            default_storage.delete(user.profile_pic.name)
                        user.profile_pic = None 
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
                general_error_message = "Please correct the errors below."
                if len(error_messages) == 1:
                    general_error_message = list(error_messages.values())[0]
                return JsonResponse({'status': 'error', 'message': general_error_message, 'errors': error_messages}, status=400)

            if fields_to_update:
                try:
                    user.save(update_fields=list(set(fields_to_update))) 
                    message = "Profile updated successfully."
                    if 'is_2fa_enabled' in fields_to_update and len(fields_to_update) == 1:
                        message = f"Two-Factor Authentication {'enabled' if user.is_2fa_enabled else 'disabled'}."
                    elif 'profile_pic' in fields_to_update and data.get('remove_profile_pic') is True and len(fields_to_update) == 1:
                        message = "Profile picture removed successfully."
                    
                    logger.info(f"Profile updated for user {user.username}. Fields: {fields_to_update}")
                    return JsonResponse({'status': 'success', 'message': message})
                except IntegrityError as e: 
                    logger.warning(f"IntegrityError updating profile for {user.username}: {e}", exc_info=True)
                    error_message = 'A data conflict occurred. Please check your input.'
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
        except Exception as e_main: 
            logger.error(f"Unexpected error in update_profile (JSON part) for user {user.username}: {e_main}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request format (Content-Type).'}, status=415)

# --- Change Password (AJAX) ---

@login_required
@csrf_protect
def change_password(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user) 
            logger.info(f"Password changed successfully for user {user.username}")
            return JsonResponse({'status': 'success', 'message': 'Password updated successfully!'})
        else:
            errors = {}
            for field, error_list in form.errors.items():
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
                        errors[field] = error_list[0] 
                else:
                    errors[field] = error_list[0] 
            
            logger.warning(f"Password change failed for user {request.user.username}. Errors: {errors}")
            return JsonResponse({'status': 'error', 'message': 'Please correct the errors below.', 'errors': errors}, status=400)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method or type.'}, status=400)

# --- Complete Profile (Post-Social-Signup) ---

@login_required
@csrf_protect
def complete_profile(request):
    user = request.user
    context = _get_full_context(request)
    next_destination_after_save = request.GET.get('next') or request.session.get('next_url_after_profile_completion') or reverse('AudioXApp:home')
    needs_completion_flow_flag = getattr(user, 'requires_extra_details_post_social_signup', False)
    phone_is_missing = (user.phone_number is None or user.phone_number.strip() == '')
    full_name_is_effectively_missing = (user.full_name is None or user.full_name.strip() == '')

    if request.method == 'GET':
        if not needs_completion_flow_flag and not phone_is_missing and not full_name_is_effectively_missing:
            logger.info(f"User {user.username} on complete_profile; flag is False and details exist. Redirecting.")
            request.session.pop('profile_incomplete', None)
            request.session.pop('next_url_after_profile_completion', None)
            messages.info(request, "Your profile is already complete.")
            return redirect(next_destination_after_save)
        elif needs_completion_flow_flag and not phone_is_missing and not full_name_is_effectively_missing:
            logger.info(f"User {user.username} on complete_profile; flag is True, but details now exist. Clearing flag & redirecting.")
            user.requires_extra_details_post_social_signup = False
            user.save(update_fields=['requires_extra_details_post_social_signup'])
            request.session.pop('profile_incomplete', None)
            request.session.pop('next_url_after_profile_completion', None)
            messages.success(request, "Your profile details seem complete and have been verified.")
            return redirect(next_destination_after_save)

    if request.method == 'POST':
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                full_name_from_form = data.get('full_name', user.full_name or '').strip()
                phone_number_full = data.get('phone_number', '').strip()
                errors = {}
                if not full_name_from_form:
                    errors['full_name'] = 'Full name cannot be empty.'
                if not phone_number_full:
                    errors['phone_number'] = 'Phone number cannot be empty for profile completion.'
                elif not (phone_number_full.startswith('+92') and len(phone_number_full) == 13 and phone_number_full[3:].isdigit()):
                    errors['phone_number'] = 'Please enter a valid phone number in the format +923xxxxxxxxx.'
                elif User.objects.exclude(pk=user.pk).filter(phone_number=phone_number_full).exists():
                    errors['phone_number'] = 'This phone number is already registered with another account.'

                if errors:
                    return JsonResponse({'status': 'error', 'message': 'Please correct the errors.', 'errors': errors}, status=400)

                user.full_name = full_name_from_form
                user.phone_number = phone_number_full
                user.requires_extra_details_post_social_signup = False
                fields_to_save = ['full_name', 'phone_number', 'requires_extra_details_post_social_signup']
                user.save(update_fields=fields_to_save)
                request.session.pop('profile_incomplete', None)
                logger.info(f"Profile details (phone/name) completed for social signup user {user.username}")
                messages.success(request, "Your profile has been updated successfully!")
                return JsonResponse({'status': 'success', 'message': 'Your profile has been updated successfully!', 'redirect_url': next_destination_after_save})
            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
            except IntegrityError as ie:
                logger.error(f"IntegrityError completing profile for {user.username}: {ie}", exc_info=True)
                error_message = 'A data conflict occurred. This phone number might already be in use.'
                if 'phone_number' in str(ie).lower():
                    errors['phone_number'] = 'This phone number is already registered.'
                return JsonResponse({'status': 'error', 'message': error_message, 'errors': errors or {'general': error_message}}, status=400)
            except Exception as e:
                logger.error(f"Error completing profile for {user.username}: {e}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid request content type. Expected application/json.'}, status=415)

    context['user_full_name_from_social'] = user.full_name or ""
    user_phone_number_only = ''
    if user.phone_number and user.phone_number.startswith('+92') and len(user.phone_number) == 13:
        user_phone_number_only = user.phone_number[3:]
    context['user_phone_number_only'] = user_phone_number_only
    context['next_destination_on_success'] = next_destination_after_save
    return render(request, 'auth/complete_profile.html', context)