# AudioXApp/views/user_views/account_activity_views.py

import datetime
import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
from ...models import User, CoinTransaction, Audiobook, Chapter, AudiobookPurchase
from ..utils import _get_full_context

logger = logging.getLogger(__name__)

# --- Billing History View ---

@login_required
def billing_history(request):
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
            end_datetime_naive_eod = datetime.datetime.combine(end_datetime_naive, datetime.time.max)
            if settings.USE_TZ:
                end_date = timezone.make_aware(end_datetime_naive_eod, timezone.get_default_timezone())
            else:
                end_date = end_datetime_naive_eod
        except ValueError:
            messages.error(request, "Invalid end date format. Please use YYYY-MM-DD.")
            pass

    audiobook_purchases_qs = AudiobookPurchase.objects.filter(user=user, status='COMPLETED').select_related('audiobook', 'audiobook__creator')
    if start_date: audiobook_purchases_qs = audiobook_purchases_qs.filter(purchase_date__gte=start_date)
    if end_date: audiobook_purchases_qs = audiobook_purchases_qs.filter(purchase_date__lte=end_date)

    for purchase in audiobook_purchases_qs.order_by('-purchase_date'):
        billing_items_list.append({
            'type': 'Audiobook Purchase',
            'description': f"'{purchase.audiobook.title}' by {purchase.audiobook.creator.creator_name if purchase.audiobook.creator else 'N/A'}",
            'date': purchase.purchase_date,
            'amount_pkr': purchase.amount_paid,
            'coins_received': None,
            'details_url': reverse('AudioXApp:audiobook_detail', kwargs={'audiobook_slug': purchase.audiobook.slug}),
            'status': purchase.get_status_display(),
            'status_class': 'bg-green-100 text-green-700'
        })

    subscription_pack_names_lower = [name.lower() for name in ['Monthly Premium Subscription', 'Annual Premium Subscription', 'Monthly Premium Renewal', 'Annual Premium Renewal']]
    all_coin_transactions_qs = CoinTransaction.objects.filter(user=user).select_related('sender', 'recipient', 'related_audiobook')
    if start_date: all_coin_transactions_qs = all_coin_transactions_qs.filter(transaction_date__gte=start_date)
    if end_date: all_coin_transactions_qs = all_coin_transactions_qs.filter(transaction_date__lte=end_date)

    for txn in all_coin_transactions_qs.order_by('-transaction_date'):
        # Calculate PKR amount for display
        amount_pkr_display = None
        coins_change = None
        
        if txn.pack_name and txn.pack_name.lower() in subscription_pack_names_lower:
            item_type_display = 'Subscription'
            description = txn.pack_name
            details_url = reverse('AudioXApp:managesubscription')
            amount_pkr_display = txn.price  # Subscription transactions have price set
            coins_change = None
        elif txn.transaction_type == 'purchase':
            item_type_display = 'Coin Purchase'
            description = txn.pack_name or f"{txn.amount} Coins"
            details_url = reverse('AudioXApp:buycoins')
            amount_pkr_display = txn.price  # Coin purchase transactions have price set
            coins_change = txn.amount
        elif txn.transaction_type == 'gift_sent':
            item_type_display = 'Coins Gifted'
            description = f"Gifted to {txn.recipient.username if txn.recipient else 'Unknown User'}"
            details_url = reverse('AudioXApp:mywallet')
            # For gifts, convert coin amount to PKR (1 coin = 1 PKR)
            amount_pkr_display = abs(txn.amount) if txn.amount else 0
            coins_change = txn.amount
        elif txn.transaction_type == 'gift_received':
            item_type_display = 'Coins Received'
            description = f"Received from {txn.sender.username if txn.sender else 'Unknown User'}"
            details_url = reverse('AudioXApp:mywallet')
            # For received gifts, show as 0 PKR since no money was spent by this user
            amount_pkr_display = 0
            coins_change = txn.amount
        elif txn.transaction_type == 'spent' or txn.transaction_type == 'audiobook_purchase':
            item_type_display = 'Coins Spent'
            
            # Enhanced description for audiobook purchases
            if txn.related_audiobook:
                description = f"Purchased audiobook: {txn.related_audiobook.title}"
                details_url = reverse('AudioXApp:audiobook_detail', kwargs={'audiobook_slug': txn.related_audiobook.slug})
            else:
                description = txn.description or "Spent on Audiobook/Feature"
                details_url = "#"
            
            # Convert coins spent to PKR equivalent (1 coin = 1 PKR)
            # txn.amount is negative for spent transactions, so we take absolute value
            amount_pkr_display = abs(txn.amount) if txn.amount else 0
            coins_change = txn.amount
        else:
            item_type_display = txn.get_transaction_type_display()
            description = txn.description or txn.pack_name or "General Transaction"
            details_url = "#"
            # For other transaction types, use price if available, otherwise convert coins
            amount_pkr_display = txn.price if txn.price is not None else (abs(txn.amount) if txn.amount else 0)
            coins_change = txn.amount

        status_display = txn.get_status_display()
        status_class = 'bg-gray-100 text-gray-700'
        if txn.status == 'completed': status_class = 'bg-green-100 text-green-700'
        elif txn.status == 'pending': status_class = 'bg-yellow-100 text-yellow-700'
        elif txn.status in ['failed', 'rejected']: status_class = 'bg-red-100 text-red-700'
        
        billing_items_list.append({
            'type': item_type_display,
            'description': description,
            'date': txn.transaction_date,
            'amount_pkr': amount_pkr_display,
            'coins_change': coins_change,
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

# --- Downloads Page View ---

@login_required
def my_downloads(request):
    context = _get_full_context(request)
    return render(request, 'user/my_downloads.html', context)

# --- Library View (Purchased Books) ---

@login_required
def my_library(request):
    context = _get_full_context(request)
    purchased_audiobooks_qs = Audiobook.objects.filter(
        audiobook_sales__user=request.user, 
        audiobook_sales__status='COMPLETED'
    ).distinct().prefetch_related(
        Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order'))
    ).order_by('-audiobook_sales__purchase_date')
    context['library_audiobooks'] = purchased_audiobooks_qs
    return render(request, 'user/my_library.html', context)
