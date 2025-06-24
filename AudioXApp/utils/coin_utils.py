from decimal import Decimal
from django.db import transaction
from django.contrib.auth.models import User
from ..models import CoinPurchase, CoinTransaction, Audiobook

def calculate_coin_commission(audiobook_price_pkr, coins_spent):
    total_amount = Decimal(str(audiobook_price_pkr))
    creator_percentage = Decimal('0.70')
    platform_percentage = Decimal('0.30')
    creator_earning = total_amount * creator_percentage
    platform_commission = total_amount * platform_percentage
    return creator_earning, platform_commission

def has_sufficient_coins(user, required_coins):
    if not user.is_authenticated:
        return False
    return user.coins >= required_coins

def deduct_coins(user, amount, description, related_audiobook=None):
    if not has_sufficient_coins(user, amount):
        return False
    
    with transaction.atomic():
        user.coins -= amount
        user.save()
        
        CoinTransaction.objects.create(
            user=user,
            transaction_type='spent',
            amount=-amount,
            status='completed',
            description=description,
            related_audiobook=related_audiobook
        )
    
    return True

def process_coin_purchase(user, audiobook, coins_required):
    try:
        with transaction.atomic():
            if CoinPurchase.objects.filter(user=user, audiobook=audiobook).exists():
                return False, "You already own this audiobook!", None
            
            if not has_sufficient_coins(user, coins_required):
                coins_short = coins_required - user.coins
                return False, f"Insufficient coins. You need {coins_short} more coins.", None
            
            creator_earning, platform_commission = calculate_coin_commission(
                audiobook.price, coins_required
            )
            
            if not deduct_coins(user, coins_required, f"Purchase: {audiobook.title}", audiobook):
                return False, "Failed to deduct coins. Please try again.", None
            
            purchase = CoinPurchase.objects.create(
                user=user,
                audiobook=audiobook,
                coins_spent=coins_required,
                creator_earning=creator_earning,
                platform_commission=platform_commission
            )
            
            if hasattr(audiobook.creator, 'creatorprofile'):
                audiobook.creator.creatorprofile.total_earnings += creator_earning
                audiobook.creator.creatorprofile.save()
            
            return True, f"Successfully purchased '{audiobook.title}' with {coins_required} coins!", purchase
            
    except Exception as e:
        return False, f"Purchase failed: {str(e)}", None

def get_audiobook_coin_price(audiobook):
    if not audiobook.is_paid:
        return 0
    return int(audiobook.price)

def user_owns_audiobook_via_coins(user, audiobook):
    if not user.is_authenticated:
        return False
    return CoinPurchase.objects.filter(user=user, audiobook=audiobook).exists()
