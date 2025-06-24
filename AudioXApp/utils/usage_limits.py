# AudioXApp/utils/usage_limits.py

"""
Usage limits utility functions for FREE vs PREMIUM users.
Handles checking and incrementing usage counters for various features.
"""

import logging
from django.db import transaction
from django.utils import timezone
from typing import Tuple

logger = logging.getLogger(__name__)

def check_and_increment_document_conversion(user) -> Tuple[bool, str]:
    """
    Check if user can perform document-to-audio conversion and increment usage if allowed.
    
    Args:
        user: User instance
        
    Returns:
        Tuple[bool, str]: (can_use, error_message)
    """
    try:
        with transaction.atomic():
            # Lock the user record to prevent race conditions
            user_locked = user.__class__.objects.select_for_update().get(pk=user.pk)
            
            # Check if user can use the feature
            can_use, error_message = user_locked.can_use_document_conversion()
            
            if can_use:
                # Increment usage counter
                user_locked.increment_document_conversion_usage()
                logger.info(f"Document conversion usage incremented for user {user_locked.username}. New count: {user_locked.monthly_document_conversions}")
                return True, None
            else:
                logger.info(f"Document conversion blocked for user {user_locked.username}: {error_message}")
                return False, error_message
                
    except Exception as e:
        logger.error(f"Error in check_and_increment_document_conversion for user {user.username}: {e}", exc_info=True)
        return False, "An error occurred while checking usage limits. Please try again."

def check_and_increment_coin_gift(user) -> Tuple[bool, str]:
    """
    Check if user can gift coins and increment usage if allowed.
    
    Args:
        user: User instance
        
    Returns:
        Tuple[bool, str]: (can_use, error_message)
    """
    try:
        with transaction.atomic():
            # Lock the user record to prevent race conditions
            user_locked = user.__class__.objects.select_for_update().get(pk=user.pk)
            
            # Check if user can gift coins
            can_gift, error_message = user_locked.can_gift_coins()
            
            if can_gift:
                # Increment usage counter
                user_locked.increment_coin_gift_usage()
                logger.info(f"Coin gift usage incremented for user {user_locked.username}. New count: {user_locked.monthly_coin_gifts}")
                return True, None
            else:
                logger.info(f"Coin gift blocked for user {user_locked.username}: {error_message}")
                return False, error_message
                
    except Exception as e:
        logger.error(f"Error in check_and_increment_coin_gift for user {user.username}: {e}", exc_info=True)
        return False, "An error occurred while checking usage limits. Please try again."

def get_usage_summary(user) -> dict:
    """
    Get a comprehensive usage summary for the user.
    
    Args:
        user: User instance
        
    Returns:
        dict: Usage summary with all feature limits and current usage
    """
    try:
        return user.get_usage_status()
    except Exception as e:
        logger.error(f"Error getting usage summary for user {user.username}: {e}", exc_info=True)
        return {
            'is_premium': user.subscription_type == 'PR',
            'document_conversions': {'used': 0, 'limit': 'Error', 'remaining': 'Error'},
            'coin_gifts': {'used': 0, 'limit': 'Error', 'remaining': 'Error'}
        }

def reset_user_monthly_counters(user) -> bool:
    """
    Manually reset monthly counters for a user (admin function).
    
    Args:
        user: User instance
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with transaction.atomic():
            user_locked = user.__class__.objects.select_for_update().get(pk=user.pk)
            
            now = timezone.now()
            user_locked.monthly_document_conversions = 0
            user_locked.last_document_conversion_reset = now
            user_locked.monthly_coin_gifts = 0
            user_locked.last_coin_gift_reset = now
            
            user_locked.save(update_fields=[
                'monthly_document_conversions', 
                'last_document_conversion_reset',
                'monthly_coin_gifts', 
                'last_coin_gift_reset'
            ])
            
            logger.info(f"Monthly counters reset for user {user_locked.username}")
            return True
            
    except Exception as e:
        logger.error(f"Error resetting monthly counters for user {user.username}: {e}", exc_info=True)
        return False

def check_feature_availability(user, feature_name: str) -> Tuple[bool, str]:
    """
    Check if a specific feature is available for the user without incrementing usage.
    
    Args:
        user: User instance
        feature_name: Name of the feature ('document_conversion' or 'coin_gift')
        
    Returns:
        Tuple[bool, str]: (is_available, message)
    """
    try:
        if feature_name == 'document_conversion':
            return user.can_use_document_conversion()
        elif feature_name == 'coin_gift':
            return user.can_gift_coins()
        else:
            return False, f"Unknown feature: {feature_name}"
            
    except Exception as e:
        logger.error(f"Error checking feature availability for user {user.username}, feature {feature_name}: {e}", exc_info=True)
        return False, "An error occurred while checking feature availability."

def get_upgrade_message(user, feature_name: str) -> str:
    """
    Get an appropriate upgrade message for the user based on the feature.
    
    Args:
        user: User instance
        feature_name: Name of the feature
        
    Returns:
        str: Upgrade message
    """
    if user.subscription_type == 'PR':
        return "You have unlimited access to all features with your Premium subscription."
    
    base_message = "Upgrade to Premium for unlimited access to all features!"
    
    if feature_name == 'document_conversion':
        return f"You've reached your monthly limit for document-to-audio conversions. {base_message}"
    elif feature_name == 'coin_gift':
        return f"You've reached your monthly limit for coin gifting. {base_message}"
    else:
        return base_message
