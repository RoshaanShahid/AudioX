# AudioXApp/views/user_views/subscription_views.py

import logging
import stripe # For Stripe API calls

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.urls import reverse


from ...models import User, Subscription # Relative import
from ..utils import _get_full_context # Relative import

logger = logging.getLogger(__name__)

# Configure Stripe API key if not already done globally (though it should be)
if hasattr(settings, 'STRIPE_SECRET_KEY') and settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY
else:
    logger.error("Stripe Secret Key not configured in settings. Subscription features will fail.")


# --- Subscription Views ---

@login_required
def subscribe(request):
    """Renders the subscription page where users can choose a plan."""
    context = _get_full_context(request)
    context['STRIPE_PUBLISHABLE_KEY'] = settings.STRIPE_PUBLISHABLE_KEY
    
    # Check if user already has an active or pending cancellation subscription
    try:
        current_subscription = Subscription.objects.get(user=request.user)
        if current_subscription.is_active() or \
           (current_subscription.status == 'canceled' and current_subscription.end_date and current_subscription.end_date > timezone.now()):
            messages.info(request, "You already have an active subscription. Manage it from your subscription page.")
            return redirect('AudioXApp:managesubscription')
    except Subscription.DoesNotExist:
        pass # No subscription exists, user can proceed to subscribe
    except Exception as e:
        logger.error(f"Error checking current subscription for user {request.user.username} in subscribe view: {e}", exc_info=True)
        # Allow to proceed but log error

    return render(request, 'user/subscription.html', context)

@login_required
def managesubscription(request):
    """Renders the manage subscription page."""
    subscription = None
    user = request.user
    try:
        subscription = Subscription.objects.select_related('user').get(user=user)
        # Check and update status if it's active but past end_date (e.g., Stripe webhook missed or delayed)
        if subscription.status == 'active' and subscription.end_date and subscription.end_date < timezone.now():
            subscription.status = 'expired'
            if user.subscription_type == 'PR': # Downgrade user type if they were premium
                user.subscription_type = 'FR'
                user.save(update_fields=['subscription_type'])
            subscription.save(update_fields=['status'])
    except Subscription.DoesNotExist:
        # If no subscription record, ensure user type is 'FR' if it was 'PR'
        if user.subscription_type == 'PR':
            user.subscription_type = 'FR'
            user.save(update_fields=['subscription_type'])
        messages.info(request, "You do not have an active subscription.")
        # Optionally redirect to subscribe page or just show a message on managesubscription template
    except Exception as e:
        logger.error(f"Error fetching subscription for user {user.username} in managesubscription: {e}", exc_info=True)
        if user.subscription_type == 'PR': # Safety check
            user.subscription_type = 'FR'
            user.save(update_fields=['subscription_type'])
        messages.error(request, "An error occurred while retrieving your subscription details.")

    context = _get_full_context(request)
    context['subscription'] = subscription
    return render(request, 'user/managesubscription.html', context)


@login_required
@require_POST # Ensure this is a POST request
@csrf_protect   # CSRF protection
@transaction.atomic # Use atomic transaction for local DB changes
def cancel_subscription(request):
    """Handles canceling a user's active Stripe subscription at period end."""
    try:
        # Get the local subscription record, ensuring it's active
        subscription = Subscription.objects.get(user=request.user, status='active')
        
        if not subscription.stripe_subscription_id:
            messages.error(request, "Cannot cancel: Your subscription is missing a payment provider ID. Please contact support.")
            return redirect('AudioXApp:managesubscription')

        # Attempt to cancel with Stripe (set to cancel at period end)
        try:
            stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=True
            )
            cancellation_successful_on_stripe = True
            logger.info(f"Stripe subscription {subscription.stripe_subscription_id} for user {request.user.username} set to cancel_at_period_end.")
        except stripe.error.StripeError as e_stripe:
            logger.error(f"Stripe API error canceling subscription {subscription.stripe_subscription_id} for user {request.user.username}: {e_stripe}", exc_info=True)
            messages.error(request, "Failed to schedule cancellation with the payment provider. Please contact support.")
            cancellation_successful_on_stripe = False
        except Exception as e_unknown_stripe: # Catch any other unexpected error from Stripe
            logger.error(f"Unknown error during Stripe subscription cancellation for {subscription.stripe_subscription_id}, user {request.user.username}: {e_unknown_stripe}", exc_info=True)
            messages.error(request, "An unexpected error occurred with the payment provider. Please contact support.")
            cancellation_successful_on_stripe = False


        if cancellation_successful_on_stripe:
            # Update local subscription status to 'canceled'
            # The subscription remains usable until subscription.end_date
            subscription.status = 'canceled' 
            subscription.save(update_fields=['status'])
            messages.success(request, "Your subscription has been scheduled for cancellation. You can continue using Premium features until the end of the current billing period.")
        # If cancellation failed on Stripe, no changes are made to local DB, message already set.

    except Subscription.DoesNotExist:
        messages.warning(request, "You do not have an active subscription to cancel.")
    except Exception as e: # Catch-all for other unexpected errors
        logger.error(f"Unexpected error in cancel_subscription for user {request.user.username}: {e}", exc_info=True)
        messages.error(request, "An error occurred while canceling your subscription. Please contact support.")
    
    return redirect('AudioXApp:managesubscription')