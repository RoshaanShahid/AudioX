# AudioXApp/views/user_views/subscription_views.py

import logging
import stripe
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
from ...models import User, Subscription
from ..utils import _get_full_context

logger = logging.getLogger(__name__)

if hasattr(settings, 'STRIPE_SECRET_KEY') and settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY
else:
    logger.error("Stripe Secret Key not configured in settings. Subscription features will fail.")

# --- Subscription Views ---

@login_required
def subscribe(request):
    context = _get_full_context(request)
    context['STRIPE_PUBLISHABLE_KEY'] = settings.STRIPE_PUBLISHABLE_KEY
    
    try:
        current_subscription = Subscription.objects.get(user=request.user)
        if current_subscription.is_active() or (current_subscription.status == 'canceled' and current_subscription.end_date and current_subscription.end_date > timezone.now()):
            messages.info(request, "You already have an active subscription. Manage it from your subscription page.")
            return redirect('AudioXApp:managesubscription')
    except Subscription.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f"Error checking current subscription for user {request.user.username} in subscribe view: {e}", exc_info=True)

    return render(request, 'user/subscription.html', context)

@login_required
def managesubscription(request):
    subscription = None
    user = request.user
    try:
        subscription = Subscription.objects.select_related('user').get(user=user)
        if subscription.status == 'active' and subscription.end_date and subscription.end_date < timezone.now():
            subscription.status = 'expired'
            if user.subscription_type == 'PR':
                user.subscription_type = 'FR'
                user.save(update_fields=['subscription_type'])
            subscription.save(update_fields=['status'])
    except Subscription.DoesNotExist:
        if user.subscription_type == 'PR':
            user.subscription_type = 'FR'
            user.save(update_fields=['subscription_type'])
        messages.info(request, "You do not have an active subscription.")
    except Exception as e:
        logger.error(f"Error fetching subscription for user {user.username} in managesubscription: {e}", exc_info=True)
        if user.subscription_type == 'PR':
            user.subscription_type = 'FR'
            user.save(update_fields=['subscription_type'])
        messages.error(request, "An error occurred while retrieving your subscription details.")

    context = _get_full_context(request)
    context['subscription'] = subscription
    return render(request, 'user/managesubscription.html', context)

@login_required
@require_POST
@csrf_protect
@transaction.atomic
def cancel_subscription(request):
    try:
        subscription = Subscription.objects.get(user=request.user, status='active')
        
        if not subscription.stripe_subscription_id:
            messages.error(request, "Cannot cancel: Your subscription is missing a payment provider ID. Please contact support.")
            return redirect('AudioXApp:managesubscription')

        cancellation_successful_on_stripe = False
        try:
            stripe.Subscription.modify(subscription.stripe_subscription_id, cancel_at_period_end=True)
            cancellation_successful_on_stripe = True
            logger.info(f"Stripe subscription {subscription.stripe_subscription_id} for user {request.user.username} set to cancel_at_period_end.")
        except stripe.error.StripeError as e_stripe:
            logger.error(f"Stripe API error canceling subscription {subscription.stripe_subscription_id} for user {request.user.username}: {e_stripe}", exc_info=True)
            messages.error(request, "Failed to schedule cancellation with the payment provider. Please contact support.")
        except Exception as e_unknown_stripe:
            logger.error(f"Unknown error during Stripe subscription cancellation for {subscription.stripe_subscription_id}, user {request.user.username}: {e_unknown_stripe}", exc_info=True)
            messages.error(request, "An unexpected error occurred with the payment provider. Please contact support.")

        if cancellation_successful_on_stripe:
            subscription.status = 'canceled' 
            subscription.save(update_fields=['status'])
            messages.success(request, "Your subscription has been scheduled for cancellation. You can continue using Premium features until the end of the current billing period.")

    except Subscription.DoesNotExist:
        messages.warning(request, "You do not have an active subscription to cancel.")
    except Exception as e:
        logger.error(f"Unexpected error in cancel_subscription for user {request.user.username}: {e}", exc_info=True)
        messages.error(request, "An error occurred while canceling your subscription. Please contact support.")
    
    return redirect('AudioXApp:managesubscription')