# AudioXApp/views/admin_views/dashboard_utils.py

from django.utils import timezone
from django.db.models import Sum, Count, Avg, F, Q, Case, When, Value, CharField, DecimalField, IntegerField, FloatField # Import IntegerField or FloatField
from django.db.models.functions import TruncDay, Coalesce
from decimal import Decimal
import json
from datetime import timedelta

# Import all necessary models
from ...models import (
    User, Creator, Audiobook, Chapter, CreatorEarning, WithdrawalRequest,
    Ticket, TicketMessage, Subscription, AudiobookPurchase, CoinTransaction, Review,
    UserDownloadedAudiobook, CreatorApplicationLog, ChatRoom, ChatMessage, Admin,
    ListeningHistory
)

# --- Data Gathering Functions ---

def get_platform_financials():
    """Calculates comprehensive financial metrics for the entire platform."""
    completed_sales = AudiobookPurchase.objects.filter(status='COMPLETED')
    coin_purchases = CoinTransaction.objects.filter(status='completed', transaction_type='purchase')
    completed_withdrawals = WithdrawalRequest.objects.filter(status='COMPLETED')

    total_sales_revenue = completed_sales.aggregate(total=Coalesce(Sum('amount_paid'), Decimal('0.00')))['total']
    total_coin_revenue = coin_purchases.aggregate(total=Coalesce(Sum('price'), Decimal('0.00')))['total']
    gross_revenue = total_sales_revenue + total_coin_revenue

    platform_fee_total = completed_sales.aggregate(total=Coalesce(Sum('platform_fee_amount'), Decimal('0.00')))['total']
    creator_share_total = completed_sales.aggregate(total=Coalesce(Sum('creator_share_amount'), Decimal('0.00')))['total']

    refunded_sales = AudiobookPurchase.objects.filter(status='REFUNDED')
    total_refunds_amount = refunded_sales.aggregate(total=Coalesce(Sum('amount_paid'), Decimal('0.00')))['total']
    total_withdrawals_issued = completed_withdrawals.aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total']

    # Coin Economy
    coins_spent = CoinTransaction.objects.filter(transaction_type='spent').aggregate(total=Coalesce(Sum('amount'), 0))['total']
    coins_rewarded = CoinTransaction.objects.filter(transaction_type='reward').aggregate(total=Coalesce(Sum('amount'), 0))['total']
    total_coins_in_wallets = User.objects.aggregate(total=Coalesce(Sum('coins'), 0))['total']

    return {
        'gross_revenue': gross_revenue,
        'total_sales_revenue': total_sales_revenue,
        'total_coin_revenue': total_coin_revenue,
        'total_platform_fee': platform_fee_total,
        'total_creator_share': creator_share_total,
        'net_revenue': gross_revenue - creator_share_total - total_refunds_amount,
        'total_refunds_amount': total_refunds_amount,
        'total_withdrawals_issued': total_withdrawals_issued,
        'refund_rate_percentage': (total_refunds_amount / gross_revenue * 100) if gross_revenue > 0 else 0,
        'total_refunds_count': refunded_sales.count(),
        'coins_spent': coins_spent,
        'coins_rewarded': coins_rewarded,
        'total_coins_in_wallets': total_coins_in_wallets,
    }

def get_user_and_creator_metrics():
    """Calculates metrics related to the user and creator lifecycle."""
    thirty_days_ago = timezone.now() - timedelta(days=30)
    ninety_days_ago = timezone.now() - timedelta(days=90)
    
    total_users = User.objects.all()
    total_user_count = total_users.count()
    active_subscriptions = Subscription.objects.filter(status='active')
    total_creators = Creator.objects.all()
    users_with_2fa_count = total_users.filter(is_2fa_enabled=True).count()
    
    # Calculate Average Listen Time (last 30 days)
    recent_listeners = ListeningHistory.objects.filter(last_listened_at__gte=thirty_days_ago).values('user').distinct()
    
    # FIX APPLIED HERE: Added output_field=IntegerField() to Coalesce
    total_listen_seconds_30d = ListeningHistory.objects.filter(last_listened_at__gte=thirty_days_ago).aggregate(
        total=Coalesce(Sum('last_position_seconds'), 0, output_field=IntegerField())
    )['total']
    
    # Ensure avg_listen_time_seconds calculation handles division by zero
    avg_listen_time_seconds = (total_listen_seconds_30d / recent_listeners.count()) if recent_listeners.count() > 0 else 0

    return {
        # User KPIs
        'total_user_count': total_user_count,
        'active_user_count_30d': total_users.filter(last_login__gte=thirty_days_ago).count(),
        'banned_user_count': total_users.filter(is_banned_by_admin=True).count(),
        'subscribed_user_count': active_subscriptions.count(),
        'free_users_count': total_user_count - active_subscriptions.count(),
        'conversion_rate': (active_subscriptions.count() / total_user_count * 100) if total_user_count > 0 else 0,
        'dormant_users_90d': total_users.filter(last_login__lt=ninety_days_ago, date_joined__lt=ninety_days_ago).count(),
        'users_with_2fa': users_with_2fa_count,
        'two_fa_adoption_rate': (users_with_2fa_count / total_user_count * 100) if total_user_count > 0 else 0,
        'incomplete_social_signups': total_users.filter(requires_extra_details_post_social_signup=True).count(),
        'avg_listen_time_hours': round(avg_listen_time_seconds / 3600, 1),
        # Creator KPIs
        'total_creator_count': total_creators.count(),
        'active_creator_count': total_creators.filter(verification_status='approved', is_banned=False).count(),
        'banned_creator_count': total_creators.filter(is_banned=True).count(),
        'pending_verification_count': total_creators.filter(verification_status='pending').count(),
    }

def get_content_and_engagement_metrics():
    """Calculates metrics for content health and user engagement."""
    total_audiobooks = Audiobook.objects.all()
    total_chapters = Chapter.objects.all()
    
    return {
        'total_audiobook_count': total_audiobooks.count(),
        'published_audiobooks': total_audiobooks.filter(status='PUBLISHED').count(),
        'takedown_audiobooks': total_audiobooks.filter(status='TAKEDOWN').count(),
        'total_chapters_count': total_chapters.count(),
        'average_rating': Review.objects.aggregate(avg=Avg('rating'))['avg'] or 0.0,
        'total_reviews_count': Review.objects.count(),
        'total_downloads_count': UserDownloadedAudiobook.objects.count(),
        'paid_audiobooks_count': total_audiobooks.filter(is_paid=True).count(),
        'free_audiobooks_count': total_audiobooks.filter(is_paid=False).count(),
        'tts_generated_chapters': total_chapters.filter(is_tts_generated=True).count(),
    }

def get_operations_and_support_metrics():
    """Calculates metrics for support tickets and financial operations."""
    pending_withdrawals = WithdrawalRequest.objects.filter(status='PENDING')
    open_tickets = Ticket.objects.filter(status__in=['OPEN', 'REOPENED', 'AWAITING_USER'])

    # Calculate Avg First Response Time
    first_replies = TicketMessage.objects.filter(is_admin_reply=True).order_by('ticket_id', 'created_at').distinct('ticket_id')
    ticket_creations = Ticket.objects.filter(id__in=first_replies.values_list('ticket_id', flat=True)).in_bulk(field_name='id')
    
    total_response_time = timedelta(0)
    valid_tickets = 0
    for reply in first_replies:
        ticket = ticket_creations.get(reply.ticket_id)
        if ticket:
            total_response_time += (reply.created_at - ticket.created_at)
            valid_tickets += 1
    avg_response_time_seconds = (total_response_time.total_seconds() / valid_tickets) if valid_tickets > 0 else 0

    return {
        'pending_withdrawal_count': pending_withdrawals.count(),
        'pending_withdrawal_total_amount': pending_withdrawals.aggregate(total=Coalesce(Sum('amount'), Decimal('0.00')))['total'],
        'open_tickets_count': open_tickets.count(),
        'avg_first_response_time_hours': round(avg_response_time_seconds / 3600, 1),
    }

def get_chart_data(financial_data):
    """Gathers and prepares data for all dashboard charts.
    Accepts financial_data to avoid re-querying.
    """
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    date_range = [thirty_days_ago + timedelta(days=i) for i in range(31)]
    date_labels = [d.strftime('%b %d') for d in date_range]

    # Revenue Over Time
    sales_by_day = {
        item['day'].date(): item['total'] for item in
        AudiobookPurchase.objects.filter(status='COMPLETED', purchase_date__gte=thirty_days_ago)
        .annotate(day=TruncDay('purchase_date')).values('day')
        .annotate(total=Sum('amount_paid')).order_by('day')
    }
    coins_by_day = {
        item['day'].date(): item['total'] for item in
        CoinTransaction.objects.filter(status='completed', transaction_type='purchase', transaction_date__gte=thirty_days_ago)
        .annotate(day=TruncDay('transaction_date')).values('day')
        .annotate(total=Sum('price')).order_by('day')
    }
    revenue_sales_values = [float(sales_by_day.get(d, 0)) for d in date_range]
    revenue_coins_values = [float(coins_by_day.get(d, 0)) for d in date_range]

    # User Growth
    user_growth_by_day = {
        item['day'].date(): item['count'] for item in
        User.objects.filter(date_joined__gte=thirty_days_ago)
        .annotate(day=TruncDay('date_joined')).values('day')
        .annotate(count=Count('user_id')).order_by('day')
    }
    user_growth_values = [user_growth_by_day.get(d, 0) for d in date_range]
    
    # Other distributions
    lang_dist = Audiobook.objects.values('language').annotate(count=Count('audiobook_id')).order_by('-count')
    creator_status_dist = Creator.objects.values('verification_status').annotate(count=Count('user_id')).order_by()
    subscription_status_dist = Subscription.objects.values('status').annotate(count=Count('user_id')).order_by()
    ticket_category_dist = Ticket.objects.values('category__name').annotate(count=Count('id')).order_by('-count')

    chart_data = {
        'revenue_labels_json': json.dumps(date_labels),
        'revenue_sales_values_json': json.dumps(revenue_sales_values),
        'revenue_coins_values_json': json.dumps(revenue_coins_values),
        'user_growth_labels_json': json.dumps(date_labels),
        'user_growth_values_json': json.dumps(user_growth_values),
        'lang_dist_labels_json': json.dumps([item['language'] or 'Not Set' for item in lang_dist]),
        'lang_dist_values_json': json.dumps([item['count'] for item in lang_dist]),
        'creator_status_labels_json': json.dumps([item['verification_status'].replace('_', ' ').title() for item in creator_status_dist]),
        'creator_status_values_json': json.dumps([item['count'] for item in creator_status_dist]),
        'subscription_status_labels_json': json.dumps([item['status'].title() for item in subscription_status_dist]),
        'subscription_status_values_json': json.dumps([item['count'] for item in subscription_status_dist]),
        'ticket_category_labels_json': json.dumps([item['category__name'] or 'Uncategorized' for item in ticket_category_dist]),
        'ticket_category_values_json': json.dumps([item['count'] for item in ticket_category_dist]),
        # NEW: Data for Revenue Breakdown chart
        'revenue_breakdown_labels_json': json.dumps(['Audiobook Sales', 'Coin Purchases']),
        'revenue_breakdown_values_json': json.dumps([
            float(financial_data.get('total_sales_revenue', 0)),
            float(financial_data.get('total_coin_revenue', 0))
        ]),
    }
    return chart_data

def get_feeds_and_leaderboards():
    """Gathers data for lists, feeds, and leaderboards."""
    
    # Leaderboards
    top_selling_books = Audiobook.objects.filter(status='PUBLISHED').order_by('-total_sales')[:5]
    lowest_rated_books = Audiobook.objects.annotate(avg_rating=Avg('reviews__rating')).filter(avg_rating__isnull=False).order_by('avg_rating')[:5]
    top_earning_creators = Creator.objects.filter(is_banned=False, verification_status='approved').annotate(
        total_earnings=Sum('earnings_log__amount_earned')
    ).filter(total_earnings__isnull=False).order_by('-total_earnings')[:5]

    # Feeds
    latest_pending_creators = Creator.objects.filter(verification_status='pending').select_related('user').order_by('-last_application_date')[:5]
    latest_open_tickets = Ticket.objects.filter(status__in=['OPEN', 'REOPENED']).select_related('user').order_by('-updated_at')[:5]
    latest_sales = AudiobookPurchase.objects.filter(status='COMPLETED').select_related('user', 'audiobook').order_by('-purchase_date')[:7]
    latest_takedowns = Audiobook.objects.filter(status='TAKEDOWN').select_related('takedown_by').order_by('-takedown_at')[:5]
    
    return {
        'top_selling_audiobooks': top_selling_books,
        'lowest_rated_audiobooks': lowest_rated_books,
        'top_earning_creators': top_earning_creators,
        'latest_pending_creators': latest_pending_creators,
        'latest_open_tickets': latest_open_tickets,
        'latest_sales': latest_sales,
        'latest_takedowns': latest_takedowns,
    }


# --- Main Function to build context ---

def get_dashboard_context():
    """
    The main engine function that calls all other data-gathering functions
    and assembles the final context dictionary for the dashboard view.
    """
    # Get financial data first as it's needed by the chart function
    financial_data = get_platform_financials()

    context = {}
    context.update(financial_data)
    context.update(get_user_and_creator_metrics())
    context.update(get_content_and_engagement_metrics())
    context.update(get_operations_and_support_metrics())
    context.update(get_chart_data(financial_data)) # Pass financial data to avoid re-querying
    context.update(get_feeds_and_leaderboards())
    
    return context