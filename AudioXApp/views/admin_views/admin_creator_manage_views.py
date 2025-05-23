# AudioXApp/views/admin_views/admin_creator_manage_views.py

import json
from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Q, Prefetch
from django.core.exceptions import ObjectDoesNotExist

from ...models import Creator, Audiobook, WithdrawalRequest, CreatorApplicationLog # Relative imports
from ..decorators import admin_role_required # Relative import

# --- Admin Creator Management Views ---

@admin_role_required('manage_creators')
def admin_manage_creators(request):
    """Renders the main creator management page with summary statistics."""
    total_creator_count = Creator.objects.count()
    approved_creator_count = Creator.objects.filter(verification_status='approved', is_banned=False).count()
    pending_applications_count = Creator.objects.filter(verification_status='pending').count()
    rejected_creator_count = Creator.objects.filter(verification_status='rejected', is_banned=False).count()
    banned_creator_count = Creator.objects.filter(is_banned=True).count()
    total_applications_count = CreatorApplicationLog.objects.count()

    total_creator_audiobooks = Audiobook.objects.filter(
        creator__verification_status='approved',
        creator__is_banned=False
    ).count()

    pending_creator_withdrawals = WithdrawalRequest.objects.filter(
        creator__verification_status='approved',
        creator__is_banned=False,
        status='pending'
    ).count()

    today = timezone.now().date()
    start_date = today - timedelta(days=6)

    daily_data = {(start_date + timedelta(days=i)): {'approved': 0, 'rejected': 0, 'pending': 0, 'banned': 0} for i in range(7)}

    log_stats = CreatorApplicationLog.objects.filter(
        processed_at__date__gte=start_date,
        processed_at__date__lte=today,
        status__in=['approved', 'rejected']
    ).values('processed_at__date', 'status').annotate(count=Count('log_id'))

    for stat in log_stats:
        date_key = stat['processed_at__date']
        if date_key in daily_data:
            daily_data[date_key][stat['status']] = stat['count']

    pending_stats = Creator.objects.filter(
        verification_status='pending',
        last_application_date__date__gte=start_date,
        last_application_date__date__lte=today
    ).values('last_application_date__date').annotate(count=Count('user_id'))

    for stat in pending_stats:
        date_key = stat['last_application_date__date']
        if date_key in daily_data:
            daily_data[date_key]['pending'] += stat['count']

    banned_stats = Creator.objects.filter(
        is_banned=True,
        banned_at__date__gte=start_date,
        banned_at__date__lte=today
    ).values('banned_at__date').annotate(count=Count('user_id'))

    for stat in banned_stats:
        date_key = stat['banned_at__date']
        if date_key in daily_data:
            daily_data[date_key]['banned'] = stat['count']

    daily_chart_labels = sorted([date_obj.strftime('%Y-%m-%d') for date_obj in daily_data.keys()])
    daily_approvals_data = [daily_data[timezone.datetime.strptime(label, '%Y-%m-%d').date()]['approved'] for label in daily_chart_labels]
    daily_rejections_data = [daily_data[timezone.datetime.strptime(label, '%Y-%m-%d').date()]['rejected'] for label in daily_chart_labels]
    daily_pending_data = [daily_data[timezone.datetime.strptime(label, '%Y-%m-%d').date()]['pending'] for label in daily_chart_labels]
    daily_banned_data = [daily_data[timezone.datetime.strptime(label, '%Y-%m-%d').date()]['banned'] for label in daily_chart_labels]

    context = {
        'admin_user': getattr(request, 'admin_user', None),
        'total_creator_count': total_creator_count,
        'approved_creator_count': approved_creator_count,
        'pending_applications_count': pending_applications_count,
        'rejected_creator_count': rejected_creator_count,
        'banned_creator_count': banned_creator_count,
        'total_creator_audiobooks': total_creator_audiobooks,
        'pending_creator_withdrawals': pending_creator_withdrawals,
        'total_applications_count': total_applications_count,
        'daily_chart_labels_json': json.dumps(daily_chart_labels),
        'daily_approvals_data_json': json.dumps(daily_approvals_data),
        'daily_rejections_data_json': json.dumps(daily_rejections_data),
        'daily_pending_data_json': json.dumps(daily_pending_data),
        'daily_banned_data_json': json.dumps(daily_banned_data),
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_overview', # Updated active_page
        'is_creator_management_page': True,
    }
    return render(request, 'admin/manage_creators.html', context)


@admin_role_required('manage_creators')
def admin_pending_creator_applications(request):
    """Lists creator applications with 'pending' status."""
    admin_user = getattr(request, 'admin_user', None)

    pending_creators_qs = Creator.objects.filter(
        verification_status='pending'
    ).select_related('user').order_by('last_application_date')

    pending_creators_data = []
    for creator in pending_creators_qs:
        attempts_this_month = creator.get_attempts_this_month()
        # Check if there's any rejected log before the current pending application
        is_re_application = creator.application_logs.filter(
            status='rejected', 
            application_date__lt=creator.last_application_date if creator.last_application_date else timezone.now()
        ).exists()


        pending_creators_data.append({
            'creator': creator,
            'is_re_application': is_re_application,
            'attempt_count': attempts_this_month,
            'previous_rejection_reason': creator.rejection_reason if is_re_application else None
        })

    context = {
        'admin_user': admin_user,
        'pending_creators_data': pending_creators_data,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_pending', # Updated active_page
        'is_creator_management_page': True,
    }

    try:
        return render(request, 'admin/creators_pendingapplications.html', context)
    except Exception:
        messages.error(request, "An unexpected error occurred while displaying the pending applications page.")
        return redirect(reverse('AudioXApp:admindashboard'))


@admin_role_required('manage_creators')
def admin_approved_creator_applications(request):
    """Lists creator applications with 'approved' status (and not banned)."""
    admin_user = getattr(request, 'admin_user', None)
    filter_option = request.GET.get('filter', 'all')
    search_query = request.GET.get('q', '').strip()

    approved_creators_qs = Creator.objects.filter(
        verification_status='approved',
        is_banned=False
    ).select_related('user', 'approved_by').order_by('-approved_at')

    now = timezone.now()
    today = now.date()
    filter_title = "Approved Creators (Active)"

    if filter_option == 'today':
        approved_creators_qs = approved_creators_qs.filter(approved_at__date=today)
        filter_title = "Approved Today (Active)"
    elif filter_option == '3days':
        start_date = today - timedelta(days=2)
        approved_creators_qs = approved_creators_qs.filter(approved_at__date__gte=start_date)
        filter_title = "Approved in Last 3 Days (Active)"
    elif filter_option == '7days':
        start_date = today - timedelta(days=6)
        approved_creators_qs = approved_creators_qs.filter(approved_at__date__gte=start_date)
        filter_title = "Approved in Last 7 Days (Active)"

    if search_query:
        search_filter = (
            Q(user__user_id__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__full_name__icontains=search_query) |
            Q(creator_name__icontains=search_query) |
            Q(creator_unique_name__icontains=search_query) |
            Q(cid__icontains=search_query) |
            Q(approved_by__username__icontains=search_query)
        )
        approved_creators_qs = approved_creators_qs.filter(search_filter)
        filter_title += f" matching '{search_query}'"

    context = {
        'admin_user': getattr(request, 'admin_user', None),
        'approved_creators': approved_creators_qs,
        'filter_title': filter_title,
        'current_filter': filter_option,
        'search_query': search_query,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_approved', # Updated active_page
        'is_creator_management_page': True,
    }
    return render(request, 'admin/creators_approvedapplications.html', context)


@admin_role_required('manage_creators')
def admin_rejected_creator_applications(request):
    """Lists creator applications with 'rejected' status (and not banned)."""
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()

    rejected_creators_qs = Creator.objects.filter(
        verification_status='rejected',
        is_banned=False
    ).select_related(
        'user'
    ).prefetch_related(
        Prefetch(
            'application_logs',
            queryset=CreatorApplicationLog.objects.filter(status='rejected').select_related('processed_by').order_by('-processed_at'),
            to_attr='latest_rejected_logs' # Gets all rejected logs, template can pick the first
        )
    ).order_by('-last_application_date') # Or by the date of the latest rejection log

    filter_title = "Rejected Creator Applications"

    if search_query:
        search_filter = (
            Q(user__user_id__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__full_name__icontains=search_query) |
            Q(creator_name__icontains=search_query) |
            Q(creator_unique_name__icontains=search_query) |
            Q(cid__icontains=search_query) |
            Q(rejection_reason__icontains=search_query) # Searches current rejection reason on Creator model
        )
        # If searching by processed_by username, it's a bit more complex with prefetch
        # For simplicity, keeping search on Creator model fields or direct user fields.
        rejected_creators_qs = rejected_creators_qs.filter(search_filter).distinct()
        filter_title += f" matching '{search_query}'"

    context = {
        'admin_user': admin_user,
        'rejected_creators': rejected_creators_qs,
        'filter_title': filter_title,
        'search_query': search_query,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_rejected', # Updated active_page
        'is_creator_management_page': True,
    }
    return render(request, 'admin/creators_rejectedapplications.html', context)


@admin_role_required('manage_creators')
def admin_creator_application_history(request):
    """Displays the application history for a specific creator."""
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()
    found_creator = None
    application_logs = None

    if search_query:
        try:
            search_filter = None
            # Prioritize CID search if it matches the format
            if search_query.lower().startswith('cid-') and len(search_query) > 4:
                search_filter = Q(cid__iexact=search_query)
            # Then try User ID if it's purely numeric
            elif search_query.isdigit():
                 search_filter = Q(user_id=int(search_query))
            # Then try email
            elif '@' in search_query:
                search_filter = Q(user__email__iexact=search_query)
            # Fallback to username
            else:
                search_filter = Q(user__username__iexact=search_query)
            
            if search_filter:
                found_creator = Creator.objects.select_related('user').get(search_filter)

            if found_creator:
                application_logs = found_creator.application_logs.select_related(
                    'processed_by' # Admin user who processed the log
                ).order_by('-application_date') # Show newest first

        except Creator.DoesNotExist:
            messages.warning(request, f"No creator found matching '{search_query}'. Please try User ID, Email, Username, or CID (e.g., cid-xxxx).")
        except ValueError: # Handles if search_query.isdigit() is true but it's not a valid int for user_id
             messages.warning(request, f"Invalid User ID format for '{search_query}'.")
        except Exception:
            messages.error(request, f"An error occurred during the search. Please ensure your query is specific (User ID, Email, Username, or CID).")
            
    context = {
        'admin_user': admin_user,
        'search_query': search_query,
        'found_creator': found_creator,
        'application_logs': application_logs,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_history', # Updated active_page
        'is_creator_management_page': True,
    }
    return render(request, 'admin/creators_totalapplications.html', context)


@admin_role_required('manage_creators')
def admin_all_creators_list(request):
    """Lists all creators with filtering and search options."""
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()

    creators_qs = Creator.objects.select_related('user').order_by('user__date_joined')

    filter_title = "All Creators"

    if search_query:
        base_search_filter = (
            Q(user__user_id__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__full_name__icontains=search_query) |
            Q(creator_name__icontains=search_query) |
            Q(creator_unique_name__icontains=search_query) |
            Q(cid__icontains=search_query)
        )

        status_filter = Q()
        query_lower = search_query.lower()
        
        # Check for specific status keywords
        if 'banned' in query_lower:
            status_filter = Q(is_banned=True)
        elif 'active' in query_lower or 'approved' in query_lower: # 'active' implies approved and not banned
            status_filter = Q(is_banned=False, verification_status='approved')
        elif 'pending' in query_lower:
            status_filter = Q(verification_status='pending')
        elif 'rejected' in query_lower:
            status_filter = Q(is_banned=False, verification_status='rejected')
        # Check if the search query itself is a valid status choice
        elif search_query in [s[0] for s in Creator.VERIFICATION_STATUS_CHOICES]:
             status_filter = Q(verification_status=search_query)


        if status_filter: # If a status keyword was found, filter by that status
            creators_qs = creators_qs.filter(status_filter)
        else: # Otherwise, use the general base search filter
            creators_qs = creators_qs.filter(base_search_filter)

        filter_title += f" matching '{search_query}'"

    context = {
        'admin_user': getattr(request, 'admin_user', None),
        'all_creators': creators_qs,
        'filter_title': filter_title,
        'search_query': search_query,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_all', # Updated active_page
        'is_creator_management_page': True,
    }
    return render(request, 'admin/creators_list.html', context)


@admin_role_required('manage_creators')
def admin_banned_creators_list(request):
    """Lists all banned creators with search options."""
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()

    banned_creators_qs = Creator.objects.filter(
        is_banned=True
    ).select_related('user', 'banned_by').order_by('-banned_at')

    filter_title = "Banned Creators"

    if search_query:
        search_filter = (
            Q(user__user_id__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__full_name__icontains=search_query) |
            Q(creator_name__icontains=search_query) |
            Q(creator_unique_name__icontains=search_query) |
            Q(cid__icontains=search_query) |
            Q(ban_reason__icontains=search_query) |
            Q(banned_by__username__icontains=search_query) # Search by banning admin's username
        )
        banned_creators_qs = banned_creators_qs.filter(search_filter)
        filter_title += f" matching '{search_query}'"

    context = {
        'admin_user': getattr(request, 'admin_user', None),
        'banned_creators': banned_creators_qs,
        'filter_title': filter_title,
        'search_query': search_query,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'manage_creators_banned', # Updated active_page
        'is_creator_management_page': True,
    }
    return render(request, 'admin/creators_banned.html', context)


@admin_role_required('manage_creators')
def admin_view_creator_detail(request, user_id):
    """Displays detailed information for a specific creator."""
    admin_user = getattr(request, 'admin_user', None)

    # Ensure user_id is an integer before querying
    try:
        user_id_int = int(user_id)
    except ValueError:
        messages.error(request, "Invalid Creator ID format.")
        # Determine a sensible redirect, perhaps to the 'all creators' list or dashboard
        return redirect(reverse('AudioXApp:admin_all_creators_list'))


    creator = get_object_or_404(
        Creator.objects.select_related('user', 'approved_by', 'banned_by'),
        user_id=user_id_int # Use the validated integer
    )

    total_audiobooks = Audiobook.objects.filter(creator=creator).count()

    # Fetch all logs, not just recent, for a complete history view on this page
    application_logs = creator.application_logs.select_related('processed_by').order_by('-application_date')

    context = {
        'admin_user': admin_user,
        'creator': creator,
        'total_audiobooks': total_audiobooks,
        'application_logs': application_logs, # Changed from recent_logs
        'is_banned': creator.is_banned,
        'is_pending': creator.verification_status == 'pending',
        'is_approved': creator.verification_status == 'approved' and not creator.is_banned,
        'is_rejected': creator.verification_status == 'rejected' and not creator.is_banned,
        'TIME_ZONE': settings.TIME_ZONE,
        # Determine active_page based on creator's status for better sidebar highlighting
        'active_page': f'manage_creators_{creator.get_status_for_active_page()}',
        'is_creator_management_page': True,
    }
    return render(request, 'admin/creator_detail.html', context)