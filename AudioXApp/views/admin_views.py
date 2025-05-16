import json
from decimal import Decimal
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from django.core.validators import validate_email
from django.core.exceptions import ValidationError, ObjectDoesNotExist, ImproperlyConfigured
from django.utils import timezone
from django.db.models import Count, Sum, Q, Prefetch
from django.contrib.auth import logout as auth_logout # Not used directly for admin, but good to keep if there's a mix
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect

from ..models import User, Admin, CoinTransaction, Creator, WithdrawalRequest, Audiobook, CreatorApplicationLog # Ensure Admin model is correctly imported
# from .utils import _get_full_context # Assuming this is used by decorators or base views
from .decorators import admin_role_required, admin_login_required


def admin_welcome_view(request):
    if request.session.get('is_admin') and request.session.get('admin_id'):
        return redirect('AudioXApp:admindashboard')
    return render(request, 'admin/admin_welcome.html')

def adminsignup(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        username = request.POST.get('username')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        roles_list = request.POST.getlist('roles')

        errors = {}
        if not email or not username or not password or not confirm_password:
            errors['__all__'] = 'All credential fields are required.'
        if password != confirm_password:
            errors['confirm_password'] = 'Passwords do not match.'
        if not roles_list:
            errors['roles'] = 'Please select at least one role.'
        else:
            valid_roles = [choice[0] for choice in Admin.RoleChoices.choices]
            if not all(role in valid_roles for role in roles_list):
                errors['roles'] = 'Invalid role selected.'

        if email:
            if Admin.objects.filter(email__iexact=email).exists(): # Use iexact for case-insensitive check
                errors['email_prefix'] = 'An admin with this email already exists.'
            try:
                validate_email(email)
            except ValidationError:
                errors['email_prefix'] = 'Invalid email format.'
        
        if username and Admin.objects.filter(username__iexact=username).exists(): # Use iexact
            errors['username_prefix'] = 'An admin with this username already exists.'


        if errors:
            return JsonResponse({
                'status': 'error',
                'message': 'Please correct the errors below.',
                'errors': errors
            }, status=400)

        try:
            roles_string = ','.join(roles_list)
            admin = Admin.objects.create_admin( # Ensure create_admin handles roles_string
                email=email,
                username=username,
                password=password,
                roles=roles_string
            )
            return JsonResponse({
                'status': 'success',
                'message': 'Admin account created successfully!',
                'redirect_url': reverse('AudioXApp:adminlogin')
            })
        except ValueError as ve: # Catch specific errors from create_admin if possible
            return JsonResponse({'status': 'error', 'message': str(ve), 'errors': {'__all__': str(ve)}}, status=400)
        except Exception as e:
            # Log the exception e for server-side debugging
            print(f"Error during admin signup: {e}") 
            return JsonResponse({
                'status': 'error',
                'message': 'An unexpected server error occurred during registration.',
                'errors': {'__all__': 'Server error during registration.'}
            }, status=500)
    else:
        context = {'role_choices': Admin.RoleChoices.choices}
        return render(request, 'admin/admin_register.html', context)


def adminlogin(request):
    if request.method == 'POST':
        login_identifier = request.POST.get('username') # Corresponds to 'username' field in HTML
        password = request.POST.get('password')
        admin = None

        if not login_identifier or not password:
            return JsonResponse({'status': 'error', 'message': 'Email/Username and password are required.'}, status=400)

        # Try to authenticate by email first
        if '@' in login_identifier:
            try:
                # Using filter for case-insensitive email search and then get
                admin_by_email = Admin.objects.filter(email__iexact=login_identifier).first()
                if admin_by_email and admin_by_email.check_password(password):
                    admin = admin_by_email
            except Admin.DoesNotExist: # Should not happen with .first() but good for explicitness if using .get()
                pass
        
        # If not found by email or login_identifier is not an email, try by username
        if not admin:
            try:
                 # Using filter for case-insensitive username search and then get
                admin_by_username = Admin.objects.filter(username__iexact=login_identifier).first()
                if admin_by_username and admin_by_username.check_password(password):
                    admin = admin_by_username
            except Admin.DoesNotExist:
                pass

        if admin:
            if admin.is_active:
                request.session['admin_id'] = admin.adminid 
                request.session['admin_username'] = admin.username
                request.session['is_admin'] = True
                
                # Store admin roles in session
                # This assumes your Admin model has a method get_roles_list()
                # or a field 'roles' that can be parsed.
                try:
                    # Example: if Admin model has a method get_roles_list() -> returns list of strings
                    admin_roles_list = admin.get_roles_list() 
                    # Or, if roles are stored as a comma-separated string in a 'roles' field:
                    # admin_roles_list = [r.strip() for r in admin.roles.split(',') if r.strip()] if admin.roles else []
                except AttributeError:
                    admin_roles_list = [] # Default to empty list if method/field doesn't exist
                    # Consider logging this as a warning if roles are expected
                    print(f"Warning: Admin model for {admin.username} does not have get_roles_list() method or 'roles' field for role extraction.")


                request.session['admin_roles'] = admin_roles_list
                request.session.set_expiry(settings.SESSION_COOKIE_AGE) # Use Django's setting for session age

                admin.last_login = timezone.now()
                admin.save(update_fields=['last_login'])
                
                # request.session.save() # Explicitly saving is usually not needed if SessionMiddleware is active

                return JsonResponse({'status': 'success', 'redirect_url': reverse('AudioXApp:admindashboard')})
            else:
                return JsonResponse({'status': 'error', 'message': 'This admin account is inactive.'}, status=403)
        else:
            return JsonResponse({'status': 'error', 'message': 'Incorrect email/username or password.'}, status=401)

    # For GET requests, if already logged in, redirect to dashboard
    if request.session.get('is_admin') and request.session.get('admin_id'):
        return redirect('AudioXApp:admindashboard')
    
    return render(request, 'admin/admin_login.html')


@admin_login_required # Ensures admin is logged in
@require_POST # Ensures this view only accepts POST requests
@csrf_protect # Ensures CSRF protection
def admin_logout_view(request):
    try:
        # Keys to remove from session upon admin logout
        keys_to_delete = ['admin_id', 'admin_username', 'is_admin', 'admin_roles']
        for key in keys_to_delete:
            if key in request.session:
                del request.session[key]
        # request.session.flush() # Alternatively, to clear the entire session
        messages.success(request, "You have been logged out successfully.")
    except Exception as e:
        # Log the exception e for server-side debugging
        print(f"Error during admin logout: {e}")
        messages.error(request, "An error occurred during logout. Please try again.")
    return redirect('AudioXApp:adminlogin') # Redirect to the admin login page


@admin_role_required() # This decorator should handle both login check and role check (if any specific roles are needed by default)
def admindashboard(request):
    # Ensure request.admin_user is populated by your decorator or middleware
    # If not, the decorator should have redirected to login.
    # admin_user = getattr(request, 'admin_user', None) # This would be for direct access if needed

    total_user_count = User.objects.count()
    subscribed_user_count = User.objects.filter(subscription_type='PR').count()
    free_user_count = total_user_count - subscribed_user_count # More direct: User.objects.filter(subscription_type='FR').count() or similar
    active_creator_count = Creator.objects.filter(verification_status='approved', is_banned=False).count()
    pending_verification_count = Creator.objects.filter(verification_status='pending').count()
    total_audiobook_count = Audiobook.objects.count()
    creator_audiobook_count = Audiobook.objects.filter(creator__verification_status='approved', creator__is_banned=False).count()

    pending_withdrawal_count = 0
    try:
        pending_withdrawal_count = WithdrawalRequest.objects.filter(
            status='pending',
            creator__verification_status='approved', # Ensure these creators are active
            creator__is_banned=False
        ).count()
    except Exception as e:
        # Log the exception e
        print(f"Error fetching pending withdrawal count: {e}")
        messages.error(request, "Could not retrieve withdrawal request count due to a server error.")


    total_earnings_query = CoinTransaction.objects.filter(
        transaction_type='purchase', status='completed'
    ).exclude(
        pack_name__icontains='Subscription' # Assuming 'Subscription' distinguishes from other purchases
    ).aggregate(total=Sum('price'))
    total_earnings = total_earnings_query['total'] or Decimal('0.00')

    context = {
        'admin_user': getattr(request, 'admin_user', None), # Ensure this is populated by your auth system
        'active_page': 'dashboard',
        'is_creator_management_page': False, # Specific to your template structure
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


# ... (rest of your admin_views.py, ensuring decorators and session usage are consistent) ...

@admin_role_required('manage_creators')
def admin_manage_creators(request):
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
    start_date = today - timedelta(days=6) # For a 7-day period including today
    
    # Initialize daily_data correctly for the 7-day period
    daily_data = {(start_date + timedelta(days=i)): {'approved': 0, 'rejected': 0, 'pending': 0, 'banned': 0} for i in range(7)}

    # Approved/Rejected from Logs
    log_stats = CreatorApplicationLog.objects.filter(
        processed_at__date__gte=start_date,
        processed_at__date__lte=today, # Ensure up to today
        status__in=['approved', 'rejected']
    ).values('processed_at__date', 'status').annotate(count=Count('log_id'))

    for stat in log_stats:
        date_key = stat['processed_at__date']
        if date_key in daily_data: # Check if the date is in our range
            daily_data[date_key][stat['status']] = stat['count']
    
    # Pending from Creator table (based on last application date)
    pending_stats = Creator.objects.filter(
        verification_status='pending',
        last_application_date__date__gte=start_date,
        last_application_date__date__lte=today
    ).values('last_application_date__date').annotate(count=Count('user_id'))

    for stat in pending_stats:
        date_key = stat['last_application_date__date']
        if date_key in daily_data:
            daily_data[date_key]['pending'] += stat['count'] # Sum up if multiple entries for a day (though count should handle this)

    # Banned from Creator table
    banned_stats = Creator.objects.filter(
        is_banned=True,
        banned_at__date__gte=start_date,
        banned_at__date__lte=today
    ).values('banned_at__date').annotate(count=Count('user_id'))

    for stat in banned_stats:
        date_key = stat['banned_at__date']
        if date_key in daily_data:
            daily_data[date_key]['banned'] = stat['count']

    # Prepare data for charts
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
        'active_page': 'manage_creators',
        'is_creator_management_page': True,
    }
    return render(request, 'admin/manage_creators.html', context)


@admin_role_required('manage_creators')
def admin_pending_creator_applications(request):
    admin_user = getattr(request, 'admin_user', None)

    pending_creators_qs = Creator.objects.filter(
        verification_status='pending'
    ).select_related('user').order_by('last_application_date') # Or '-last_application_date' for newest first

    pending_creators_data = []
    for creator in pending_creators_qs:
        attempts_this_month = creator.get_attempts_this_month() # Ensure this method exists and works
        # is_re_application logic might need refinement based on how rejections are logged vs. current status
        is_re_application = creator.application_logs.filter(status='rejected').exists() and attempts_this_month > 0


        pending_creators_data.append({
            'creator': creator,
            'is_re_application': is_re_application,
            'attempt_count': attempts_this_month,
            'previous_rejection_reason': creator.rejection_reason if is_re_application else None # Ensure rejection_reason is on Creator model
        })

    context = {
        'admin_user': admin_user,
        'pending_creators_data': pending_creators_data,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'pending_creators',
        'is_creator_management_page': True,
    }

    try:
        return render(request, 'admin/creators_pendingapplications.html', context)
    except Exception as e:
        print(f"Error rendering pending applications page: {e}")
        messages.error(request, "An unexpected error occurred while displaying the pending applications page.")
        return redirect(reverse('AudioXApp:admindashboard'))


@admin_role_required('manage_creators')
def admin_approved_creator_applications(request):
    admin_user = getattr(request, 'admin_user', None)
    filter_option = request.GET.get('filter', 'all')
    search_query = request.GET.get('q', '').strip()

    approved_creators_qs = Creator.objects.filter(
        verification_status='approved',
        is_banned=False # Only show non-banned approved creators
    ).select_related('user', 'approved_by').order_by('-approved_at') # approved_by implies a FK to Admin model

    now = timezone.now()
    today = now.date()
    filter_title = "Approved Creators (Active)"

    if filter_option == 'today':
        approved_creators_qs = approved_creators_qs.filter(approved_at__date=today) # Use today, not start_date
        filter_title = "Approved Today (Active)"
    elif filter_option == '3days':
        start_date = today - timedelta(days=2)
        approved_creators_qs = approved_creators_qs.filter(approved_at__date__gte=start_date)
        filter_title = "Approved in Last 3 Days (Active)"
    elif filter_option == '7days':
        start_date = today - timedelta(days=6)
        approved_creators_qs = approved_creators_qs.filter(approved_at__date__gte=start_date)
        filter_title = "Approved in Last 7 Days (Active)"
    # 'all' filter_option needs no date filtering beyond the initial query

    if search_query:
        search_filter = (
            Q(user__user_id__icontains=search_query) | # Assuming user_id is a string or can be cast
            Q(user__email__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__full_name__icontains=search_query) |
            Q(creator_name__icontains=search_query) |
            Q(creator_unique_name__icontains=search_query) |
            Q(cid__icontains=search_query) | # Assuming cid is a field on Creator
            Q(approved_by__username__icontains=search_query) # Search by admin who approved
        )
        approved_creators_qs = approved_creators_qs.filter(search_filter)
        filter_title += f" matching '{search_query}'"

    context = {
        'admin_user': admin_user,
        'approved_creators': approved_creators_qs,
        'filter_title': filter_title,
        'current_filter': filter_option,
        'search_query': search_query,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'approved_creators',
        'is_creator_management_page': True,
    }
    return render(request, 'admin/creators_approvedapplications.html', context)


@admin_role_required('manage_creators')
def admin_rejected_creator_applications(request):
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()

    # Prefetch the latest rejected log for each creator
    # This is a bit complex; a simpler approach might be to just get all logs and process in template if needed,
    # or ensure 'rejection_reason' and 'rejected_by' are directly on the Creator model for the latest rejection.
    rejected_creators_qs = Creator.objects.filter(
        verification_status='rejected',
        is_banned=False 
    ).select_related(
        'user' 
        # 'rejected_by' # If you have a field on Creator for who rejected last
    ).prefetch_related(
        Prefetch(
            'application_logs', # Assuming related_name is 'application_logs'
            queryset=CreatorApplicationLog.objects.filter(status='rejected').select_related('processed_by').order_by('-processed_at'),
            to_attr='latest_rejected_logs' # This will be a list, you'd take the first one
        )
    ).order_by('-last_application_date') # Or by rejection date if available on Creator model

    filter_title = "Rejected Creator Applications"

    if search_query:
        # Adjust search_filter based on how rejection info is best accessed
        # (e.g., directly on Creator model or via the latest_rejected_logs)
        search_filter = (
            Q(user__user_id__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__full_name__icontains=search_query) |
            Q(creator_name__icontains=search_query) |
            Q(creator_unique_name__icontains=search_query) |
            Q(cid__icontains=search_query) |
            Q(rejection_reason__icontains=search_query) # If rejection_reason is on Creator for the latest
            # Add Q(latest_rejected_logs__rejection_reason__icontains=search_query) if querying prefetched data (more complex)
            # Add Q(latest_rejected_logs__processed_by__username__icontains=search_query)
        )
        rejected_creators_qs = rejected_creators_qs.filter(search_filter).distinct() # distinct if prefetch causes duplicates
        filter_title += f" matching '{search_query}'"

    # Process latest_rejected_logs in Python if needed before passing to template, or handle in template
    # For example, to get the single latest log:
    # for creator in rejected_creators_qs:
    #    creator.latest_log = creator.latest_rejected_logs[0] if creator.latest_rejected_logs else None
        
    context = {
        'admin_user': admin_user,
        'rejected_creators': rejected_creators_qs,
        'filter_title': filter_title,
        'search_query': search_query,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'rejected_creators',
        'is_creator_management_page': True,
    }
    return render(request, 'admin/creators_rejectedapplications.html', context)


@admin_role_required('manage_creators')
def admin_creator_application_history(request):
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()
    found_creator = None
    application_logs = None

    if search_query:
        try:
            search_filter = None
            # Prioritize CID search if it has a specific prefix
            if search_query.lower().startswith('cid-') and len(search_query) > 4:
                search_filter = Q(cid__iexact=search_query)
            elif '@' in search_query: # Likely an email
                search_filter = Q(user__email__iexact=search_query)
            else: # Could be user_id (int) or username (string)
                try:
                    user_id_int = int(search_query)
                    search_filter = Q(user_id=user_id_int)
                except ValueError: # Not an integer, so assume username
                    search_filter = Q(user__username__iexact=search_query)
            
            if search_filter:
                found_creator = Creator.objects.select_related('user').get(search_filter)
            
            if found_creator:
                application_logs = found_creator.application_logs.select_related(
                    'processed_by' # Admin who processed the log
                ).order_by('-application_date') # Or '-processed_at'

        except Creator.DoesNotExist:
            messages.warning(request, f"No creator found matching '{search_query}'. Please try User ID, Email, Username, or CID (e.g., cid-xxxx).")
        # User.DoesNotExist should not be hit if Creator query fails first, but good to be aware of
        except Exception as e:
            print(f"Error searching creator application history: {e}")
            messages.error(request, f"An error occurred during the search. Please ensure your query is specific (User ID, Email, Username, or CID).")


    context = {
        'admin_user': admin_user,
        'search_query': search_query,
        'found_creator': found_creator,
        'application_logs': application_logs,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'application_history',
        'is_creator_management_page': True,
    }
    return render(request, 'admin/creators_totalapplications.html', context)


@admin_role_required('manage_creators') # Or a more general role if all admins can view
def admin_all_creators_list(request):
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()

    creators_qs = Creator.objects.select_related('user').order_by('user__date_joined') # Default ordering

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
        
        # Handle status keywords in search
        status_filter = Q()
        query_lower = search_query.lower()
        if 'banned' in query_lower:
            status_filter = Q(is_banned=True)
        elif 'active' in query_lower or 'approved' in query_lower:
            status_filter = Q(is_banned=False, verification_status='approved')
        elif 'pending' in query_lower:
            status_filter = Q(verification_status='pending')
        elif 'rejected' in query_lower:
            status_filter = Q(is_banned=False, verification_status='rejected')
        elif search_query in [s[0] for s in Creator.VerificationStatusChoices.choices]: # Direct match for status choice
             status_filter = Q(verification_status=search_query)


        if status_filter: # If a status keyword was found, primarily filter by that
            creators_qs = creators_qs.filter(status_filter)
            # Optionally, you can combine with base_search_filter if you want to search within that status
            # creators_qs = creators_qs.filter(status_filter & base_search_filter) 
        else: # Otherwise, use the general text search
            creators_qs = creators_qs.filter(base_search_filter)
            
        filter_title += f" matching '{search_query}'"

    context = {
        'admin_user': admin_user,
        'all_creators': creators_qs,
        'filter_title': filter_title,
        'search_query': search_query,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'all_creators',
        'is_creator_management_page': True, # Assuming this page is part of creator management
    }
    return render(request, 'admin/creators_list.html', context)


@admin_role_required('manage_creators') # Or specific role for viewing banned creators
def admin_banned_creators_list(request):
    admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()

    banned_creators_qs = Creator.objects.filter(
        is_banned=True
    ).select_related('user', 'banned_by').order_by('-banned_at') # banned_by implies FK to Admin

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
            Q(ban_reason__icontains=search_query) | # Search in ban reason
            Q(banned_by__username__icontains=search_query) # Search by admin who banned
        )
        banned_creators_qs = banned_creators_qs.filter(search_filter)
        filter_title += f" matching '{search_query}'"

    context = {
        'admin_user': admin_user,
        'banned_creators': banned_creators_qs,
        'filter_title': filter_title,
        'search_query': search_query,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'banned_creators',
        'is_creator_management_page': True,
    }
    return render(request, 'admin/creators_banned.html', context)


@admin_role_required('manage_creators') # Or a role that can view creator details
def admin_view_creator_detail(request, user_id): # user_id refers to User's ID
    admin_user = getattr(request, 'admin_user', None)
    
    # Fetch creator by user_id, ensuring related objects are selected
    creator = get_object_or_404(
        Creator.objects.select_related('user', 'approved_by', 'banned_by'), # approved_by, banned_by are FKs to Admin
        user_id=user_id # This assumes user_id is the PK of the User model, and Creator has a OneToOneField to User
    )

    total_audiobooks = Audiobook.objects.filter(creator=creator).count()
    
    # Fetch recent application logs for this creator
    recent_logs = creator.application_logs.select_related('processed_by').order_by('-application_date')[:5] # Or '-processed_at'

    context = {
        'admin_user': admin_user,
        'creator': creator,
        'total_audiobooks': total_audiobooks,
        'recent_logs': recent_logs,
        'is_banned': creator.is_banned, # For quick checks in template
        'is_pending': creator.verification_status == 'pending',
        'is_approved': creator.verification_status == 'approved' and not creator.is_banned, # Active approved
        'is_rejected': creator.verification_status == 'rejected' and not creator.is_banned, # Active rejected
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'all_creators', # Or a more specific active page like 'view_creator_detail'
        'is_creator_management_page': True,
    }
    return render(request, 'admin/creator_detail.html', context)
