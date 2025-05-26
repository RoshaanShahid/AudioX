# AudioXApp/views/admin_views/admin_dashboard_views.py

from django.shortcuts import render
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal

from ...models import User, Creator, Audiobook, CoinTransaction, WithdrawalRequest # Relative imports
from ..decorators import admin_role_required # Relative import

# --- Admin Dashboard View ---

@admin_role_required() # Default role requirement (any authenticated admin)
def admindashboard(request):
    """Renders the admin dashboard with key metrics."""
    total_user_count = User.objects.count()
    # Note: The logic for subscribed_user_count might need an update if 'subscription_type' isn't how you track subscriptions.
    # Consider using the same logic as in admin_manage_users if User model has a direct link to Subscription.
    subscribed_user_count = User.objects.filter(subscription__status='active').distinct().count() # Example adjustment
    free_user_count = total_user_count - subscribed_user_count # This will be accurate if subscribed_user_count is accurate
    active_creator_count = Creator.objects.filter(verification_status='approved', is_banned=False).count()
    pending_verification_count = Creator.objects.filter(verification_status='pending').count()
    total_audiobook_count = Audiobook.objects.count()
    creator_audiobook_count = Audiobook.objects.filter(creator__verification_status='approved', creator__is_banned=False).count()

    pending_withdrawal_count = 0
    try:
        pending_withdrawal_count = WithdrawalRequest.objects.filter(
            status='PENDING', # Changed from 'pending' to 'PENDING' for consistency if your choices are uppercase
            creator__verification_status='approved', # Ensure creator is active
            creator__is_banned=False
        ).count()
    except Exception as e: # Catch specific exceptions if possible
        messages.error(request, f"Could not retrieve withdrawal request count: {e}")


    total_earnings_query = CoinTransaction.objects.filter(
        transaction_type='purchase', status='completed' # Assuming 'purchase' is for coins, 'completed' is correct status
    ).exclude(
        pack_name__icontains='Subscription' # If coin packs for subscriptions have this in name
    ).aggregate(total=Sum('price')) # Assuming 'price' field exists and stores the value
    total_earnings = total_earnings_query['total'] or Decimal('0.00')

    context = {
        'admin_user': getattr(request, 'admin_user', None),
        'active_page': 'dashboard',
        'is_creator_management_page': False, # This page is not part of creator management specifics
        'total_user_count': total_user_count,
        'subscribed_user_count': subscribed_user_count,
        'free_user_count': free_user_count,
        'active_creator_count': active_creator_count,
        'total_audiobook_count': total_audiobook_count,
        'creator_audiobook_count': creator_audiobook_count,
        'pending_verification_count': pending_verification_count,
        'pending_withdrawal_count': pending_withdrawal_count,
        'total_earnings': total_earnings.quantize(Decimal("0.01")),
        'TIME_ZONE': settings.TIME_ZONE,
    }
    return render(request, 'admin/admin_dashboard.html', context) 