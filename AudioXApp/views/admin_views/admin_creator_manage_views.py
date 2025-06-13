# AudioXApp/views/admin_views/admin_creator_manage_views.py

import json
from datetime import timedelta, datetime as dt_datetime
import logging
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Q, Prefetch, Sum, Value, CharField, F, OuterRef, Subquery
from django.db.models.functions import Concat
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import Http404

from ...models import Creator, Audiobook, WithdrawalRequest, CreatorApplicationLog, Admin, AudiobookPurchase, CreatorEarning, WithdrawalAccount, Chapter
from ..decorators import admin_role_required

logger = logging.getLogger(__name__)

# --- Admin Creator Management Main Overview ---

@admin_role_required('manage_creators')
def admin_manage_creators(request):
    total_creator_count = Creator.objects.count()
    approved_creator_count = Creator.objects.filter(verification_status='approved', is_banned=False).count()
    pending_applications_count = Creator.objects.filter(verification_status='pending').count()
    rejected_creator_count = Creator.objects.filter(verification_status='rejected', is_banned=False).count()
    banned_creator_count = Creator.objects.filter(is_banned=True).count()
    total_applications_count = CreatorApplicationLog.objects.count()
    total_creator_audiobooks = Audiobook.objects.filter(creator__verification_status='approved', creator__is_banned=False).count()
    pending_or_processing_creator_withdrawals_count = WithdrawalRequest.objects.filter(status__in=['PENDING', 'PROCESSING']).count()

    today = timezone.now().date()
    start_date = today - timedelta(days=6)
    daily_data = {(start_date + timedelta(days=i)): {'approved': 0, 'rejected': 0, 'pending': 0, 'banned': 0} for i in range(7)}

    log_stats = CreatorApplicationLog.objects.filter(processed_at__date__gte=start_date, processed_at__date__lte=today, status__in=['approved', 'rejected']).values('processed_at__date', 'status').annotate(count=Count('log_id'))
    for stat in log_stats:
        date_key = stat['processed_at__date']
        if date_key in daily_data:
            daily_data[date_key][stat['status']] = stat['count']

    pending_creators_daily = Creator.objects.filter(verification_status='pending', last_application_date__date__gte=start_date, last_application_date__date__lte=today).values('last_application_date__date').annotate(count=Count('user_id'))
    for stat in pending_creators_daily:
        date_key = stat['last_application_date__date']
        if date_key in daily_data:
            daily_data[date_key]['pending'] = stat['count']

    banned_stats = Creator.objects.filter(is_banned=True, banned_at__date__gte=start_date, banned_at__date__lte=today).values('banned_at__date').annotate(count=Count('user_id'))
    for stat in banned_stats:
        date_key = stat['banned_at__date']
        if date_key in daily_data:
            daily_data[date_key]['banned'] = stat['count']

    daily_chart_labels = [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    daily_approvals_data = [daily_data.get(dt_datetime.strptime(label, '%Y-%m-%d').date(), {}).get('approved', 0) for label in daily_chart_labels]
    daily_rejections_data = [daily_data.get(dt_datetime.strptime(label, '%Y-%m-%d').date(), {}).get('rejected', 0) for label in daily_chart_labels]
    daily_pending_data = [daily_data.get(dt_datetime.strptime(label, '%Y-%m-%d').date(), {}).get('pending', 0) for label in daily_chart_labels]
    daily_banned_data = [daily_data.get(dt_datetime.strptime(label, '%Y-%m-%d').date(), {}).get('banned', 0) for label in daily_chart_labels]

    context = {
        'admin_user': getattr(request, 'admin_user', None),
        'total_creator_count': total_creator_count,
        'approved_creator_count': approved_creator_count,
        'pending_applications_count': pending_applications_count,
        'rejected_creator_count': rejected_creator_count,
        'banned_creator_count': banned_creator_count,
        'total_creator_audiobooks': total_creator_audiobooks,
        'pending_creator_withdrawals_count': pending_or_processing_creator_withdrawals_count,
        'total_applications_count': total_applications_count,
        'daily_chart_labels_json': json.dumps(daily_chart_labels),
        'daily_approvals_data_json': json.dumps(daily_approvals_data),
        'daily_rejections_data_json': json.dumps(daily_rejections_data),
        'daily_pending_data_json': json.dumps(daily_pending_data),
        'daily_banned_data_json': json.dumps(daily_banned_data),
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_overview',
    }
    return render(request, 'admin/manage_creators/manage_creators.html', context)

# --- Pending Creator Applications ---

@admin_role_required('manage_creators')
def admin_pending_creator_applications(request):
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()
    
    pending_creators_qs = Creator.objects.select_related('user').filter(verification_status='pending').order_by('-last_application_date')
    filter_title = "Pending Creator Applications"

    if search_query:
        pending_creators_qs = pending_creators_qs.filter(Q(cid__exact=search_query) | Q(user__email__iexact=search_query))
        filter_title = f"Pending Applications (Search: '{search_query}')"

    paginator = Paginator(pending_creators_qs, 25)
    page_number = request.GET.get('page')
    try:
        pending_creators_page = paginator.page(page_number)
    except PageNotAnInteger:
        pending_creators_page = paginator.page(1)
    except EmptyPage:
        pending_creators_page = paginator.page(paginator.num_pages)

    processed_pending_list = []
    for creator_obj in pending_creators_page.object_list:
        creator_obj.attempt_count = creator_obj.application_attempts_current_month
        creator_obj.is_re_application = creator_obj.application_attempts_current_month > 1 
        creator_obj.previous_rejection_reason = None
        if creator_obj.is_re_application and creator_obj.last_application_date:
            last_rejected_log = CreatorApplicationLog.objects.filter(creator=creator_obj, status='rejected', application_date__lt=creator_obj.last_application_date).order_by('-application_date').first()
            if last_rejected_log:
                creator_obj.previous_rejection_reason = last_rejected_log.rejection_reason
        processed_pending_list.append(creator_obj)
    
    pending_creators_page.object_list = processed_pending_list

    context = {
        'admin_user': admin_user,
        'pending_creators_data': pending_creators_page,
        'filter_title': filter_title,
        'search_query': search_query,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_pending',
    }
    return render(request, 'admin/manage_creators/admin_creators_pending_applications_list.html', context)

# --- Approved Creator Applications ---

@admin_role_required('manage_creators')
def admin_approved_creator_applications(request):
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()
    
    approved_creators_qs = Creator.objects.select_related('user').filter(verification_status='approved', is_banned=False).order_by('-approved_at', '-user__date_joined')
    filter_title = "Approved Creators"

    if search_query:
        approved_creators_qs = approved_creators_qs.filter(Q(cid__exact=search_query) | Q(user__email__iexact=search_query))
        filter_title = f"Approved Creators (Search: '{search_query}')"
    
    paginator = Paginator(approved_creators_qs, 25)
    page_number = request.GET.get('page')
    try:
        approved_creators_page = paginator.page(page_number)
    except PageNotAnInteger:
        approved_creators_page = paginator.page(1)
    except EmptyPage:
        approved_creators_page = paginator.page(paginator.num_pages)
    
    context = {
        'admin_user': admin_user,
        'approved_creators': approved_creators_page,
        'filter_title': filter_title,
        'search_query': search_query,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_approved',
    }
    return render(request, 'admin/manage_creators/admin_creators_approved_applications_list.html', context)

# --- Rejected Creator Applications ---

@admin_role_required('manage_creators')
def admin_rejected_creator_applications(request):
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()

    latest_rejected_log_prefetch = Prefetch('application_logs', queryset=CreatorApplicationLog.objects.filter(status='rejected').select_related('processed_by').order_by('-application_date'), to_attr='latest_rejected_log_list')
    rejected_creators_qs = Creator.objects.select_related('user').filter(verification_status='rejected', is_banned=False).prefetch_related(latest_rejected_log_prefetch).order_by('-last_application_date')
    filter_title = "Rejected Creator Applications"

    if search_query:
        rejected_creators_qs = rejected_creators_qs.filter(Q(cid__exact=search_query) | Q(user__email__iexact=search_query)).distinct()
        filter_title = f"Rejected Applications (Search by Creator: '{search_query}')"

    paginator = Paginator(rejected_creators_qs, 25)
    page_number = request.GET.get('page')
    try:
        rejected_creators_page = paginator.page(page_number)
    except PageNotAnInteger:
        rejected_creators_page = paginator.page(1)
    except EmptyPage:
        rejected_creators_page = paginator.page(paginator.num_pages)

    context = {
        'admin_user': admin_user,
        'rejected_creators': rejected_creators_page,
        'filter_title': filter_title,
        'search_query': search_query,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_rejected',
    }
    return render(request, 'admin/manage_creators/admin_creators_rejected_applications_list.html', context)

# --- Creator Application History ---

@admin_role_required('manage_creators')
def admin_creator_application_history(request):
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()
    found_creator = None
    application_logs_qs = CreatorApplicationLog.objects.none() 
    filter_title = "Creator Application History"

    if search_query:
        try:
            found_creator = Creator.objects.select_related('user').filter(Q(cid__exact=search_query) | Q(user__email__iexact=search_query)).first()
            if found_creator:
                application_logs_qs = CreatorApplicationLog.objects.filter(creator=found_creator).select_related('processed_by').order_by('-application_date', '-log_id')
                filter_title = f"Application History for {found_creator.creator_name or found_creator.user.username}"
            else:
                messages.warning(request, f"No creator found matching '{search_query}' by CID or Email. Showing all logs if applicable or none.")
                application_logs_qs = CreatorApplicationLog.objects.none()
                filter_title = "Creator Application History (No match)"
        except Exception as e:
            messages.error(request, f"An error occurred while searching for creator: {e}")
            logger.error(f"Error in admin_creator_application_history creator search: {e}", exc_info=True)
            application_logs_qs = CreatorApplicationLog.objects.none()
            filter_title = "Creator Application History (Search Error)"
            
    paginator = Paginator(application_logs_qs, 25)
    page_number = request.GET.get('page')
    try:
        application_logs_page = paginator.page(page_number)
    except PageNotAnInteger:
        application_logs_page = paginator.page(1)
    except EmptyPage:
        application_logs_page = paginator.page(paginator.num_pages)
    
    context = {
        'admin_user': admin_user,
        'search_query': search_query,
        'found_creator': found_creator,
        'application_logs_page': application_logs_page,
        'filter_title': filter_title,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_history',
    }
    return render(request, 'admin/manage_creators/admin_creators_all_applications_list.html', context)

# --- All Creators List ---

@admin_role_required('manage_creators')
def admin_all_creators_list(request):
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()
    status_filter_param = request.GET.get('status', '')
    
    creators_list = Creator.objects.select_related('user').all().order_by('-user__date_joined')
    filter_title_parts = []

    if search_query:
        creators_list = creators_list.filter(Q(cid__exact=search_query) | Q(user__email__iexact=search_query))
        filter_title_parts.append(f"Search: '{search_query}'")
        
    if status_filter_param:
        creators_list = creators_list.filter(verification_status=status_filter_param)
        status_display = dict(Creator.VERIFICATION_STATUS_CHOICES).get(status_filter_param, status_filter_param.capitalize())
        filter_title_parts.append(f"Status: {status_display}")

    filter_title = " | ".join(filter_title_parts) if filter_title_parts else "All Creators"

    paginator = Paginator(creators_list, 25)
    page_number = request.GET.get('page')
    try:
        all_creators_page = paginator.page(page_number)
    except PageNotAnInteger:
        all_creators_page = paginator.page(1)
    except EmptyPage:
        all_creators_page = paginator.page(paginator.num_pages)

    context = {
        'admin_user': admin_user,
        'all_creators_page': all_creators_page,
        'filter_title': filter_title,
        'search_query': search_query,
        'current_status_filter': status_filter_param,
        'verification_status_choices': Creator.VERIFICATION_STATUS_CHOICES,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_all',
    }
    return render(request, 'admin/manage_creators/admin_total_creators_list.html', context)

# --- Banned Creators List ---

@admin_role_required('manage_creators')
def admin_banned_creators_list(request):
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()
    
    banned_creators_qs = Creator.objects.select_related('user', 'banned_by').filter(is_banned=True).order_by('-banned_at', '-user__date_joined')
    filter_title = "Banned Creators"

    if search_query:
        banned_creators_qs = banned_creators_qs.filter(Q(cid__exact=search_query) | Q(user__email__iexact=search_query))
        filter_title = f"Banned Creators (Search: '{search_query}')"

    paginator = Paginator(banned_creators_qs, 25)
    page_number = request.GET.get('page')
    try:
        banned_creators_page = paginator.page(page_number)
    except PageNotAnInteger:
        banned_creators_page = paginator.page(1)
    except EmptyPage:
        banned_creators_page = paginator.page(paginator.num_pages)

    context = {
        'admin_user': admin_user,
        'banned_creators_page': banned_creators_page,
        'filter_title': filter_title,
        'search_query': search_query,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_banned',
    }
    return render(request, 'admin/manage_creators/admin_banned_creators_list.html', context)

# --- View Creator Detail ---

@admin_role_required('manage_creators')
def admin_view_creator_detail(request, user_id):
    admin_user = getattr(request, 'admin_user', None)
    try:
        user_id_int = int(user_id)
        creator = get_object_or_404(
            Creator.objects.select_related('user', 'approved_by', 'banned_by')
                            .prefetch_related(
                                'withdrawal_accounts', 
                                Prefetch('application_logs', queryset=CreatorApplicationLog.objects.select_related('processed_by').order_by('-application_date')), 
                                'audiobooks',
                                Prefetch('withdrawal_requests', queryset=WithdrawalRequest.objects.select_related('withdrawal_account', 'processed_by').order_by('-request_date'))
                            ),
            user_id=user_id_int
        )
    except ValueError:
        raise Http404("Creator ID must be an integer.")

    primary_withdrawal_account = creator.primary_withdrawal_account
    total_audiobooks = creator.audiobooks.count() 
    
    total_audiobook_sales = AudiobookPurchase.objects.filter(audiobook__creator=creator, status='COMPLETED').aggregate(total_sales=Sum('amount_paid'))['total_sales'] or Decimal('0.00')
    total_withdrawn_by_creator = WithdrawalRequest.objects.filter(creator=creator, status='COMPLETED').aggregate(total_withdrawn=Sum('amount'))['total_withdrawn'] or Decimal('0.00')
    
    application_logs_qs = creator.application_logs.all()
    paginator_logs = Paginator(application_logs_qs, 10)
    page_number_logs = request.GET.get('log_page')
    try:
        application_logs_page = paginator_logs.page(page_number_logs)
    except PageNotAnInteger:
        application_logs_page = paginator_logs.page(1)
    except EmptyPage:
        application_logs_page = paginator_logs.page(paginator_logs.num_pages)

    withdrawal_requests_qs = creator.withdrawal_requests.all()
    paginator_withdrawals = Paginator(withdrawal_requests_qs, 5)
    page_number_withdrawals = request.GET.get('withdrawal_page')
    try:
        withdrawal_requests_page = paginator_withdrawals.page(page_number_withdrawals)
    except PageNotAnInteger:
        withdrawal_requests_page = paginator_withdrawals.page(1)
    except EmptyPage:
        withdrawal_requests_page = paginator_withdrawals.page(paginator_withdrawals.num_pages)

    context = {
        'admin_user': admin_user,
        'creator': creator, 
        'primary_withdrawal_account': primary_withdrawal_account, 
        'total_audiobooks': total_audiobooks,
        'total_audiobook_sales': total_audiobook_sales, 
        'total_withdrawn_by_creator': total_withdrawn_by_creator,
        'application_logs_page': application_logs_page, 
        'withdrawal_requests_history_page': withdrawal_requests_page, 
        'is_banned': creator.is_banned,
        'is_pending': creator.verification_status == 'pending',
        'is_approved_active': creator.verification_status == 'approved' and not creator.is_banned,
        'is_rejected_not_banned': creator.verification_status == 'rejected' and not creator.is_banned,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': f'manage_creators_detail_{user_id_int}',
    }
    return render(request, 'admin/manage_creators/admin_creator_detail.html', context)

# --- Manage Withdrawal Requests ---

@admin_role_required('manage_withdrawals')
@transaction.atomic
def admin_manage_withdrawal_requests(request):
    admin_user_profile = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')

    if request.method == 'POST':
        request_id_to_update = request.POST.get('request_id')
        action = request.POST.get('action') 
        
        processing_admin_instance = None
        if admin_user_profile and isinstance(admin_user_profile, Admin):
            processing_admin_instance = admin_user_profile
        else:
            try:
                if hasattr(request, 'user') and request.user.is_authenticated and hasattr(request.user, 'email'):
                    current_django_user_email = request.user.email
                    processing_admin_instance = Admin.objects.get(email=current_django_user_email)
                if not processing_admin_instance:
                    messages.error(request, "Could not identify the processing admin. Action aborted.")
                    current_query_params = request.GET.urlencode()
                    return redirect(reverse('AudioXApp:admin_manage_withdrawal_requests') + (f'?{current_query_params}' if current_query_params else ''))
            except Admin.DoesNotExist:
                messages.error(request, "Admin profile matching your user email not found. Action aborted.")
                current_query_params = request.GET.urlencode()
                return redirect(reverse('AudioXApp:admin_manage_withdrawal_requests') + (f'?{current_query_params}' if current_query_params else ''))
            except Exception as e:
                messages.error(request, f"Error identifying processing admin: {e}. Action aborted.")
                current_query_params = request.GET.urlencode()
                return redirect(reverse('AudioXApp:admin_manage_withdrawal_requests') + (f'?{current_query_params}' if current_query_params else ''))

        if processing_admin_instance:
            try:
                wd_request = WithdrawalRequest.objects.select_related('creator').get(id=request_id_to_update)
                original_status = wd_request.status

                if action == 'approve_and_complete':
                    if original_status == 'PROCESSING':
                        admin_remarks = request.POST.get('completion_notes', '')
                        payment_reference = request.POST.get('completion_reference', '')
                        payment_slip_file = request.FILES.get('payment_slip')
                        wd_request.complete_payment_by_admin(admin_user=processing_admin_instance, payment_slip_file=payment_slip_file, reference=payment_reference, notes=admin_remarks)
                        messages.success(request, f"Withdrawal request {wd_request.display_request_id} successfully Approved & Completed.")
                    else:
                        messages.error(request, f"Request {wd_request.display_request_id} must be 'Processing' to be approved. Current status: {wd_request.get_status_display()}.")
                
                elif action == 'reject':
                    if original_status in ['PENDING', 'PROCESSING']:
                        admin_remarks = request.POST.get('rejection_reason', '')
                        if not admin_remarks: 
                            messages.error(request, "Rejection reason is required when rejecting a request.")
                        else:
                            wd_request.reject_by_admin(admin_user=processing_admin_instance, reason=admin_remarks)
                            messages.success(request, f"Withdrawal request {wd_request.display_request_id} has been Rejected.")
                    else:
                        messages.error(request, f"Request {wd_request.display_request_id} cannot be rejected. Current status: {wd_request.get_status_display()}.")

                elif action == 'mark_processing':
                    if original_status == 'PENDING':
                        admin_remarks = request.POST.get('processing_notes', '')
                        wd_request.mark_as_processing_by_admin(admin_user=processing_admin_instance, notes=admin_remarks)
                        messages.info(request, f"Withdrawal request {wd_request.display_request_id} marked as Processing.")
                    else:
                        messages.error(request, f"Request {wd_request.display_request_id} must be 'Pending' to be marked as processing. Current status: {wd_request.get_status_display()}.")
                
                else:
                    messages.error(request, f"Invalid action '{action}' provided for withdrawal request.")
            
            except WithdrawalRequest.DoesNotExist:
                messages.error(request, "Withdrawal request not found.")
            except ValueError as ve:
                messages.error(request, str(ve))
            except Exception as e:
                messages.error(request, f"An unexpected error occurred: {e}")
                logger.error(f"Error updating withdrawal request {request_id_to_update} with action '{action}': {e}", exc_info=True)
            
        redirect_url = reverse('AudioXApp:admin_manage_withdrawal_requests')
        query_params_from_get = request.GET.urlencode() 
        if query_params_from_get:
            redirect_url += "?" + query_params_from_get
        return redirect(redirect_url)

    withdrawal_requests_qs = WithdrawalRequest.objects.select_related('creator__user', 'processed_by', 'withdrawal_account').all().order_by('-request_date')
    filter_title_parts = []
    if search_query:
        is_req_id_search = False
        if search_query.upper().startswith('REQ-') and search_query[4:].isdigit():
            try:
                actual_id = int(search_query[4:]) - 10000 
                if actual_id >= 0:
                    withdrawal_requests_qs = withdrawal_requests_qs.filter(id=actual_id)
                    is_req_id_search = True
            except ValueError:
                pass 
        if not is_req_id_search:
            try:
                amount_val = Decimal(search_query)
                withdrawal_requests_qs = withdrawal_requests_qs.filter(amount=amount_val)
            except InvalidOperation:
                withdrawal_requests_qs = withdrawal_requests_qs.filter(Q(creator__cid__exact=search_query) | Q(creator__user__email__iexact=search_query))
        filter_title_parts.append(f"Search: '{search_query}'")

    if status_filter and status_filter.upper() != 'ALL':
        withdrawal_requests_qs = withdrawal_requests_qs.filter(status=status_filter)
        status_display = dict(WithdrawalRequest.STATUS_CHOICES).get(status_filter, status_filter.capitalize())
        filter_title_parts.append(f"Status: {status_display}")
    
    filter_title = " | ".join(filter_title_parts) if filter_title_parts else "All Withdrawal Requests"

    paginator = Paginator(withdrawal_requests_qs, 25)
    page_number = request.GET.get('page')
    try:
        withdrawal_requests_page = paginator.page(page_number)
    except PageNotAnInteger:
        withdrawal_requests_page = paginator.page(1)
    except EmptyPage:
        withdrawal_requests_page = paginator.page(paginator.num_pages)

    context = {
        'admin_user': admin_user_profile,
        'withdrawal_requests_page': withdrawal_requests_page,
        'filter_title': filter_title,
        'current_status_filter': status_filter if status_filter else 'all', 
        'search_query': search_query,
        'status_choices': WithdrawalRequest.STATUS_CHOICES, 
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_withdrawals',
    }
    return render(request, 'admin/manage_creators/admin_creators_withdrawal_requests_list.html', context)

# --- Creator Uploads and Earnings View ---

@admin_role_required('manage_creators')
def admin_creator_uploads_view(request):
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()
    found_creator = None
    audiobooks_page = None
    filter_title = "View Creator Uploads & Earnings"

    if request.method == 'GET' and search_query:
        try:
            found_creator = Creator.objects.select_related('user').filter(Q(cid__exact=search_query) | Q(user__email__iexact=search_query)).first()
        except Exception as e:
            messages.error(request, f"An error occurred while searching for the creator: {str(e)}")
            logger.error(f"Error searching for creator in admin_creator_uploads_view: {e}", exc_info=True)
            found_creator = None

        if found_creator:
            filter_title = f"Uploads by: {found_creator.creator_name} ({found_creator.cid or found_creator.user.email})"
            audiobooks_list = Audiobook.objects.filter(creator=found_creator).prefetch_related(Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order'))).order_by('-created_at')
            processed_audiobooks = []
            for audiobook_item in audiobooks_list:
                creator_earnings_data = CreatorEarning.objects.filter(creator=found_creator, audiobook=audiobook_item).aggregate(creator_share_from_book=Sum('amount_earned'))
                audiobook_item.creator_specific_earnings = creator_earnings_data['creator_share_from_book'] or Decimal('0.00')
                platform_commission_data = AudiobookPurchase.objects.filter(audiobook=audiobook_item, status='COMPLETED').aggregate(total_platform_commission=Sum('platform_fee_amount'))
                audiobook_item.platform_commission_from_book = platform_commission_data['total_platform_commission'] or Decimal('0.00')
                processed_audiobooks.append(audiobook_item)

            paginator = Paginator(processed_audiobooks, 10) 
            page_number = request.GET.get('page')
            try:
                audiobooks_page = paginator.page(page_number)
            except PageNotAnInteger:
                audiobooks_page = paginator.page(1)
            except EmptyPage:
                audiobooks_page = paginator.page(paginator.num_pages)
            if not audiobooks_page.object_list:
                messages.info(request, f"Creator '{found_creator.creator_name}' ({found_creator.cid or found_creator.user.email}) has not uploaded any audiobooks yet.")
        elif search_query: 
            messages.warning(request, f"No creator found matching your query: '{search_query}'. Please search by exact Creator ID or Email.")

    context = {
        'admin_user': admin_user,
        'search_query': search_query,
        'found_creator': found_creator,
        'audiobooks_page': audiobooks_page,
        'filter_title': filter_title,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_uploads', 
    }
    return render(request, 'admin/manage_creators/admin_creator_uploads.html', context)
