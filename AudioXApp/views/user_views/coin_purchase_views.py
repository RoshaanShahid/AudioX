# Updated coin_purchase_views.py with correct model references

import json
from decimal import Decimal, InvalidOperation
import logging
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError

from ...models import User, Audiobook, AudiobookPurchase, Creator, CreatorEarning, CoinTransaction, CoinPurchase

logger = logging.getLogger(__name__)

@login_required
@require_POST
@csrf_protect
def purchase_audiobook_with_coins(request):
    """
    Handle coin-based audiobook purchases.
    Validates user's coin balance, deducts coins, creates purchase record,
    and credits creator with the same commission logic as Stripe purchases.
    """
    try:
        data = json.loads(request.body)
        audiobook_slug = data.get('audiobook_slug', '').strip()
        
        if not audiobook_slug:
            return JsonResponse({
                'status': 'error',
                'message': 'Audiobook identifier is required.'
            }, status=400)
        
        # Get the audiobook
        try:
            audiobook = Audiobook.objects.select_related('creator').get(
                slug=audiobook_slug,
                status='PUBLISHED',
                is_paid=True
            )
        except Audiobook.DoesNotExist:
            logger.warning(f"Audiobook with slug '{audiobook_slug}' not found or not available for purchase by user {request.user.username}")
            return JsonResponse({
                'status': 'error',
                'message': 'Audiobook not found or not available for purchase.'
            }, status=404)
        
        # Validate audiobook is purchasable
        if not audiobook.is_paid or audiobook.price <= 0:
            return JsonResponse({
                'status': 'error',
                'message': 'This audiobook is not available for coin purchase.'
            }, status=400)
        
        # Check if user already purchased this audiobook (check both Stripe and Coin purchases)
        stripe_purchase_exists = AudiobookPurchase.objects.filter(
            user=request.user, 
            audiobook=audiobook, 
            status='COMPLETED'
        ).exists()
        
        coin_purchase_exists = CoinPurchase.objects.filter(
            user=request.user,
            audiobook=audiobook
        ).exists()
        
        if stripe_purchase_exists or coin_purchase_exists:
            return JsonResponse({
                'status': 'already_purchased',
                'message': 'You have already purchased this audiobook.',
                'redirect_url': f'/audiobook/{audiobook.slug}/'
            })
        
        # Convert price to coins (1 PKR = 1 Coin)
        coins_required = int(audiobook.price)
        
        # Start atomic transaction
        with transaction.atomic():
            # Lock user record to prevent race conditions
            user_locked = User.objects.select_for_update().get(pk=request.user.pk)
            
            # Check if user has sufficient coins
            if user_locked.coins < coins_required:
                return JsonResponse({
                    'status': 'insufficient_coins',
                    'message': f'Insufficient coins. You need {coins_required} coins but have {user_locked.coins} coins.',
                    'coins_needed': coins_required,
                    'coins_available': user_locked.coins,
                    'coins_short': coins_required - user_locked.coins
                }, status=400)
            
            # Calculate platform commission (same logic as Stripe)
            platform_fee_percentage_str = getattr(settings, 'PLATFORM_FEE_PERCENTAGE_AUDIOBOOK', '10.00')
            try:
                platform_fee_percentage = Decimal(platform_fee_percentage_str)
            except InvalidOperation:
                platform_fee_percentage = Decimal('10.00')
                logger.warning(f"Invalid PLATFORM_FEE_PERCENTAGE_AUDIOBOOK setting: '{platform_fee_percentage_str}'. Using default 10.00%")
            
            amount_paid_pkr = audiobook.price
            platform_fee_amount = (amount_paid_pkr * platform_fee_percentage / Decimal('100.00')).quantize(Decimal("0.01"))
            creator_share_amount = amount_paid_pkr - platform_fee_amount
            
            # Deduct coins from user
            user_locked.coins = F('coins') - coins_required
            user_locked.save(update_fields=['coins'])
            user_locked.refresh_from_db(fields=['coins'])
            
            # Create coin transaction record for the purchase
            coin_transaction = CoinTransaction.objects.create(
                user=user_locked,
                transaction_type='spent',
                amount=-coins_required,
                status='completed',
                description=f"Purchased audiobook: {audiobook.title}",
                pack_name=f"Audiobook Purchase: {audiobook.title}",
                related_audiobook=audiobook  # Link to the purchased audiobook
            )
            
            # Create coin purchase record (separate from Stripe purchases)
            coin_purchase = CoinPurchase.objects.create(
                user=user_locked,
                audiobook=audiobook,
                coins_spent=coins_required,
                creator_earning=creator_share_amount,
                platform_commission=platform_fee_amount
            )
            
            # Credit creator if they exist and are approved
            creator = audiobook.creator
            if creator and creator.is_approved:
                try:
                    creator_locked = Creator.objects.select_for_update().get(pk=creator.pk)
                    
                    # Update creator earnings
                    creator_locked.total_earning = F('total_earning') + amount_paid_pkr
                    creator_locked.available_balance = F('available_balance') + creator_share_amount
                    creator_locked.save(update_fields=['total_earning', 'available_balance'])
                    
                    # Create creator earning record
                    CreatorEarning.objects.create(
                        creator=creator_locked,
                        audiobook=audiobook,
                        purchase=None,  # No Stripe purchase for coin purchases
                        amount_earned=creator_share_amount,
                        earning_type='sale',
                        notes=f"Coin purchase by {user_locked.username}. Transaction ID: {coin_transaction.id}",
                        audiobook_title_at_transaction=audiobook.title
                    )
                    
                    logger.info(f"Creator {creator.creator_name} credited PKR {creator_share_amount} for coin purchase of '{audiobook.title}' by {user_locked.username}")
                    
                except Creator.DoesNotExist:
                    logger.error(f"Creator for audiobook '{audiobook.title}' not found during coin purchase fulfillment")
                except Exception as e:
                    logger.error(f"Error crediting creator for coin purchase: {e}", exc_info=True)
                    # Don't fail the purchase if creator crediting fails
            
            # Update audiobook sales analytics
            try:
                audiobook_locked = Audiobook.objects.select_for_update().get(pk=audiobook.pk)
                audiobook_locked.total_sales = F('total_sales') + 1
                audiobook_locked.total_revenue_generated = F('total_revenue_generated') + amount_paid_pkr
                audiobook_locked.save(update_fields=['total_sales', 'total_revenue_generated'])
            except Exception as e:
                logger.error(f"Error updating audiobook analytics for coin purchase: {e}", exc_info=True)
                # Don't fail the purchase if analytics update fails
            
            logger.info(f"Coin purchase completed: User {user_locked.username} purchased '{audiobook.title}' for {coins_required} coins. New balance: {user_locked.coins}")
            
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully purchased "{audiobook.title}" for {coins_required} coins!',
                'purchase_id': str(coin_purchase.id),
                'coins_spent': coins_required,
                'new_coin_balance': user_locked.coins,
                'audiobook_title': audiobook.title,
                'creator_earned': float(creator_share_amount) if creator and creator.is_approved else 0,
                'platform_fee': float(platform_fee_amount),
                'redirect_url': f'/audiobook/{audiobook.slug}/?purchase=success&method=coins'
            })
            
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid request data format.'
        }, status=400)
    
    except IntegrityError as e:
        logger.error(f"Database integrity error during coin purchase by {request.user.username}: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': 'A database error occurred. Please try again.'
        }, status=500)
    
    except Exception as e:
        logger.error(f"Unexpected error during coin purchase by {request.user.username}: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': 'An unexpected error occurred. Please try again.'
        }, status=500)


@login_required
def check_coin_purchase_eligibility(request, audiobook_slug):
    """
    Check if user can purchase the audiobook with coins.
    Returns user's coin balance, audiobook price, and eligibility status.
    """
    try:
        # Get the audiobook
        try:
            audiobook = Audiobook.objects.select_related('creator').get(
                slug=audiobook_slug,
                status='PUBLISHED',
                is_paid=True
            )
        except Audiobook.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Audiobook not found or not available for purchase.'
            }, status=404)
        
        # Check if already purchased (both Stripe and Coin purchases)
        stripe_purchase_exists = AudiobookPurchase.objects.filter(
            user=request.user,
            audiobook=audiobook,
            status='COMPLETED'
        ).exists()
        
        coin_purchase_exists = CoinPurchase.objects.filter(
            user=request.user,
            audiobook=audiobook
        ).exists()
        
        already_purchased = stripe_purchase_exists or coin_purchase_exists
        
        if already_purchased:
            return JsonResponse({
                'status': 'already_purchased',
                'message': 'You have already purchased this audiobook.'
            })
        
        # Calculate coin requirements
        coins_required = int(audiobook.price)
        user_coins = request.user.coins
        can_afford = user_coins >= coins_required
        coins_short = max(0, coins_required - user_coins)
        
        return JsonResponse({
            'status': 'success',
            'eligible': can_afford,
            'audiobook_title': audiobook.title,
            'audiobook_price_pkr': float(audiobook.price),
            'coins_required': coins_required,
            'user_coins': user_coins,
            'can_afford': can_afford,
            'coins_short': coins_short,
            'already_purchased': False
        })
        
    except Exception as e:
        logger.error(f"Error checking coin purchase eligibility for {audiobook_slug} by {request.user.username}: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': 'Could not check purchase eligibility.'
        }, status=500)


@login_required
def get_user_coin_balance(request):
    """
    Simple endpoint to get current user's coin balance.
    Useful for real-time balance updates in the frontend.
    """
    try:
        return JsonResponse({
            'status': 'success',
            'coin_balance': request.user.coins
        })
    except Exception as e:
        logger.error(f"Error getting coin balance for {request.user.username}: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': 'Could not retrieve coin balance.'
        }, status=500)
