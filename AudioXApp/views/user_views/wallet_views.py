# AudioXApp/views/user_views/wallet_views.py

import json
from decimal import Decimal, InvalidOperation
import logging

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.db import transaction, IntegrityError
from django.db.models import F
from django.conf import settings
from django.urls import reverse

from ...models import User, CoinTransaction
from ..utils import _get_full_context

logger = logging.getLogger(__name__)

# --- Wallet and Coin Views ---

@login_required
def buycoins(request):
    """Renders the buy coins page."""
    purchase_history = CoinTransaction.objects.filter(
        user=request.user, transaction_type='purchase'
    ).exclude(
        pack_name__in=['Monthly Premium Subscription', 'Annual Premium Subscription', 
                       'Monthly Premium Renewal', 'Annual Premium Renewal']
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
        recipient_identifier = data.get('recipient', '').strip()
        amount_str = data.get('amount')

        if not recipient_identifier or not amount_str:
            return JsonResponse({'status': 'error', 'message': 'Recipient and amount are required.'}, status=400)

        try:
            amount = int(amount_str)
            if amount <= 0:
                return JsonResponse({'status': 'error', 'message': 'Gift amount must be positive.'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid gift amount format.'}, status=400)

        try:
            if '@' in recipient_identifier:
                recipient = User.objects.get(email__iexact=recipient_identifier)
            else:
                recipient = User.objects.get(username__iexact=recipient_identifier)
            
            if recipient == sender:
                return JsonResponse({'status': 'error', 'message': 'You cannot gift coins to yourself.'}, status=400)
        except User.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Recipient user not found.'}, status=404)

        sender_locked = User.objects.select_for_update().get(pk=sender.pk)
        
        if sender_locked.coins < amount:
            return JsonResponse({'status': 'error', 'message': 'Insufficient coins.'}, status=400)

        sender_locked.coins -= amount
        sender_locked.save(update_fields=['coins'])
        
        recipient_locked = User.objects.select_for_update().get(pk=recipient.pk)
        recipient_locked.coins += amount
        recipient_locked.save(update_fields=['coins'])

        CoinTransaction.objects.create(
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
        
        sender.refresh_from_db(fields=['coins']) 
        logger.info(f"User {sender.username} gifted {amount} coins to {recipient.username}. Sender new balance: {sender.coins}")
        return JsonResponse({'status': 'success', 'message': f'Successfully gifted {amount} coins to {recipient.username}!', 'new_balance': sender.coins})

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid request data format.'}, status=400)
    except IntegrityError:
        logger.error(f"IntegrityError during gift_coins from {request.user.username}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Database error during transaction. Please try again.'}, status=500)
    except Exception as e:
        logger.error(f"Unexpected error in gift_coins for user {request.user.username}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)

@login_required
def mywallet(request):
    """Renders the user's wallet page showing transaction history."""
    transaction_history = CoinTransaction.objects.filter(
        user=request.user
    ).exclude(
        pack_name__in=['Monthly Premium Subscription', 'Annual Premium Subscription',
                       'Monthly Premium Renewal', 'Annual Premium Renewal']
    ).select_related('sender', 'recipient').order_by('-transaction_date')

    context = _get_full_context(request)
    context['gift_history'] = transaction_history
    return render(request, 'user/mywallet.html', context)