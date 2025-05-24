# AudioXApp/views/creator_views/admin_actions_views.py

import logging
from django.shortcuts import redirect, get_object_or_404
from django.http import JsonResponse # Not strictly needed for these views as they redirect, but good practice
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.db import transaction
from django.utils import timezone
from django.urls import reverse

from ...models import Creator, Admin, CreatorApplicationLog # Relative imports
from ..decorators import admin_role_required # Relative import from parent views.decorators

logger = logging.getLogger(__name__)

@admin_role_required('manage_creators')
@require_POST
@csrf_protect
@transaction.atomic # Ensure database operations are atomic
def admin_approve_creator(request, user_id):
    """
    Handles the admin action to approve a pending creator application.
    """
    # user_id here refers to the User's ID, which is the PK for Creator model
    creator = get_object_or_404(Creator.objects.select_related('user'), user_id=user_id)
    admin_user = request.admin_user # From admin_role_required decorator

    if creator.verification_status == 'pending':
        creator_cid = f"cid-{creator.user.user_id}" # Generate CID based on user_id
        approval_time = timezone.now()
        attempts_when_submitted = creator.application_attempts_current_month # Log attempts at time of this submission

        creator.verification_status = 'approved'
        creator.cid = creator_cid
        creator.approved_at = approval_time
        creator.approved_by = admin_user
        creator.attempts_at_approval = attempts_when_submitted # Store how many attempts it took for this approval
        creator.rejection_reason = None # Clear any previous rejection reason
        creator.welcome_popup_shown = False # Reset for new approval
        creator.rejection_popup_shown = False # Reset
        
        # Ensure ban status is cleared on approval
        creator.is_banned = False
        creator.ban_reason = None
        creator.banned_at = None
        creator.banned_by = None
        
        # Reset name change cooldowns if desired upon approval, or leave them.
        # For now, we'll assume they are not reset by approval itself.
        # creator.last_name_change_date = None 
        # creator.last_unique_name_change_date = None

        fields_to_update = [
            'verification_status', 'cid', 'approved_at', 'approved_by', 'attempts_at_approval',
            'rejection_reason', 'welcome_popup_shown', 'rejection_popup_shown', 'is_banned',
            'ban_reason', 'banned_at', 'banned_by',
        ]
        creator.save(update_fields=fields_to_update)

        # Update the latest CreatorApplicationLog for this creator
        try:
            # Find the most recent 'submitted' log for this creator
            latest_log = CreatorApplicationLog.objects.filter(creator=creator, status='submitted').latest('application_date')
            latest_log.status = 'approved'
            latest_log.processed_at = approval_time
            latest_log.processed_by = admin_user
            latest_log.rejection_reason = None # Clear rejection reason on the log too
            latest_log.save(update_fields=['status', 'processed_at', 'processed_by', 'rejection_reason'])
        except CreatorApplicationLog.DoesNotExist:
            logger.warning(f"Could not find a 'submitted' application log for creator {creator.user.username} (ID: {creator.user_id}) to mark as approved.")
            messages.warning(request, f"Creator approved, but could not find a matching 'submitted' application log for {creator.user.username} to update.")
        except Exception as log_e:
            logger.error(f"Error updating application log to 'approved' for creator {creator.user.username}: {log_e}", exc_info=True)
            messages.error(request, f"Creator approved, but an error occurred while updating the application log: {log_e}")

        messages.success(request, f"Creator '{creator.creator_name}' (User: {creator.user.username}) approved successfully by {admin_user.username} with CID: {creator_cid}.")
    else:
        messages.warning(request, f"Creator '{creator.creator_name}' is not pending approval (Status: {creator.get_verification_status_display()}). No action taken.")
    
    return redirect(request.META.get('HTTP_REFERER', reverse('AudioXApp:admin_pending_creator_applications')))


@admin_role_required('manage_creators')
@require_POST
@csrf_protect
@transaction.atomic
def admin_reject_creator(request, user_id):
    """
    Handles the admin action to reject a pending creator application.
    """
    creator = get_object_or_404(Creator.objects.select_related('user'), user_id=user_id)
    admin_user = request.admin_user
    rejection_reason_input = request.POST.get('rejection_reason', '').strip()
    rejection_time = timezone.now()

    if not rejection_reason_input:
        messages.error(request, "Rejection reason is required to reject an application.")
        return redirect(request.META.get('HTTP_REFERER', reverse('AudioXApp:admin_pending_creator_applications')))

    if creator.verification_status == 'pending':
        creator.verification_status = 'rejected'
        creator.rejection_reason = rejection_reason_input
        creator.rejection_popup_shown = False # Reset for new rejection
        creator.welcome_popup_shown = False # Ensure welcome popup isn't shown
        
        # Clear approval related fields if any were set erroneously
        creator.approved_at = None
        creator.approved_by = None
        creator.attempts_at_approval = None
        creator.cid = None # No CID for rejected applications

        fields_to_update = [
            'verification_status', 'rejection_reason', 'rejection_popup_shown', 'welcome_popup_shown',
            'approved_at', 'approved_by', 'attempts_at_approval', 'cid',
        ]
        creator.save(update_fields=fields_to_update)

        try:
            latest_log = CreatorApplicationLog.objects.filter(creator=creator, status='submitted').latest('application_date')
            latest_log.status = 'rejected'
            latest_log.processed_at = rejection_time
            latest_log.processed_by = admin_user
            latest_log.rejection_reason = rejection_reason_input
            latest_log.save(update_fields=['status', 'processed_at', 'processed_by', 'rejection_reason'])
        except CreatorApplicationLog.DoesNotExist:
            logger.warning(f"Could not find a 'submitted' application log for creator {creator.user.username} (ID: {creator.user_id}) to mark as rejected.")
            messages.warning(request, f"Application rejected, but could not find a matching 'submitted' application log for {creator.user.username} to update.")
        except Exception as log_e:
            logger.error(f"Error updating application log to 'rejected' for creator {creator.user.username}: {log_e}", exc_info=True)
            messages.error(request, f"Application rejected, but an error occurred while updating the application log: {log_e}")

        messages.success(request, f"Creator '{creator.creator_name}' (User: {creator.user.username}) application rejected by {admin_user.username}.")
    else:
        messages.warning(request, f"Creator '{creator.creator_name}' is not pending rejection (Status: {creator.get_verification_status_display()}). No action taken.")
    
    return redirect(request.META.get('HTTP_REFERER', reverse('AudioXApp:admin_pending_creator_applications')))


@admin_role_required('manage_creators')
@require_POST
@csrf_protect
@transaction.atomic
def admin_ban_creator(request, user_id):
    """
    Handles the admin action to ban a creator.
    """
    creator = get_object_or_404(Creator.objects.select_related('user'), user_id=user_id)
    admin_user = request.admin_user # From decorator
    ban_reason_input = request.POST.get('ban_reason', '').strip()
    redirect_url = request.META.get('HTTP_REFERER', reverse('AudioXApp:admin_all_creators_list')) # Sensible default

    if not ban_reason_input:
        messages.error(request, "A reason is required to ban a creator.")
        return redirect(redirect_url)

    # Check if all necessary ban-related attributes exist on the model
    required_attrs = ['is_banned', 'ban_reason', 'banned_at', 'banned_by', 'verification_status']
    if not all(hasattr(creator, attr) for attr in required_attrs):
        logger.error(f"Creator model for {creator.user.username} is missing required ban attributes.")
        messages.error(request, "Cannot perform ban: Creator model is missing required fields. Please contact support.")
        return redirect(redirect_url)

    if not creator.is_banned:
        creator.is_banned = True
        creator.ban_reason = ban_reason_input
        creator.banned_at = timezone.now()
        creator.banned_by = admin_user
        
        # Optionally, set verification_status to 'rejected' or another status if not already.
        # This depends on your desired workflow for banned users.
        if creator.verification_status != 'rejected': # Example: if approved, mark as rejected upon ban
            creator.verification_status = 'rejected' 
            # Also clear approval details if moving from approved to banned/rejected
            creator.approved_at = None
            creator.approved_by = None
            creator.cid = None # Remove CID if banned and status changed from approved

        creator.save(update_fields=['is_banned', 'ban_reason', 'banned_at', 'banned_by', 'verification_status', 'approved_at', 'approved_by', 'cid'])
        messages.success(request, f"Creator '{creator.user.username}' ({creator.creator_name}) has been banned by {admin_user.username}.")
    else:
        messages.warning(request, f"Creator '{creator.user.username}' is already banned.")
    
    return redirect(redirect_url)


@admin_role_required('manage_creators')
@require_POST
@csrf_protect
@transaction.atomic
def admin_unban_creator(request, user_id):
    """
    Handles the admin action to unban a creator.
    """
    creator = get_object_or_404(Creator.objects.select_related('user'), user_id=user_id)
    admin_user = request.admin_user # From decorator
    unban_reason_input = request.POST.get('unban_reason', '').strip() # Reason for unbanning for audit log
    redirect_url = request.META.get('HTTP_REFERER', reverse('AudioXApp:admin_banned_creators_list'))

    if not unban_reason_input:
        messages.error(request, "A reason is required to unban a creator (for admin records).")
        return redirect(redirect_url)

    required_attrs = ['is_banned', 'ban_reason', 'banned_at', 'banned_by', 'admin_notes', 'verification_status', 'welcome_popup_shown']
    if not all(hasattr(creator, attr) for attr in required_attrs):
        logger.error(f"Creator model for {creator.user.username} is missing required unban attributes.")
        messages.error(request, "Cannot perform unban: Creator model is missing required fields. Please contact support.")
        return redirect(redirect_url)

    if creator.is_banned:
        unban_time = timezone.now()
        unban_note = f"Unbanned by {admin_user.username} on {unban_time.strftime('%Y-%m-%d %H:%M:%S %Z')}. Reason: {unban_reason_input}. Previous ban reason: {creator.ban_reason}"
        
        creator.is_banned = False
        creator.banned_at = None # Clear ban timestamp
        creator.banned_by = None # Clear banning admin
        creator.ban_reason = None # Clear ban reason
        
        # Add unban note to admin_notes
        if creator.admin_notes:
            creator.admin_notes = f"{creator.admin_notes}\n\n{unban_note}"
        else:
            creator.admin_notes = unban_note
            
        # Decide what the verification_status should be upon unbanning.
        # Common practice: set to 'approved' if they were previously approved or if unbanning implies approval.
        # Or, set to 'pending' if they need to re-verify/re-apply.
        # For this example, let's set to 'approved' and reset welcome popup.
        creator.verification_status = 'approved'
        creator.welcome_popup_shown = False # Allow welcome popup again
        # If they don't have a CID yet and are being approved, generate one.
        if not creator.cid:
            creator.cid = f"cid-{creator.user.user_id}"

        creator.save(update_fields=[
            'is_banned', 'banned_at', 'banned_by', 'ban_reason', 'admin_notes', 
            'verification_status', 'welcome_popup_shown', 'cid'
        ])
        messages.success(request, f"Creator '{creator.user.username}' ({creator.creator_name}) has been unbanned and set to approved by {admin_user.username}.")
    else:
        messages.warning(request, f"Creator '{creator.user.username}' is not currently banned.")
        
    return redirect(redirect_url)