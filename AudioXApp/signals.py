"""
============================================================================
AUDIOX PLATFORM - DJANGO SIGNALS
============================================================================
Signal handlers for automatic model processing and user management.

This file contains signal handlers that automatically process model
changes, initialize new records, and handle user authentication flows.

Key Features:
- New user initialization with proper usage limits (COIN GIFT BUG FIX)
- Social authentication profile completion handling
- Creator earnings from free audiobook views
- Comprehensive logging for debugging and monitoring

Author: AudioX Development Team
Version: 2.1
Last Updated: 2024
============================================================================
"""

import logging
from decimal import Decimal

from django.dispatch import receiver
from django.urls import reverse
from django.conf import settings
from django.db.models.signals import post_save
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from allauth.account.signals import user_logged_in
from allauth.socialaccount.signals import social_account_added

from .models import User, AudiobookViewLog, CreatorEarning, Creator

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# USER INITIALIZATION SIGNALS (COIN GIFT BUG FIX)
# ============================================================================

@receiver(post_save, sender=User)  # FIXED: Removed created=True from decorator
def initialize_new_user_limits(sender, instance, created, **kwargs):
    """
    Initialize usage limits for newly created users.
    
    CRITICAL BUG FIX: Set reset dates to 30+ days ago so new users get full 
    allowance immediately instead of seeing 0 remaining gifts/conversions.
    """
    # Only process newly created FREE users
    if created and instance.subscription_type == 'FR':
        thirty_one_days_ago = timezone.now() - timezone.timedelta(days=31)
        
        try:
            # Update the user's usage tracking fields
            User.objects.filter(pk=instance.pk).update(
                monthly_document_conversions=0,
                last_document_conversion_reset=thirty_one_days_ago,
                monthly_coin_gifts=0,
                last_coin_gift_reset=thirty_one_days_ago
            )
            
            logger.info(f"COIN GIFT FIX: Initialized usage limits for new FREE user: {instance.username} (ID: {instance.pk})")
            logger.debug(f"Set reset dates to {thirty_one_days_ago} for user {instance.username}")
            
        except Exception as e:
            logger.error(f"ERROR: Failed to initialize usage limits for user {instance.pk}: {e}", exc_info=True)

# ============================================================================
# SOCIAL AUTHENTICATION SIGNALS
# ============================================================================

def needs_profile_completion(user):
    """
    Check if user needs to complete their profile after social signup.
    
    Args:
        user: User instance to check
        
    Returns:
        bool: True if profile completion is needed
    """
    # Check if full name is missing or empty
    if not hasattr(user, 'full_name') or not user.full_name or not user.full_name.strip():
        return True
    
    # Check if phone number is missing
    if not hasattr(user, 'phone_number') or not user.phone_number:
        return True
    
    return False

@receiver(user_logged_in)
def handle_user_logged_in(sender, request, user, **kwargs):
    """
    Handle user login and check for profile completion requirements.
    
    This signal is triggered when a user logs in (both regular and social login).
    It checks if the user needs to complete their profile and sets appropriate
    session variables for redirection.
    
    Args:
        sender: Signal sender
        request: HTTP request object
        user: User instance that logged in
        **kwargs: Additional signal arguments
    """
    try:
        if needs_profile_completion(user):
            # User needs to complete profile
            next_url = request.GET.get('next')
            if not next_url:
                next_url = request.session.get('socialaccount_login_redirect_url') or \
                           request.session.get('account_login_redirect_url')
            
            request.session['next_url_after_profile_completion'] = next_url or reverse('AudioXApp:home')
            request.session['profile_incomplete'] = True
            
            logger.info(f"User {user.username} needs profile completion after login")
        else:
            # Profile is complete, clear any existing flags
            if 'profile_incomplete' in request.session:
                del request.session['profile_incomplete']
            if 'next_url_after_profile_completion' in request.session:
                del request.session['next_url_after_profile_completion']
                
            logger.debug(f"User {user.username} logged in with complete profile")
            
    except Exception as e:
        logger.error(f"Error in handle_user_logged_in for user {user.pk}: {e}", exc_info=True)

@receiver(social_account_added)
def handle_social_account_added(request, sociallogin, **kwargs):
    """
    Handle social account addition and profile completion requirements.
    
    This signal is triggered when a user connects a social account.
    It checks if profile completion is needed after social signup.
    
    Args:
        request: HTTP request object
        sociallogin: Social login instance
        **kwargs: Additional signal arguments
    """
    try:
        user = sociallogin.user
        
        if needs_profile_completion(user):
            # User needs to complete profile after social signup
            next_url = request.GET.get('next')
            request.session['next_url_after_profile_completion'] = next_url or reverse('AudioXApp:home')
            request.session['profile_incomplete'] = True
            
            logger.info(f"Social user {user.username} needs profile completion")
        else:
            # Profile is complete, clear any existing flags
            if 'profile_incomplete' in request.session:
                del request.session['profile_incomplete']
            if 'next_url_after_profile_completion' in request.session:
                del request.session['next_url_after_profile_completion']
                
            logger.debug(f"Social user {user.username} has complete profile")
            
    except Exception as e:
        logger.error(f"Error in handle_social_account_added: {e}", exc_info=True)

# ============================================================================
# CREATOR EARNINGS SIGNALS
# ============================================================================

@receiver(post_save, sender=AudiobookViewLog)
def create_creator_earning_for_free_audiobook_view(sender, instance, created, **kwargs):
    """
    Create creator earnings when users view free audiobooks.
    
    This signal automatically generates earnings for creators when their
    free audiobooks are viewed, providing a revenue stream for free content.
    
    Args:
        sender: AudiobookViewLog model class
        instance: The view log instance that was created
        created: Boolean indicating if this is a new record
        **kwargs: Additional signal arguments
    """
    # Only process new view logs
    if not created:
        return
    
    try:
        audiobook = instance.audiobook
        
        # Validate audiobook eligibility for earnings
        if not audiobook or audiobook.is_paid or not audiobook.is_creator_book:
            logger.debug(f"Audiobook {audiobook.title if audiobook else 'None'} not eligible for view earnings")
            return
        
        # Only process published audiobooks
        if audiobook.status != 'PUBLISHED':
            logger.debug(f"Audiobook {audiobook.title} not published, skipping view earning")
            return
        
        # Validate creator
        creator = audiobook.creator
        if not creator or not creator.is_approved:
            logger.debug(f"Creator for audiobook {audiobook.title} not approved, skipping view earning")
            return
        
        # Get earning amount from settings
        earning_per_view = Decimal(getattr(settings, 'CREATOR_EARNING_PER_FREE_VIEW', '1.00'))
        
        # Create earning record and update creator balance
        with transaction.atomic():
            creator_earning = CreatorEarning.objects.create(
                creator=creator,
                audiobook=audiobook,
                earning_type='view',
                amount_earned=earning_per_view,
                transaction_date=instance.viewed_at,
                view_count_for_earning=1,
                earning_per_view_at_transaction=earning_per_view,
                audiobook_title_at_transaction=audiobook.title,
                notes=f"Earning from view logged at {instance.viewed_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            # Update creator's balance atomically
            Creator.objects.filter(pk=creator.pk).update(
                available_balance=F('available_balance') + earning_per_view,
                total_earning=F('total_earning') + earning_per_view
            )
            
            logger.info(f"Created earning of PKR {earning_per_view} for creator {creator.creator_name} from view of free audiobook '{audiobook.title}'")
            
    except Exception as e:
        logger.error(f"Error creating creator earning for view log {instance.view_id}: {e}", exc_info=True)

