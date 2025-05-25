# AudioXApp/views/user_views/payment_processing_views.py

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import datetime # Keep for fromtimestamp
import logging
import stripe
from django.db import IntegrityError


from django.shortcuts import redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt, csrf_protect 
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.urls import reverse

from ...models import User, CoinTransaction, Subscription, Audiobook, AudiobookPurchase, Creator, CreatorEarning # Relative import
# from ..utils import _get_full_context # _get_full_context might not be needed here if these are API endpoints

logger = logging.getLogger(__name__)

# Configure Stripe API key
if hasattr(settings, 'STRIPE_SECRET_KEY') and settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY
else:
    logger.critical("CRITICAL: Stripe Secret Key not configured in settings. Payment processing will FAIL.")


# --- Stripe Payment Views ---

@login_required
@require_POST # Should be a POST request to create a session
@csrf_protect # Protect this endpoint as it initiates a payment flow
def create_checkout_session(request):
    """Creates a Stripe Checkout Session for purchasing coins, subscriptions, or audiobooks."""
    try:
        data = json.loads(request.body)
        item_type = data.get('item_type')
        item_id = data.get('item_id') # For coins/subscriptions, this is the pack/plan ID. For audiobooks, it's the slug.

        if not item_type or not item_id:
            return JsonResponse({'error': 'Item type and ID are required.'}, status=400)

        stripe_price_ids = {
            'coins': {
                '250': getattr(settings, 'STRIPE_PRICE_ID_COINS_250', None),
                '500': getattr(settings, 'STRIPE_PRICE_ID_COINS_500', None),
                '1000': getattr(settings, 'STRIPE_PRICE_ID_COINS_1000', None),
            },
            'subscription': {
                'monthly': getattr(settings, 'STRIPE_PRICE_ID_SUB_MONTHLY', None),
                'annual': getattr(settings, 'STRIPE_PRICE_ID_SUB_ANNUAL', None),
            }
        }

        price_lookup = None
        mode = None
        success_url_path = None
        cancel_url_path = None
        line_items = []
        metadata = {
            'django_user_id': request.user.pk, # Use pk for user ID
            'item_type': item_type,
            'item_id': str(item_id), # Ensure item_id is a string for metadata
        }

        if item_type == 'subscription':
            price_lookup = stripe_price_ids.get(item_type, {}).get(str(item_id))
            if not price_lookup:
                logger.error(f"Stripe price ID not found for subscription plan: {item_id}")
                return JsonResponse({'error': f'Pricing information not found for subscription plan ({item_id}). Please contact support.'}, status=400)
            
            mode = 'subscription'
            success_url_path = reverse('AudioXApp:managesubscription') + '?stripe_session_id={CHECKOUT_SESSION_ID}&status=success'
            cancel_url_path = reverse('AudioXApp:subscribe') + '?status=cancel'
            line_items = [{'price': price_lookup, 'quantity': 1}]

            try: # Check if user already has an active subscription
                current_subscription = Subscription.objects.get(user=request.user)
                if current_subscription.is_active() or \
                   (current_subscription.status == 'canceled' and current_subscription.end_date and current_subscription.end_date > timezone.now()):
                    return JsonResponse({'status': 'already_subscribed', 'message': 'You already have an active subscription.', 'redirect_url': reverse('AudioXApp:managesubscription')})
            except Subscription.DoesNotExist:
                pass # User does not have a subscription, can proceed

        elif item_type == 'coins':
            price_lookup = stripe_price_ids.get(item_type, {}).get(str(item_id))
            if not price_lookup:
                logger.error(f"Stripe price ID not found for coin pack: {item_id}")
                return JsonResponse({'error': f'Pricing information not found for coin pack ({item_id}). Please contact support.'}, status=400)
            
            mode = 'payment'
            success_url_path = reverse('AudioXApp:mywallet') + '?stripe_session_id={CHECKOUT_SESSION_ID}&status=success'
            cancel_url_path = reverse('AudioXApp:buycoins') + '?status=cancel'
            line_items = [{'price': price_lookup, 'quantity': 1}]

        elif item_type == 'audiobook':
            audiobook_slug = str(item_id)
            try:
                audiobook = Audiobook.objects.get(slug=audiobook_slug)
                if not audiobook.is_paid or audiobook.price <= 0:
                    return JsonResponse({'error': 'This audiobook is not available for purchase.'}, status=400)

                if request.user.has_purchased_audiobook(audiobook): # Assumes has_purchased_audiobook method on User model
                    return JsonResponse({'status': 'already_purchased', 'message': 'You have already purchased this audiobook.'})

                mode = 'payment'
                success_url_path = reverse('AudioXApp:audiobook_detail', kwargs={'audiobook_slug': audiobook.slug}) + '?purchase=success&session_id={CHECKOUT_SESSION_ID}'
                cancel_url_path = reverse('AudioXApp:audiobook_detail', kwargs={'audiobook_slug': audiobook.slug}) + '?purchase=cancel'
                
                try:
                    amount_in_paisa = int(audiobook.price * 100) # Stripe expects amount in smallest currency unit
                except (TypeError, InvalidOperation):
                    logger.error(f"Invalid price format for audiobook {audiobook.slug}: {audiobook.price}")
                    return JsonResponse({'error': 'Invalid price format for audiobook.'}, status=500)

                line_items = [{
                    'price_data': {
                        'currency': 'pkr', # Ensure this matches your Stripe account currency
                        'product_data': {
                            'name': f'Audiobook: {audiobook.title}',
                            'description': f'Purchase of audiobook "{audiobook.title}" by {audiobook.creator.creator_name if audiobook.creator else "Unknown Creator"}',
                            # 'images': [audiobook.cover_image.url if audiobook.cover_image else 'default_image_url'] # Optional
                        },
                        'unit_amount': amount_in_paisa,
                    },
                    'quantity': 1,
                }]
            except Audiobook.DoesNotExist:
                return JsonResponse({'error': 'Audiobook not found.'}, status=404)
            except Exception as e_ab:
                logger.error(f"Error retrieving audiobook details for checkout ({audiobook_slug}): {e_ab}", exc_info=True)
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
                'allow_promotion_codes': True, # Allow discount codes if you use them
            }
            # If it's a subscription and user might already be a Stripe customer
            if mode == 'subscription':
                try:
                    existing_subscription_details = Subscription.objects.get(user=request.user)
                    if existing_subscription_details.stripe_customer_id:
                        checkout_session_params['customer'] = existing_subscription_details.stripe_customer_id
                except Subscription.DoesNotExist:
                    pass # No existing Stripe customer ID for this user in our DB

            checkout_session = stripe.checkout.Session.create(**checkout_session_params)
            return JsonResponse({'sessionId': checkout_session.id})

        except stripe.error.InvalidRequestError as e_stripe_req:
            logger.error(f"Stripe InvalidRequestError creating checkout session: {e_stripe_req}", exc_info=True)
            error_message = str(e_stripe_req)
            # Provide more user-friendly messages for common configuration errors
            if "You cannot use `line_items.price_data` in `subscription` mode" in error_message:
                 error_message = "Configuration error with subscription pricing. Please contact support."
            return JsonResponse({'error': f'Payment Provider Error: {error_message}'}, status=400)
        except Exception as e_checkout:
            logger.error(f"Error creating Stripe checkout session: {e_checkout}", exc_info=True)
            return JsonResponse({'error': 'Could not initiate payment session. Please try again or contact support.'}, status=500)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request data format (expected JSON).'}, status=400)
    except Exception as e_main: # Catch-all for other unexpected errors
        logger.error(f"Unexpected error in create_checkout_session: {e_main}", exc_info=True)
        return JsonResponse({'error': 'An unexpected server error occurred.'}, status=500)


@csrf_exempt # Stripe webhooks require CSRF exemption
@require_POST
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)

    if not endpoint_secret:
        logger.critical("CRITICAL: Stripe Webhook Secret not configured on server. Webhook processing will fail.")
        return JsonResponse({'error': 'Webhook secret not configured on server.'}, status=500)

    event = None
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError as e_val: # Invalid payload
        logger.error(f"Stripe webhook ValueError (Invalid payload): {e_val}", exc_info=True)
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError as e_sig: # Invalid signature
        logger.error(f"Stripe webhook SignatureVerificationError: {e_sig}", exc_info=True)
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    except Exception as e_construct: # Other construction errors
        logger.error(f"Stripe webhook construction error: {e_construct}", exc_info=True)
        return JsonResponse({'error': 'Webhook processing error during construction'}, status=500)

    logger.info(f"Stripe webhook received: Event ID {event.id}, Type {event.type}")

    # Handle the checkout.session.completed event
    if event.type == 'checkout.session.completed':
        session = event.data.object
        metadata = session.get('metadata', {})
        user_id = metadata.get('django_user_id')
        item_type = metadata.get('item_type')
        item_id = metadata.get('item_id') # This was the plan_id, coin_pack_id, or audiobook_slug

        if not user_id or not item_type or not item_id:
            logger.error(f"Stripe webhook 'checkout.session.completed' missing essential metadata: UserID {user_id}, ItemType {item_type}, ItemID {item_id}. Session: {session.id}")
            return JsonResponse({'status': 'error', 'message': 'Missing essential metadata.'}, status=200) # Stripe expects 200 for ack

        if session.payment_status == 'paid':
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                logger.error(f"User with ID {user_id} not found for Stripe webhook fulfillment. Session: {session.id}")
                return JsonResponse({'status': 'error', 'message': 'User not found.'}, status=200)

            idempotency_key_description = f"stripe_checkout_session_{session.id}" # For coin/audiobook one-time payments
            stripe_subscription_id_from_session = session.get('subscription') # For subscriptions

            # Idempotency check: Has this session already been processed?
            already_processed = False
            if item_type == 'subscription':
                if stripe_subscription_id_from_session and Subscription.objects.filter(stripe_subscription_id=stripe_subscription_id_from_session).exists():
                    already_processed = True
            elif item_type == 'coins': # Check CoinTransaction based on description
                if CoinTransaction.objects.filter(description=idempotency_key_description).exists():
                    already_processed = True
            elif item_type == 'audiobook': # Check AudiobookPurchase based on session ID
                if AudiobookPurchase.objects.filter(stripe_checkout_session_id=session.id).exists():
                    already_processed = True
            
            if already_processed:
                logger.info(f"Stripe webhook 'checkout.session.completed' for session {session.id} already processed.")
                return JsonResponse({'status': 'already_processed'})

            payment_intent_id = session.get('payment_intent')
            payment_brand, payment_last4 = None, None
            if payment_intent_id:
                try:
                    payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                    if payment_intent.payment_method:
                        payment_method_id = payment_intent.payment_method
                        if isinstance(payment_method_id, str): # It can be an object or ID string
                            payment_method_obj = stripe.PaymentMethod.retrieve(payment_method_id)
                            if payment_method_obj.card:
                                payment_brand = payment_method_obj.card.brand
                                payment_last4 = payment_method_obj.card.last4
                except stripe.error.StripeError as e_pi:
                    logger.warning(f"Could not retrieve payment method details from PaymentIntent {payment_intent_id}: {e_pi}")
                except Exception as e_pi_unknown:
                     logger.warning(f"Unknown error retrieving payment method details from PaymentIntent {payment_intent_id}: {e_pi_unknown}")


            try:
                with transaction.atomic():
                    user_locked = User.objects.select_for_update().get(pk=user.pk) # Lock user row

                    if item_type == 'subscription' and item_id in ['monthly', 'annual']:
                        plan_type = item_id
                        sub_prices_settings = getattr(settings, 'SUBSCRIPTION_PRICES', {})
                        sub_durations_settings = getattr(settings, 'SUBSCRIPTION_DURATIONS', {})
                        default_price_str = sub_prices_settings.get(plan_type, '350.00' if plan_type == 'monthly' else '3500.00')
                        duration_days = sub_durations_settings.get(plan_type, 30 if plan_type == 'monthly' else 365)
                        pack_name = "Monthly Premium Subscription" if plan_type == 'monthly' else "Annual Premium Subscription"
                        
                        price = Decimal('0.00')
                        try:
                            amount_total_from_stripe = session.get('amount_total') # Amount in smallest currency unit (e.g., paisa)
                            if amount_total_from_stripe is not None:
                                price = (Decimal(amount_total_from_stripe) / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                            else: price = Decimal(default_price_str)
                        except (InvalidOperation, TypeError): price = Decimal(default_price_str) # Fallback

                        end_date = timezone.now() + timezone.timedelta(days=duration_days)
                        stripe_customer_id_from_session = session.get('customer')

                        if not stripe_subscription_id_from_session:
                            logger.error(f"CRITICAL: Stripe subscription ID missing in checkout.session.completed for user {user_id}, session {session.id}")
                            return JsonResponse({'status': 'error', 'message': 'Internal error: Missing Stripe subscription ID.'}, status=200)

                        sub, created = Subscription.objects.update_or_create(
                            user=user_locked,
                            defaults={
                                'plan': plan_type, 'start_date': timezone.now(), 'end_date': end_date, 'status': 'active',
                                'stripe_subscription_id': stripe_subscription_id_from_session,
                                'stripe_customer_id': stripe_customer_id_from_session,
                                'stripe_payment_method_brand': payment_brand,
                                'stripe_payment_method_last4': payment_last4,
                            }
                        )
                        # If not created, it means we are updating. Ensure all fields are updated.
                        if not created:
                            sub.plan = plan_type; sub.start_date = timezone.now(); sub.end_date = end_date; sub.status = 'active'
                            sub.stripe_subscription_id = stripe_subscription_id_from_session # Ensure it's updated if changed
                            sub.stripe_customer_id = stripe_customer_id_from_session
                            sub.stripe_payment_method_brand = payment_brand
                            sub.stripe_payment_method_last4 = payment_last4
                            sub.save()
                        
                        if user_locked.subscription_type != 'PR':
                            user_locked.subscription_type = 'PR'
                            user_locked.save(update_fields=['subscription_type'])
                        
                        # Log this as a CoinTransaction for billing history
                        CoinTransaction.objects.update_or_create(
                            description=idempotency_key_description, # Use session ID to make it unique for this checkout
                            defaults={
                                'user': user_locked, 'transaction_type': 'purchase', 'amount': 0, # No direct coins for subscription
                                'status': 'completed', 'pack_name': pack_name, 'price': price
                            }
                        )
                        logger.info(f"Subscription '{plan_type}' activated for user {user.username} via Stripe session {session.id}")

                    elif item_type == 'coins':
                        coins_pack_id_str = str(item_id) # Ensure it's a string for dict lookup
                        try:
                            coins_to_grant = int(coins_pack_id_str)
                            if coins_to_grant <= 0: raise ValueError("Coins must be positive.")

                            coin_prices_settings = getattr(settings, 'COIN_PACK_PRICES', {}) # e.g., {'250': '250.00', ...}
                            default_price_str = coin_prices_settings.get(coins_pack_id_str)
                            pack_name = f"{coins_to_grant} Coins Pack" # Default pack name
                            
                            # More descriptive pack names
                            if coins_to_grant == 250: pack_name = "Starter Pack (250 Coins)"
                            elif coins_to_grant == 500: pack_name = "Value Pack (500 Coins)"
                            elif coins_to_grant == 1000: pack_name = "Pro Pack (1000 Coins)"
                            # Add more specific names if you have other packs

                            if default_price_str is None: # Fallback if price not in settings
                                default_price_str = f"{coins_to_grant}.00" # Simple fallback, adjust as needed
                                logger.warning(f"Price for coin pack '{coins_pack_id_str}' not found in COIN_PACK_PRICES settings. Using fallback.")
                            
                            price_paid = Decimal('0.00')
                            try:
                                amount_total_from_stripe = session.get('amount_total')
                                if amount_total_from_stripe is not None:
                                    price_paid = (Decimal(amount_total_from_stripe) / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                                else: price_paid = Decimal(default_price_str)
                            except (InvalidOperation, TypeError): price_paid = Decimal(default_price_str)

                            user_locked.coins = ('coins') + coins_to_grant
                            user_locked.save(update_fields=['coins'])
                            user_locked.refresh_from_db(fields=['coins']) # Get the updated value for logging

                            CoinTransaction.objects.update_or_create(
                                description=idempotency_key_description, # Use session ID
                                defaults={
                                    'user': user_locked, 'transaction_type': 'purchase', 'amount': coins_to_grant,
                                    'status': 'completed', 'pack_name': pack_name, 'price': price_paid
                                }
                            )
                            logger.info(f"{coins_to_grant} coins added to user {user.username}. New balance: {user_locked.coins}. Stripe session {session.id}")
                        except (ValueError, TypeError) as e_coin:
                            logger.error(f"Invalid coin data in metadata for Stripe session {session.id}: {e_coin}", exc_info=True)
                            return JsonResponse({'status': 'error', 'message': 'Invalid coin data in metadata.'}, status=200)

                    elif item_type == 'audiobook':
                        audiobook_slug = str(item_id)
                        try:
                            audiobook = Audiobook.objects.select_related('creator').get(slug=audiobook_slug)
                            creator = audiobook.creator # Can be None if not a creator book, handle this
                            
                            # Idempotency check specifically for this audiobook purchase via this session
                            if AudiobookPurchase.objects.filter(stripe_checkout_session_id=session.id).exists():
                                logger.info(f"Audiobook purchase for {audiobook_slug} via session {session.id} already processed.")
                                return JsonResponse({'status': 'already_processed'})

                            amount_paid_paisa = session.amount_total # Amount in smallest currency unit (e.g., paisa)
                            amount_paid_pkr = (Decimal(amount_paid_paisa) / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                            platform_fee_percentage_str = getattr(settings, 'PLATFORM_FEE_PERCENTAGE_AUDIOBOOK', '10.00')
                            try: platform_fee_percentage = Decimal(platform_fee_percentage_str)
                            except InvalidOperation: platform_fee_percentage = Decimal('10.00') # Default

                            platform_fee_amount = (amount_paid_pkr * platform_fee_percentage / Decimal('100.00')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                            creator_share_amount = amount_paid_pkr - platform_fee_amount

                            purchase = AudiobookPurchase.objects.create(
                                user=user_locked, audiobook=audiobook, amount_paid=amount_paid_pkr,
                                platform_fee_percentage=platform_fee_percentage,
                                platform_fee_amount=platform_fee_amount,
                                creator_share_amount=creator_share_amount,
                                stripe_checkout_session_id=session.id, # Store session ID
                                stripe_payment_intent_id=payment_intent_id, # Store payment intent ID
                                status='COMPLETED' # Mark as completed
                            )
                            
                            # Update creator earnings and audiobook sales stats if it's a creator's book
                            if creator and creator.is_approved: # Check if creator exists and is approved
                                creator_locked = Creator.objects.select_for_update().get(pk=creator.pk)
                                creator_locked.total_earning = ('total_earning') + amount_paid_pkr # Gross amount for creator's total
                                creator_locked.available_balance = ('available_balance') + creator_share_amount # Net for withdrawal
                                creator_locked.save(update_fields=['total_earning', 'available_balance'])

                                CreatorEarning.objects.create(
                                    creator=creator_locked, audiobook=audiobook, purchase=purchase,
                                    amount_earned=creator_share_amount, earning_type='sale',
                                    notes=f"Sale via Stripe Checkout Session: {session.id}",
                                    audiobook_title_at_transaction=audiobook.title # Denormalize title
                                )
                            
                            # Update audiobook's own sales stats
                            audiobook_locked = Audiobook.objects.select_for_update().get(pk=audiobook.pk)
                            audiobook_locked.total_sales = ('total_sales') + 1
                            audiobook_locked.total_revenue_generated = ('total_revenue_generated') + amount_paid_pkr
                            audiobook_locked.save(update_fields=['total_sales', 'total_revenue_generated'])
                            logger.info(f"Audiobook '{audiobook.title}' purchased by user {user.username}. Stripe session {session.id}")

                        except Audiobook.DoesNotExist:
                            logger.error(f"Audiobook with slug {audiobook_slug} not found for Stripe fulfillment. Session: {session.id}")
                            return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=200)
                        except Creator.DoesNotExist: # If audiobook.creator points to a non-existent creator
                            logger.error(f"Creator for audiobook {audiobook_slug} not found during Stripe fulfillment. Session: {session.id}")
                            # Decide if purchase should still proceed without creator earning update or fail
                            return JsonResponse({'status': 'error', 'message': 'Creator data error for audiobook.'}, status=500) # Or 200 if purchase is okay
                        except Exception as e_ab_fulfill:
                            logger.error(f"Error fulfilling audiobook purchase for {audiobook_slug}, session {session.id}: {e_ab_fulfill}", exc_info=True)
                            return JsonResponse({'error': 'Internal server error during audiobook fulfillment.'}, status=500) # Or 200
                    else:
                        logger.error(f"Unknown item_type '{item_type}' in Stripe webhook metadata. Session: {session.id}")
                        return JsonResponse({'status': 'error', 'message': 'Unknown item type in metadata.'}, status=200)

            except IntegrityError as e_int: # e.g. if update_or_create fails due to unique constraint not on PK
                logger.error(f"IntegrityError during Stripe webhook fulfillment for session {session.id}: {e_int}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': 'Database conflict during fulfillment.'}, status=200) # Ack to Stripe
            except Exception as e_fulfill: # Catch-all for other errors during fulfillment
                logger.error(f"General error during Stripe webhook fulfillment for session {session.id}: {e_fulfill}", exc_info=True)
                return JsonResponse({'error': 'Internal server error during fulfillment.'}, status=500) # Or 200
        else: # Payment not successful
            logger.warning(f"Checkout session {session.id} completed but payment_status is '{session.payment_status}'. No action taken.")
            pass # Or handle other payment_statuses if necessary

    elif event.type == 'customer.subscription.updated':
        subscription_data = event.data.object
        stripe_sub_id = subscription_data.id
        try:
            with transaction.atomic():
                local_sub = Subscription.objects.select_for_update().get(stripe_subscription_id=stripe_sub_id)
                user_locked = User.objects.select_for_update().get(pk=local_sub.user.pk)

                stripe_status = subscription_data.status
                original_local_status = local_sub.status
                
                # Map Stripe status to local status
                if stripe_status == 'active': local_sub.status = 'active'
                elif stripe_status == 'canceled': local_sub.status = 'canceled' # User cancelled, active until period end
                elif stripe_status in ['past_due', 'unpaid']: local_sub.status = 'past_due'
                elif stripe_status == 'trialing': local_sub.status = 'active' # Treat trialing as active
                else: local_sub.status = 'expired' # Default for other statuses like incomplete_expired

                # Update period end
                if subscription_data.current_period_end:
                    local_sub.end_date = timezone.make_aware(datetime.datetime.fromtimestamp(subscription_data.current_period_end))
                else: # Should not happen for active subscriptions
                    local_sub.end_date = None 
                
                # If Stripe says it's cancelled at period end AND that period end has passed, mark as expired
                if subscription_data.cancel_at_period_end and local_sub.end_date and timezone.now() >= local_sub.end_date:
                    local_sub.status = 'expired'

                fields_to_save = []
                if local_sub.status != original_local_status: fields_to_save.append('status')
                # Check if end_date actually changed before adding to update_fields
                # This requires fetching the current DB state or trusting the webhook is the source of truth
                # For simplicity, we'll update if the calculated local_sub.end_date is different from what it might have been
                current_db_end_date = Subscription.objects.get(pk=local_sub.pk).end_date # Get current from DB
                if local_sub.end_date != current_db_end_date : fields_to_save.append('end_date')
                
                # Update payment method details if available and changed
                if 'default_payment_method' in subscription_data and subscription_data.default_payment_method:
                    pm_id = subscription_data.default_payment_method
                    if isinstance(pm_id, str): # Ensure it's an ID string
                        try:
                            pm_obj = stripe.PaymentMethod.retrieve(pm_id)
                            if pm_obj.card:
                                if local_sub.stripe_payment_method_brand != pm_obj.card.brand:
                                    local_sub.stripe_payment_method_brand = pm_obj.card.brand
                                    fields_to_save.append('stripe_payment_method_brand')
                                if local_sub.stripe_payment_method_last4 != pm_obj.card.last4:
                                    local_sub.stripe_payment_method_last4 = pm_obj.card.last4
                                    fields_to_save.append('stripe_payment_method_last4')
                        except stripe.error.StripeError as e_pm_retrieve:
                            logger.warning(f"Could not retrieve new payment method {pm_id} for sub {stripe_sub_id}: {e_pm_retrieve}")


                if fields_to_save: # Only save if there are actual changes
                    local_sub.save(update_fields=list(set(fields_to_save))) # Use set to ensure unique fields
                    logger.info(f"Subscription {stripe_sub_id} for user {local_sub.user.username} updated. New status: {local_sub.status}, End date: {local_sub.end_date}")

                # Update user's main subscription type if local subscription became expired
                if local_sub.status == 'expired' and user_locked.subscription_type == 'PR':
                    user_locked.subscription_type = 'FR'
                    user_locked.save(update_fields=['subscription_type'])
                    logger.info(f"User {user_locked.username} subscription type changed to FR due to expired Stripe subscription {stripe_sub_id}.")
                elif local_sub.status == 'active' and user_locked.subscription_type != 'PR':
                    user_locked.subscription_type = 'PR'
                    user_locked.save(update_fields=['subscription_type'])
                    logger.info(f"User {user_locked.username} subscription type changed to PR due to active Stripe subscription {stripe_sub_id}.")


        except Subscription.DoesNotExist:
            logger.warning(f"Received Stripe 'customer.subscription.updated' event for non-existent local subscription: {stripe_sub_id}")
            pass # No local subscription to update
        except Exception as e_sub_update:
            logger.error(f"Error processing 'customer.subscription.updated' for Stripe sub ID {stripe_sub_id}: {e_sub_update}", exc_info=True)
            return JsonResponse({'error': 'Internal server error processing subscription update.'}, status=500) # Or 200 to ack

    elif event.type == 'customer.subscription.deleted': # Subscription permanently deleted in Stripe
        subscription_data = event.data.object
        stripe_sub_id = subscription_data.id
        try:
            with transaction.atomic():
                local_sub = Subscription.objects.select_for_update().get(stripe_subscription_id=stripe_sub_id)
                user_locked = User.objects.select_for_update().get(pk=local_sub.user.pk)
                
                local_sub.status = 'expired' # Or a new status like 'deleted'
                local_sub.end_date = timezone.now() # Mark end as now
                local_sub.save(update_fields=['status', 'end_date'])

                if user_locked.subscription_type == 'PR':
                    user_locked.subscription_type = 'FR'
                    user_locked.save(update_fields=['subscription_type'])
                logger.info(f"Stripe subscription {stripe_sub_id} deleted, local record for user {local_sub.user.username} marked as expired.")
        except Subscription.DoesNotExist:
            logger.warning(f"Received Stripe 'customer.subscription.deleted' event for non-existent local subscription: {stripe_sub_id}")
            pass
        except Exception as e_sub_deleted:
            logger.error(f"Error processing 'customer.subscription.deleted' for Stripe sub ID {stripe_sub_id}: {e_sub_deleted}", exc_info=True)
            return JsonResponse({'error': 'Internal server error processing subscription deletion.'}, status=500) # Or 200

    elif event.type == 'invoice.paid':
        invoice = event.data.object
        stripe_subscription_id = getattr(invoice, 'subscription', None) # Subscription ID from invoice

        # Handle subscription renewal payments
        if stripe_subscription_id and invoice.billing_reason == 'subscription_cycle':
            try:
                with transaction.atomic():
                    local_sub = Subscription.objects.select_for_update().get(stripe_subscription_id=stripe_subscription_id)
                    user_locked = User.objects.select_for_update().get(pk=local_sub.user.pk)

                    update_fields = ['status'] # Status will likely change to active
                    local_sub.status = 'active'

                    # Update period start/end from the invoice
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
                    
                    # Update payment method from charge if available
                    charge_id = getattr(invoice, 'charge', None)
                    if charge_id and isinstance(charge_id, str):
                        try:
                            charge = stripe.Charge.retrieve(charge_id)
                            if charge.payment_method_details and charge.payment_method_details.card:
                                if local_sub.stripe_payment_method_brand != charge.payment_method_details.card.brand:
                                    local_sub.stripe_payment_method_brand = charge.payment_method_details.card.brand
                                    update_fields.append('stripe_payment_method_brand')
                                if local_sub.stripe_payment_method_last4 != charge.payment_method_details.card.last4:
                                    local_sub.stripe_payment_method_last4 = charge.payment_method_details.card.last4
                                    update_fields.append('stripe_payment_method_last4')
                        except stripe.error.StripeError as e_charge:
                            logger.warning(f"Could not retrieve charge {charge_id} details for invoice {invoice.id}: {e_charge}")

                    if update_fields: # Only save if there are changes
                        local_sub.save(update_fields=list(set(update_fields)))
                    
                    if user_locked.subscription_type != 'PR': # Ensure user is marked as premium
                        user_locked.subscription_type = 'PR'
                        user_locked.save(update_fields=['subscription_type'])

                    # Log this renewal as a CoinTransaction for billing history
                    pack_name = "Monthly Premium Renewal" if local_sub.plan == 'monthly' else "Annual Premium Renewal"
                    price = Decimal(invoice.amount_paid / 100.0) # amount_paid is in smallest unit
                    idempotency_key_description = f"stripe_invoice_{invoice.id}" # Use invoice ID for idempotency
                    
                    CoinTransaction.objects.update_or_create(
                        description=idempotency_key_description,
                        defaults={
                            'user': user_locked, 'transaction_type': 'purchase', 'amount': 0,
                            'status': 'completed', 'pack_name': pack_name, 'price': price
                        }
                    )
                    logger.info(f"Subscription renewal processed for user {local_sub.user.username} from invoice {invoice.id}.")
            except Subscription.DoesNotExist:
                logger.warning(f"Received 'invoice.paid' for unknown Stripe subscription ID: {stripe_subscription_id}")
            except Exception as e_invoice_paid:
                logger.error(f"Error processing 'invoice.paid' for Stripe subscription ID {stripe_subscription_id}: {e_invoice_paid}", exc_info=True)
                return JsonResponse({'error': 'Internal server error during invoice.paid renewal processing.'}, status=500) # Or 200
        
        elif invoice.billing_reason == 'subscription_create': # Initial subscription payment, handled by checkout.session.completed
            logger.info(f"Received 'invoice.paid' for subscription_create (invoice: {invoice.id}). Handled by checkout.session.completed.")
            pass 
        else:
            logger.info(f"Received 'invoice.paid' with unhandled billing_reason: {invoice.billing_reason} (invoice: {invoice.id})")
            pass

    elif event.type == 'invoice.payment_failed':
        invoice = event.data.object
        stripe_subscription_id = getattr(invoice, 'subscription', None)
        if stripe_subscription_id:
            try:
                with transaction.atomic():
                    local_sub = Subscription.objects.select_for_update().get(stripe_subscription_id=stripe_subscription_id)
                    if local_sub.status != 'past_due': # Or other appropriate status like 'failed'
                        local_sub.status = 'past_due' # Mark as past_due, Stripe might retry
                        local_sub.save(update_fields=['status'])
                        logger.info(f"Subscription {stripe_subscription_id} for user {local_sub.user.username} marked as 'past_due' due to failed payment (invoice: {invoice.id}).")
            except Subscription.DoesNotExist:
                logger.warning(f"Received 'invoice.payment_failed' for unknown Stripe subscription ID: {stripe_subscription_id}")
            except Exception as e_payment_failed:
                logger.error(f"Error processing 'invoice.payment_failed' for Stripe subscription ID {stripe_subscription_id}: {e_payment_failed}", exc_info=True)
                return JsonResponse({'error': 'Internal server error processing payment failure.'}, status=500) # Or 200
        else:
            logger.info(f"Received 'invoice.payment_failed' without a subscription ID (invoice: {invoice.id}).")
            pass # Payment failure not related to a subscription we track by ID

    else:
        logger.info(f"Unhandled Stripe event type received: {event.type}")
        pass # Unhandled event type

    return JsonResponse({'status': 'success'}) # Acknowledge receipt of the event to Stripe
