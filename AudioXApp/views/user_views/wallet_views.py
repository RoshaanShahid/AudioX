"""
AudioX Wallet Views - User Coin Management System
Handles coin purchases, gifting, and transaction history.
"""

import json
import logging
from decimal import Decimal

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.db import transaction, IntegrityError
from django.conf import settings

from ...models import User, CoinTransaction

logger = logging.getLogger(__name__)

# ============================================================================
# MAIN VIEWS
# ============================================================================

@login_required
def buycoins(request):
    """Display coin purchase page with purchase history."""
    try:
        logger.info(f"Buy coins page accessed by user: {request.user.username}")
        
        # Get purchase history (exclude subscription transactions)
        purchase_history = CoinTransaction.objects.filter(
            user=request.user, 
            transaction_type='purchase'
        ).exclude(
            pack_name__in=[
                'Monthly Premium Subscription', 
                'Annual Premium Subscription', 
                'Monthly Premium Renewal', 
                'Annual Premium Renewal'
            ]
        ).order_by('-transaction_date')

        # Prepare context
        request.user.refresh_from_db()
        usage_status = request.user.get_usage_status()

        context = {
            'user': request.user,
            'usage_status': usage_status,
            'purchase_history': purchase_history,
            'STRIPE_PUBLISHABLE_KEY': getattr(settings, 'STRIPE_PUBLISHABLE_KEY', ''),
        }
        
        logger.info(f"Buy coins page loaded successfully for user: {request.user.username}")
        return render(request, 'user/buycoins.html', context)
        
    except Exception as e:
        logger.error(f"Error loading buy coins page for user {request.user.username}: {e}", exc_info=True)
        messages.error(request, 'Unable to load the buy coins page. Please try again.')
        return redirect('AudioXApp:mywallet')


@login_required
@require_POST
@csrf_protect
@transaction.atomic
def gift_coins(request):
    """Handle coin gifting via AJAX with proper validation and limits."""
    try:
        logger.info(f"Gift coins request initiated by user: {request.user.username}")
        
        # Parse request data
        data = None
        try:
            # First, try to load as JSON, which is the intended method for AJAX
            data = json.loads(request.body)
        except json.JSONDecodeError:
            # If JSON loading fails, check if data was sent as form data (fallback)
            logger.warning(f"Could not decode JSON from request body for user {request.user.username}. Checking POST data as fallback.")
            if request.POST:
                data = request.POST
            else:
                # If it's not JSON and not in POST, it's a malformed request
                logger.error(f"Request from user {request.user.username} is not valid JSON and has no POST data.")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Invalid request data format.'
                }, status=400)

        sender = request.user
        recipient_identifier = data.get('recipient', '').strip()
        amount_str = data.get('amount')

        # Validate required fields
        if not recipient_identifier or not amount_str:
            return JsonResponse({
                'status': 'error', 
                'message': 'Recipient and amount are required.'
            }, status=400)

        # Validate and parse amount
        try:
            amount = int(amount_str)
            if amount <= 0:
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Gift amount must be positive.'
                }, status=400)
            if amount > 1000000:
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Gift amount exceeds maximum limit.'
                }, status=400)
        except (ValueError, TypeError):
            return JsonResponse({
                'status': 'error', 
                'message': 'Invalid gift amount format.'
            }, status=400)

        # Find recipient user
        try:
            if '@' in recipient_identifier:
                recipient = User.objects.get(email__iexact=recipient_identifier)
            else:
                recipient = User.objects.get(username__iexact=recipient_identifier)
            
            if recipient == sender:
                return JsonResponse({
                    'status': 'error', 
                    'message': 'You cannot gift coins to yourself.'
                }, status=400)
                
        except User.DoesNotExist:
            logger.info(f"Gift attempt to non-existent user: {recipient_identifier} by {sender.username}")
            return JsonResponse({
                'status': 'error', 
                'message': 'Recipient user not found.'
            }, status=404)

        # Check usage limits for FREE users
        if sender.subscription_type == 'FR':
            can_gift, error_msg = sender.can_gift_coins()
            if not can_gift:
                logger.info(f"FREE user {sender.username} reached gift limit: {error_msg}")
                return JsonResponse({
                    'status': 'limit_reached',
                    'message': error_msg or 'You have reached your monthly gift limit. Upgrade to Premium for unlimited gifting.'
                }, status=403)

        # Process transaction with database locking
        sender_locked = User.objects.select_for_update().get(pk=sender.pk)
        
        if sender_locked.coins < amount:
            return JsonResponse({
                'status': 'error', 
                'message': 'Insufficient coins for this gift.'
            }, status=400)

        # Update balances
        sender_locked.coins -= amount
        sender_locked.save(update_fields=['coins'])
        
        recipient_locked = User.objects.select_for_update().get(pk=recipient.pk)
        recipient_locked.coins += amount
        recipient_locked.save(update_fields=['coins'])

        # Create transaction records
        sender_transaction = CoinTransaction.objects.create(
            user=sender_locked, 
            transaction_type='gift_sent', 
            amount=-amount,
            recipient=recipient_locked, 
            status='completed',
            description=f"Gifted {amount} coins to {recipient_locked.username}"
        )
        
        CoinTransaction.objects.create(
            user=recipient_locked, 
            transaction_type='gift_received', 
            amount=amount,
            sender=sender_locked, 
            status='completed',
            description=f"Received {amount} coins from {sender_locked.username}"
        )
        
        # Update usage counter for FREE users
        if sender.subscription_type == 'FR':
            sender_locked.increment_coin_gift_usage()

        # Prepare response
        sender.refresh_from_db()
        updated_usage_status = sender.get_usage_status()
        
        logger.info(f"Successful gift: {sender.username} -> {recipient.username}, Amount: {amount}, New sender balance: {sender.coins}")
        
        return JsonResponse({
            'status': 'success', 
            'message': f'Successfully gifted {amount} coins to {recipient.username}!', 
            'new_balance': sender.coins,
            'transaction': {
                'id': sender_transaction.id,
                'transaction_date': sender_transaction.transaction_date.isoformat(),
                'amount': amount,
                'recipient': {'username': recipient.username},
                'transaction_type': 'gift_sent'
            },
            'usage_status': updated_usage_status
        })

    except IntegrityError as e:
        logger.error(f"Database integrity error during gift_coins from {request.user.username}: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error', 
            'message': 'Database error during transaction. Please try again.'
        }, status=500)
        
    except Exception as e:
        logger.error(f"Unexpected error in gift_coins for user {request.user.username}: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error', 
            'message': 'An unexpected error occurred. Please try again.'
        }, status=500)


@login_required
def mywallet(request):
    """Display user wallet dashboard with transaction history."""
    try:
        logger.info(f"Wallet page accessed by user: {request.user.username}, Balance: {request.user.coins}")
        
        # Get transaction history (exclude subscription transactions)
        transaction_history = CoinTransaction.objects.filter(
            user=request.user
        ).exclude(
            pack_name__in=[
                'Monthly Premium Subscription', 
                'Annual Premium Subscription',
                'Monthly Premium Renewal', 
                'Annual Premium Renewal'
            ]
        ).select_related('sender', 'recipient').order_by('-transaction_date')

        # Prepare context
        request.user.refresh_from_db()
        usage_status = request.user.get_usage_status()

        context = {
            'user': request.user,
            'usage_status': usage_status,
            'gift_history': transaction_history,
            'page_title': 'My Wallet',
        }
        
        logger.info(f"Wallet page loaded successfully for user: {request.user.username}")
        return render(request, 'user/mywallet.html', context)
        
    except Exception as e:
        logger.error(f"Error loading wallet page for user {request.user.username}: {e}", exc_info=True)
        messages.error(request, 'Unable to load your wallet. Please try again.')
        
        # Fallback context
        context = {
            'user': request.user,
            'usage_status': None,
            'gift_history': [],
            'page_title': 'My Wallet',
        }
        return render(request, 'user/mywallet.html', context)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def validate_coin_amount(amount_str):
    """
    Validate and convert coin amount string to integer.
    
    Args:
        amount_str: String representation of coin amount
        
    Returns:
        tuple: (is_valid, amount_or_error_message)
    """
    try:
        amount = int(amount_str)
        
        if amount <= 0:
            return False, "Amount must be positive"
            
        if amount > 1000000:
            return False, "Amount exceeds maximum limit"
            
        return True, amount
        
    except (ValueError, TypeError):
        return False, "Invalid amount format"


def get_transaction_display_data(transaction):
    """
    Format transaction data for template display.
    
    Args:
        transaction: CoinTransaction instance
        
    Returns:
        dict: Formatted transaction data
    """
    display_data = {
        'id': transaction.id,
        'type': transaction.transaction_type,
        'amount': abs(transaction.amount) if transaction.amount else 0,
        'date': transaction.transaction_date,
        'status': transaction.status,
        'description': transaction.description or '',
    }
    
    # Add type-specific data
    if transaction.transaction_type == 'gift_sent' and transaction.recipient:
        display_data['recipient_username'] = transaction.recipient.username
        
    elif transaction.transaction_type == 'gift_received' and transaction.sender:
        display_data['sender_username'] = transaction.sender.username
        
    elif transaction.transaction_type == 'purchase':
        display_data['pack_name'] = transaction.pack_name or 'Coin Purchase'
        display_data['price'] = transaction.price
    
    return display_data


def check_user_gift_eligibility(user, amount):
    """
    Check if user is eligible to send a gift of specified amount.
    
    Args:
        user: User instance
        amount: Gift amount to validate
        
    Returns:
        tuple: (is_eligible, error_message_or_none)
    """
    # Check subscription limits for FREE users
    if user.subscription_type == 'FR':
        can_gift, error_msg = user.can_gift_coins()
        if not can_gift:
            return False, error_msg
    
    # Check user balance
    if user.coins < amount:
        return False, "Insufficient coins for this gift."
    
    return True, None


def log_transaction_activity(user, transaction_type, amount, details=None):
    """
    Log transaction activity for monitoring and debugging.
    
    Args:
        user: User instance
        transaction_type: Type of transaction
        amount: Transaction amount
        details: Additional transaction details (optional)
    """
    log_message = f"Transaction: {user.username} - {transaction_type} - Amount: {amount}"
    if details:
        log_message += f" - Details: {details}"
    
    logger.info(log_message)
