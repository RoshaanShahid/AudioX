import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import datetime

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
from django.urls import reverse
from django.core.validators import validate_email

from ..models import User, CoinTransaction, Subscription, Audiobook, Chapter, Review, AudiobookPurchase, CreatorEarning, Creator
from .utils import _get_full_context

if not hasattr(settings, 'STRIPE_SECRET_KEY') or not settings.STRIPE_SECRET_KEY:
    pass # Critical error should be handled in a production environment
stripe.api_key = settings.STRIPE_SECRET_KEY


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
        if 'profile_pic' in request.FILES:
            if user.profile_pic:
                try:
                    if default_storage.exists(user.profile_pic.name):
                        default_storage.delete(user.profile_pic.name)
                except Exception as e:
                    pass # Error deleting old picture

            user.profile_pic = request.FILES['profile_pic']
            try:
                user.save(update_fields=['profile_pic'])
                pic_url = user.profile_pic.url + f'?t={timezone.now().timestamp()}'
                return JsonResponse({'status': 'success', 'message': 'Profile picture updated successfully', 'profile_pic_url': pic_url})
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': f'Error saving profile picture.'}, status=500)
        else:
            return JsonResponse({'status': 'error', 'message': 'No profile picture file found in request.'}, status=400)

    elif request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
            fields_to_update = []

            if 'username' in data:
                username = data['username'].strip()
                if not username: return JsonResponse({'status': 'error', 'message': 'Username cannot be empty.'}, status=400)
                if user.username != username:
                    if User.objects.exclude(pk=user.pk).filter(username=username).exists():
                        return JsonResponse({'status': 'error', 'message': 'Username already exists'}, status=400)
                    user.username = username
                    fields_to_update.append('username')

            if 'full_name' in data:
                full_name = data['full_name'].strip()
                if user.full_name != full_name:
                    user.full_name = full_name
                    fields_to_update.append('full_name')

            if 'email' in data:
                email = data['email'].strip()
                if not email: return JsonResponse({'status': 'error', 'message': 'Email cannot be empty.'}, status=400)
                try: validate_email(email)
                except ValidationError: return JsonResponse({'status': 'error', 'message': 'Invalid email address format.'}, status=400)
                if user.email != email:
                    if User.objects.exclude(pk=user.pk).filter(email=email).exists():
                        return JsonResponse({'status': 'error', 'message': 'Email already exists'}, status=400)
                    user.email = email
                    fields_to_update.append('email')

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
                        return JsonResponse({'status': 'error', 'message': f'Error removing profile picture.'}, status=500)

            if 'is_2fa_enabled' in data:
                new_2fa_status = data.get('is_2fa_enabled')
                if isinstance(new_2fa_status, bool):
                    if user.is_2fa_enabled != new_2fa_status:
                        user.is_2fa_enabled = new_2fa_status
                        fields_to_update.append('is_2fa_enabled')
                else:
                    return JsonResponse({'status': 'error', 'message': 'Invalid value for 2FA status.'}, status=400)

            if fields_to_update:
                try:
                    user.save(update_fields=fields_to_update)
                    message = "Profile updated successfully."
                    if 'is_2fa_enabled' in fields_to_update and len(fields_to_update) == 1:
                        message = f"Two-Factor Authentication {'enabled' if user.is_2fa_enabled else 'disabled'}."
                    elif 'profile_pic' in fields_to_update and data.get('remove_profile_pic') is True and len(fields_to_update) == 1:
                        message = "Profile picture removed successfully."
                    return JsonResponse({'status': 'success', 'message': message})
                except Exception as e:
                    return JsonResponse({'status': 'error', 'message': f'Error saving profile.'}, status=500)
            else:
                return JsonResponse({'status': 'success', 'message': 'No changes detected.'})

        except json.JSONDecodeError: return JsonResponse({'status': 'error', 'message': 'Invalid request data format.'}, status=400)
        except Exception as e:
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
            if 'old_password' in errors and 'Invalid password' in errors['old_password']:
                errors['old_password'] = 'Incorrect current password.'
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
        return JsonResponse({'status': 'error', 'message': 'Database error during transaction. Please try again.'}, status=500)
    except Exception as e:
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
        if user.subscription_type == 'PR':
            user.subscription_type = 'FR'
            user.save(update_fields=['subscription_type'])

    payment_history = CoinTransaction.objects.filter(
        user=user, transaction_type='purchase',
        pack_name__in=['Monthly Premium Subscription', 'Annual Premium Subscription']
    ).order_by('-transaction_date')

    context = _get_full_context(request)
    context['subscription'] = subscription
    context['payment_history'] = payment_history
    return render(request, 'user/managesubscription.html', context)

@login_required
@require_POST
@csrf_protect
@transaction.atomic
def cancel_subscription(request):
    try:
        subscription = Subscription.objects.get(user=request.user, status='active')
        if not subscription.stripe_subscription_id:
            messages.error(request, "Cannot cancel: Stripe subscription ID is missing.")
            return redirect('AudioXApp:managesubscription')

        try:
            stripe.Subscription.modify(subscription.stripe_subscription_id, cancel_at_period_end=True)
            cancellation_successful_on_stripe = True
        except stripe.error.StripeError as e:
            messages.error(request, f"Failed to schedule cancellation with the payment provider. Please contact support.")
            cancellation_successful_on_stripe = False

        if cancellation_successful_on_stripe:
            subscription.status = 'canceled'
            subscription.save(update_fields=['status'])
            messages.success(request, "Your subscription has been scheduled for cancellation. You can continue using Premium features until the end of the current period.")
    except Subscription.DoesNotExist: messages.warning(request, "You do not have an active subscription to cancel.")
    except Exception as e:
        messages.error(request, f"An error occurred while canceling your subscription. Please contact support.")
    return redirect('AudioXApp:managesubscription')


@login_required
@require_POST
@csrf_protect
def create_checkout_session(request):
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
            metadata['plan'] = item_id
            line_items = [{'price': price_lookup, 'quantity': 1}]

            try:
                Subscription.objects.get(user=request.user, status='active')
                return JsonResponse({'status': 'already_subscribed', 'redirect_url': reverse('AudioXApp:managesubscription')})
            except Subscription.DoesNotExist: pass

        elif item_type == 'coins':
            price_lookup = stripe_price_ids.get(item_type, {}).get(item_id)
            if not price_lookup:
                return JsonResponse({'error': f'Pricing information not found for coin pack ({item_id}).'}, status=400)
            mode = 'payment'
            success_url_path = reverse('AudioXApp:mywallet') + '?stripe_session_id={CHECKOUT_SESSION_ID}&status=success'
            cancel_url_path = reverse('AudioXApp:buycoins') + '?status=cancel'
            metadata['coins'] = item_id
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
                success_url_path = reverse('AudioXApp:audiobook_detail', kwargs={'audiobook_slug': audiobook.slug}) + '?purchase=success'
                cancel_url_path = reverse('AudioXApp:audiobook_detail', kwargs={'audiobook_slug': audiobook.slug}) + '?purchase=cancel'
                metadata['audiobook_slug'] = audiobook_slug

                try:
                    amount_in_paisa = int(audiobook.price * 100)
                except (TypeError, InvalidOperation):
                    return JsonResponse({'error': 'Invalid price format for audiobook.'}, status=500)

                line_items = [{
                    'price_data': {
                        'currency': 'pkr',
                        'product_data': {
                            'name': f'Audiobook: {audiobook.title}',
                            'description': f'Purchase of audiobook "{audiobook.title}" by {audiobook.creator.creator_name}',
                        },
                        'unit_amount': amount_in_paisa,
                    },
                    'quantity': 1,
                }]
            except Audiobook.DoesNotExist:
                return JsonResponse({'error': 'Audiobook not found.'}, status=404)
            except Exception as e:
                return JsonResponse({'error': 'Error retrieving audiobook details.'}, status=500)
        else:
            return JsonResponse({'error': 'Invalid item type specified.'}, status=400)

        protocol = 'https' if request.is_secure() else 'http'
        host = request.get_host()
        success_url = f"{protocol}://{host}{success_url_path}"
        cancel_url = f"{protocol}://{host}{cancel_url_path}"

        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=line_items,
                mode=mode,
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata,
                customer_email=request.user.email,
                allow_promotion_codes=True,
            )
            return JsonResponse({'sessionId': checkout_session.id})
        except stripe.error.InvalidRequestError as e:
            return JsonResponse({'error': f'Payment Provider Error: {str(e)}'}, status=400)
        except Exception as e:
            return JsonResponse({'error': 'Could not initiate payment session.'}, status=500)

    except json.JSONDecodeError: return JsonResponse({'error': 'Invalid request data format.'}, status=400)
    except Exception as e:
        return JsonResponse({'error': 'An unexpected server error occurred.'}, status=500)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    event = None

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError: return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError: return JsonResponse({'error': 'Invalid signature'}, status=400)
    except Exception as e:
        return JsonResponse({'error': 'Webhook processing error'}, status=500)

    if event.type == 'checkout.session.completed':
        session = event.data.object
        metadata = session.get('metadata', {})
        user_id = metadata.get('django_user_id')
        item_type = metadata.get('item_type')
        item_id = metadata.get('item_id')

        if not user_id or not item_type or not item_id:
            return JsonResponse({'status': 'error', 'message': 'Missing essential metadata'}, status=200)

        if session.payment_status == 'paid':
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'User not found'}, status=200)

            idempotency_key = f"stripe_session_{session.id}"
            if CoinTransaction.objects.filter(description__icontains=idempotency_key).exists() or \
               AudiobookPurchase.objects.filter(stripe_checkout_session_id=session.id).exists():
                return JsonResponse({'status': 'already_processed'})

            payment_brand, payment_last4 = None, None
            # Logic to retrieve payment_brand/payment_last4 would go here

            try:
                with transaction.atomic():
                    user_locked = User.objects.select_for_update().get(pk=user.pk)

                    if item_type == 'subscription' and item_id in ['monthly', 'annual']:
                        plan = item_id
                        if plan == 'monthly': price = Decimal('350.00'); pack_name = "Monthly Premium Subscription"; end_date = timezone.now() + timezone.timedelta(days=30)
                        else: price = Decimal('3500.00'); pack_name = "Annual Premium Subscription"; end_date = timezone.now() + timezone.timedelta(days=365)
                        stripe_subscription_id = session.get('subscription')
                        stripe_customer_id = session.get('customer')

                        sub, created = Subscription.objects.update_or_create(
                            user=user_locked,
                            defaults={
                                'plan': plan, 'start_date': timezone.now(), 'end_date': end_date, 'status': 'active',
                                'stripe_subscription_id': stripe_subscription_id, 'stripe_customer_id': stripe_customer_id,
                                'stripe_payment_method_brand': payment_brand, 'stripe_payment_method_last4': payment_last4,
                            }
                        )
                        if user_locked.subscription_type != 'PR':
                            user_locked.subscription_type = 'PR'
                            user_locked.save(update_fields=['subscription_type'])
                        try:
                            CoinTransaction.objects.create(
                                user=user_locked, transaction_type='purchase', amount=0, status='completed',
                                pack_name=pack_name, price=price, description=f"{idempotency_key}"
                            )
                        except Exception as log_e: pass # Log failure

                    elif item_type == 'coins':
                        coins_str = item_id
                        try:
                            coins_to_grant = int(coins_str)
                            if coins_to_grant <= 0: raise ValueError("Coins must be positive.")
                            if coins_to_grant == 250: price_paid = Decimal('250.00'); pack_name = "Starter Pack"
                            elif coins_to_grant == 500: price_paid = Decimal('500.00'); pack_name = "Value Pack"
                            elif coins_to_grant == 1000: price_paid = Decimal('1000.00'); pack_name = "Pro Pack"
                            else:
                                price_paid = Decimal(coins_to_grant); pack_name = f"{coins_to_grant} Coins"

                            user_locked.coins = F('coins') + coins_to_grant
                            user_locked.save(update_fields=['coins'])
                            try:
                                CoinTransaction.objects.create(
                                    user=user_locked, transaction_type='purchase', amount=coins_to_grant, status='completed',
                                    pack_name=pack_name, price=price_paid, description=f"{idempotency_key}"
                                )
                            except Exception as log_e: pass # Log failure
                        except (ValueError, TypeError, InvalidOperation) as e:
                            return JsonResponse({'status': 'error', 'message': 'Invalid coin data in metadata'}, status=200)

                    elif item_type == 'audiobook':
                        audiobook_slug = item_id
                        try:
                            audiobook = Audiobook.objects.select_related('creator').get(slug=audiobook_slug)
                            creator = audiobook.creator

                            if AudiobookPurchase.objects.filter(user=user_locked, audiobook=audiobook).exists():
                                return JsonResponse({'status': 'already_processed'})

                            amount_paid_paisa = session.amount_total
                            amount_paid_pkr = (Decimal(amount_paid_paisa) / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                            platform_fee_percentage = Decimal('10.00')
                            platform_fee_amount = (amount_paid_pkr * platform_fee_percentage / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                            creator_share_amount = amount_paid_pkr - platform_fee_amount

                            purchase = AudiobookPurchase.objects.create(
                                user=user_locked,
                                audiobook=audiobook,
                                amount_paid=amount_paid_pkr,
                                platform_fee_percentage=platform_fee_percentage,
                                platform_fee_amount=platform_fee_amount,
                                creator_share_amount=creator_share_amount,
                                stripe_checkout_session_id=session.id,
                                stripe_payment_intent_id=session.payment_intent
                            )

                            earning = CreatorEarning.objects.create(
                                creator=creator,
                                audiobook=audiobook,
                                purchase=purchase,
                                amount_earned=creator_share_amount,
                                notes=f"Sale via Stripe Session: {session.id}"
                            )

                            creator_locked = Creator.objects.select_for_update().get(pk=creator.pk)
                            creator_locked.total_earning = F('total_earning') + amount_paid_pkr
                            creator_locked.available_balance = F('available_balance') + creator_share_amount
                            creator_locked.save(update_fields=['total_earning', 'available_balance'])

                            audiobook_locked = Audiobook.objects.select_for_update().get(pk=audiobook.pk)
                            audiobook_locked.total_sales = F('total_sales') + 1
                            audiobook_locked.total_revenue_generated = F('total_revenue_generated') + amount_paid_pkr
                            audiobook_locked.save(update_fields=['total_sales', 'total_revenue_generated'])

                        except Audiobook.DoesNotExist:
                            return JsonResponse({'status': 'error', 'message': 'Audiobook not found'}, status=200)
                        except Creator.DoesNotExist:
                            return JsonResponse({'status': 'error', 'message': 'Creator not found'}, status=200)
                        except Exception as fulfill_error:
                            return JsonResponse({'error': 'Internal server error during audiobook fulfillment'}, status=500)
                    else:
                        return JsonResponse({'status': 'error', 'message': 'Unknown item type'}, status=200)
            except Exception as e:
                return JsonResponse({'error': 'Internal server error during fulfillment transaction'}, status=500)
        else:
            pass # Payment not successful

    elif event.type == 'customer.subscription.updated':
        pass
    elif event.type == 'customer.subscription.deleted':
        pass
    elif event.type == 'invoice.paid':
        pass
    elif event.type == 'invoice.payment_failed':
        pass
    else:
        pass # Unhandled event type

    return JsonResponse({'status': 'success'})
