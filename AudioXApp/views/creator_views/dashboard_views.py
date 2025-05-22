# AudioXApp/views/creator_views/dashboard_views.py

import json
from decimal import Decimal
from datetime import datetime, timedelta
from collections import OrderedDict
import logging

from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Sum, F, Value, Case, When, DecimalField, OuterRef, Subquery, Exists, Count
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from django.urls import reverse
from django.core.serializers.json import DjangoJSONEncoder
from django.conf import settings
from django.core.exceptions import FieldError


from ...models import Creator, Audiobook, Chapter, WithdrawalRequest, WithdrawalAccount, CreatorEarning # Relative imports
from ..utils import _get_full_context # Relative import
from ..decorators import creator_required # Relative import

logger = logging.getLogger(__name__)

@creator_required
def creator_dashboard_view(request):
    try:
        creator_profile = request.creator
    except AttributeError:
        messages.error(request, "Creator profile not available. Please log in again.")
        logger.warning("Creator profile not found on request in creator_dashboard_view.")
        return redirect('AudioXApp:home')

    user = request.user
    now = timezone.now()

    try:
        audiobooks_qs = Audiobook.objects.filter(creator=creator_profile).prefetch_related('chapters')
        total_audiobooks_count = audiobooks_qs.count()
        recent_audiobooks_list = audiobooks_qs.order_by('-publish_date')[:5]
        total_chapters_uploaded = Chapter.objects.filter(audiobook__creator=creator_profile).count()

        sales_earnings_aggregation = CreatorEarning.objects.filter(
            creator=creator_profile, earning_type='sale'
        ).aggregate(total_sales_earn=Sum('amount_earned'))
        sales_earnings = sales_earnings_aggregation['total_sales_earn'] or Decimal('0.00')

        view_earnings_aggregation = CreatorEarning.objects.filter(
            creator=creator_profile, earning_type='view'
        ).aggregate(total_view_earn=Sum('amount_earned'))
        view_earnings = view_earnings_aggregation['total_view_earn'] or Decimal('0.00')
        total_earnings_amount = sales_earnings + view_earnings

        total_withdrawn_aggregation = WithdrawalRequest.objects.filter(
            creator=creator_profile, status='completed'
        ).aggregate(total_withdrawn=Sum('amount'))
        total_withdrawn_amount = total_withdrawn_aggregation['total_withdrawn'] or Decimal('0.00')

        total_listens_aggregation = audiobooks_qs.aggregate(total_listens=Sum('total_views'))
        total_listens_all_time = total_listens_aggregation['total_listens'] or 0

        top_performing_book_obj = audiobooks_qs.order_by('-total_views').first()
        best_performing_book_info = None
        if top_performing_book_obj:
            best_performing_book_info = {
                'title': top_performing_book_obj.title,
                'listens': top_performing_book_obj.total_views or 0
            }

        recent_activities = []

        latest_book_uploads = Audiobook.objects.filter(creator=creator_profile).order_by(
            Coalesce('publish_date', 'created_at', Value(now - timedelta(days=365*10))) # Ensure a valid date for sorting
        )[:5]
        for book in latest_book_uploads:
            ts = book.publish_date if book.publish_date else (book.created_at if hasattr(book, 'created_at') else None)
            if ts:
                recent_activities.append({
                    'type': 'audiobook_upload', 'icon_class': 'fas fa-book-medical',
                    'description': f"Audiobook '{book.title}' published.", 'timestamp': ts,
                    'url': reverse('AudioXApp:creator_manage_upload_detail', args=[book.slug]) if book.slug else '#'
                })

        if hasattr(Audiobook, 'updated_at') and hasattr(Audiobook, 'created_at'):
            recent_book_edits = Audiobook.objects.filter(creator=creator_profile)\
                .annotate(effective_creation_date=Coalesce(F('publish_date'), F('created_at'))) \
                .filter(updated_at__gt=F('effective_creation_date') + timedelta(minutes=1))\
                .order_by('-updated_at')[:5]
            for book in recent_book_edits:
                if book.updated_at:
                    recent_activities.append({
                        'type': 'audiobook_edit', 'icon_class': 'fas fa-edit',
                        'description': f"Details for '{book.title}' updated.", 'timestamp': book.updated_at,
                        'url': reverse('AudioXApp:creator_manage_upload_detail', args=[book.slug]) if book.slug else '#'
                    })

        if hasattr(WithdrawalAccount, 'added_at'):
            recent_accounts_added = WithdrawalAccount.objects.filter(creator=creator_profile).order_by('-added_at')[:5]
            for acc in recent_accounts_added:
                if acc.added_at:
                    recent_activities.append({
                        'type': 'payment_account_add', 'icon_class': 'fas fa-university',
                        'description': f"{acc.get_account_type_display()} account added.", 'timestamp': acc.added_at,
                        'url': reverse('AudioXApp:creator_manage_withdrawal_accounts')
                    })

        latest_withdrawals = WithdrawalRequest.objects.filter(creator=creator_profile).order_by('-request_date')[:5]
        for wr in latest_withdrawals:
            if wr.request_date:
                recent_activities.append({
                    'type': 'withdrawal_request', 'icon_class': 'fas fa-hand-holding-usd',
                    'description': f"Withdrawal for Rs. {wr.amount:.2f} ({wr.get_status_display()}).", 'timestamp': wr.request_date,
                    'url': reverse('AudioXApp:creator_request_withdrawal_list')
                })

        if creator_profile.last_name_change_date and (now - creator_profile.last_name_change_date) < timedelta(days=90):
                    recent_activities.append({
                        'type': 'profile_update_name', 'icon_class': 'fas fa-user-edit',
                        'description': f"Display name changed.", 'timestamp': creator_profile.last_name_change_date,
                        'url': reverse('AudioXApp:update_creator_profile')
                    })

        recent_earning_events = CreatorEarning.objects.filter(creator=creator_profile).order_by('-transaction_date')[:5]
        for earning in recent_earning_events:
            if earning.transaction_date:
                activity_desc = f"Received earning of Rs. {earning.amount_earned:.2f}"
                title_to_display = earning.audiobook_title_at_transaction
                if not title_to_display and earning.audiobook:
                    title_to_display = earning.audiobook.title
                if title_to_display:
                    activity_desc += f" from '{title_to_display}'."
                else:
                    activity_desc += "."
                recent_activities.append({
                    'type': 'earning_received', 'icon_class': 'fas fa-coins',
                    'description': activity_desc, 'timestamp': earning.transaction_date,
                    'url': reverse('AudioXApp:creator_my_earnings')
                })

        recent_activities.sort(key=lambda x: x.get('timestamp', now - timedelta(days=365*20)), reverse=True)
        recent_activities = recent_activities[:15]


        today = timezone.now().date()
        months_data = OrderedDict()

        first_month_in_sequence = None
        for i in range(11, -1, -1): # Iterate from 11 down to 0 to get the last 12 months including current
            year = today.year
            month_offset = today.month - i
            final_month = month_offset
            final_year = year
            while final_month <= 0: # Adjust year and month if month_offset is zero or negative
                final_month += 12
                final_year -= 1
            
            month_start_dt_naive = datetime(final_year, final_month, 1)
            if first_month_in_sequence is None: # This will be the earliest month in our 12-month sequence
                first_month_in_sequence = month_start_dt_naive
            
            month_key = month_start_dt_naive.strftime('%Y-%m')
            month_label = month_start_dt_naive.strftime('%b %Y')
            months_data[month_key] = {'label': month_label, 'earnings': Decimal('0.00'), 'uploads': 0}

        # Ensure query_start_date is correctly set for timezone-aware or naive datetime
        query_start_date = first_month_in_sequence
        if query_start_date:
            query_start_date = datetime.combine(query_start_date, datetime.min.time()) # Start of the day
            if settings.USE_TZ:
                query_start_date = timezone.make_aware(query_start_date, timezone.get_default_timezone())
        else: # Fallback if first_month_in_sequence was somehow not set (should not happen with the loop logic)
            fallback_date = datetime(today.year -1, today.month, 1) # Approx 1 year ago
            query_start_date = timezone.make_aware(fallback_date) if settings.USE_TZ else fallback_date


        earnings_by_month_qs = CreatorEarning.objects.filter(
            creator=creator_profile,
            transaction_date__gte=query_start_date # Filter from the start of the 12-month period
        ).annotate(
            month=TruncMonth('transaction_date')
        ).values('month').annotate(
            total_amount=Sum('amount_earned')
        ).order_by('month')

        for earning_entry in earnings_by_month_qs:
            month_obj = earning_entry['month']
            # Convert date to naive datetime for key generation if it's aware
            month_dt_naive = timezone.localtime(month_obj) if timezone.is_aware(month_obj) else month_obj
            month_key = month_dt_naive.strftime('%Y-%m')
            if month_key in months_data:
                months_data[month_key]['earnings'] = earning_entry['total_amount'] or Decimal('0.00')

        if hasattr(Audiobook, 'created_at'):
            uploads_by_month_qs = Audiobook.objects.filter(
                creator=creator_profile,
                created_at__gte=query_start_date # Filter from the start of the 12-month period
            ).annotate(
                month=TruncMonth('created_at')
            ).values('month').annotate(
                count=Count('audiobook_id')
            ).order_by('month')

            for upload_entry in uploads_by_month_qs:
                month_obj = upload_entry['month']
                month_dt_naive = timezone.localtime(month_obj) if timezone.is_aware(month_obj) else month_obj
                month_key = month_dt_naive.strftime('%Y-%m')
                if month_key in months_data:
                    months_data[month_key]['uploads'] = upload_entry['count'] or 0
        
        # Ensure the order of labels/data matches the OrderedDict for the chart
        earnings_chart_labels = [data['label'] for data in months_data.values()]
        earnings_chart_values = [float(data['earnings']) for data in months_data.values()] # Chart.js usually expects numbers
        uploads_chart_labels = [data['label'] for data in months_data.values()] # Can be the same labels
        uploads_chart_values = [data['uploads'] for data in months_data.values()]

        earnings_chart_data = { 'labels': earnings_chart_labels, 'data': earnings_chart_values }
        uploads_chart_data = { 'labels': uploads_chart_labels, 'data': uploads_chart_values }


        context = _get_full_context(request)
        context.update({
            'creator': creator_profile,
            'total_earnings_amount': total_earnings_amount,
            'total_withdrawn_amount': total_withdrawn_amount,
            'total_audiobooks_count': total_audiobooks_count,
            'total_chapters_uploaded': total_chapters_uploaded,
            'total_listens_all_time': total_listens_all_time,
            'best_performing_book': best_performing_book_info,
            'audiobooks': recent_audiobooks_list,
            'recent_activities': recent_activities,
            'show_welcome_popup': not creator_profile.welcome_popup_shown,
            'available_balance': creator_profile.available_balance,
            'earnings_chart_data_json': json.dumps(earnings_chart_data, cls=DjangoJSONEncoder),
            'uploads_chart_data_json': json.dumps(uploads_chart_data, cls=DjangoJSONEncoder),
        })
        return render(request, 'creator/creator_dashboard.html', context)

    except FieldError as fe:
        logger.error(f"FieldError in creator_dashboard_view: {fe}", exc_info=True)
        messages.error(request, f"A data error occurred while loading the dashboard (missing field: {fe.args[0]}). Please ensure migrations are complete and the database schema is up to date. If the issue persists, contact support.")
        return redirect('AudioXApp:home')
    except Creator.DoesNotExist: # Should be caught by decorator, but as a safeguard
        logger.warning("Creator.DoesNotExist in creator_dashboard_view after initial check.")
        messages.error(request, "Creator profile not found. Please log in again.")
        return redirect('AudioXApp:home')
    except Exception as e:
        logger.error(f"Unexpected error in creator_dashboard_view: {e}", exc_info=True)
        messages.error(request, "An unexpected error occurred while loading your dashboard. Please try again later.")
        return redirect('AudioXApp:home')