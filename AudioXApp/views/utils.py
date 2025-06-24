"""
============================================================================
AUDIOX PLATFORM - VIEW UTILITY FUNCTIONS
============================================================================
Comprehensive utility functions for preparing template context data across
the AudioX platform including user authentication, creator management,
subscription handling, and usage limit tracking.

Features:
- User authentication and subscription context
- Creator profile and verification status management
- Usage limit tracking for FREE vs PREMIUM users
- JavaScript context preparation for frontend functionality
- Comprehensive error handling and logging

Author: AudioX Development Team
Version: 2.1 (COIN GIFT BUG FIX)
Last Updated: 2024
============================================================================
"""

# ============================================================================
# IMPORTS AND DEPENDENCIES
# ============================================================================

import json
import logging
from django.urls import reverse, NoReverseMatch
from django.conf import settings as django_settings
from ..models import User, Creator

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# CREATOR CONTEXT MANAGEMENT
# ============================================================================

def get_creator_context(user):
    """
    Prepare creator-specific context data for templates.
    
    Handles creator verification status, ban management, application tracking,
    and popup notifications for creator-related UI elements.
    
    Args:
        user: Django User instance
        
    Returns:
        dict: Creator context data including status, permissions, and UI flags
    """
    # Initialize default creator context
    context = {
        'is_creator': False,
        'creator_status': None, 
        'is_banned': False,
        'ban_reason': None,
        'can_reapply': False,
        'rejection_reason': None,
        'show_welcome_popup': False,
        'show_rejection_popup': False,
        'application_attempts_current_month': 0,
        'max_application_attempts': getattr(django_settings, 'MAX_CREATOR_APPLICATION_ATTEMPTS', 3)
    }

    # Return default context for unauthenticated users
    if not user.is_authenticated:
        return context

    # ============================================================================
    # RETRIEVE CREATOR PROFILE WITH ERROR HANDLING
    # ============================================================================
    
    creator_profile = None
    try:
        if hasattr(user, 'creator_profile') and user.creator_profile is not None:
            creator_profile = user.creator_profile
    except Creator.DoesNotExist:
        logger.warning(f"Creator.DoesNotExist for user {user.pk} when accessing creator_profile.")
        creator_profile = None
    except AttributeError:
        logger.info(f"User {user.pk} does not have a 'creator_profile' attribute.")
        creator_profile = None
    except Exception as e:
        logger.error(f"Error accessing creator_profile for user {user.pk}: {e}", exc_info=True)
        creator_profile = None

    # ============================================================================
    # PROCESS CREATOR PROFILE DATA
    # ============================================================================
    
    if creator_profile:
        # Basic creator status information
        context['creator_status'] = creator_profile.verification_status
        context['is_banned'] = creator_profile.is_banned
        context['ban_reason'] = creator_profile.ban_reason if context['is_banned'] else None
        
        # Determine if user is an active creator
        if creator_profile.verification_status == 'approved' and not creator_profile.is_banned:
            context['is_creator'] = True
            # Check if welcome popup should be shown
            if not creator_profile.welcome_popup_shown:
                context['show_welcome_popup'] = True

        # Application attempt tracking
        context['application_attempts_current_month'] = creator_profile.get_attempts_this_month()

        # Handle rejected applications
        if creator_profile.verification_status == 'rejected':
            context['can_reapply'] = creator_profile.can_reapply()
            context['rejection_reason'] = creator_profile.rejection_reason
            # Check if rejection popup should be shown
            if not creator_profile.rejection_popup_shown:
                context['show_rejection_popup'] = True
    else:
        # User has no creator profile - hasn't applied yet
        context['creator_status'] = 'not_applied' 
        
    return context

# ============================================================================
# MAIN CONTEXT PREPARATION FUNCTION
# ============================================================================

def _get_full_context(request):
    """
    Prepare comprehensive context data for Django templates.
    
    UPDATED FOR COIN GIFT BUG FIX: Now includes proper usage status tracking
    to ensure FREE users see correct remaining limits instead of always showing 0.
    
    This function consolidates all necessary context data including:
    - User authentication and subscription status
    - Usage limits and remaining allowances (FIXED)
    - Creator profile and verification status
    - Admin user context
    - JavaScript context for frontend functionality
    
    Args:
        request: Django HTTP request object
        
    Returns:
        dict: Comprehensive context dictionary for template rendering
    """
    user = request.user
    base_context = {}
    
    # ============================================================================
    # ADMIN USER CONTEXT
    # ============================================================================
    
    # Handle admin user context if present
    admin_user_from_request = getattr(request, 'admin_user', None)
    base_context['admin_user'] = admin_user_from_request

    # ============================================================================
    # USER AUTHENTICATION AND SUBSCRIPTION CONTEXT
    # ============================================================================
    
    if user.is_authenticated:
        try:
            # CRITICAL FIX: Refresh user data to ensure we have latest information
            user.refresh_from_db()
            
            # CRITICAL FIX: Get updated usage status using our corrected method
            usage_status = user.get_usage_status()
            
            logger.debug(f"Context prepared for user {user.username}: {usage_status}")
            
            # Prepare comprehensive user context
            base_context.update({
                'user': user, 
                'is_authenticated': True,
                'subscription_type': user.subscription_type,
                'is_premium_user': (user.subscription_type == 'PR'),
                'is_free_user': (user.subscription_type == 'FR'),
                'is_2fa_enabled': user.is_2fa_enabled,
                'user_coins': user.coins,
                'usage_status': usage_status,  # CRITICAL FIX: Add usage status to context
            })
            
            # Add convenience flags for templates
            base_context['has_unlimited_gifts'] = usage_status['is_premium']
            base_context['has_unlimited_conversions'] = usage_status['is_premium']
            
            # Add remaining limits for easy template access
            if not usage_status['is_premium']:
                base_context['remaining_coin_gifts'] = usage_status['coin_gifts']['remaining']
                base_context['remaining_document_conversions'] = usage_status['document_conversions']['remaining']
                base_context['coin_gift_limit'] = usage_status['coin_gifts']['limit']
                base_context['document_conversion_limit'] = usage_status['document_conversions']['limit']
            
        except AttributeError as e:
            logger.error(f"AttributeError on request.user (pk: {user.pk if hasattr(user, 'pk') else 'N/A'}) in _get_full_context: {e}. Using defaults.", exc_info=True)
            # Fallback context with safe defaults
            base_context.update({ 
                'user': user, 
                'is_authenticated': True, 
                'subscription_type': 'FR', 
                'is_premium_user': False,
                'is_free_user': True,
                'is_2fa_enabled': False, 
                'user_coins': 0,
                'usage_status': None,  # Will be handled by templates
            })
        except Exception as e:
            logger.error(f"Unexpected error processing user data in _get_full_context for user {user.pk if hasattr(user, 'pk') else 'N/A'}: {e}", exc_info=True)
            # Fallback context with safe defaults
            base_context.update({ 
                'user': user, 
                'is_authenticated': True, 
                'subscription_type': 'FR',
                'is_premium_user': False,
                'is_free_user': True,
                'is_2fa_enabled': False, 
                'user_coins': 0,
                'usage_status': None,  # Will be handled by templates
            })
    else: 
        # ============================================================================
        # UNAUTHENTICATED USER CONTEXT
        # ============================================================================
        base_context.update({
            'user': user, 
            'is_authenticated': False, 
            'subscription_type': 'NA', 
            'is_premium_user': False,
            'is_free_user': False,
            'is_2fa_enabled': False, 
            'user_coins': 0,
            'usage_status': None,
        })

    # ============================================================================
    # CREATOR-SPECIFIC CONTEXT
    # ============================================================================
    
    # Add creator context (verification status, ban status, etc.)
    creator_specific_context = get_creator_context(user)
    base_context.update(creator_specific_context)

    # ============================================================================
    # JAVASCRIPT CONTEXT PREPARATION
    # ============================================================================
    
    # Prepare URLs for AJAX endpoints (with error handling)
    mark_welcome_url = None
    mark_rejection_url = None
    if user.is_authenticated:
        try:
            mark_welcome_url = reverse('AudioXApp:api_mark_welcome_popup')
        except NoReverseMatch:
            logger.warning("URL 'AudioXApp:api_mark_welcome_popup' not found.")
        try:
            mark_rejection_url = reverse('AudioXApp:api_mark_rejection_popup')
        except NoReverseMatch:
            logger.warning("URL 'AudioXApp:api_mark_rejection_popup' not found.")

    # Determine creator status for JavaScript context
    js_creator_status_for_popup = base_context.get('creator_status', 'not_applicable')
    if base_context.get('is_banned'): 
        js_creator_status_for_popup = 'banned'
    
    # Prepare JavaScript context data for frontend
    creator_js_context_data = {
        'is_creator': base_context.get('is_creator', False),
        'creator_status': js_creator_status_for_popup,
        'can_reapply': base_context.get('can_reapply', False), 
        'rejectionReason': base_context.get('rejection_reason'),
        'showWelcomePopup': base_context.get('show_welcome_popup', False),
        'showRejectionPopup': base_context.get('show_rejection_popup', False),
        'applicationAttemptsCurrentMonth': base_context.get('application_attempts_current_month', 0),
        'max_application_attempts': base_context.get('max_application_attempts', getattr(django_settings, 'MAX_CREATOR_APPLICATION_ATTEMPTS', 3)),
        'isBanned': base_context.get('is_banned', False),
        'banReason': base_context.get('ban_reason'),
        'markWelcomeUrl': mark_welcome_url,
        'markRejectionUrl': mark_rejection_url,
    }
    base_context['creator_js_context'] = creator_js_context_data
    
    return base_context

# ============================================================================
# ADDITIONAL UTILITY FUNCTIONS
# ============================================================================

def get_user_usage_summary(user):
    """
    Get a formatted summary of user's usage limits.
    
    Convenience function for displaying usage information in templates
    or for API responses.
    
    Args:
        user: Django User instance
        
    Returns:
        dict: Formatted usage summary
    """
    if not user.is_authenticated:
        return {}
    
    usage_status = user.get_usage_status()
    
    if usage_status['is_premium']:
        return {
            'subscription_type': 'Premium',
            'coin_gifts': 'Unlimited',
            'document_conversions': 'Unlimited',
            'status': 'premium'
        }
    else:
        coin_gifts = usage_status['coin_gifts']
        document_conversions = usage_status['document_conversions']
        
        return {
            'subscription_type': 'Free',
            'coin_gifts': f"{coin_gifts['remaining']}/{coin_gifts['limit']}",
            'document_conversions': f"{document_conversions['remaining']}/{document_conversions['limit']}",
            'status': 'free',
            'limits_reached': {
                'coin_gifts': coin_gifts['remaining'] <= 0,
                'document_conversions': document_conversions['remaining'] <= 0
            }
        }

def check_feature_access(user, feature_type):
    """
    Check if user has access to a specific feature based on subscription and usage limits.
    
    Args:
        user: Django User instance
        feature_type: String ('coin_gifts' or 'document_conversions')
        
    Returns:
        tuple: (has_access: bool, reason: str)
    """
    if not user.is_authenticated:
        return False, "User not authenticated"
    
    if feature_type == 'coin_gifts':
        can_gift, error_msg = user.can_gift_coins()
        return can_gift, error_msg
    elif feature_type == 'document_conversions':
        can_convert, error_msg = user.can_use_document_conversion()
        return can_convert, error_msg
    else:
        return False, "Unknown feature type"

