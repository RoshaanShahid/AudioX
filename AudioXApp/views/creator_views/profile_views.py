# AudioXApp/views/creator_views/profile_views.py

import json
from datetime import datetime, timedelta
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.urls import reverse
from django.core.files.storage import default_storage
from django.core.validators import RegexValidator
from django.conf import settings

from ...models import User, Creator, CreatorApplicationLog # Relative imports
from ..utils import _get_full_context # Relative import
from ..decorators import creator_required # Relative import

logger = logging.getLogger(__name__)

@login_required # Standard login_required, not creator_required, as this is a landing/info page
def creator_welcome_view(request):
    context = _get_full_context(request)
    # Redirect to dashboard if already an approved creator
    if request.user.is_authenticated and hasattr(request.user, 'creator_profile'):
        try:
            creator = Creator.objects.get(user=request.user)
            if creator.is_approved: # is_approved checks verification_status and not banned
                return redirect('AudioXApp:creator_dashboard')
        except Creator.DoesNotExist:
            pass # Continue to welcome page if no creator profile exists
        except Exception as e:
            logger.error(f"Error checking creator status in welcome view for {request.user.username}: {e}")
            # Fall through to welcome page, but log the error

    return render(request, 'creator/creator_welcome.html', context)


@login_required
@csrf_protect # Protects both GET (for initial load) and POST
@require_http_methods(["GET", "POST"]) # Allow both GET and POST
def creator_apply_view(request):
    user = request.user
    creator_profile = None
    can_reapply_status = True # Default to true, will be updated
    application_status = None
    rejection_reason_from_db = None # Store rejection reason from DB

    # Check existing creator status
    try:
        creator_profile = Creator.objects.get(user=user)
        application_status = creator_profile.verification_status

        if application_status == 'approved' and not getattr(creator_profile, 'is_banned', False):
            messages.info(request, "You are already an approved creator.")
            return redirect('AudioXApp:creator_dashboard')
        elif application_status == 'pending':
            messages.info(request, "Your creator application is currently pending review.")
            # No redirect here, let them see the page but form might be disabled by template
        elif application_status == 'rejected':
            can_reapply_status = creator_profile.can_reapply()
            rejection_reason_from_db = creator_profile.rejection_reason # Get reason from DB
            if not can_reapply_status:
                messages.warning(request, "You have reached the maximum number of creator applications for this month.")
        
        if getattr(creator_profile, 'is_banned', False):
            messages.error(request, f"Your creator account is banned. Reason: {getattr(creator_profile, 'ban_reason', 'N/A')}")
            context = _get_full_context(request)
            context['is_banned_on_apply_page'] = True # Flag for template
            return render(request, 'creator/creator_apply.html', context)

    except Creator.DoesNotExist:
        application_status = None # No existing application
    except Exception as e:
        logger.error(f"Error checking creator status in creator_apply_view for user {user.username}: {e}", exc_info=True)
        messages.error(request, "An error occurred while checking your creator status.")
        return redirect('AudioXApp:home')


    if request.method == 'POST':
        # Re-check status before processing POST to prevent race conditions or stale data
        if application_status == 'pending':
            return JsonResponse({'status': 'error', 'message': 'Your application is already pending review.'}, status=400)
        if application_status == 'rejected' and not can_reapply_status: # Use the status determined on GET
            return JsonResponse({'status': 'error', 'message': 'You have reached the application limit for this month.'}, status=400)
        if creator_profile and getattr(creator_profile, 'is_banned', False): # Re-check ban status
            return JsonResponse({'status': 'error', 'message': 'Banned users cannot apply.'}, status=403)

        creator_name = request.POST.get('creator_name', '').strip()
        creator_unique_name = request.POST.get('creator_unique_name', '').strip().lower() # Store unique names in lowercase
        terms_agree = request.POST.get('terms_agree') == 'on'
        content_rights = request.POST.get('content_rights') == 'on'
        legal_use = request.POST.get('legal_use') == 'on'
        accurate_info = request.POST.get('accurate_info') == 'on'
        cnic_front_file = request.FILES.get('cnic_front')
        cnic_back_file = request.FILES.get('cnic_back')

        errors = {}
        if not creator_name: errors['creator_name'] = 'Creator Name is required.'
        if not creator_unique_name: errors['creator_unique_name'] = 'Creator Unique Name (@handle) is required.'
        else:
            # Use the validator from the Creator model
            validator = Creator.unique_name_validator
            try:
                validator(creator_unique_name)
                # Check for uniqueness, excluding current user if they are re-applying (creator_profile exists)
                query = Creator.objects.filter(creator_unique_name__iexact=creator_unique_name)
                if creator_profile:
                    query = query.exclude(pk=creator_profile.pk)
                if query.exists():
                    errors['creator_unique_name'] = 'This unique name is already taken.'
            except ValidationError as e:
                errors['creator_unique_name'] = e.message # Use the validator's message

        if not all([terms_agree, content_rights, legal_use, accurate_info]):
            errors['agreements'] = 'You must agree to all terms and conditions.'
        
        # CNIC validation: required if no existing approved CNIC or if files are explicitly provided for update
        # This logic assumes that if creator_profile exists and has CNIC images, they are from a previous valid submission.
        # If re-application requires new CNIC, this logic might need adjustment.
        if not creator_profile or not creator_profile.cnic_front or cnic_front_file: # Require if new or if a file is given
             if not cnic_front_file: errors['cnic_front'] = 'CNIC Front image is required for new applications.'
        if not creator_profile or not creator_profile.cnic_back or cnic_back_file: # Require if new or if a file is given
             if not cnic_back_file: errors['cnic_back'] = 'CNIC Back image is required for new applications.'
        
        max_size = 2 * 1024 * 1024 # 2MB
        allowed_types = ['image/png', 'image/jpeg', 'image/jpg']

        def validate_image(file, field_name_for_error):
            if file:
                if file.size > max_size: errors[field_name_for_error] = f'{field_name_for_error.replace("_", " ").title()} too large (Max 2MB).'
                if file.content_type not in allowed_types: errors[field_name_for_error] = 'Invalid file type (PNG, JPG/JPEG only).'
        
        if cnic_front_file: validate_image(cnic_front_file, 'cnic_front')
        if cnic_back_file: validate_image(cnic_back_file, 'cnic_back')

        if errors:
            return JsonResponse({'status': 'error', 'message': 'Please correct the errors below.', 'errors': errors}, status=400)

        try:
            with transaction.atomic():
                now = timezone.now()
                
                # Determine attempts this month
                attempts_this_month = 0
                if creator_profile:
                    # If last application was this month, increment. Else, reset to 1.
                    if creator_profile.last_application_date and \
                       creator_profile.last_application_date.year == now.year and \
                       creator_profile.last_application_date.month == now.month:
                        attempts_this_month = creator_profile.application_attempts_current_month + 1
                    else:
                        attempts_this_month = 1 # First attempt of a new month cycle
                else:
                    attempts_this_month = 1 # First ever attempt

                if attempts_this_month > getattr(settings, 'MAX_CREATOR_APPLICATION_ATTEMPTS', 3):
                     return JsonResponse({'status': 'error', 'message': 'Application limit reached for this month.'}, status=400)

                creator_defaults = {
                    'creator_name': creator_name,
                    'creator_unique_name': creator_unique_name, # Already lowercased
                    'terms_accepted_at': now,
                    'verification_status': 'pending', # Set to pending for review
                    'last_application_date': now,
                    'application_attempts_current_month': attempts_this_month,
                    'rejection_reason': None, # Clear previous rejection reason
                    'rejection_popup_shown': False, # Reset popup flags
                    'welcome_popup_shown': False,
                    'approved_at': None, # Clear approval details
                    'approved_by': None,
                    'attempts_at_approval': None,
                    'is_banned': False, # Ensure not marked as banned on new application
                    'ban_reason': None,
                    'banned_at': None,
                    'banned_by': None,
                    # Do not reset last_name_change_date or last_unique_name_change_date here
                }
                if cnic_front_file: creator_defaults['cnic_front'] = cnic_front_file
                if cnic_back_file: creator_defaults['cnic_back'] = cnic_back_file
                
                # Use update_or_create to handle both new and re-applications
                creator, created = Creator.objects.update_or_create(
                    user=user,
                    defaults=creator_defaults
                )
                
                # Log this specific application attempt
                # Use the CNIC files from the current submission for the log
                log_cnic_front = cnic_front_file if cnic_front_file else (creator.cnic_front if created else None)
                log_cnic_back = cnic_back_file if cnic_back_file else (creator.cnic_back if created else None)

                CreatorApplicationLog.objects.create(
                    creator=creator,
                    application_date=now,
                    attempt_number_monthly=attempts_this_month,
                    creator_name_submitted=creator_name,
                    creator_unique_name_submitted=creator_unique_name,
                    cnic_front_submitted=log_cnic_front,
                    cnic_back_submitted=log_cnic_back,
                    terms_accepted_at_submission=now,
                    status='submitted' # Log status is 'submitted'
                )

            redirect_url = reverse('AudioXApp:home') # Or a specific "application received" page
            messages.success(request, 'Creator application submitted successfully! It is now pending review.')
            return JsonResponse({'status': 'success', 'message': 'Application submitted.', 'redirect_url': redirect_url})

        except IntegrityError as e:
            logger.error(f"IntegrityError in creator_apply_view POST: {e}", exc_info=True)
            error_message = 'An error occurred.'
            errors_response = {}
            if 'creator_unique_name' in str(e).lower(): # Check if it's a unique constraint violation
                error_message = 'That unique name is already taken.'
                errors_response['creator_unique_name'] = error_message
            else:
                error_message = "A database error occurred. Please try again."; errors_response['__all__'] = error_message
            return JsonResponse({ 'status': 'error', 'message': error_message, 'errors': errors_response }, status=400)
        except Exception as e:
            logger.error(f"Unexpected error in creator_apply_view POST: {e}", exc_info=True)
            return JsonResponse({ 'status': 'error', 'message': 'An unexpected server error occurred.', 'errors': {'__all__': 'Server error.'} }, status=500)

    else: # GET Request
        context = _get_full_context(request)
        context['application_status'] = application_status
        context['can_reapply'] = can_reapply_status
        context['rejection_reason'] = rejection_reason_from_db # Pass DB rejection reason
        context['creator_profile'] = creator_profile # Pass the profile if it exists
        return render(request, 'creator/creator_apply.html', context)


@creator_required # Ensures only active, approved, non-banned creators can access
@require_http_methods(["GET", "POST"]) # Allow both GET and POST
@csrf_protect
def update_creator_profile(request):
    creator = request.creator # From @creator_required decorator
    user = request.user
    now = timezone.now()
    cooldown_period = timedelta(days=getattr(settings, 'CREATOR_NAME_CHANGE_COOLDOWN_DAYS', 60))


    can_change_name = not creator.last_name_change_date or (now - creator.last_name_change_date) >= cooldown_period
    next_name_change_date = (creator.last_name_change_date + cooldown_period) if creator.last_name_change_date else None

    can_change_unique_name = not creator.last_unique_name_change_date or (now - creator.last_unique_name_change_date) >= cooldown_period
    next_unique_name_change_date = (creator.last_unique_name_change_date + cooldown_period) if creator.last_unique_name_change_date else None
    
    form_errors = {}
    form_values = { # Initialize with current values for GET or if POST fails
        'creator_name': creator.creator_name,
        'creator_unique_name': creator.creator_unique_name,
    }

    if request.method == 'POST':
        new_creator_name = request.POST.get('creator_name', '').strip()
        new_unique_name = request.POST.get('creator_unique_name', '').strip().lower() # Store unique names in lowercase
        profile_pic_file = request.FILES.get('creator_profile_pic')
        remove_profile_pic = request.POST.get('remove_profile_pic') == '1' # Check if '1' or 'on' depending on your JS

        # Update form_values with submitted data for repopulation on error
        form_values['creator_name'] = new_creator_name
        form_values['creator_unique_name'] = new_unique_name
        
        update_fields = []
        made_changes = False
        
        # Profile Picture Logic
        old_profile_pic_path = creator.creator_profile_pic.name if creator.creator_profile_pic else None
        if remove_profile_pic and not profile_pic_file: # If remove is checked and no new file uploaded
            if creator.creator_profile_pic:
                if old_profile_pic_path and default_storage.exists(old_profile_pic_path):
                    try: default_storage.delete(old_profile_pic_path)
                    except Exception as del_e: logger.warning(f"Failed to delete old profile pic {old_profile_pic_path}: {del_e}")
                creator.creator_profile_pic = None
                update_fields.append('creator_profile_pic')
                creator.profile_pic_updated_at = now # Track update time
                update_fields.append('profile_pic_updated_at')
                made_changes = True
        elif profile_pic_file:
            max_size = 2 * 1024 * 1024; allowed_types = ['image/png', 'image/jpeg', 'image/jpg']
            if profile_pic_file.size > max_size: form_errors['creator_profile_pic'] = 'Picture too large (Max 2MB).'
            elif profile_pic_file.content_type not in allowed_types: form_errors['creator_profile_pic'] = 'Invalid file type (PNG, JPG/JPEG only).'
            else:
                if old_profile_pic_path and old_profile_pic_path != profile_pic_file.name and default_storage.exists(old_profile_pic_path):
                    try: default_storage.delete(old_profile_pic_path)
                    except Exception as del_e: logger.warning(f"Failed to delete old profile pic {old_profile_pic_path} during update: {del_e}")
                creator.creator_profile_pic = profile_pic_file
                update_fields.append('creator_profile_pic')
                creator.profile_pic_updated_at = now # Track update time
                update_fields.append('profile_pic_updated_at')
                made_changes = True

        # Creator Name Logic
        name_changed_from_db = creator.creator_name != new_creator_name
        if name_changed_from_db:
            if not can_change_name: form_errors['creator_name'] = f"You cannot change your display name again until {next_name_change_date.strftime('%b %d, %Y')}."
            elif not new_creator_name: form_errors['creator_name'] = "Display name cannot be empty."
            elif len(new_creator_name) > 100: form_errors['creator_name'] = "Display name is too long (max 100 characters)."
            else:
                creator.creator_name = new_creator_name
                creator.last_name_change_date = now
                update_fields.extend(['creator_name', 'last_name_change_date'])
                made_changes = True
        
        # Unique Name Logic
        unique_name_changed_from_db = creator.creator_unique_name != new_unique_name
        if unique_name_changed_from_db:
            if not can_change_unique_name: form_errors['creator_unique_name'] = f"You cannot change your unique handle again until {next_unique_name_change_date.strftime('%b %d, %Y')}."
            elif not new_unique_name: form_errors['creator_unique_name'] = "Unique handle cannot be empty."
            elif len(new_unique_name) > 50: form_errors['creator_unique_name'] = "Unique handle is too long (max 50 characters)."
            else:
                validator = Creator.unique_name_validator
                try:
                    validator(new_unique_name)
                    if Creator.objects.filter(creator_unique_name__iexact=new_unique_name).exclude(user=user).exists():
                        form_errors['creator_unique_name'] = 'This unique name is already taken.'
                    else:
                        creator.creator_unique_name = new_unique_name
                        creator.last_unique_name_change_date = now
                        update_fields.extend(['creator_unique_name', 'last_unique_name_change_date'])
                        made_changes = True
                except ValidationError as e: form_errors['creator_unique_name'] = e.message

        if form_errors:
            messages.error(request, "Please correct the errors below.")
            # No redirect, re-render the page with errors
        else:
            try:
                with transaction.atomic():
                    if update_fields: # Only save if there are fields to update
                        update_fields = list(set(update_fields)) # Ensure unique fields
                        creator.save(update_fields=update_fields)
                        messages.success(request, "Creator profile updated successfully!")
                    elif made_changes: # This case handles if only profile pic was removed (no new pic) and no other text fields changed
                         messages.success(request, "Creator profile updated successfully!") # Or a more specific message like "Profile picture removed."
                    else:
                        messages.info(request, "No changes were detected.")
                return redirect('AudioXApp:update_creator_profile') # Redirect on success
            except IntegrityError: # Specifically for unique_name conflict if somehow missed by earlier check
                logger.warning(f"IntegrityError updating creator profile for {creator.user.username}", exc_info=True)
                messages.error(request, "That unique name might already be taken. Please try another.")
                form_errors['creator_unique_name'] = 'This unique name is already taken.'
            except Exception as e:
                logger.error(f"Unexpected error updating creator profile for {creator.user.username}: {e}", exc_info=True)
                messages.error(request, "An unexpected error occurred while updating your profile.")
                form_errors['general_error'] = "An unexpected server error occurred."


    # For GET request or if POST had errors, prepare context
    context = _get_full_context(request) # Get base context
    context.update({
        'creator': creator, # The current creator object
        'form_errors': form_errors,
        'form_values': form_values, # Contains current or submitted values
        'can_change_name': can_change_name, 
        'next_name_change_date': next_name_change_date,
        'can_change_unique_name': can_change_unique_name, 
        'next_unique_name_change_date': next_unique_name_change_date,
        'available_balance': creator.available_balance, # Assuming this is needed in the template
    })
    return render(request, 'creator/creator_profile.html', context)


@login_required # User must be logged in
@require_POST # This action should only be via POST
@csrf_protect # CSRF protection
def mark_welcome_popup_shown(request):
    try:
        with transaction.atomic(): # Ensure atomic update
            # Use select_for_update to lock the row if multiple requests come nearly simultaneously
            creator = Creator.objects.select_for_update().get(user=request.user)
            if creator.verification_status == 'approved' and not creator.is_banned and not creator.welcome_popup_shown:
                creator.welcome_popup_shown = True
                creator.save(update_fields=['welcome_popup_shown'])
                return JsonResponse({'status': 'success', 'message': 'Welcome popup marked as shown.'})
            else:
                # It's okay if it's already shown or not applicable, just inform the client
                return JsonResponse({'status': 'ignored', 'message': 'Popup status not applicable or already updated.'})
    except Creator.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Creator profile not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error marking welcome popup shown for {request.user.username}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)

@login_required
@require_POST
@csrf_protect
def mark_rejection_popup_shown(request):
    try:
        with transaction.atomic():
            creator = Creator.objects.select_for_update().get(user=request.user)
            # Only mark if currently rejected and popup not yet shown
            if creator.verification_status == 'rejected' and not creator.rejection_popup_shown:
                creator.rejection_popup_shown = True
                creator.save(update_fields=['rejection_popup_shown'])
                return JsonResponse({'status': 'success', 'message': 'Rejection popup marked as shown.'})
            else:
                return JsonResponse({'status': 'ignored', 'message': 'Popup status not applicable or already updated.'})
    except Creator.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Creator profile not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error marking rejection popup shown for {request.user.username}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)