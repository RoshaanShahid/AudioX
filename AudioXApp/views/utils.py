import json
from django.urls import reverse, NoReverseMatch

from ..models import User, Creator, Subscription


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
            creator_profile = Creator.objects.select_related('user').get(user=user)

            context['creator_status'] = creator_profile.verification_status
            context['is_banned'] = getattr(creator_profile, 'is_banned', False)
            context['ban_reason'] = getattr(creator_profile, 'ban_reason', None) if context['is_banned'] else None
            context['is_creator'] = user.is_creator
            context['application_attempts_current_month'] = creator_profile.get_attempts_this_month()

            if creator_profile.verification_status == 'rejected':
                context['can_reapply'] = creator_profile.can_reapply()
                context['rejection_reason'] = creator_profile.rejection_reason
                if not creator_profile.rejection_popup_shown:
                    context['show_rejection_popup'] = True
            elif creator_profile.verification_status == 'approved' and not context['is_banned']:
                if not creator_profile.welcome_popup_shown:
                    context['show_welcome_popup'] = True
        except Creator.DoesNotExist:
            context['creator_status'] = None
            context['can_reapply'] = True
            context['application_attempts_current_month'] = 0
            context['is_banned'] = False
            context['ban_reason'] = None
            context['is_creator'] = False
        except AttributeError:
            context['is_creator'] = False
        except Exception as e:
            context['is_creator'] = False
    return context


def _get_full_context(request):
    user = request.user
    base_context = {}
    subscription_type = 'NA'
    is_premium_user = False

    if user.is_authenticated:
        try:
            current_user_data = User.objects.values('subscription_type', 'is_2fa_enabled', 'coins').get(pk=user.pk)
            subscription_type = current_user_data.get('subscription_type', 'FR')
            is_premium_user = (subscription_type == 'PR')

            base_context.update({
                'user': user,
                'is_authenticated': True,
                'subscription_type': subscription_type,
                'is_premium_user': is_premium_user,
                'is_2fa_enabled': current_user_data.get('is_2fa_enabled', False),
                'user_coins': current_user_data.get('coins', 0),
            })
        except User.DoesNotExist:
            base_context.update({
                'user': user,
                'is_authenticated': True,
                'subscription_type': 'FR',
                'is_premium_user': False,
                'is_2fa_enabled': False,
                'user_coins': 0,
            })
        except Exception as e:
            base_context.update({
                'user': user,
                'is_authenticated': True,
                'subscription_type': 'FR',
                'is_premium_user': False,
                'is_2fa_enabled': getattr(user, 'is_2fa_enabled', False),
                'user_coins': getattr(user, 'coins', 0),
            })
    else:
        base_context.update({
            'user': None,
            'is_authenticated': False,
            'subscription_type': 'NA',
            'is_premium_user': False,
            'is_2fa_enabled': False,
            'user_coins': 0,
        })

    creator_template_context = get_creator_context(user)
    base_context.update(creator_template_context)

    mark_welcome_url = None
    mark_rejection_url = None
    if user.is_authenticated:
        try:
            mark_welcome_url = reverse('AudioXApp:api_mark_welcome_popup')
        except NoReverseMatch:
            pass
        except Exception as e:
            pass

        try:
            mark_rejection_url = reverse('AudioXApp:api_mark_rejection_popup')
        except NoReverseMatch:
            pass
        except Exception as e:
            pass

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
