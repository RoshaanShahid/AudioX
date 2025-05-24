# AudioXApp/views/user_views/account_activity_views.py

import datetime # For strptime
import logging

from django.shortcuts import render, redirect # redirect might be used if a page is under construction
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.utils import timezone
from django.conf import settings # For settings.USE_TZ
from django.urls import reverse


from ...models import User, CoinTransaction, Audiobook, Chapter, AudiobookPurchase # Relative import
from ..utils import _get_full_context # Relative import

logger = logging.getLogger(__name__)

# --- Billing and Library Views ---

@login_required
def billing_history(request):
    """Renders the user's billing history page, combining various transaction types."""
    user = request.user
    billing_items_list = []

    # Date filtering logic from GET parameters
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
            # Potentially redirect or just show unfiltered if date is invalid
            pass 

    if end_date_str:
        try:
            end_datetime_naive = datetime.datetime.strptime(end_date_str, '%Y-%m-%d')
            # To include the whole end day, set time to end of day
            end_datetime_naive_eod = datetime.datetime.combine(end_datetime_naive, datetime.time.max)
            if settings.USE_TZ:
                end_date = timezone.make_aware(end_datetime_naive_eod, timezone.get_default_timezone())
            else:
                end_date = end_datetime_naive_eod
        except ValueError:
            messages.error(request, "Invalid end date format. Please use YYYY-MM-DD.")
            pass

    # 1. Audiobook Purchases (Direct via Stripe, not coins)
    audiobook_purchases_qs = AudiobookPurchase.objects.filter(user=user, status='COMPLETED').select_related('audiobook', 'audiobook__creator')
    if start_date: audiobook_purchases_qs = audiobook_purchases_qs.filter(purchase_date__gte=start_date)
    if end_date: audiobook_purchases_qs = audiobook_purchases_qs.filter(purchase_date__lte=end_date)

    for purchase in audiobook_purchases_qs.order_by('-purchase_date'):
        billing_items_list.append({
            'type': 'Audiobook Purchase',
            'description': f"'{purchase.audiobook.title}' by {purchase.audiobook.creator.creator_name if purchase.audiobook.creator else 'N/A'}",
            'date': purchase.purchase_date,
            'amount_pkr': purchase.amount_paid, # This is the actual amount paid
            'coins_received': None, # No coins involved in direct purchase
            'details_url': reverse('AudioXApp:audiobook_detail', kwargs={'audiobook_slug': purchase.audiobook.slug}),
            'status': purchase.get_status_display(), # Use model's display method
            'status_class': 'bg-green-100 text-green-700' # Assuming COMPLETED is green
        })

    # 2. Coin Transactions (Purchases, Gifts, Spent - excluding Subscriptions handled by their own history)
    # We need to be careful not to double-count if audiobook purchases via coins are also logged here.
    # Assuming CoinTransaction for 'spent' on audiobooks is distinct from AudiobookPurchase.
    
    # Define subscription pack names to exclude from general coin transaction history
    # These might be better defined in settings or a constants file.
    subscription_pack_names_lower = [
        name.lower() for name in [
            'Monthly Premium Subscription', 'Annual Premium Subscription',
            'Monthly Premium Renewal', 'Annual Premium Renewal'
        ]
    ]

    all_coin_transactions_qs = CoinTransaction.objects.filter(user=user).select_related('sender', 'recipient')
    if start_date: all_coin_transactions_qs = all_coin_transactions_qs.filter(transaction_date__gte=start_date)
    if end_date: all_coin_transactions_qs = all_coin_transactions_qs.filter(transaction_date__lte=end_date)

    for txn in all_coin_transactions_qs.order_by('-transaction_date'):
        # Skip if it's a subscription-related coin transaction (these are usually 0 amount with price)
        if txn.pack_name and txn.pack_name.lower() in subscription_pack_names_lower:
            item_type_display = 'Subscription'
            description = txn.pack_name
            details_url = reverse('AudioXApp:managesubscription')
            coins_change = None # No direct coin change for user wallet from subscription record itself
        elif txn.transaction_type == 'purchase':
            item_type_display = 'Coin Purchase'
            description = txn.pack_name or f"{txn.amount} Coins"
            details_url = reverse('AudioXApp:buycoins')
            coins_change = txn.amount # Positive
        elif txn.transaction_type == 'gift_sent':
            item_type_display = 'Coins Gifted'
            description = f"Gifted to {txn.recipient.username if txn.recipient else 'Unknown User'}"
            details_url = reverse('AudioXApp:mywallet') # Or a specific gift history page
            coins_change = txn.amount # Negative
        elif txn.transaction_type == 'gift_received':
            item_type_display = 'Coins Received'
            description = f"Received from {txn.sender.username if txn.sender else 'Unknown User'}"
            details_url = reverse('AudioXApp:mywallet')
            coins_change = txn.amount # Positive
        elif txn.transaction_type == 'spent': # Example: if you log coin spending on audiobooks
            item_type_display = 'Coins Spent'
            description = txn.description or "Spent on Audiobook/Feature" # Make description more specific if possible
            details_url = "#" # Link to the item if applicable
            coins_change = txn.amount # Negative
        else: # Other transaction types if any
            item_type_display = txn.get_transaction_type_display()
            description = txn.description or txn.pack_name or "General Transaction"
            details_url = "#"
            coins_change = txn.amount

        status_display = txn.get_status_display()
        status_class = 'bg-gray-100 text-gray-700' # Default
        if txn.status == 'completed': status_class = 'bg-green-100 text-green-700'
        elif txn.status == 'pending': status_class = 'bg-yellow-100 text-yellow-700'
        elif txn.status in ['failed', 'rejected']: status_class = 'bg-red-100 text-red-700'
        
        billing_items_list.append({
            'type': item_type_display,
            'description': description,
            'date': txn.transaction_date,
            'amount_pkr': txn.price, # Price of the pack/item, if applicable
            'coins_change': coins_change, # How many coins were added/removed
            'details_url': details_url,
            'status': status_display,
            'status_class': status_class
        })

    # Sort all collected items by date
    billing_items_list.sort(key=lambda x: x['date'], reverse=True)

    context = _get_full_context(request)
    context['billing_items'] = billing_items_list
    context['start_date_str'] = start_date_str # For repopulating filter fields
    context['end_date_str'] = end_date_str   # For repopulating filter fields

    return render(request, 'user/billing_history.html', context)


@login_required
def my_downloads(request):
    """Renders the user's downloads page (placeholder)."""
    context = _get_full_context(request)
    # This view is a placeholder as actual download tracking is complex
    # and depends on how downloads are implemented (e.g., direct file, temporary links).
    context['downloaded_audiobooks'] = [] # Empty list for now
    messages.info(request, "My Downloads page is currently under construction and will be available soon.")
    # Redirect to a more relevant page if this one is truly just a placeholder
    return redirect('AudioXApp:myprofile') # Or 'AudioXApp:home' or 'AudioXApp:my_library'


@login_required
def my_library(request):
    """Renders the user's library page showing purchased audiobooks."""
    context = _get_full_context(request)
    
    # Fetch audiobooks for which the user has a completed purchase record
    # Using AudiobookPurchase as the source of truth for "owned" audiobooks
    purchased_audiobooks_qs = Audiobook.objects.filter(
        audiobook_sales__user=request.user, 
        audiobook_sales__status='COMPLETED' # Ensure purchase was completed
    ).distinct().prefetch_related(
        Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order')) # Pre-fetch chapters
    ).order_by('-audiobook_sales__purchase_date') # Order by most recent purchase

    context['library_audiobooks'] = purchased_audiobooks_qs
    return render(request, 'user/my_library.html', context)