# AudioXApp/views/user_views.py

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import datetime
import re

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

from ..models import User, CoinTransaction, Subscription, Audiobook, Chapter, Review, AudiobookPurchase, CreatorEarning, Creator
from .utils import _get_full_context

# Configure Stripe API key
if not hasattr(settings, 'STRIPE_SECRET_KEY') or not settings.STRIPE_SECRET_KEY:
    # In a production environment, handle this critically
    pass
stripe.api_key = settings.STRIPE_SECRET_KEY

# --- Profile Views ---

@login_required
def myprofile(request):
    """Renders the user's profile page."""
    context = _get_full_context(request)
    if context.get('is_banned'):
        context['ban_reason_display'] = context.get('ban_reason', 'No reason provided.')
    return render(request, 'user/myprofile.html', context)

@login_required
@require_POST
@csrf_protect
def update_profile(request):
    """Handles updating user profile information via AJAX."""
    user = request.user
    if request.content_type.startswith('multipart'):
        # Handle profile picture upload
        if 'profile_pic' in request.FILES:
            if user.profile_pic:
                try:
                    if default_storage.exists(user.profile_pic.name):
                        default_storage.delete(user.profile_pic.name)
                except Exception:
                    pass

            user.profile_pic = request.FILES['profile_pic']
            try:
                user.save(update_fields=['profile_pic'])
                pic_url = user.profile_pic.url + f'?t={timezone.now().timestamp()}'
                return JsonResponse({'status': 'success', 'message': 'Profile picture updated successfully.', 'profile_pic_url': pic_url})
            except Exception:
                return JsonResponse({'status': 'error', 'message': 'Error saving profile picture.'}, status=500)
        else:
            return JsonResponse({'status': 'error', 'message': 'No profile picture file found in request.'}, status=400)

    elif request.content_type == 'application/json':
        # Handle other profile fields update
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
                    if user.phone_number != '':
                        user.phone_number = ''
                        fields_to_update.append('phone_number')

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
                    except Exception:
                        error_messages['profile_pic'] = 'Error removing profile picture.'

            if 'is_2fa_enabled' in data:
                new_2fa_status = data.get('is_2fa_enabled')
                if isinstance(new_2fa_status, bool):
                    if user.is_2fa_enabled != new_2fa_status:
                        user.is_2fa_enabled = new_2fa_status
                        fields_to_update.append('is_2fa_enabled')
                else:
                    error_messages['is_2fa_enabled'] = 'Invalid value for 2FA status.'

            if error_messages:
                general_error_message = "Please correct the errors below."
                if len(error_messages) == 1 and 'profile_pic' in error_messages and 'Error removing profile picture' in error_messages['profile_pic']:
                     general_error_message = error_messages['profile_pic']

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
                except IntegrityError as e:
                    error_message = 'A data conflict occurred. Please check your input.'
                    if 'username' in str(e).lower():
                        error_message = 'Username already exists.'
                    elif 'email' in str(e).lower():
                        error_message = 'Email already exists.'
                    return JsonResponse({'status': 'error', 'message': error_message, 'errors': {'general': error_message}}, status=400)
                except Exception:
                    return JsonResponse({'status': 'error', 'message': 'Error saving profile.'}, status=500)
            else:
                return JsonResponse({'status': 'success', 'message': 'No changes detected.'})

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid request data format.'}, status=400)
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request format.'}, status=415)

@login_required
@csrf_protect
def change_password(request):
    """Handles user password change via AJAX."""
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            return JsonResponse({'status': 'success', 'message': 'Password updated successfully!'})
        else:
            errors = {field: error[0] for field, error in form.errors.items()}
            if 'old_password' in errors and 'Invalid password' in errors['old_password']:
                errors['old_password'] = 'Incorrect current password.'

            if 'new_password2' in errors:
                if "The two password fields didn’t match." in errors['new_password2']:
                    errors['new_password2'] = "Passwords didn't match."
                elif "password is too common" in errors['new_password2'].lower():
                    errors['new_password2'] = "This password is too common."
                elif "password is too short" in errors['new_password2'].lower():
                    min_length = getattr(settings, 'AUTH_PASSWORD_VALIDATORS', [{'OPTIONS': {'min_length': 8}}])[0].get('OPTIONS', {}).get('min_length', 8)
                    errors['new_password2'] = f"Password must be at least {min_length} characters."
                elif "entirely numeric" in errors['new_password2'].lower():
                    errors['new_password2'] = "Password can't be entirely numeric."

            return JsonResponse({'status': 'error', 'message': 'Please correct the errors below.', 'errors': errors}, status=400)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method or type.'}, status=400)

# --- Wallet and Coin Views ---

@login_required
def buycoins(request):
    """Renders the buy coins page."""
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
    """Handles gifting coins to another user."""
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
        return JsonResponse({'status': 'error', 'message': 'Database error during transaction. Please try again.'}, status=500)
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)

@login_required
def mywallet(request):
    """Renders the user's wallet page showing transaction history."""
    transaction_history = CoinTransaction.objects.filter(user=request.user).exclude(
        pack_name__in=['Monthly Premium Subscription', 'Annual Premium Subscription']
    ).select_related('sender', 'recipient').order_by('-transaction_date')

    context = _get_full_context(request)
    context['user'] = request.user
    context['gift_history'] = transaction_history
    return render(request, 'user/mywallet.html', context)

# --- Subscription Views ---

@login_required
def subscribe(request):
    """Renders the subscription page."""
    context = _get_full_context(request)
    context['STRIPE_PUBLISHABLE_KEY'] = settings.STRIPE_PUBLISHABLE_KEY
    return render(request, 'user/subscription.html', context)

@login_required
def managesubscription(request):
    """Renders the manage subscription page."""
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
    except Exception:
        if user.subscription_type == 'PR':
            user.subscription_type = 'FR'
            user.save(update_fields=['subscription_type'])

    context = _get_full_context(request)
    context['subscription'] = subscription
    return render(request, 'user/managesubscription.html', context)

@login_required
@require_POST
@csrf_protect
@transaction.atomic
def cancel_subscription(request):
    """Handles canceling a user's subscription."""
    try:
        subscription = Subscription.objects.get(user=request.user, status='active')
        if not subscription.stripe_subscription_id:
            messages.error(request, "Cannot cancel: Stripe subscription ID is missing.")
            return redirect('AudioXApp:managesubscription')

        try:
            stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=True
            )
            cancellation_successful_on_stripe = True
        except stripe.error.StripeError:
            messages.error(request, "Failed to schedule cancellation with the payment provider. Please contact support.")
            cancellation_successful_on_stripe = False

        if cancellation_successful_on_stripe:
            subscription.status = 'canceled'
            subscription.save(update_fields=['status'])
            messages.success(request, "Your subscription has been scheduled for cancellation. You can continue using Premium features until the end of the current billing period.")

    except Subscription.DoesNotExist:
        messages.warning(request, "You do not have an active subscription to cancel.")
    except Exception:
        messages.error(request, "An error occurred while canceling your subscription. Please contact support.")
    return redirect('AudioXApp:managesubscription')

# --- Stripe Payment Views ---

@login_required
@require_POST
@csrf_protect
def create_checkout_session(request):
    """Creates a Stripe Checkout Session for purchasing coins, subscriptions, or audiobooks."""
    try:
        data = json.loads(request.body)
        item_type = data.get('item_type')
        item_id = data.get('item_id')

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
            'item_id': item_id,
        }

        if item_type == 'subscription':
            price_lookup = stripe_price_ids.get(item_type, {}).get(item_id)
            if not price_lookup:
                return JsonResponse({'error': f'Pricing information not found for subscription plan ({item_id}).'}, status=400)
            mode = 'subscription'
            success_url_path = reverse('AudioXApp:managesubscription') + '?stripe_session_id={CHECKOUT_SESSION_ID}&status=success'
            cancel_url_path = reverse('AudioXApp:subscribe') + '?status=cancel'
            line_items = [{'price': price_lookup, 'quantity': 1}]

            try:
                current_subscription = Subscription.objects.get(user=request.user)
                if current_subscription.status == 'active' or \
                   (current_subscription.status == 'canceled' and current_subscription.end_date and current_subscription.end_date > timezone.now()):
                    return JsonResponse({'status': 'already_subscribed', 'redirect_url': reverse('AudioXApp:managesubscription')})
            except Subscription.DoesNotExist:
                pass

        elif item_type == 'coins':
            price_lookup = stripe_price_ids.get(item_type, {}).get(item_id)
            if not price_lookup:
                return JsonResponse({'error': f'Pricing information not found for coin pack ({item_id}).'}, status=400)
            mode = 'payment'
            success_url_path = reverse('AudioXApp:mywallet') + '?stripe_session_id={CHECKOUT_SESSION_ID}&status=success'
            cancel_url_path = reverse('AudioXApp:buycoins') + '?status=cancel'
            line_items = [{'price': price_lookup, 'quantity': 1}]

        elif item_type == 'audiobook':
            audiobook_slug = item_id
            try:
                audiobook = Audiobook.objects.get(slug=audiobook_slug)
                if not audiobook.is_paid or audiobook.price <= 0:
                    return JsonResponse({'error': 'This audiobook is not available for purchase.'}, status=400)

                if request.user.has_purchased_audiobook(audiobook):
                    return JsonResponse({'status': 'already_purchased', 'message': 'You have already purchased this audiobook.'})

                mode = 'payment'
                success_url_path = reverse('AudioXApp:audiobook_detail', kwargs={'audiobook_slug': audiobook.slug}) + '?purchase=success&session_id={CHECKOUT_SESSION_ID}'
                cancel_url_path = reverse('AudioXApp:audiobook_detail', kwargs={'audiobook_slug': audiobook.slug}) + '?purchase=cancel'

                try:
                    amount_in_paisa = int(audiobook.price * 100)
                except (TypeError, InvalidOperation):
                    return JsonResponse({'error': 'Invalid price format for audiobook.'}, status=500)

                line_items = [{
                    'price_data': {
                        'currency': 'pkr',
                        'product_data': {
                            'name': f'Audiobook: {audiobook.title}',
                            'description': f'Purchase of audiobook "{audiobook.title}" by {audiobook.creator.creator_name if audiobook.creator else "Unknown Creator"}',
                        },
                        'unit_amount': amount_in_paisa,
                    },
                    'quantity': 1,
                }]
            except Audiobook.DoesNotExist:
                return JsonResponse({'error': 'Audiobook not found.'}, status=404)
            except Exception:
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
                'customer_email': request.user.email,
                'allow_promotion_codes': True,
            }
            if mode == 'subscription':
                try:
                    existing_subscription_details = Subscription.objects.get(user=request.user)
                    if existing_subscription_details.stripe_customer_id:
                        checkout_session_params['customer'] = existing_subscription_details.stripe_customer_id
                except Subscription.DoesNotExist:
                    pass

            checkout_session = stripe.checkout.Session.create(**checkout_session_params)
            return JsonResponse({'sessionId': checkout_session.id})

        except stripe.error.InvalidRequestError as e:
            error_message = str(e)
            if "You cannot use `line_items.price_data` in `subscription` mode" in error_message:
                 error_message = "Configuration error with subscription pricing. Please contact support."
            return JsonResponse({'error': f'Payment Provider Error: {error_message}'}, status=400)
        except Exception:
            return JsonResponse({'error': 'Could not initiate payment session.'}, status=500)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request data format.'}, status=400)
    except Exception:
        return JsonResponse({'error': 'An unexpected server error occurred.'}, status=500)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Handles Stripe webhook events for payment fulfillment."""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)

    if not endpoint_secret:
        return JsonResponse({'error': 'Webhook secret not configured on server.'}, status=500)

    event = None
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError:
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    except Exception:
        return JsonResponse({'error': 'Webhook processing error'}, status=500)

    if event.type == 'checkout.session.completed':
        session = event.data.object
        metadata = session.get('metadata', {})
        user_id = metadata.get('django_user_id')
        item_type = metadata.get('item_type')
        item_id = metadata.get('item_id')

        if not user_id or not item_type or not item_id:
            return JsonResponse({'status': 'error', 'message': 'Missing essential metadata.'}, status=200)

        if session.payment_status == 'paid':
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'User not found.'}, status=200)

            idempotency_key_description = f"stripe_checkout_session_{session.id}"
            stripe_subscription_id_from_session = session.get('subscription')

            already_processed = False
            if item_type == 'subscription':
                if stripe_subscription_id_from_session and Subscription.objects.filter(stripe_subscription_id=stripe_subscription_id_from_session).exists():
                    already_processed = True
            elif item_type == 'coins':
                if CoinTransaction.objects.filter(description=idempotency_key_description).exists():
                    already_processed = True
            elif item_type == 'audiobook':
                if AudiobookPurchase.objects.filter(stripe_checkout_session_id=session.id).exists():
                    already_processed = True

            if already_processed:
                return JsonResponse({'status': 'already_processed'})

            payment_intent_id = session.get('payment_intent')
            payment_brand, payment_last4 = None, None
            if payment_intent_id:
                try:
                    payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                    if payment_intent.payment_method:
                        payment_method_id = payment_intent.payment_method
                        if isinstance(payment_method_id, str):
                            payment_method_obj = stripe.PaymentMethod.retrieve(payment_method_id)
                            if payment_method_obj.card:
                                payment_brand = payment_method_obj.card.brand
                                payment_last4 = payment_method_obj.card.last4
                except stripe.error.StripeError:
                    pass

            try:
                with transaction.atomic():
                    user_locked = User.objects.select_for_update().get(pk=user.pk)

                    if item_type == 'subscription' and item_id in ['monthly', 'annual']:
                        plan_type = item_id

                        sub_prices_settings = getattr(settings, 'SUBSCRIPTION_PRICES', {})
                        sub_durations_settings = getattr(settings, 'SUBSCRIPTION_DURATIONS', {})

                        default_price_str = sub_prices_settings.get(plan_type, '350.00' if plan_type == 'monthly' else '3500.00')
                        duration_days = sub_durations_settings.get(plan_type, 30 if plan_type == 'monthly' else 365)
                        pack_name = "Monthly Premium Subscription" if plan_type == 'monthly' else "Annual Premium Subscription"

                        price = Decimal('0.00')
                        try:
                            amount_total_from_stripe = session.get('amount_total')
                            if amount_total_from_stripe is not None:
                                price = (Decimal(amount_total_from_stripe) / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                            else:
                                price = Decimal(default_price_str)
                        except (InvalidOperation, TypeError):
                            pass

                        end_date = timezone.now() + timezone.timedelta(days=duration_days)

                        stripe_customer_id_from_session = session.get('customer')

                        if not stripe_subscription_id_from_session:
                             return JsonResponse({'status': 'error', 'message': 'Internal error: Missing Stripe subscription ID.'}, status=200)

                        sub, created = Subscription.objects.update_or_create(
                            user=user_locked,
                            defaults={
                                'plan': plan_type,
                                'start_date': timezone.now(),
                                'end_date': end_date,
                                'status': 'active',
                                'stripe_subscription_id': stripe_subscription_id_from_session,
                                'stripe_customer_id': stripe_customer_id_from_session,
                                'stripe_payment_method_brand': payment_brand,
                                'stripe_payment_method_last4': payment_last4,
                            }
                        )
                        if not created and sub.stripe_subscription_id != stripe_subscription_id_from_session:
                             sub.stripe_subscription_id = stripe_subscription_id_from_session
                             sub.plan = plan_type
                             sub.start_date = timezone.now()
                             sub.end_date = end_date
                             sub.status = 'active'
                             sub.stripe_customer_id = stripe_customer_id_from_session
                             sub.stripe_payment_method_brand = payment_brand
                             sub.stripe_payment_method_last4 = payment_last4
                             sub.save()

                        if user_locked.subscription_type != 'PR':
                            user_locked.subscription_type = 'PR'
                            user_locked.save(update_fields=['subscription_type'])

                        CoinTransaction.objects.update_or_create(
                            description=idempotency_key_description,
                            defaults={
                                'user': user_locked,
                                'transaction_type': 'purchase',
                                'amount': 0,
                                'status': 'completed',
                                'pack_name': pack_name,
                                'price': price
                            }
                        )

                    elif item_type == 'coins':
                        coins_pack_id_str = item_id
                        try:
                            coins_to_grant = int(coins_pack_id_str)
                            if coins_to_grant <= 0: raise ValueError("Coins must be positive.")

                            coin_prices_settings = getattr(settings, 'COIN_PACK_PRICES', {})
                            default_price_str = coin_prices_settings.get(coins_pack_id_str)
                            pack_name = f"{coins_to_grant} Coins Pack"

                            if default_price_str is None:
                                default_price_str = coins_pack_id_str + ".00"
                                if coins_to_grant == 250: pack_name = "Starter Pack (250 Coins)"
                                elif coins_to_grant == 500: pack_name = "Value Pack (500 Coins)"
                                elif coins_to_grant == 1000: pack_name = "Pro Pack (1000 Coins)"
                                else: pack_name = f"Unknown Pack ({coins_to_grant} Coins)"
                            else:
                                if coins_to_grant == 250: pack_name = "Starter Pack (250 Coins)"
                                elif coins_to_grant == 500: pack_name = "Value Pack (500 Coins)"
                                elif coins_to_grant == 1000: pack_name = "Pro Pack (1000 Coins)"

                            price_paid = Decimal('0.00')
                            try:
                                amount_total_from_stripe = session.get('amount_total')
                                if amount_total_from_stripe is not None:
                                    price_paid = (Decimal(amount_total_from_stripe) / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                                else:
                                    price_paid = Decimal(default_price_str)
                            except (InvalidOperation, TypeError):
                                pass

                            user_locked.coins = F('coins') + coins_to_grant
                            user_locked.save(update_fields=['coins'])
                            user_locked.refresh_from_db(fields=['coins'])

                            CoinTransaction.objects.update_or_create(
                                description=idempotency_key_description,
                                defaults={
                                    'user': user_locked,
                                    'transaction_type': 'purchase',
                                    'amount': coins_to_grant,
                                    'status': 'completed',
                                    'pack_name': pack_name,
                                    'price': price_paid
                                }
                            )
                        except (ValueError, TypeError):
                             return JsonResponse({'status': 'error', 'message': 'Invalid coin data in metadata.'}, status=200)

                    elif item_type == 'audiobook':
                        audiobook_slug = item_id
                        try:
                            audiobook = Audiobook.objects.select_related('creator').get(slug=audiobook_slug)
                            creator = audiobook.creator
                            if not creator:
                                return JsonResponse({'status': 'error', 'message': 'Audiobook creator not found.'}, status=500)

                            if AudiobookPurchase.objects.filter(stripe_checkout_session_id=session.id).exists():
                                return JsonResponse({'status': 'already_processed'})

                            amount_paid_paisa = session.amount_total
                            amount_paid_pkr = (Decimal(amount_paid_paisa) / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                            platform_fee_percentage_str = getattr(settings, 'PLATFORM_FEE_PERCENTAGE_AUDIOBOOK', '10.00')
                            try:
                                platform_fee_percentage = Decimal(platform_fee_percentage_str)
                            except InvalidOperation:
                                platform_fee_percentage = Decimal('10.00')

                            platform_fee_amount = (amount_paid_pkr * platform_fee_percentage / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                            creator_share_amount = amount_paid_pkr - platform_fee_amount

                            purchase = AudiobookPurchase.objects.create(
                                user=user_locked, audiobook=audiobook, amount_paid=amount_paid_pkr,
                                platform_fee_percentage=platform_fee_percentage,
                                platform_fee_amount=platform_fee_amount,
                                creator_share_amount=creator_share_amount,
                                stripe_checkout_session_id=session.id,
                                stripe_payment_intent_id=payment_intent_id
                            )

                            creator_locked = Creator.objects.select_for_update().get(pk=creator.pk)
                            creator_locked.total_earning = F('total_earning') + amount_paid_pkr
                            creator_locked.available_balance = F('available_balance') + creator_share_amount
                            creator_locked.save(update_fields=['total_earning', 'available_balance'])

                            CreatorEarning.objects.create(
                                creator=creator_locked, audiobook=audiobook, purchase=purchase,
                                amount_earned=creator_share_amount, earning_type='sale',
                                notes=f"Sale via Stripe Checkout Session: {session.id}",
                                audiobook_title_at_transaction=audiobook.title
                            )

                            audiobook_locked = Audiobook.objects.select_for_update().get(pk=audiobook.pk)
                            audiobook_locked.total_sales = F('total_sales') + 1
                            audiobook_locked.total_revenue_generated = F('total_revenue_generated') + amount_paid_pkr
                            audiobook_locked.save(update_fields=['total_sales', 'total_revenue_generated'])

                        except Audiobook.DoesNotExist:
                             return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=200)
                        except Creator.DoesNotExist:
                             return JsonResponse({'status': 'error', 'message': 'Creator data error.'}, status=500)
                        except Exception:
                             return JsonResponse({'error': 'Internal server error during audiobook fulfillment.'}, status=500)
                    else:
                         return JsonResponse({'status': 'error', 'message': 'Unknown item type in metadata.'}, status=200)

            except IntegrityError:
                return JsonResponse({'status': 'error', 'message': 'Database conflict during fulfillment.'}, status=200)
            except Exception:
                return JsonResponse({'error': 'Internal server error during fulfillment.'}, status=500)
        else:
            pass

    elif event.type == 'customer.subscription.updated':
        subscription_data = event.data.object
        stripe_sub_id = subscription_data.id
        try:
            with transaction.atomic():
                local_sub = Subscription.objects.select_for_update().get(stripe_subscription_id=stripe_sub_id)

                stripe_status = subscription_data.status
                original_local_status = local_sub.status

                if stripe_status == 'active': local_sub.status = 'active'
                elif stripe_status == 'canceled': local_sub.status = 'canceled'
                elif stripe_status in ['past_due', 'unpaid']: local_sub.status = 'past_due'
                elif stripe_status in ['trialing']: local_sub.status = 'active'
                else: local_sub.status = 'expired'

                if subscription_data.current_period_end:
                    local_sub.end_date = timezone.make_aware(datetime.datetime.fromtimestamp(subscription_data.current_period_end))
                else:
                    local_sub.end_date = None

                if subscription_data.cancel_at_period_end and local_sub.end_date and timezone.now() >= local_sub.end_date:
                    local_sub.status = 'expired'

                fields_to_save = []
                if local_sub.status != original_local_status:
                    fields_to_save.append('status')

                current_db_end_date = Subscription.objects.get(pk=local_sub.pk).end_date
                if local_sub.end_date != current_db_end_date :
                    fields_to_save.append('end_date')

                if len(fields_to_save) > 0:
                    local_sub.save(update_fields=list(set(fields_to_save)))

                if local_sub.status == 'expired' and local_sub.user.subscription_type == 'PR':
                    user_locked = User.objects.select_for_update().get(pk=local_sub.user.pk)
                    user_locked.subscription_type = 'FR'
                    user_locked.save(update_fields=['subscription_type'])

        except Subscription.DoesNotExist:
            pass
        except Exception:
            return JsonResponse({'error': 'Internal server error processing subscription update.'}, status=500)

    elif event.type == 'customer.subscription.deleted':
        subscription_data = event.data.object
        stripe_sub_id = subscription_data.id
        try:
            with transaction.atomic():
                local_sub = Subscription.objects.select_for_update().get(stripe_subscription_id=stripe_sub_id)
                local_sub.status = 'expired'
                local_sub.end_date = timezone.now()
                local_sub.save(update_fields=['status', 'end_date'])

                if local_sub.user.subscription_type == 'PR':
                    user_locked = User.objects.select_for_update().get(pk=local_sub.user.pk)
                    user_locked.subscription_type = 'FR'
                    user_locked.save(update_fields=['subscription_type'])
        except Subscription.DoesNotExist:
            pass
        except Exception:
            return JsonResponse({'error': 'Internal server error processing subscription deletion.'}, status=500)

    elif event.type == 'invoice.paid':
        invoice = event.data.object
        stripe_subscription_id = getattr(invoice, 'subscription', None)

        if stripe_subscription_id and invoice.billing_reason == 'subscription_cycle':
            try:
                with transaction.atomic():
                    local_sub = Subscription.objects.select_for_update().get(stripe_subscription_id=stripe_subscription_id)
                    user_locked = User.objects.select_for_update().get(pk=local_sub.user.pk)

                    update_fields = ['status']
                    local_sub.status = 'active'

                    if invoice.period_start:
                        new_start_date = timezone.make_aware(datetime.datetime.fromtimestamp(invoice.period_start))
                        if local_sub.start_date != new_start_date:
                            local_sub.start_date = new_start_date
                            update_fields.append('start_date')
                    if invoice.period_end:
                        new_end_date = timezone.make_aware(datetime.datetime.fromtimestamp(invoice.period_end))
                        if local_sub.end_date != new_end_date:
                            local_sub.end_date = new_end_date
                            update_fields.append('end_date')

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
                        except stripe.error.StripeError:
                            pass

                    if len(update_fields) > 0:
                        local_sub.save(update_fields=list(set(update_fields)))

                    if user_locked.subscription_type != 'PR':
                        user_locked.subscription_type = 'PR'
                        user_locked.save(update_fields=['subscription_type'])

                    pack_name = "Monthly Premium Renewal" if local_sub.plan == 'monthly' else "Annual Premium Renewal"
                    price = Decimal(invoice.amount_paid / 100.0)
                    idempotency_key_description = f"stripe_invoice_{invoice.id}"
                    CoinTransaction.objects.update_or_create(
                        description=idempotency_key_description,
                        defaults={
                            'user': user_locked,
                            'transaction_type': 'purchase',
                            'amount': 0,
                            'status': 'completed',
                            'pack_name': pack_name,
                            'price': price
                        }
                    )
            except Subscription.DoesNotExist:
                pass
            except Exception:
                return JsonResponse({'error': 'Internal server error during invoice.paid renewal processing.'}, status=500)
        elif invoice.billing_reason == 'subscription_create':
             pass
        else:
             pass

    elif event.type == 'invoice.payment_failed':
        invoice = event.data.object
        stripe_subscription_id = getattr(invoice, 'subscription', None)
        if stripe_subscription_id:
            try:
                with transaction.atomic():
                    local_sub = Subscription.objects.select_for_update().get(stripe_subscription_id=stripe_subscription_id)
                    if local_sub.status != 'past_due':
                        local_sub.status = 'past_due'
                        local_sub.save(update_fields=['status'])
            except Subscription.DoesNotExist:
                pass
            except Exception:
                return JsonResponse({'error': 'Internal server error processing payment failure.'}, status=500)
        else:
            pass

    else:
        pass

    return JsonResponse({'status': 'success'})


# --- Billing and Library Views ---

@login_required
def billing_history(request):
    """Renders the user's billing history page."""
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

    all_purchases_qs = CoinTransaction.objects.filter(user=user, transaction_type='purchase')
    if start_date: all_purchases_qs = all_purchases_qs.filter(transaction_date__gte=start_date)
    if end_date: all_purchases_qs = all_purchases_qs.filter(transaction_date__lte=end_date)

    subscription_pack_names_lower = [name.lower() for name in ['Monthly Premium Subscription', 'Annual Premium Subscription', 'Monthly Premium Renewal', 'Annual Premium Renewal']]

    for txn in all_purchases_qs.order_by('-transaction_date'):
        status_display = txn.get_status_display()
        status_class = 'bg-gray-100 text-gray-700'
        if txn.status == 'completed': status_class = 'bg-green-100 text-green-700'
        elif txn.status == 'pending': status_class = 'bg-yellow-100 text-yellow-700'
        elif txn.status in ['failed', 'rejected']: status_class = 'bg-red-100 text-red-700'

        item_type_display = 'Coin Purchase'
        details_url = reverse('AudioXApp:buycoins')
        description = txn.pack_name or f"{txn.amount} Coins"
        coins_received = txn.amount if txn.amount > 0 else None

        if txn.pack_name and txn.pack_name.lower() in subscription_pack_names_lower:
            item_type_display = 'Subscription'
            details_url = reverse('AudioXApp:managesubscription')
            coins_received = None

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

    billing_items_list.sort(key=lambda x: x['date'], reverse=True)

    context = _get_full_context(request)
    context['billing_items'] = billing_items_list
    context['start_date_str'] = start_date_str
    context['end_date_str'] = end_date_str

    return render(request, 'user/billing_history.html', context)

@login_required
def my_downloads(request):
    """Renders the user's downloads page (placeholder)."""
    context = _get_full_context(request)
    context['downloaded_audiobooks'] = []
    messages.info(request, "My Downloads page is under construction.")
    return redirect('AudioXApp:myprofile')

@login_required
def my_library(request):
    """Renders the user's library page showing purchased audiobooks."""
    context = _get_full_context(request)
    purchased_audiobooks = Audiobook.objects.filter(purchases__user=request.user).distinct().prefetch_related(
        Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order'))
    ).order_by('-purchases__purchase_date')

    context['library_audiobooks'] = purchased_audiobooks
    return render(request, 'user/my_library.html', context)

# --- Profile Completion View ---

@login_required
@csrf_protect
def complete_profile(request):
    """Handles the profile completion page."""
    user = request.user
    context = _get_full_context(request)

    next_destination_after_save = request.GET.get('next')
    if not next_destination_after_save:
        next_destination_after_save = request.session.get('next_url_after_profile_completion')
        if next_destination_after_save and not next_destination_after_save.startswith('/'):
            try:
                next_destination_after_save = reverse(next_destination_after_save)
            except:
                next_destination_after_save = reverse('AudioXApp:home')
    if not next_destination_after_save:
        next_destination_after_save = reverse('AudioXApp:home')

    profile_is_complete = bool(
        user.full_name and user.full_name.strip() and
        user.phone_number and user.phone_number.startswith('+92') and len(user.phone_number) == 13 and user.phone_number[3:].isdigit()
    )

    if profile_is_complete and request.method == 'GET':
        if 'profile_incomplete' in request.session: del request.session['profile_incomplete']
        if 'next_url_after_profile_completion' in request.session: del request.session['next_url_after_profile_completion']
        messages.info(request, "Your profile is already complete.")
        return redirect(next_destination_after_save)

    if request.method == 'POST':
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                full_name = data.get('full_name', '').strip()
                phone_number_full = data.get('phone_number', '').strip()

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

                messages.success(request, "Your profile has been updated successfully!")
                return JsonResponse({
                    'status': 'success',
                    'message': 'Your profile has been updated successfully!',
                    'redirect_url': next_destination_after_save
                })

            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
            except Exception:
                return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid request content type. Expected application/json.'}, status=415)

    user_phone_number_only = ''
    if user.phone_number and user.phone_number.startswith('+92') and len(user.phone_number) == 13:
        user_phone_number_only = user.phone_number[3:]

    context['user_phone_number_only'] = user_phone_number_only
    context['user_full_phone_number'] = user.phone_number
    context['next_destination_on_success'] = next_destination_after_save

    return render(request, 'auth/complete_profile.html', context)
