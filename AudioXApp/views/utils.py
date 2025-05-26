# AudioXApp/views/utils.py
import json
from django.urls import reverse, NoReverseMatch
import logging # It's good practice to have logging available

# Import Admin model if you need to type hint or for other direct uses,
# but getattr will work even if it's not imported here for this specific change.
from ..models import User, Creator, Subscription, Admin 

logger = logging.getLogger(__name__) # Initialize logger if you plan to use it

def get_creator_context(user):
    context = {
        'is_creator': False,
        'creator_status': None,
        'can_reapply': True,
        'rejection_reason': None,
        'show_welcome_popup': False,
        'show_rejection_popup': False,
        'application_attempts_current_month': 0,
        'is_banned': False,
        'ban_reason': None,
    }
    if user.is_authenticated:
        try:
            # Assuming user.is_creator is a boolean field or property on your custom User model
            # that indicates if a Creator profile link exists.
            if hasattr(user, 'is_creator') and user.is_creator: # Check if user is marked as a creator
                creator_profile = Creator.objects.select_related('user').get(user=user)
                context['creator_status'] = creator_profile.verification_status
                context['is_banned'] = getattr(creator_profile, 'is_banned', False)
                context['ban_reason'] = getattr(creator_profile, 'ban_reason', None) if context['is_banned'] else None
                context['is_creator'] = True # Confirm based on fetched profile
                context['application_attempts_current_month'] = creator_profile.get_attempts_this_month()

                if creator_profile.verification_status == 'rejected':
                    context['can_reapply'] = creator_profile.can_reapply()
                    context['rejection_reason'] = creator_profile.rejection_reason
                    if not creator_profile.rejection_popup_shown:
                        context['show_rejection_popup'] = True
                elif creator_profile.verification_status == 'approved' and not context['is_banned']:
                    if not creator_profile.welcome_popup_shown:
                        context['show_welcome_popup'] = True
            else: # User is authenticated but not flagged as a creator or no Creator profile exists
                context['is_creator'] = False # Ensure it's false
                # Other defaults are already set

        except Creator.DoesNotExist:
            # This means user.is_creator might have been true, but no profile found (data inconsistency?)
            # Or the initial check for user.is_creator was bypassed.
            # Reset creator-specific flags to default.
            context['is_creator'] = False
            # Defaults are already set, so pass is okay, or explicitly reset if needed.
            pass
        except AttributeError as e:
            logger.warning(f"AttributeError in get_creator_context for user {user.pk if user else 'Anonymous'}: {e}")
            context['is_creator'] = False # Ensure it's reset
        except Exception as e:
            logger.error(f"Unexpected error in get_creator_context for user {user.pk if user else 'Anonymous'}: {e}", exc_info=True)
            context['is_creator'] = False # Ensure it's reset
    return context


def _get_full_context(request):
    user = request.user
    base_context = {}
    
    # --- THIS IS THE CRUCIAL ADDITION ---
    # Attempt to get the admin_user set by the @admin_role_required decorator
    admin_user_from_request = getattr(request, 'admin_user', None)
    base_context['admin_user'] = admin_user_from_request 
    # --- END OF CRUCIAL ADDITION ---

    subscription_type = 'NA'
    is_premium_user = False

    if user.is_authenticated:
        try:
            # Assuming User is your custom user model from ..models
            current_user_data = User.objects.values('subscription_type', 'is_2fa_enabled', 'coins').get(pk=user.pk)
            subscription_type = current_user_data.get('subscription_type', 'FR')
            is_premium_user = (subscription_type == 'PR')

            base_context.update({
                'user': user, # This is the standard Django user for frontend context
                'is_authenticated': True,
                'subscription_type': subscription_type,
                'is_premium_user': is_premium_user,
                'is_2fa_enabled': current_user_data.get('is_2fa_enabled', False),
                'user_coins': current_user_data.get('coins', 0),
            })
        except User.DoesNotExist:
            # This case should ideally not happen for an authenticated user if User is AUTH_USER_MODEL
            # and request.user is already an instance of it.
            # If request.user can be an AnonymousUser object, this might be fine.
            logger.warning(f"User.DoesNotExist for authenticated user ID: {user.pk} in _get_full_context. This might indicate an issue if User is AUTH_USER_MODEL.")
            base_context.update({
                'user': user, 
                'is_authenticated': True, # Still true, but data fetch failed
                'subscription_type': 'FR', 
                'is_premium_user': False,
                'is_2fa_enabled': False,
                'user_coins': 0,
            })
        except Exception as e:
            logger.error(f"Error fetching user data in _get_full_context for user {user.pk if hasattr(user, 'pk') else 'Anonymous'}: {e}", exc_info=True)
            base_context.update({ 
                'user': user,
                'is_authenticated': True,
                'subscription_type': 'FR',
                'is_premium_user': False,
                'is_2fa_enabled': getattr(user, 'is_2fa_enabled', False), 
                'user_coins': getattr(user, 'coins', 0), 
            })
    else: # User is not authenticated (AnonymousUser)
        base_context.update({
            'user': None, # Or request.user which would be AnonymousUser instance
            'is_authenticated': False,
            'subscription_type': 'NA',
            'is_premium_user': False,
            'is_2fa_enabled': False,
            'user_coins': 0,
        })

    # This part adds information relevant to the 'user' being a 'creator'
    creator_template_context = get_creator_context(user) # user here is request.user
    base_context.update(creator_template_context)

    mark_welcome_url = None
    mark_rejection_url = None
    if user.is_authenticated:
        try:
            mark_welcome_url = reverse('AudioXApp:api_mark_welcome_popup')
        except NoReverseMatch:
            logger.warning("URL 'AudioXApp:api_mark_welcome_popup' not found.")
        # Removed broad except Exception as e: pass

        try:
            mark_rejection_url = reverse('AudioXApp:api_mark_rejection_popup')
        except NoReverseMatch:
            logger.warning("URL 'AudioXApp:api_mark_rejection_popup' not found.")
        # Removed broad except Exception as e: pass

    creator_js_context_data = {
        'is_creator': creator_template_context.get('is_creator', False),
        'creator_status': creator_template_context.get('creator_status'),
        'can_reapply': creator_template_context.get('can_reapply', True),
        'rejectionReason': creator_template_context.get('rejection_reason'),
        'showWelcomePopup': creator_template_context.get('show_welcome_popup', False),
        'showRejectionPopup': creator_template_context.get('show_rejection_popup', False),
        'applicationAttemptsCurrentMonth': creator_template_context.get('application_attempts_current_month', 0),
        'isBanned': creator_template_context.get('is_banned', False),
        'banReason': creator_template_context.get('ban_reason'),
        'markWelcomeUrl': mark_welcome_url,
        'markRejectionUrl': mark_rejection_url,
    }
    base_context['creator_js_context'] = creator_js_context_data

    return base_context