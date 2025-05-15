import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import datetime
import logging
import re # Import the 're' module for regular expressions


import stripe
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.db.models import F
from django.core.files.storage import default_storage
from django.utils import timezone
from django.db.models import Value, CharField
from django.db.models.functions import Concat
from django.urls import reverse
from django.core.validators import validate_email
# from datetime import datetime # datetime is already imported above


from ..models import User, CoinTransaction, Subscription, Audiobook, Chapter, Review, AudiobookPurchase, CreatorEarning, Creator
from .utils import _get_full_context

if not hasattr(settings, 'STRIPE_SECRET_KEY') or not settings.STRIPE_SECRET_KEY:
    pass # Critical error should be handled in a production environment
stripe.api_key = settings.STRIPE_SECRET_KEY

logger = logging.getLogger(__name__) # Add this for logging

@login_required
def myprofile(request):
    context = _get_full_context(request)
    if context.get('is_banned'):
        context['ban_reason_display'] = context.get('ban_reason', 'No reason provided.')
    return render(request, 'user/myprofile.html', context)

@login_required
@require_POST
@csrf_protect
def update_profile(request):
    user = request.user
    if request.content_type.startswith('multipart'):
        # Profile picture upload (multipart form data)
        if 'profile_pic' in request.FILES:
            if user.profile_pic:
                try:
                    if default_storage.exists(user.profile_pic.name):
                        default_storage.delete(user.profile_pic.name)
                except Exception as e:
                    logger.error(f"Error deleting old profile picture for user {user.pk}: {e}")
                    pass # Error deleting old picture

            user.profile_pic = request.FILES['profile_pic']
            try:
                user.save(update_fields=['profile_pic'])
                pic_url = user.profile_pic.url + f'?t={timezone.now().timestamp()}' # Cache buster
                return JsonResponse({'status': 'success', 'message': 'Profile picture updated successfully.', 'profile_pic_url': pic_url})
            except Exception as e:
                logger.error(f"Error saving profile picture for user {user.pk}: {e}")
                return JsonResponse({'status': 'error', 'message': 'Error saving profile picture.'}, status=500)
        else:
            return JsonResponse({'status': 'error', 'message': 'No profile picture file found in request.'}, status=400)

    elif request.content_type == 'application/json':
        # Other profile fields update (JSON data)
        try:
            data = json.loads(request.body)
            fields_to_update = []
            error_messages = {} # To collect any validation errors

            if 'username' in data:
                username = data['username'].strip()
                if not username:
                    error_messages['username'] = 'Username cannot be empty.'
                elif len(username) < 3:
                    error_messages['username'] = 'Username must be at least 3 characters long.'
                elif user.username != username:
                    if User.objects.exclude(pk=user.pk).filter(username=username).exists():
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
                        if user.email != email:
                            if User.objects.exclude(pk=user.pk).filter(email=email).exists():
                                error_messages['email'] = 'Email already exists.'
                            else:
                                user.email = email
                                fields_to_update.append('email')
                    except ValidationError:
                        error_messages['email'] = 'Invalid email address format.'
            
            # --- NEW: Phone Number Validation ---
            if 'phone_number' in data:
                phone_number = data['phone_number'].strip()
                if phone_number: # Only validate if not empty
                    # Regex for +923xxxxxxxxx format
                    phone_regex = r"^\+923\d{9}$"
                    if not re.match(phone_regex, phone_number):
                        error_messages['phone_number'] = 'Invalid phone number format. Use +923xxxxxxxxx.'
                    # Add uniqueness check if phone_number should be unique across users
                    # elif User.objects.exclude(pk=user.pk).filter(phone_number=phone_number).exists():
                    #     error_messages['phone_number'] = 'This phone number is already registered.'
                    else:
                        if user.phone_number != phone_number:
                            user.phone_number = phone_number
                            fields_to_update.append('phone_number')
                else: # If phone_number is an empty string (user wants to clear it)
                    if user.phone_number != '': # Check if it's actually a change
                        user.phone_number = ''
                        fields_to_update.append('phone_number')
            # --- END: Phone Number Validation ---


            if 'bio' in data:
                bio = data['bio'].strip()
                if user.bio != bio:
                    user.bio = bio
                    fields_to_update.append('bio')

            if data.get('remove_profile_pic') is True:
                if user.profile_pic:
                    try:
                        if default_storage.exists(user.profile_pic.name):
                            default_storage.delete(user.profile_pic.name)
                        user.profile_pic = None
                        fields_to_update.append('profile_pic')
                    except Exception as e:
                        logger.error(f"Error removing profile picture for user {user.pk}: {e}")
                        # Decide if this should be a hard error or just a warning
                        error_messages['profile_pic'] = 'Error removing profile picture.'


            if 'is_2fa_enabled' in data:
                new_2fa_status = data.get('is_2fa_enabled')
                if isinstance(new_2fa_status, bool):
                    if user.is_2fa_enabled != new_2fa_status:
                        user.is_2fa_enabled = new_2fa_status
                        fields_to_update.append('is_2fa_enabled')
                else:
                    error_messages['is_2fa_enabled'] = 'Invalid value for 2FA status.'

            # If there were any validation errors, return them
            if error_messages:
                # Construct a general message if needed, or rely on field-specific messages
                general_error_message = "Please correct the errors below."
                # Check if only one error message and it's for profile_pic removal to customize general message
                if len(error_messages) == 1 and 'profile_pic' in error_messages and 'Error removing profile picture' in error_messages['profile_pic']:
                    general_error_message = error_messages['profile_pic'] # Use the specific error as general

                return JsonResponse({'status': 'error', 'message': general_error_message, 'errors': error_messages}, status=400)

            if fields_to_update:
                try:
                    user.save(update_fields=fields_to_update)
                    message = "Profile updated successfully."
                    if 'is_2fa_enabled' in fields_to_update and len(fields_to_update) == 1:
                        message = f"Two-Factor Authentication {'enabled' if user.is_2fa_enabled else 'disabled'}."
                    elif 'profile_pic' in fields_to_update and data.get('remove_profile_pic') is True and len(fields_to_update) == 1:
                        message = "Profile picture removed successfully."
                    return JsonResponse({'status': 'success', 'message': message})
                except IntegrityError as e: # Catch specific database errors like unique constraint violations
                    logger.error(f"IntegrityError saving profile for user {user.pk}: {e}")
                    # Try to identify which field caused it (this is a bit simplistic)
                    if 'username' in str(e).lower():
                        return JsonResponse({'status': 'error', 'message': 'Username already exists.', 'errors': {'username': 'Username already exists.'}}, status=400)
                    elif 'email' in str(e).lower():
                         return JsonResponse({'status': 'error', 'message': 'Email already exists.', 'errors': {'email': 'Email already exists.'}}, status=400)
                    # Add similar checks for other unique fields if any (e.g. phone_number if it were unique)
                    return JsonResponse({'status': 'error', 'message': 'A data conflict occurred. Please check your input.'}, status=400)
                except Exception as e:
                    logger.error(f"Error saving profile for user {user.pk}: {e}")
                    return JsonResponse({'status': 'error', 'message': 'Error saving profile.'}, status=500)
            else:
                return JsonResponse({'status': 'success', 'message': 'No changes detected.'})

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid request data format.'}, status=400)
        except Exception as e:
            logger.error(f"Unexpected error in update_profile for user {user.pk}: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request format.'}, status=415)

@login_required
@csrf_protect
def change_password(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            return JsonResponse({'status': 'success', 'message': 'Password updated successfully!'})
        else:
            errors = {field: error[0] for field, error in form.errors.items()}
            # Customize specific error messages if needed
            if 'old_password' in errors and 'Invalid password' in errors['old_password']: # Django's default message
                errors['old_password'] = 'Incorrect current password.'
            
            # For new_password2 (confirmation)
            if 'new_password2' in errors:
                if "The two password fields didn’t match." in errors['new_password2']:
                     errors['new_password2'] = "Passwords didn't match."
                # Add other common password error messages if you want to customize them
                # For example, Django's common password validators:
                elif "password is too common" in errors['new_password2'].lower():
                    errors['new_password2'] = "This password is too common."
                elif "password is too short" in errors['new_password2'].lower():
                     min_length = getattr(settings, 'AUTH_PASSWORD_VALIDATORS', [{'OPTIONS': {'min_length': 8}}])[0].get('OPTIONS', {}).get('min_length', 8)
                     errors['new_password2'] = f"Password must be at least {min_length} characters."
                elif "entirely numeric" in errors['new_password2'].lower():
                    errors['new_password2'] = "Password can't be entirely numeric."
                # Add more specific messages based on your validators

            return JsonResponse({'status': 'error', 'message': 'Please correct the errors below.', 'errors': errors}, status=400)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method or type.'}, status=400)


@login_required
def buycoins(request):
    purchase_history = CoinTransaction.objects.filter(
        user=request.user, transaction_type='purchase'
    ).exclude(
        pack_name__in=['Monthly Premium Subscription', 'Annual Premium Subscription']
    ).order_by('-transaction_date')

    context = _get_full_context(request)
    context['purchase_history'] = purchase_history
    context['STRIPE_PUBLISHABLE_KEY'] = settings.STRIPE_PUBLISHABLE_KEY
    return render(request, 'user/buycoins.html', context)

@login_required
@require_POST
@csrf_protect
@transaction.atomic
def gift_coins(request):
    try:
        data = json.loads(request.body)
        sender = request.user
        recipient_identifier = data.get('recipient')
        amount_str = data.get('amount')

        if not recipient_identifier or not amount_str:
            return JsonResponse({'status': 'error', 'message': 'Recipient and amount are required.'}, status=400)

        try:
            amount = int(amount_str)
            if amount <= 0: return JsonResponse({'status': 'error', 'message': 'Gift amount must be positive.'}, status=400)
        except (ValueError, TypeError): return JsonResponse({'status': 'error', 'message': 'Invalid gift amount format.'}, status=400)

        try:
            if '@' in recipient_identifier: recipient = User.objects.get(email__iexact=recipient_identifier)
            else: recipient = User.objects.get(username__iexact=recipient_identifier)
            if recipient == sender: return JsonResponse({'status': 'error', 'message': 'You cannot gift coins to yourself.'}, status=400)
        except User.DoesNotExist: return JsonResponse({'status': 'error', 'message': 'Recipient user not found.'}, status=404)

        sender_locked = User.objects.select_for_update().get(pk=sender.pk)
        if sender_locked.coins < amount: return JsonResponse({'status': 'error', 'message': 'Insufficient coins.'}, status=400)

        sender_locked.coins -= amount
        sender_locked.save(update_fields=['coins'])
        recipient_locked = User.objects.select_for_update().get(pk=recipient.pk)
        recipient_locked.coins += amount
        recipient_locked.save(update_fields=['coins'])

        CoinTransaction.objects.create(user=sender_locked, transaction_type='gift_sent', amount=-amount, recipient=recipient_locked, status='completed')
        CoinTransaction.objects.create(user=recipient_locked, transaction_type='gift_received', amount=amount, sender=sender_locked, status='completed')

        sender.refresh_from_db()
        return JsonResponse({'status': 'success', 'message': f'Successfully gifted {amount} coins to {recipient.username}!', 'new_balance': sender.coins})
    except json.JSONDecodeError: return JsonResponse({'status': 'error', 'message': 'Invalid request data format.'}, status=400)
    except IntegrityError:
        logger.error(f"IntegrityError during gift_coins from {sender.pk} to {recipient_identifier}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Database error during transaction. Please try again.'}, status=500)
    except Exception as e:
        logger.error(f"Unexpected error in gift_coins from {sender.pk} to {recipient_identifier}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)

@login_required
def mywallet(request):
    transaction_history = CoinTransaction.objects.filter(user=request.user).exclude(
        pack_name__in=['Monthly Premium Subscription', 'Annual Premium Subscription']
    ).select_related('sender', 'recipient').order_by('-transaction_date')

    context = _get_full_context(request)
    context['user'] = request.user
    context['gift_history'] = transaction_history
    return render(request, 'user/mywallet.html', context)


@login_required
def subscribe(request):
    context = _get_full_context(request)
    context['STRIPE_PUBLISHABLE_KEY'] = settings.STRIPE_PUBLISHABLE_KEY
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
    except Exception as e:
        logger.error(f"Error fetching or updating subscription for user {user.id}: {e}", exc_info=True)
        if user.subscription_type == 'PR':
            user.subscription_type = 'FR'
            user.save(update_fields=['subscription_type'])

    context = _get_full_context(request)
    context['subscription'] = subscription
    return render(request, 'user/managesubscription.html', context)

@login_required
@require_POST
@csrf_protect
@transaction.atomic # Ensure atomicity
def cancel_subscription(request):
    try:
        subscription = Subscription.objects.get(user=request.user, status='active')
        if not subscription.stripe_subscription_id:
            messages.error(request, "Cannot cancel: Stripe subscription ID is missing.")
            return redirect('AudioXApp:managesubscription')

        try:
            # Tell Stripe to cancel at the end of the current billing period
            stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=True
            )
            cancellation_successful_on_stripe = True
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error canceling subscription {subscription.stripe_subscription_id} for user {request.user.pk}: {e}", exc_info=True)
            messages.error(request, "Failed to schedule cancellation with the payment provider. Please contact support.")
            cancellation_successful_on_stripe = False
        
        if cancellation_successful_on_stripe:
            # Update local status to 'canceled' but user retains access until period end.
            # The actual 'expired' status and user downgrade will happen via webhook or a periodic task checking end_date.
            subscription.status = 'canceled' 
            subscription.save(update_fields=['status'])
            messages.success(request, "Your subscription has been scheduled for cancellation. You can continue using Premium features until the end of the current billing period.")
            
    except Subscription.DoesNotExist:
        messages.warning(request, "You do not have an active subscription to cancel.")
    except Exception as e:
        logger.error(f"Error canceling subscription for user {request.user.pk}: {e}", exc_info=True)
        messages.error(request, "An error occurred while canceling your subscription. Please contact support.")
    return redirect('AudioXApp:managesubscription')


@login_required
@require_POST
@csrf_protect
def create_checkout_session(request):
    try:
        data = json.loads(request.body)
        item_type = data.get('item_type')
        item_id = data.get('item_id') # For coins/subs, this is '250','500','monthly', etc. For audiobooks, it's the slug.

        stripe_price_ids = {
            'coins': {
                '250': settings.STRIPE_PRICE_ID_COINS_250,
                '500': settings.STRIPE_PRICE_ID_COINS_500,
                '1000': settings.STRIPE_PRICE_ID_COINS_1000,
            },
            'subscription': {
                'monthly': settings.STRIPE_PRICE_ID_SUB_MONTHLY,
                'annual': settings.STRIPE_PRICE_ID_SUB_ANNUAL,
            }
        }

        price_lookup = None
        mode = None
        success_url_path = None
        cancel_url_path = None
        line_items = []
        metadata = {
            'django_user_id': request.user.pk,
            'item_type': item_type,
            'item_id': item_id, # Store the original item_id (e.g. '250' coins or 'monthly' sub or audiobook_slug)
        }

        if item_type == 'subscription':
            price_lookup = stripe_price_ids.get(item_type, {}).get(item_id)
            if not price_lookup:
                return JsonResponse({'error': f'Pricing information not found for subscription plan ({item_id}).'}, status=400)
            mode = 'subscription'
            success_url_path = reverse('AudioXApp:managesubscription') + '?stripe_session_id={CHECKOUT_SESSION_ID}&status=success'
            cancel_url_path = reverse('AudioXApp:subscribe') + '?status=cancel'
            # metadata['plan'] = item_id # 'item_id' in metadata already covers this
            line_items = [{'price': price_lookup, 'quantity': 1}]

            try:
                # Check if user already has an active or canceled (pending expiry) subscription
                current_subscription = Subscription.objects.get(user=request.user)
                if current_subscription.status == 'active' or \
                   (current_subscription.status == 'canceled' and current_subscription.end_date and current_subscription.end_date > timezone.now()):
                    return JsonResponse({'status': 'already_subscribed', 'redirect_url': reverse('AudioXApp:managesubscription')})
            except Subscription.DoesNotExist:
                pass # Good, user can subscribe

        elif item_type == 'coins':
            price_lookup = stripe_price_ids.get(item_type, {}).get(item_id)
            if not price_lookup:
                return JsonResponse({'error': f'Pricing information not found for coin pack ({item_id}).'}, status=400)
            mode = 'payment'
            success_url_path = reverse('AudioXApp:mywallet') + '?stripe_session_id={CHECKOUT_SESSION_ID}&status=success'
            cancel_url_path = reverse('AudioXApp:buycoins') + '?status=cancel'
            # metadata['coins'] = item_id # 'item_id' in metadata already covers this
            line_items = [{'price': price_lookup, 'quantity': 1}]

        elif item_type == 'audiobook':
            audiobook_slug = item_id # item_id is the slug for audiobooks
            try:
                audiobook = Audiobook.objects.get(slug=audiobook_slug)
                if not audiobook.is_paid or audiobook.price <= 0:
                    return JsonResponse({'error': 'This audiobook is not available for purchase.'}, status=400)

                if request.user.has_purchased_audiobook(audiobook):
                    return JsonResponse({'status': 'already_purchased', 'message': 'You have already purchased this audiobook.'})

                mode = 'payment'
                success_url_path = reverse('AudioXApp:audiobook_detail', kwargs={'audiobook_slug': audiobook.slug}) + '?purchase=success&session_id={CHECKOUT_SESSION_ID}'
                cancel_url_path = reverse('AudioXApp:audiobook_detail', kwargs={'audiobook_slug': audiobook.slug}) + '?purchase=cancel'
                # metadata['audiobook_slug'] = audiobook_slug # 'item_id' in metadata already covers this

                try:
                    amount_in_paisa = int(audiobook.price * 100) # Stripe expects amount in the smallest currency unit
                except (TypeError, InvalidOperation):
                    logger.error(f"Invalid price format for audiobook {audiobook.slug}: {audiobook.price}", exc_info=True)
                    return JsonResponse({'error': 'Invalid price format for audiobook.'}, status=500)

                line_items = [{
                    'price_data': {
                        'currency': 'pkr', # Ensure this matches your Stripe account currency
                        'product_data': {
                            'name': f'Audiobook: {audiobook.title}',
                            'description': f'Purchase of audiobook "{audiobook.title}" by {audiobook.creator.creator_name if audiobook.creator else "Unknown Creator"}',
                            # 'images': [request.build_absolute_uri(audiobook.cover_image.url)] if audiobook.cover_image else [], # Optional: show image in checkout
                        },
                        'unit_amount': amount_in_paisa,
                    },
                    'quantity': 1,
                }]
            except Audiobook.DoesNotExist:
                return JsonResponse({'error': 'Audiobook not found.'}, status=404)
            except Exception as e:
                logger.error(f"Error retrieving audiobook details for checkout ({audiobook_slug}): {e}", exc_info=True)
                return JsonResponse({'error': 'Error retrieving audiobook details.'}, status=500)
        else:
            return JsonResponse({'error': 'Invalid item type specified.'}, status=400)

        protocol = 'https' if request.is_secure() else 'http'
        host = request.get_host()
        success_url = f"{protocol}://{host}{success_url_path}"
        cancel_url = f"{protocol}://{host}{cancel_url_path}"

        try:
            checkout_session_params = {
                'payment_method_types': ['card'],
                'line_items': line_items,
                'mode': mode,
                'success_url': success_url,
                'cancel_url': cancel_url,
                'metadata': metadata,
                'customer_email': request.user.email, # Pre-fill email
                'allow_promotion_codes': True, # Allow discount codes
            }
            # For subscriptions, if user has a Stripe customer ID, use it
            if mode == 'subscription':
                try:
                    # Check if user has an existing (even if not active) subscription object to get stripe_customer_id
                    existing_subscription_details = Subscription.objects.get(user=request.user)
                    if existing_subscription_details.stripe_customer_id:
                        checkout_session_params['customer'] = existing_subscription_details.stripe_customer_id
                except Subscription.DoesNotExist:
                    pass # No existing customer ID to reuse, Stripe will create one.
            
            checkout_session = stripe.checkout.Session.create(**checkout_session_params)
            return JsonResponse({'sessionId': checkout_session.id})
        
        except stripe.error.InvalidRequestError as e:
            logger.error(f"Stripe InvalidRequestError for user {request.user.pk}, item {item_type}/{item_id}: {e}", exc_info=True)
            error_message = str(e)
            # Check for common specific errors to provide better feedback
            if "You cannot use `line_items.price_data` in `subscription` mode" in error_message:
                 error_message = "Configuration error with subscription pricing. Please contact support."
            return JsonResponse({'error': f'Payment Provider Error: {error_message}'}, status=400)
        except Exception as e:
            logger.error(f"Error creating Stripe checkout session for user {request.user.pk}, item {item_type}/{item_id}: {e}", exc_info=True)
            return JsonResponse({'error': 'Could not initiate payment session.'}, status=500)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request data format.'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected server error in create_checkout_session for user {request.user.pk}: {e}", exc_info=True)
        return JsonResponse({'error': 'An unexpected server error occurred.'}, status=500)


# Ensure these imports are at the top of your AudioXApp/views/user_views.py file
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import datetime # Ensure this is imported
import logging
import stripe # Ensure stripe is imported
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.utils import timezone # Ensure timezone is imported
from django.db import transaction, IntegrityError
from django.db.models import F
# Ensure all your models used in the webhook are imported
from ..models import User, CoinTransaction, Subscription, Audiobook, AudiobookPurchase, CreatorEarning, Creator

# stripe.api_key should be set (as in your existing code, typically after settings are loaded)
# Ensure logger is defined in your views.py, e.g.:
# logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)

    if not endpoint_secret:
        logger.critical("CRITICAL: STRIPE_WEBHOOK_SECRET is not configured in Django settings.")
        # In a production environment, you might want to avoid returning detailed error messages.
        return JsonResponse({'error': 'Webhook secret not configured on server.'}, status=500)
    
    event = None
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError as e: # Invalid payload
        logger.error(f"Stripe webhook ValueError: Invalid payload. {e}", exc_info=True)
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError as e: # Invalid signature
        logger.error(f"Stripe webhook SignatureVerificationError: Invalid signature. {e}", exc_info=True)
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    except Exception as e: # Catch any other exception during event construction
        logger.error(f"Stripe webhook error during event construction: {e}", exc_info=True)
        return JsonResponse({'error': 'Webhook processing error'}, status=500)

    # Log the received event type and ID for easier debugging
    logger.info(f"Stripe webhook received event: {event.type}, ID: {event.id}")

    # --- Handle checkout.session.completed ---
    if event.type == 'checkout.session.completed':
        session = event.data.object
        metadata = session.get('metadata', {})
        user_id = metadata.get('django_user_id')
        item_type = metadata.get('item_type')
        item_id = metadata.get('item_id') # e.g. '250' coins, 'monthly' sub, or audiobook_slug

        if not user_id or not item_type or not item_id:
            logger.error(f"Stripe webhook 'checkout.session.completed' (ID: {session.id}) missing essential metadata. UserID: {user_id}, ItemType: {item_type}, ItemID: {item_id}")
            # Return 200 to Stripe to acknowledge receipt and prevent retries for this specific error.
            return JsonResponse({'status': 'error', 'message': 'Missing essential metadata.'}, status=200)

        if session.payment_status == 'paid':
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                logger.error(f"Stripe webhook 'checkout.session.completed' (ID: {session.id}): User with ID {user_id} not found.")
                return JsonResponse({'status': 'error', 'message': 'User not found.'}, status=200)

            # Idempotency: Check if this specific fulfillment has already occurred
            idempotency_key_description = f"stripe_checkout_session_{session.id}"
            stripe_subscription_id_from_session = session.get('subscription') # Used for subscription type

            # More specific idempotency checks
            already_processed = False
            if item_type == 'subscription':
                if stripe_subscription_id_from_session and Subscription.objects.filter(stripe_subscription_id=stripe_subscription_id_from_session).exists():
                    already_processed = True
                    logger.info(f"Webhook 'checkout.session.completed' (ID: {session.id}): Subscription {stripe_subscription_id_from_session} already exists for user {user_id}.")
            elif item_type == 'coins':
                if CoinTransaction.objects.filter(description=idempotency_key_description).exists():
                    already_processed = True
                    logger.info(f"Webhook 'checkout.session.completed' (ID: {session.id}): Coin transaction {idempotency_key_description} already exists for user {user_id}.")
            elif item_type == 'audiobook':
                if AudiobookPurchase.objects.filter(stripe_checkout_session_id=session.id).exists():
                    already_processed = True
                    logger.info(f"Webhook 'checkout.session.completed' (ID: {session.id}): Audiobook purchase {session.id} already exists for user {user_id}.")
            
            if already_processed:
                return JsonResponse({'status': 'already_processed'})

            payment_intent_id = session.get('payment_intent')
            payment_brand, payment_last4 = None, None
            if payment_intent_id:
                try:
                    payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                    if payment_intent.payment_method:
                        payment_method_id = payment_intent.payment_method
                        # payment_method can be an ID string or an expanded PaymentMethod object
                        if isinstance(payment_method_id, str):
                            payment_method_obj = stripe.PaymentMethod.retrieve(payment_method_id)
                            if payment_method_obj.card:
                                payment_brand = payment_method_obj.card.brand
                                payment_last4 = payment_method_obj.card.last4
                        # If it's already an expanded object (less common for session.payment_intent.payment_method)
                        # elif hasattr(payment_method_id, 'card') and payment_method_id.card:
                        #     payment_brand = payment_method_id.card.brand
                        #     payment_last4 = payment_method_id.card.last4
                except stripe.error.StripeError as e:
                    logger.warning(f"Could not retrieve payment method details for PI {payment_intent_id} from session {session.id}: {e}")
            
            try:
                with transaction.atomic():
                    user_locked = User.objects.select_for_update().get(pk=user.pk) # Lock user row

                    if item_type == 'subscription' and item_id in ['monthly', 'annual']:
                        plan_type = item_id
                        
                        # Use getattr for safer access to settings
                        sub_prices_settings = getattr(settings, 'SUBSCRIPTION_PRICES', {})
                        sub_durations_settings = getattr(settings, 'SUBSCRIPTION_DURATIONS', {})

                        # Fallback prices/durations if not in settings (though they should be)
                        default_price_str = sub_prices_settings.get(plan_type, '350.00' if plan_type == 'monthly' else '3500.00')
                        duration_days = sub_durations_settings.get(plan_type, 30 if plan_type == 'monthly' else 365)
                        pack_name = "Monthly Premium Subscription" if plan_type == 'monthly' else "Annual Premium Subscription"
                        
                        price = Decimal('0.00') # Initialize as Decimal
                        try:
                            # Prefer amount_total from the session for accuracy
                            amount_total_from_stripe = session.get('amount_total') # In smallest currency unit (e.g., paisa)
                            if amount_total_from_stripe is not None:
                                price = (Decimal(amount_total_from_stripe) / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                            else:
                                logger.warning(f"Stripe session {session.id} for subscription missing amount_total. Falling back to settings price: {default_price_str}")
                                price = Decimal(default_price_str) # Fallback to settings price
                        except (InvalidOperation, TypeError) as e: # Catch Decimal conversion errors
                            logger.error(f"Invalid price format for subscription '{plan_type}'. Settings value: '{default_price_str}'. Error: {e}. Using 0.00.")
                        
                        end_date = timezone.now() + timezone.timedelta(days=duration_days)
                        
                        # stripe_subscription_id_from_session was fetched earlier
                        stripe_customer_id_from_session = session.get('customer')

                        if not stripe_subscription_id_from_session: # Should have been caught by idempotency if existing
                            logger.error(f"Stripe webhook: Critical - Missing stripe_subscription_id in session for user {user_id}, session {session.id} (item_type: subscription)")
                            return JsonResponse({'status': 'error', 'message': 'Internal error: Missing Stripe subscription ID.'}, status=200)

                        # Use update_or_create for the Subscription object
                        sub, created = Subscription.objects.update_or_create(
                            user=user_locked, # Assumes one active subscription object per user; if multiple possible, key on stripe_subscription_id
                            defaults={
                                'plan': plan_type,
                                'start_date': timezone.now(), # Or more precise from Stripe if available
                                'end_date': end_date, # Or more precise from Stripe subscription object if available
                                'status': 'active',
                                'stripe_subscription_id': stripe_subscription_id_from_session,
                                'stripe_customer_id': stripe_customer_id_from_session,
                                'stripe_payment_method_brand': payment_brand,
                                'stripe_payment_method_last4': payment_last4,
                            }
                        )
                        # If the subscription record existed but had a different stripe_subscription_id (e.g., user re-subscribed after a lapse)
                        if not created and sub.stripe_subscription_id != stripe_subscription_id_from_session:
                             sub.stripe_subscription_id = stripe_subscription_id_from_session
                             sub.plan = plan_type # Update plan if it changed
                             sub.start_date = timezone.now()
                             sub.end_date = end_date
                             sub.status = 'active'
                             sub.stripe_customer_id = stripe_customer_id_from_session
                             # Update payment method details if they changed
                             sub.stripe_payment_method_brand = payment_brand
                             sub.stripe_payment_method_last4 = payment_last4
                             sub.save()
                        
                        if user_locked.subscription_type != 'PR':
                            user_locked.subscription_type = 'PR'
                            user_locked.save(update_fields=['subscription_type'])
                        
                        # Log the subscription purchase in CoinTransaction for history, using update_or_create for idempotency
                        CoinTransaction.objects.update_or_create(
                            description=idempotency_key_description, # Use session ID for idempotency
                            defaults={
                                'user': user_locked, 
                                'transaction_type': 'purchase', 
                                'amount': 0, # No coins granted for subscription itself
                                'status': 'completed', 
                                'pack_name': pack_name, 
                                'price': price
                            }
                        )
                        logger.info(f"Subscription '{plan_type}' (Stripe ID: {stripe_subscription_id_from_session}) processed for user {user_id} via Stripe session {session.id}.")

                    elif item_type == 'coins':
                        coins_pack_id_str = item_id
                        try:
                            coins_to_grant = int(coins_pack_id_str)
                            if coins_to_grant <= 0: raise ValueError("Coins must be positive.")
                            
                            coin_prices_settings = getattr(settings, 'COIN_PACK_PRICES', {})
                            default_price_str = coin_prices_settings.get(coins_pack_id_str)
                            pack_name = f"{coins_to_grant} Coins Pack" # Generic default

                            if default_price_str is None: # Price not found in settings
                                logger.error(f"Price not found in settings.COIN_PACK_PRICES for coin pack ID '{coins_pack_id_str}'. Using fallback pack name.")
                                default_price_str = coins_pack_id_str + ".00" # Fallback as per original code's implicit structure
                                # Determine pack_name based on common values if price not in settings
                                if coins_to_grant == 250: pack_name = "Starter Pack (250 Coins)"
                                elif coins_to_grant == 500: pack_name = "Value Pack (500 Coins)"
                                elif coins_to_grant == 1000: pack_name = "Pro Pack (1000 Coins)"
                                else: pack_name = f"Unknown Pack ({coins_to_grant} Coins)" # Or "Custom Pack"
                            else: # Price found in settings, use more specific names
                                if coins_to_grant == 250: pack_name = "Starter Pack (250 Coins)"
                                elif coins_to_grant == 500: pack_name = "Value Pack (500 Coins)"
                                elif coins_to_grant == 1000: pack_name = "Pro Pack (1000 Coins)"
                                # else pack_name remains the generic one if coins_to_grant doesn't match common packs

                            price_paid = Decimal('0.00') # Initialize
                            try:
                                amount_total_from_stripe = session.get('amount_total')
                                if amount_total_from_stripe is not None:
                                    price_paid = (Decimal(amount_total_from_stripe) / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                                else:
                                    logger.warning(f"Stripe session {session.id} for coins missing amount_total. Falling back to settings price: {default_price_str}")
                                    price_paid = Decimal(default_price_str)
                            except (InvalidOperation, TypeError) as e:
                                logger.error(f"Invalid price format for coins '{coins_pack_id_str}'. Settings value: '{default_price_str}'. Error: {e}. Using 0.00.")

                            user_locked.coins = F('coins') + coins_to_grant
                            user_locked.save(update_fields=['coins'])
                            user_locked.refresh_from_db(fields=['coins']) # Get the updated coin value

                            CoinTransaction.objects.update_or_create(
                                description=idempotency_key_description, # Use session ID for idempotency
                                defaults={
                                    'user': user_locked, 
                                    'transaction_type': 'purchase', 
                                    'amount': coins_to_grant,
                                    'status': 'completed', 
                                    'pack_name': pack_name, 
                                    'price': price_paid
                                }
                            )
                            logger.info(f"{coins_to_grant} coins granted to user {user_id} (New Balance: {user_locked.coins}) via Stripe session {session.id}.")
                        except (ValueError, TypeError) as e: # Catches int() conversion error or if coins_to_grant <= 0
                            logger.error(f"Invalid coin data in webhook metadata for user {user_id}, session {session.id}: '{coins_pack_id_str}'. Error: {e}", exc_info=True)
                            return JsonResponse({'status': 'error', 'message': 'Invalid coin data in metadata.'}, status=200)
                    
                    elif item_type == 'audiobook':
                        audiobook_slug = item_id
                        try:
                            audiobook = Audiobook.objects.select_related('creator').get(slug=audiobook_slug)
                            creator = audiobook.creator # From related_name
                            if not creator: # This should ideally not happen if creator is mandatory on Audiobook
                                logger.error(f"Audiobook {audiobook_slug} is missing a creator. Cannot process purchase for user {user_id}, session {session.id}.")
                                return JsonResponse({'status': 'error', 'message': 'Audiobook creator not found.'}, status=500) # 500 as it's a data integrity issue

                            # Idempotency for AudiobookPurchase (already checked outside transaction, but as a safeguard)
                            if AudiobookPurchase.objects.filter(stripe_checkout_session_id=session.id).exists():
                                logger.info(f"Audiobook {audiobook_slug} purchase via session {session.id} already recorded (checked inside transaction).")
                                return JsonResponse({'status': 'already_processed'})
                                
                            amount_paid_paisa = session.amount_total # This is from Stripe checkout session (in smallest currency unit)
                            amount_paid_pkr = (Decimal(amount_paid_paisa) / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                            
                            platform_fee_percentage_str = getattr(settings, 'PLATFORM_FEE_PERCENTAGE_AUDIOBOOK', '10.00')
                            try:
                                platform_fee_percentage = Decimal(platform_fee_percentage_str)
                            except InvalidOperation:
                                logger.error(f"Invalid decimal for PLATFORM_FEE_PERCENTAGE_AUDIOBOOK in settings. Using 10.00. Value was: {platform_fee_percentage_str}")
                                platform_fee_percentage = Decimal('10.00')
                                
                            platform_fee_amount = (amount_paid_pkr * platform_fee_percentage / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                            creator_share_amount = amount_paid_pkr - platform_fee_amount

                            purchase = AudiobookPurchase.objects.create(
                                user=user_locked, audiobook=audiobook, amount_paid=amount_paid_pkr,
                                platform_fee_percentage=platform_fee_percentage,
                                platform_fee_amount=platform_fee_amount,
                                creator_share_amount=creator_share_amount,
                                stripe_checkout_session_id=session.id, # For idempotency
                                stripe_payment_intent_id=payment_intent_id
                            )
                            
                            # Update Creator's earnings (lock creator row)
                            creator_locked = Creator.objects.select_for_update().get(pk=creator.pk)
                            creator_locked.total_earning = F('total_earning') + amount_paid_pkr # Gross earning
                            creator_locked.available_balance = F('available_balance') + creator_share_amount # Net earning
                            creator_locked.save(update_fields=['total_earning', 'available_balance'])
                            
                            # Log detailed earning
                            CreatorEarning.objects.create(
                                creator=creator_locked, audiobook=audiobook, purchase=purchase,
                                amount_earned=creator_share_amount, earning_type='sale',
                                notes=f"Sale via Stripe Checkout Session: {session.id}",
                                audiobook_title_at_transaction=audiobook.title # Store historical title
                            )

                            # Update Audiobook's sales analytics (lock audiobook row)
                            audiobook_locked = Audiobook.objects.select_for_update().get(pk=audiobook.pk)
                            audiobook_locked.total_sales = F('total_sales') + 1
                            audiobook_locked.total_revenue_generated = F('total_revenue_generated') + amount_paid_pkr
                            audiobook_locked.save(update_fields=['total_sales', 'total_revenue_generated'])
                            
                            logger.info(f"Audiobook '{audiobook_slug}' purchased by user {user_id}. Creator {creator.creator_unique_name} earned {creator_share_amount}. Session: {session.id}")

                        except Audiobook.DoesNotExist:
                            logger.error(f"Audiobook with slug '{audiobook_slug}' not found for purchase by user {user_id}, session {session.id}.")
                            return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=200)
                        except Creator.DoesNotExist: # Should not happen if audiobook.creator is enforced
                            logger.error(f"Creator not found for audiobook '{audiobook_slug}'. User {user_id}, session {session.id}.")
                            return JsonResponse({'status': 'error', 'message': 'Creator data error.'}, status=500) # Server data issue
                        except Exception as fulfill_error: # Catch any other error during audiobook fulfillment
                            logger.error(f"Error fulfilling audiobook purchase for user {user_id}, audiobook slug {audiobook_slug}, session {session.id}: {fulfill_error}", exc_info=True)
                            return JsonResponse({'error': 'Internal server error during audiobook fulfillment.'}, status=500) # status 500 to retry if transient
                    else:
                        logger.warning(f"Stripe webhook 'checkout.session.completed' (ID: {session.id}): Unknown item_type '{item_type}' for user {user_id}.")
                        return JsonResponse({'status': 'error', 'message': 'Unknown item type in metadata.'}, status=200)
            
            except IntegrityError as e: # Catch potential race conditions if select_for_update wasn't enough or unique constraints hit
                logger.error(f"Stripe webhook 'checkout.session.completed' (ID: {session.id}): IntegrityError during fulfillment for user {user_id}. {e}", exc_info=True)
                # 200 if it might be an idempotency issue that was already handled or a unique constraint violation that shouldn't be retried by Stripe.
                return JsonResponse({'status': 'error', 'message': 'Database conflict during fulfillment.'}, status=200) 
            except Exception as e: # Catch-all for other errors within the transaction
                logger.error(f"Stripe webhook 'checkout.session.completed' (ID: {session.id}): General error during fulfillment for user {user_id}. {e}", exc_info=True)
                return JsonResponse({'error': 'Internal server error during fulfillment.'}, status=500) # 500 to encourage Stripe retry
        else: # Payment not 'paid'
            logger.info(f"Stripe webhook 'checkout.session.completed' (ID: {session.id}): Payment not successful (status: {session.payment_status}). No fulfillment action taken for user {user_id}.")

    # --- Handle customer.subscription.updated ---
    elif event.type == 'customer.subscription.updated':
        subscription_data = event.data.object
        stripe_sub_id = subscription_data.id
        try:
            with transaction.atomic():
                # Use select_for_update to lock the row during the update
                local_sub = Subscription.objects.select_for_update().get(stripe_subscription_id=stripe_sub_id)
                
                stripe_status = subscription_data.status
                original_local_status = local_sub.status # Store original status for comparison
                
                # Map Stripe status to local status
                if stripe_status == 'active': local_sub.status = 'active'
                elif stripe_status == 'canceled': local_sub.status = 'canceled' # Will expire at period end
                elif stripe_status in ['past_due', 'unpaid']: local_sub.status = 'past_due'
                # For 'trialing', 'incomplete', 'incomplete_expired', map to a sensible local status.
                # 'incomplete_expired' often means it's effectively 'expired'.
                # 'trialing' could be 'active' or a specific 'trialing' status if you have one.
                elif stripe_status in ['trialing']: local_sub.status = 'active' # Assuming trial is a form of active
                else: local_sub.status = 'expired' # Default for others like incomplete_expired

                # Update end_date from Stripe's current_period_end
                if subscription_data.current_period_end:
                    local_sub.end_date = timezone.make_aware(datetime.datetime.fromtimestamp(subscription_data.current_period_end))
                else: # Should ideally not happen for an active subscription
                    local_sub.end_date = None 
                    logger.warning(f"Stripe subscription {stripe_sub_id} for user {local_sub.user.id} has no current_period_end in 'updated' event.")

                # If Stripe says cancel_at_period_end is true AND the period has now ended, mark as expired.
                if subscription_data.cancel_at_period_end and local_sub.end_date and timezone.now() >= local_sub.end_date:
                    local_sub.status = 'expired'
                
                # Only save if there are actual changes to relevant fields
                fields_to_save = []
                if local_sub.status != original_local_status:
                    fields_to_save.append('status')
                
                # To check if end_date changed, you might need to compare with the DB value before this instance was modified
                # This is a bit tricky without fetching the object again. A simpler approach:
                current_db_end_date = Subscription.objects.get(pk=local_sub.pk).end_date # Fetch current DB state
                if local_sub.end_date != current_db_end_date :
                    fields_to_save.append('end_date')

                if fields_to_save:
                    local_sub.save(update_fields=fields_to_save)

                # Downgrade user if subscription becomes expired
                if local_sub.status == 'expired' and local_sub.user.subscription_type == 'PR':
                    user_locked = User.objects.select_for_update().get(pk=local_sub.user.pk)
                    user_locked.subscription_type = 'FR'
                    user_locked.save(update_fields=['subscription_type'])
                    logger.info(f"User {local_sub.user.id} (Stripe Sub ID: {stripe_sub_id}) downgraded to Free due to subscription status changing to '{local_sub.status}'.")
                
                logger.info(f"Subscription {stripe_sub_id} updated for user {local_sub.user.id}. New local status: {local_sub.status}, End date: {local_sub.end_date}. Stripe reported status: {stripe_status}")

        except Subscription.DoesNotExist:
            logger.warning(f"Received 'customer.subscription.updated' for unknown Stripe subscription ID: {stripe_sub_id}")
        except Exception as e:
            logger.error(f"Error processing 'customer.subscription.updated' for {stripe_sub_id}: {e}", exc_info=True)
            return JsonResponse({'error': 'Internal server error processing subscription update.'}, status=500)


    # --- Handle customer.subscription.deleted ---
    # This event occurs when a subscription is actually removed/canceled (immediately or at period end if it was scheduled).
    elif event.type == 'customer.subscription.deleted':
        subscription_data = event.data.object
        stripe_sub_id = subscription_data.id
        try:
            with transaction.atomic():
                local_sub = Subscription.objects.select_for_update().get(stripe_subscription_id=stripe_sub_id)
                local_sub.status = 'expired' # Or 'canceled', but 'deleted' implies it's fully gone
                local_sub.end_date = timezone.now() # Mark as ended now as it's deleted from Stripe
                local_sub.save(update_fields=['status', 'end_date'])

                if local_sub.user.subscription_type == 'PR':
                    user_locked = User.objects.select_for_update().get(pk=local_sub.user.pk)
                    user_locked.subscription_type = 'FR'
                    user_locked.save(update_fields=['subscription_type'])
                    logger.info(f"User {local_sub.user.id} (Stripe Sub ID: {stripe_sub_id}) downgraded to Free due to deleted subscription.")
                logger.info(f"Subscription {stripe_sub_id} marked as deleted/expired for user {local_sub.user.id}.")
        except Subscription.DoesNotExist:
            logger.warning(f"Received 'customer.subscription.deleted' for unknown Stripe subscription ID: {stripe_sub_id}")
        except Exception as e:
            logger.error(f"Error processing 'customer.subscription.deleted' for {stripe_sub_id}: {e}", exc_info=True)
            return JsonResponse({'error': 'Internal server error processing subscription deletion.'}, status=500)

    # --- Handle invoice.paid (primarily for renewals, but also initial subscription payment) ---
    elif event.type == 'invoice.paid':
        invoice = event.data.object
        stripe_subscription_id = getattr(invoice, 'subscription', None) # Safely get subscription ID
        
        if stripe_subscription_id and invoice.billing_reason == 'subscription_cycle': # This is a renewal payment
            try:
                with transaction.atomic():
                    local_sub = Subscription.objects.select_for_update().get(stripe_subscription_id=stripe_subscription_id)
                    user_locked = User.objects.select_for_update().get(pk=local_sub.user.pk)

                    update_fields = ['status'] # Always update status on renewal
                    local_sub.status = 'active' # Ensure it's active on renewal
                    
                    # Update subscription period from the invoice
                    if invoice.period_start:
                        new_start_date = timezone.make_aware(datetime.datetime.fromtimestamp(invoice.period_start))
                        if local_sub.start_date != new_start_date: # Only update if changed
                            local_sub.start_date = new_start_date
                            update_fields.append('start_date')
                    if invoice.period_end:
                        new_end_date = timezone.make_aware(datetime.datetime.fromtimestamp(invoice.period_end))
                        if local_sub.end_date != new_end_date: # Only update if changed
                            local_sub.end_date = new_end_date
                            update_fields.append('end_date')
                    
                    # Update payment method details if available and changed on the charge associated with the invoice
                    charge_id = getattr(invoice, 'charge', None)
                    if charge_id:
                        try:
                            charge = stripe.Charge.retrieve(charge_id)
                            if charge.payment_method_details and charge.payment_method_details.card:
                                if local_sub.stripe_payment_method_brand != charge.payment_method_details.card.brand:
                                    local_sub.stripe_payment_method_brand = charge.payment_method_details.card.brand
                                    update_fields.append('stripe_payment_method_brand')
                                if local_sub.stripe_payment_method_last4 != charge.payment_method_details.card.last4:
                                    local_sub.stripe_payment_method_last4 = charge.payment_method_details.card.last4
                                    update_fields.append('stripe_payment_method_last4')
                        except stripe.error.StripeError as e:
                            logger.warning(f"Could not retrieve charge/payment method details for invoice {invoice.id} (renewal): {e}")
                    
                    if len(update_fields) > 0:
                        local_sub.save(update_fields=list(set(update_fields))) # Use set to avoid duplicate field names if any logic error

                    if user_locked.subscription_type != 'PR':
                        user_locked.subscription_type = 'PR'
                        user_locked.save(update_fields=['subscription_type'])
                    
                    # Log renewal in CoinTransaction for history, using update_or_create for idempotency
                    pack_name = "Monthly Premium Renewal" if local_sub.plan == 'monthly' else "Annual Premium Renewal"
                    price = Decimal(invoice.amount_paid / 100.0) # amount_paid is in cents
                    idempotency_key_description = f"stripe_invoice_{invoice.id}" # Unique key for this invoice payment
                    CoinTransaction.objects.update_or_create(
                        description=idempotency_key_description,
                        defaults={
                            'user': user_locked, 
                            'transaction_type': 'purchase', 
                            'amount': 0, # No coins for renewal itself
                            'status': 'completed',
                            'pack_name': pack_name, 
                            'price': price
                        }
                    )
                    logger.info(f"Subscription {stripe_subscription_id} renewed for user {user_locked.pk}. Invoice: {invoice.id}. New end date: {local_sub.end_date}.")
            except Subscription.DoesNotExist:
                logger.warning(f"Received 'invoice.paid' for renewal (Invoice: {invoice.id}) of unknown Stripe subscription ID: {stripe_subscription_id}")
            except Exception as e: # Catch any other error during renewal processing
                logger.error(f"Error processing 'invoice.paid' renewal for {stripe_subscription_id} (Invoice ID: {invoice.id}): {e}", exc_info=True)
                # Return 500 to potentially retry if it's a transient issue
                return JsonResponse({'error': 'Internal server error during invoice.paid renewal processing.'}, status=500)
        elif invoice.billing_reason == 'subscription_create':
             # This invoice is for the initial creation of the subscription.
             # The main fulfillment logic (creating Subscription object, etc.) is handled by 'checkout.session.completed'.
             # We can log this event for completeness or if specific actions are needed for first invoices.
             logger.info(f"Received 'invoice.paid' (ID: {invoice.id}) for initial subscription creation. Fulfillment handled by 'checkout.session.completed'. Stripe Sub ID: {stripe_subscription_id or 'N/A'}")
        else: # Invoice paid for other reasons (e.g., one-time payment, not a subscription cycle)
            logger.info(f"Received 'invoice.paid' (ID: {invoice.id}) for reason: '{invoice.billing_reason}'. Not a subscription renewal. Stripe Subscription ID: {stripe_subscription_id if stripe_subscription_id else 'N/A'}. Amount: {invoice.amount_paid/100.0} {invoice.currency.upper()}.")
            # If you use Invoices for one-time payments for audiobooks (not via Checkout), you might add fulfillment logic here.

    # --- Handle invoice.payment_failed ---
    elif event.type == 'invoice.payment_failed':
        invoice = event.data.object
        stripe_subscription_id = getattr(invoice, 'subscription', None)
        if stripe_subscription_id: # If the failed invoice is related to a subscription
            try:
                with transaction.atomic():
                    local_sub = Subscription.objects.select_for_update().get(stripe_subscription_id=stripe_subscription_id)
                    if local_sub.status != 'past_due': # Avoid redundant saves if already past_due
                        local_sub.status = 'past_due' # Or other appropriate status based on Stripe's dunning
                        local_sub.save(update_fields=['status'])
                    # Log details about the failed payment
                    logger.info(f"Subscription {stripe_subscription_id} payment failed for user {local_sub.user.id}. Invoice: {invoice.id}. Status set to 'past_due'. Next payment attempt (if any): {invoice.next_payment_attempt}")
            except Subscription.DoesNotExist:
                # This might happen if the payment failure is for a new subscription attempt from checkout that wasn't yet saved locally,
                # or if the subscription was deleted locally for some reason.
                logger.warning(f"Received 'invoice.payment_failed' for Stripe subscription ID: {stripe_subscription_id} (Invoice: {invoice.id}) which is not a known local subscription.")
            except Exception as e:
                logger.error(f"Error processing 'invoice.payment_failed' for subscription {stripe_subscription_id} (Invoice: {invoice.id}): {e}", exc_info=True)
                return JsonResponse({'error': 'Internal server error processing payment failure.'}, status=500)
        else: # Payment failure for an invoice not directly tied to a subscription object (e.g., one-time payment via invoice)
            logger.warning(f"Received 'invoice.payment_failed' for invoice ID {invoice.id} (not linked to a subscription). Customer: {invoice.customer}, Amount Due: {invoice.amount_due/100.0} {invoice.currency.upper()}, Billing Reason: {invoice.billing_reason}")
    
    # Add handlers for other events as needed, e.g.:
    # elif event.type == 'customer.subscription.trial_will_end':
    #     # Send a reminder to the user
    #     pass

    else:
        logger.debug(f"Stripe webhook: Unhandled or non-critical event type '{event.type}' (ID: {event.id})")

    return JsonResponse({'status': 'success'})



@login_required
def billing_history(request):
    user = request.user
    billing_items_list = []

    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    start_date = None
    end_date = None

    if start_date_str:
        try:
            start_datetime_naive = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
            if settings.USE_TZ:
                start_date = timezone.make_aware(start_datetime_naive, timezone.get_default_timezone())
            else:
                start_date = start_datetime_naive
        except ValueError:
            messages.error(request, "Invalid start date format. Please use YYYY-MM-DD.")
            pass 
            
    if end_date_str:
        try:
            end_datetime_naive = datetime.datetime.strptime(end_date_str, '%Y-%m-%d')
            end_datetime_naive_eod = datetime.datetime.combine(end_datetime_naive, datetime.datetime.max.time())
            if settings.USE_TZ:
                end_date = timezone.make_aware(end_datetime_naive_eod, timezone.get_default_timezone())
            else:
                end_date = end_datetime_naive_eod
        except ValueError:
            messages.error(request, "Invalid end date format. Please use YYYY-MM-DD.")
            pass

    # 1. Fetch Audiobook Purchases
    audiobook_purchases_qs = AudiobookPurchase.objects.filter(user=user).select_related('audiobook', 'audiobook__creator')
    if start_date: audiobook_purchases_qs = audiobook_purchases_qs.filter(purchase_date__gte=start_date)
    if end_date: audiobook_purchases_qs = audiobook_purchases_qs.filter(purchase_date__lte=end_date)
    
    for purchase in audiobook_purchases_qs.order_by('-purchase_date'):
        billing_items_list.append({
            'type': 'Audiobook Purchase',
            'description': f"'{purchase.audiobook.title}' by {purchase.audiobook.creator.creator_name if purchase.audiobook.creator else 'N/A'}",
            'date': purchase.purchase_date,
            'amount_pkr': purchase.amount_paid,
            'details_url': reverse('AudioXApp:audiobook_detail', kwargs={'audiobook_slug': purchase.audiobook.slug}),
            'status': 'Completed', 
            'status_class': 'bg-green-100 text-green-700'
        })

    # 2. Fetch Subscription Payments and Coin Purchases (from CoinTransaction)
    # We can combine these and then differentiate by pack_name or amount
    all_purchases_qs = CoinTransaction.objects.filter(user=user, transaction_type='purchase')
    if start_date: all_purchases_qs = all_purchases_qs.filter(transaction_date__gte=start_date)
    if end_date: all_purchases_qs = all_purchases_qs.filter(transaction_date__lte=end_date)

    subscription_pack_names_lower = [name.lower() for name in ['Monthly Premium Subscription', 'Annual Premium Subscription', 'Monthly Premium Renewal', 'Annual Premium Renewal']]

    for txn in all_purchases_qs.order_by('-transaction_date'):
        status_display = txn.get_status_display()
        status_class = 'bg-gray-100 text-gray-700' # Default
        if txn.status == 'completed': status_class = 'bg-green-100 text-green-700'
        elif txn.status == 'pending': status_class = 'bg-yellow-100 text-yellow-700'
        elif txn.status in ['failed', 'rejected']: status_class = 'bg-red-100 text-red-700'

        item_type_display = 'Coin Purchase'
        details_url = reverse('AudioXApp:buycoins')
        description = txn.pack_name or f"{txn.amount} Coins"
        coins_received = txn.amount if txn.amount > 0 else None # Show coins only if it's a coin pack

        if txn.pack_name and txn.pack_name.lower() in subscription_pack_names_lower:
            item_type_display = 'Subscription'
            details_url = reverse('AudioXApp:managesubscription')
            coins_received = None # No coins for subscriptions

        billing_items_list.append({
            'type': item_type_display,
            'description': description,
            'date': txn.transaction_date,
            'amount_pkr': txn.price,
            'coins_received': coins_received,
            'details_url': details_url,
            'status': status_display,
            'status_class': status_class
        })
    
    # Sort all items by date, descending
    billing_items_list.sort(key=lambda x: x['date'], reverse=True)

    context = _get_full_context(request)
    context['billing_items'] = billing_items_list
    context['start_date_str'] = start_date_str 
    context['end_date_str'] = end_date_str
    
    return render(request, 'user/billing_history.html', context)

@login_required
def my_downloads(request):
    context = _get_full_context(request)
    context['downloaded_audiobooks'] = [] 
    messages.info(request, "My Downloads page is under construction.") 
    return redirect('AudioXApp:myprofile') 

@login_required
def my_library(request):
    context = _get_full_context(request)
    # Fetch audiobooks the user has purchased
    purchased_audiobooks = Audiobook.objects.filter(purchases__user=request.user).distinct().prefetch_related(
        Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order'))
    ).order_by('-purchases__purchase_date') # Order by most recent purchase

    context['library_audiobooks'] = purchased_audiobooks
    # messages.info(request, "My Library page is under construction.") 
    # return redirect('AudioXApp:myprofile') 
    return render(request, 'user/my_library.html', context)


@login_required
@csrf_protect # Ensures CSRF for POST, but GET is also protected by @login_required
def complete_profile(request):
    user = request.user
    context = _get_full_context(request)

    # Determine the intended 'next' URL
    # Priority: 1. 'next' query param, 2. Session variable, 3. Fallback to home
    next_destination_after_save = request.GET.get('next')
    if not next_destination_after_save:
        next_destination_after_save = request.session.get('next_url_after_profile_completion')
        if next_destination_after_save and not next_destination_after_save.startswith('/'):
            try: # Ensure it's a path if it was a name
                next_destination_after_save = reverse(next_destination_after_save)
            except: # NoReverseMatch
                next_destination_after_save = reverse('AudioXApp:home') # Fallback
    if not next_destination_after_save: # If still nothing (e.g. session var was empty/invalid)
        next_destination_after_save = reverse('AudioXApp:home')


    # Check if the profile is already complete based on required fields
    # This definition of "complete" should match the one that triggers the middleware redirect
    profile_is_complete = bool(
        user.full_name and user.full_name.strip() and
        user.phone_number and user.phone_number.startswith('+92') and len(user.phone_number) == 13 and user.phone_number[3:].isdigit()
    )

    if profile_is_complete and request.method == 'GET': # Only redirect on GET if already complete
        if 'profile_incomplete' in request.session: del request.session['profile_incomplete']
        if 'next_url_after_profile_completion' in request.session: del request.session['next_url_after_profile_completion']
        messages.info(request, "Your profile is already complete.")
        return redirect(next_destination_after_save)

    if request.method == 'POST':
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                full_name = data.get('full_name', '').strip()
                phone_number_full = data.get('phone_number', '').strip() # Expects full +92... number

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

                user.full_name = full_name
                user.phone_number = phone_number_full
                user.save(update_fields=['full_name', 'phone_number'])

                if 'profile_incomplete' in request.session: del request.session['profile_incomplete']
                if 'next_url_after_profile_completion' in request.session: del request.session['next_url_after_profile_completion']
                
                messages.success(request, "Your profile has been updated successfully!") # For the next page
                return JsonResponse({
                    'status': 'success',
                    'message': 'Your profile has been updated successfully!',
                    'redirect_url': next_destination_after_save
                })

            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
            except Exception as e:
                logger.error(f"Error in complete_profile POST for user {user.pk}: {e}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid request content type. Expected application/json.'}, status=415)

    # For GET request:
    # Pre-fill form with existing data if any
    user_phone_number_only = ''
    if user.phone_number and user.phone_number.startswith('+92') and len(user.phone_number) == 13:
        user_phone_number_only = user.phone_number[3:] # For display in the 10-digit input part

    context['user_phone_number_only'] = user_phone_number_only # For the input that takes only 10 digits
    context['user_full_phone_number'] = user.phone_number # For the hidden input or direct use if form structure changes
    context['next_destination_on_success'] = next_destination_after_save # Pass to template if needed for JS redirect or hidden field

    return render(request, 'auth/complete_profile.html', context)
