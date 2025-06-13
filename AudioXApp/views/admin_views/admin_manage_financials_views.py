# AudioXApp/views/admin_views/admin_manage_financials_views.py

import os
import io
from django.shortcuts import render, redirect
from django.conf import settings
from django.db.models import Sum, Q, F, Count
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.http import HttpResponse
from django.template.loader import get_template
from django.contrib import messages
from xhtml2pdf import pisa
import logging

from ...models import AudiobookPurchase, WithdrawalRequest, CoinTransaction, Subscription, Creator, User, Audiobook
from ..decorators import admin_role_required

logger = logging.getLogger(__name__)
MAX_TABLE_ROWS_HTML = 50

# --- Financial Data Filtering Helper ---

def _get_filtered_financial_data(date_from_str, date_to_str):
    date_from = None
    date_to = None
    date_filter_applied = False

    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            date_filter_applied = True
        except ValueError:
            logger.warning(f"Invalid date_from string: {date_from_str}")
            pass
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            date_filter_applied = True
        except ValueError:
            logger.warning(f"Invalid date_to string: {date_to_str}")
            pass

    audiobook_purchases_base_qs = AudiobookPurchase.objects.select_related('user', 'audiobook', 'audiobook__creator').filter(status='COMPLETED')
    coin_transactions_base_qs = CoinTransaction.objects.select_related('user').filter(status='completed')
    withdrawal_requests_base_qs = WithdrawalRequest.objects.select_related('creator__user', 'withdrawal_account', 'processed_by')
    subscriptions_base_qs = Subscription.objects.select_related('user')

    audiobook_purchases_qs = audiobook_purchases_base_qs
    coin_transactions_qs = coin_transactions_base_qs
    withdrawal_requests_qs = withdrawal_requests_base_qs
    subscriptions_qs = subscriptions_base_qs

    start_datetime_for_new_subs_count = timezone.make_aware(datetime.min)
    end_datetime_for_new_subs_count = timezone.now()

    if date_from:
        start_datetime = timezone.make_aware(datetime.combine(date_from, datetime.min.time()))
        start_datetime_for_new_subs_count = start_datetime
        audiobook_purchases_qs = audiobook_purchases_qs.filter(purchase_date__gte=start_datetime)
        coin_transactions_qs = coin_transactions_qs.filter(transaction_date__gte=start_datetime)
        subscriptions_qs = subscriptions_qs.filter(Q(start_date__gte=start_datetime) | Q(end_date__gte=start_datetime) | Q(status='active'))
        withdrawal_requests_qs = withdrawal_requests_qs.filter(Q(request_date__gte=start_datetime, status__in=['PENDING', 'PROCESSING']) | Q(processed_date__gte=start_datetime, status__in=['APPROVED', 'REJECTED']))
    
    if date_to:
        end_datetime = timezone.make_aware(datetime.combine(date_to, datetime.max.time()))
        end_datetime_for_new_subs_count = end_datetime
        audiobook_purchases_qs = audiobook_purchases_qs.filter(purchase_date__lte=end_datetime)
        coin_transactions_qs = coin_transactions_qs.filter(transaction_date__lte=end_datetime)
        subscriptions_qs = subscriptions_qs.filter(Q(start_date__lte=end_datetime))
        withdrawal_requests_qs = withdrawal_requests_qs.filter(Q(request_date__lte=end_datetime, status__in=['PENDING', 'PROCESSING']) | Q(processed_date__lte=end_datetime, status__in=['APPROVED', 'REJECTED']))

    revenue_from_platform_commission = audiobook_purchases_qs.aggregate(total=Sum('platform_fee_amount'))['total'] or Decimal('0.00')
    priced_coin_purchases_qs = coin_transactions_qs.filter(transaction_type='purchase', price__isnull=False)
    subscription_coin_purchase_filter = Q(pack_name__icontains='Subscription') | Q(description__icontains='Subscription purchase')
    revenue_from_subscription_sales = priced_coin_purchases_qs.filter(subscription_coin_purchase_filter).aggregate(total=Sum('price'))['total'] or Decimal('0.00')
    revenue_from_general_coin_sales = priced_coin_purchases_qs.exclude(subscription_coin_purchase_filter).aggregate(total=Sum('price'))['total'] or Decimal('0.00')
    grand_total_platform_revenue = (revenue_from_platform_commission + revenue_from_subscription_sales + revenue_from_general_coin_sales)
    summary_total_paid_for_audiobooks = audiobook_purchases_qs.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
    summary_creator_share_from_sales = audiobook_purchases_qs.aggregate(total=Sum('creator_share_amount'))['total'] or Decimal('0.00')
    
    summary_total_withdrawn_by_creators = WithdrawalRequest.objects.filter(status='COMPLETED')
    if date_from:
        summary_total_withdrawn_by_creators = summary_total_withdrawn_by_creators.filter(processed_date__gte=timezone.make_aware(datetime.combine(date_from, datetime.min.time())))
    if date_to:
        summary_total_withdrawn_by_creators = summary_total_withdrawn_by_creators.filter(processed_date__lte=timezone.make_aware(datetime.combine(date_to, datetime.max.time())))
    summary_total_withdrawn_by_creators = summary_total_withdrawn_by_creators.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    summary_active_subscriptions_count_overall = Subscription.objects.filter(status='active').count()
    new_subscriptions_in_period_count = Subscription.objects.filter(start_date__gte=start_datetime_for_new_subs_count, start_date__lte=end_datetime_for_new_subs_count).count()

    detailed_audiobook_purchases_qs = audiobook_purchases_qs
    detailed_coin_transactions_qs = coin_transactions_qs.filter(Q(transaction_type='purchase') | Q(transaction_type='spent') | Q(transaction_type='refund') | Q(transaction_type='reward') | Q(transaction_type='gift_sent') | Q(transaction_type='gift_received'))
    detailed_withdrawal_requests_qs = withdrawal_requests_qs
    detailed_subscriptions_qs = subscriptions_qs

    return {
        'date_from_str': date_from_str, 'date_to_str': date_to_str,
        'date_from': date_from, 'date_to': date_to,
        'date_filter_applied': date_filter_applied,
        'revenue_from_platform_commission': revenue_from_platform_commission,
        'revenue_from_subscription_sales': revenue_from_subscription_sales,
        'revenue_from_general_coin_sales': revenue_from_general_coin_sales,
        'grand_total_platform_revenue': grand_total_platform_revenue,
        'summary_total_paid_for_audiobooks': summary_total_paid_for_audiobooks,
        'summary_creator_share_from_sales': summary_creator_share_from_sales,
        'summary_total_withdrawn_by_creators': summary_total_withdrawn_by_creators,
        'summary_active_subscriptions_count_overall': summary_active_subscriptions_count_overall,
        'new_subscriptions_in_period_count': new_subscriptions_in_period_count,
        'detailed_audiobook_purchases_qs': detailed_audiobook_purchases_qs,
        'detailed_coin_transactions_qs': detailed_coin_transactions_qs,
        'detailed_withdrawal_requests_qs': detailed_withdrawal_requests_qs,
        'detailed_subscriptions_qs': detailed_subscriptions_qs,
    }

# --- Admin Financials Overview View ---

@admin_role_required('full_access', 'manage_financials')
def admin_financials_overview(request):
    date_from_str = request.GET.get('date_from')
    date_to_str = request.GET.get('date_to')
    
    data = _get_filtered_financial_data(date_from_str, date_to_str)

    context = {
        'admin_user': getattr(request, 'admin_user', None),
        'active_page': 'manage_financials_overview',
        'header_title': "Financials Report",
        'TIME_ZONE': settings.TIME_ZONE,
        'max_table_rows': MAX_TABLE_ROWS_HTML,
        'filter_date_from': data['date_from_str'] or '',
        'filter_date_to': data['date_to_str'] or '',
        'date_filter_applied': data['date_filter_applied'],
        'revenue_from_platform_commission': data['revenue_from_platform_commission'].quantize(Decimal("0.01")),
        'revenue_from_subscription_sales': data['revenue_from_subscription_sales'].quantize(Decimal("0.01")),
        'revenue_from_general_coin_sales': data['revenue_from_general_coin_sales'].quantize(Decimal("0.01")),
        'grand_total_platform_revenue': data['grand_total_platform_revenue'].quantize(Decimal("0.01")),
        'summary_total_paid_for_audiobooks': data['summary_total_paid_for_audiobooks'].quantize(Decimal("0.01")),
        'summary_creator_share_from_sales': data['summary_creator_share_from_sales'].quantize(Decimal("0.01")),
        'summary_total_withdrawn_by_creators': data['summary_total_withdrawn_by_creators'].quantize(Decimal("0.01")),
        'summary_active_subscriptions_count_overall': data['summary_active_subscriptions_count_overall'],
        'new_subscriptions_in_period_count': data['new_subscriptions_in_period_count'],
        'detailed_audiobook_purchases': data['detailed_audiobook_purchases_qs'].order_by('-purchase_date')[:MAX_TABLE_ROWS_HTML],
        'detailed_coin_transactions': data['detailed_coin_transactions_qs'].order_by('-transaction_date')[:MAX_TABLE_ROWS_HTML],
        'detailed_withdrawal_requests': data['detailed_withdrawal_requests_qs'].order_by('-request_date')[:MAX_TABLE_ROWS_HTML],
        'detailed_subscriptions': data['detailed_subscriptions_qs'].order_by('-start_date')[:MAX_TABLE_ROWS_HTML],
    }
    return render(request, 'admin/manage_financials/financials_overview.html', context)

# --- Generate Financials PDF Report ---

@admin_role_required('full_access', 'manage_financials')
def admin_generate_financials_report_pdf(request):
    date_from_str = request.GET.get('date_from')
    date_to_str = request.GET.get('date_to')

    data = _get_filtered_financial_data(date_from_str, date_to_str)

    context = {
        'generation_time': timezone.now(),
        'TIME_ZONE': settings.TIME_ZONE,
        'filter_date_from': data['date_from_str'] or "N/A",
        'filter_date_to': data['date_to_str'] or "N/A",
        'date_filter_applied': data['date_filter_applied'],
        'revenue_from_platform_commission': data['revenue_from_platform_commission'],
        'revenue_from_subscription_sales': data['revenue_from_subscription_sales'],
        'revenue_from_general_coin_sales': data['revenue_from_general_coin_sales'],
        'grand_total_platform_revenue': data['grand_total_platform_revenue'],
        'summary_total_paid_for_audiobooks': data['summary_total_paid_for_audiobooks'],
        'summary_creator_share_from_sales': data['summary_creator_share_from_sales'],
        'summary_total_withdrawn_by_creators': data['summary_total_withdrawn_by_creators'],
        'summary_active_subscriptions_count_overall': data['summary_active_subscriptions_count_overall'],
        'new_subscriptions_in_period_count': data['new_subscriptions_in_period_count'],
        'detailed_audiobook_purchases': data['detailed_audiobook_purchases_qs'].order_by('-purchase_date'),
        'detailed_coin_transactions': data['detailed_coin_transactions_qs'].order_by('-transaction_date'),
        'detailed_withdrawal_requests': data['detailed_withdrawal_requests_qs'].order_by('-request_date'),
        'detailed_subscriptions': data['detailed_subscriptions_qs'].order_by('-start_date'),
    }

    template_path = 'admin/manage_financials/financials_report_pdf.html'
    template = get_template(template_path)
    html = template.render(context)

    result = io.BytesIO()
    try:
        pdf_status = pisa.CreatePDF(html, dest=result)
    except Exception as e:
        logger.error(f"Error during pisa.CreatePDF: {e}", exc_info=True)
        messages.error(request, f"Could not generate PDF report due to an internal error: {e}")
        return redirect('AudioXApp:admin_financials_overview')

    if not pdf_status.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        fname_parts = ["AudioX_Financial_Report"]
        if data['date_filter_applied']:
            if data['date_from_str'] and data['date_to_str']:
                fname_parts.append(f"{data['date_from_str']}_to_{data['date_to_str']}")
            elif data['date_from_str']:
                fname_parts.append(f"from_{data['date_from_str']}")
            elif data['date_to_str']:
                fname_parts.append(f"until_{data['date_to_str']}")
        else:
            fname_parts.append("All_Time")
        
        filename = "_".join(fname_parts) + ".pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    logger.error(f"Error generating PDF with xhtml2pdf: {pdf_status.err} - Problematic HTML snippet (first 1000 chars): {html[:1000]}")
    messages.error(request, f"Could not generate PDF report. Error code: {pdf_status.err}. Please check server logs for more details or contact support if the issue persists.")
    return redirect('AudioXApp:admin_financials_overview')