# AudioXApp/views/utils.py

import json
from django.urls import reverse, NoReverseMatch
import logging
from django.conf import settings as django_settings
from ..models import User, Creator

logger = logging.getLogger(__name__)

# --- Creator Context Helper ---

def get_creator_context(user):
    context = {
        'is_creator': False,
        'creator_status': None, 
        'is_banned': False,
        'ban_reason': None,
        'can_reapply': False,
        'rejection_reason': None,
        'show_welcome_popup': False,
        'show_rejection_popup': False,
        'application_attempts_current_month': 0,
        'max_application_attempts': getattr(django_settings, 'MAX_CREATOR_APPLICATION_ATTEMPTS', 3)
    }

    if not user.is_authenticated:
        return context

    creator_profile = None
    try:
        if hasattr(user, 'creator_profile') and user.creator_profile is not None:
            creator_profile = user.creator_profile
    except Creator.DoesNotExist:
        logger.warning(f"Creator.DoesNotExist for user {user.pk} when accessing creator_profile.")
        creator_profile = None
    except AttributeError:
        logger.info(f"User {user.pk} does not have a 'creator_profile' attribute.")
        creator_profile = None
    except Exception as e:
        logger.error(f"Error accessing creator_profile for user {user.pk}: {e}", exc_info=True)
        creator_profile = None

    if creator_profile:
        context['creator_status'] = creator_profile.verification_status
        context['is_banned'] = creator_profile.is_banned
        context['ban_reason'] = creator_profile.ban_reason if context['is_banned'] else None
        
        if creator_profile.verification_status == 'approved' and not creator_profile.is_banned:
            context['is_creator'] = True
            if not creator_profile.welcome_popup_shown:
                context['show_welcome_popup'] = True

        context['application_attempts_current_month'] = creator_profile.get_attempts_this_month()

        if creator_profile.verification_status == 'rejected':
            context['can_reapply'] = creator_profile.can_reapply()
            context['rejection_reason'] = creator_profile.rejection_reason
            if not creator_profile.rejection_popup_shown:
                context['show_rejection_popup'] = True
    else:
        context['creator_status'] = 'not_applied' 
    return context

# --- Full Context Helper ---

def _get_full_context(request):
    user = request.user
    base_context = {}
    
    admin_user_from_request = getattr(request, 'admin_user', None)
    base_context['admin_user'] = admin_user_from_request

    if user.is_authenticated:
        try:
            base_context.update({
                'user': user, 
                'is_authenticated': True,
                'subscription_type': user.subscription_type,
                'is_premium_user': (user.subscription_type == 'PR'),
                'is_2fa_enabled': user.is_2fa_enabled,
                'user_coins': user.coins,
            })
        except AttributeError as e:
            logger.error(f"AttributeError on request.user (pk: {user.pk if hasattr(user, 'pk') else 'N/A'}) in _get_full_context: {e}. Using defaults.", exc_info=True)
            base_context.update({ 
                'user': user, 'is_authenticated': True, 'subscription_type': 'FR', 
                'is_premium_user': False, 'is_2fa_enabled': False, 'user_coins': 0,
            })
        except Exception as e:
            logger.error(f"Unexpected error processing user data in _get_full_context for user {user.pk if hasattr(user, 'pk') else 'N/A'}: {e}", exc_info=True)
            base_context.update({ 
                'user': user, 'is_authenticated': True, 'subscription_type': 'FR',
                'is_premium_user': False, 'is_2fa_enabled': False, 'user_coins': 0,
            })
    else: 
        base_context.update({
            'user': user, 
            'is_authenticated': False, 'subscription_type': 'NA', 'is_premium_user': False,
            'is_2fa_enabled': False, 'user_coins': 0,
        })

    creator_specific_context = get_creator_context(user)
    base_context.update(creator_specific_context)

    mark_welcome_url = None
    mark_rejection_url = None
    if user.is_authenticated:
        try:
            mark_welcome_url = reverse('AudioXApp:api_mark_welcome_popup')
        except NoReverseMatch:
            logger.warning("URL 'AudioXApp:api_mark_welcome_popup' not found.")
        try:
            mark_rejection_url = reverse('AudioXApp:api_mark_rejection_popup')
        except NoReverseMatch:
            logger.warning("URL 'AudioXApp:api_mark_rejection_popup' not found.")

    js_creator_status_for_popup = base_context.get('creator_status', 'not_applicable')
    if base_context.get('is_banned'): 
        js_creator_status_for_popup = 'banned'
    
    creator_js_context_data = {
        'is_creator': base_context.get('is_creator', False),
        'creator_status': js_creator_status_for_popup,
        'can_reapply': base_context.get('can_reapply', False), 
        'rejectionReason': base_context.get('rejection_reason'),
        'showWelcomePopup': base_context.get('show_welcome_popup', False),
        'showRejectionPopup': base_context.get('show_rejection_popup', False),
        'applicationAttemptsCurrentMonth': base_context.get('application_attempts_current_month', 0),
        'max_application_attempts': base_context.get('max_application_attempts', getattr(django_settings, 'MAX_CREATOR_APPLICATION_ATTEMPTS', 3)),
        'isBanned': base_context.get('is_banned', False),
        'banReason': base_context.get('ban_reason'),
        'markWelcomeUrl': mark_welcome_url,
        'markRejectionUrl': mark_rejection_url,
    }
    base_context['creator_js_context'] = creator_js_context_data
    
    return base_context