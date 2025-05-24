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
    subscribed_user_count = User.objects.filter(subscription_type='PR').count()
    free_user_count = total_user_count - subscribed_user_count
    active_creator_count = Creator.objects.filter(verification_status='approved', is_banned=False).count()
    pending_verification_count = Creator.objects.filter(verification_status='pending').count()
    total_audiobook_count = Audiobook.objects.count()
    creator_audiobook_count = Audiobook.objects.filter(creator__verification_status='approved', creator__is_banned=False).count()

    pending_withdrawal_count = 0
    try:
        pending_withdrawal_count = WithdrawalRequest.objects.filter(
            status='pending',
            creator__verification_status='approved',
            creator__is_banned=False
        ).count()
    except Exception:
        messages.error(request, "Could not retrieve withdrawal request count due to a server error.")

    total_earnings_query = CoinTransaction.objects.filter(
        transaction_type='purchase', status='completed'
    ).exclude(
        pack_name__icontains='Subscription'
    ).aggregate(total=Sum('price'))
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
