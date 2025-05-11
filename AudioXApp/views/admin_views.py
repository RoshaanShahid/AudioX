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
from django.contrib.auth import logout as auth_logout
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect

from ..models import User, Admin, CoinTransaction, Creator, WithdrawalRequest, Audiobook, CreatorApplicationLog
from .utils import _get_full_context
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

        if email and Admin.objects.filter(email=email).exists():
            errors['email_prefix'] = 'An admin with this email already exists.'
        if username and Admin.objects.filter(username=username).exists():
            errors['username_prefix'] = 'An admin with this username already exists.'

        if email:
            try:
                validate_email(email)
            except ValidationError:
                errors['email_prefix'] = 'Invalid email format.'

        if errors:
            return JsonResponse({
                'status': 'error',
                'message': 'Please correct the errors below.',
                'errors': errors
            }, status=400)

        try:
            roles_string = ','.join(roles_list)
            admin = Admin.objects.create_admin(
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
        except ValueError as ve:
            return JsonResponse({'status': 'error', 'message': str(ve), 'errors': {'__all__': str(ve)}}, status=400)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': 'An unexpected server error occurred.',
                'errors': {'__all__': 'Server error during registration.'}
            }, status=500)
    else:
        context = {'role_choices': Admin.RoleChoices.choices}
        return render(request, 'admin/admin_register.html', context)


def adminlogin(request):
    if request.method == 'POST':
        login_identifier = request.POST.get('username')
        password = request.POST.get('password')
        admin = None

        if not login_identifier or not password:
            return JsonResponse({'status': 'error', 'message': 'Email/Username and password are required.'}, status=400)

        if '@' in login_identifier:
            try:
                admin_by_email = Admin.objects.get(email__iexact=login_identifier)
                if admin_by_email.check_password(password):
                    admin = admin_by_email
            except Admin.DoesNotExist:
                pass

        if not admin:
            try:
                admin_by_username = Admin.objects.get(username__iexact=login_identifier)
                if admin_by_username.check_password(password):
                    admin = admin_by_username
            except Admin.DoesNotExist:
                pass

        if admin:
            if admin.is_active:
                request.session['admin_id'] = admin.adminid
                request.session['admin_username'] = admin.username
                request.session['is_admin'] = True
                request.session.set_expiry(settings.SESSION_COOKIE_AGE)

                admin.last_login = timezone.now()
                admin.save(update_fields=['last_login'])

                return JsonResponse({'status': 'success', 'redirect_url': reverse('AudioXApp:admindashboard')})
            else:
                return JsonResponse({'status': 'error', 'message': 'This admin account is inactive.'}, status=403)
        else:
            return JsonResponse({'status': 'error', 'message': 'Incorrect email/username or password.'}, status=401)

    if request.session.get('is_admin') and request.session.get('admin_id'):
        return redirect('AudioXApp:admindashboard')
    return render(request, 'admin/admin_login.html')


@admin_login_required
@require_POST
@csrf_protect
def admin_logout_view(request):
    try:
        keys_to_delete = ['admin_id', 'admin_username', 'is_admin', 'admin_roles']
        for key in keys_to_delete:
            if key in request.session:
                del request.session[key]
        messages.success(request, "You have been logged out successfully.")
    except Exception as e:
        messages.error(request, "An error occurred during logout.")
    return redirect('AudioXApp:adminlogin')


@admin_role_required()
def admindashboard(request):
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
    except Exception as e:
        messages.error(request, "Could not retrieve withdrawal request count.")

    total_earnings_query = CoinTransaction.objects.filter(
        transaction_type='purchase', status='completed'
    ).exclude(
        pack_name__icontains='Subscription'
    ).aggregate(total=Sum('price'))
    total_earnings = total_earnings_query['total'] or Decimal('0.00')

    context = {
        'admin_user': request.admin_user,
        'active_page': 'dashboard',
        'is_creator_management_page': False,
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
    start_date = today - timedelta(days=6)
    daily_data = { (start_date + timedelta(days=i)).strftime('%Y-%m-%d'): {'approved': 0, 'rejected': 0, 'pending': 0, 'banned': 0} for i in range(7) }

    log_stats = CreatorApplicationLog.objects.filter(
        processed_at__date__gte=start_date,
        status__in=['approved', 'rejected']
    ).values('processed_at__date', 'status').annotate(count=Count('log_id'))

    pending_stats = Creator.objects.filter(
        verification_status='pending',
        last_application_date__date__gte=start_date
    ).values('last_application_date__date').annotate(count=Count('user_id'))

    banned_stats = Creator.objects.filter(
        is_banned=True,
        banned_at__date__gte=start_date
    ).values('banned_at__date').annotate(count=Count('user_id'))

    for stat in log_stats:
        date_str = stat['processed_at__date'].strftime('%Y-%m-%d')
        if date_str in daily_data:
            status = stat['status']
            daily_data[date_str][status] = stat['count']

    for stat in pending_stats:
        date_str = stat['last_application_date__date'].strftime('%Y-%m-%d')
        if date_str in daily_data:
            daily_data[date_str]['pending'] = stat['count']

    for stat in banned_stats:
        date_str = stat['banned_at__date'].strftime('%Y-%m-%d')
        if date_str in daily_data:
            daily_data[date_str]['banned'] = stat['count']

    daily_chart_labels = sorted(list(daily_data.keys()))
    daily_approvals_data = [daily_data[label]['approved'] for label in daily_chart_labels]
    daily_rejections_data = [daily_data[label]['rejected'] for label in daily_chart_labels]
    daily_pending_data = [daily_data[label]['pending'] for label in daily_chart_labels]
    daily_banned_data = [daily_data[label]['banned'] for label in daily_chart_labels]

    context = {
        'admin_user': request.admin_user,
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
    admin_user = request.admin_user

    pending_creators_qs = Creator.objects.filter(
        verification_status='pending'
    ).select_related('user').order_by('last_application_date')

    pending_creators_data = []
    for creator in pending_creators_qs:
        attempts_this_month = creator.get_attempts_this_month()
        is_re_application = bool(creator.rejection_reason) and attempts_this_month > 0

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
        'active_page': 'pending_creators',
        'is_creator_management_page': True,
    }

    try:
        return render(request, 'admin/creators_pendingapplications.html', context)
    except Exception as e:
        messages.error(request, "An unexpected error occurred while displaying the pending applications page.")
        return redirect(reverse('AudioXApp:admindashboard'))


@admin_role_required('manage_creators')
def admin_approved_creator_applications(request):
    admin_user = request.admin_user
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
        start_date = today
        approved_creators_qs = approved_creators_qs.filter(approved_at__date=start_date)
        filter_title = "Approved Today (Active)"
    elif filter_option == '3days':
        start_date = today - timedelta(days=2)
        approved_creators_qs = approved_creators_qs.filter(approved_at__date__gte=start_date)
        filter_title = "Approved in Last 3 Days (Active)"
    elif filter_option == '7days':
        start_date = today - timedelta(days=6)
        approved_creators_qs = approved_creators_qs.filter(approved_at__date__gte=start_date)
        filter_title = "Approved in Last 7 Days (Active)"
    else:
        filter_option = 'all'

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
    admin_user = request.admin_user
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
            to_attr='latest_rejected_logs'
        )
    ).order_by('-last_application_date')

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
            Q(rejection_reason__icontains=search_query) |
            Q(latest_rejected_logs__rejection_reason__icontains=search_query) |
            Q(latest_rejected_logs__processed_by__username__icontains=search_query)
        )
        rejected_creators_qs = rejected_creators_qs.filter(search_filter).distinct()
        filter_title += f" matching '{search_query}'"

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
    admin_user = request.admin_user
    search_query = request.GET.get('q', '').strip()
    found_creator = None
    application_logs = None

    if search_query:
        try:
            search_filter = None
            if search_query.lower().startswith('cid-'):
                search_filter = Q(cid__iexact=search_query)
            elif '@' in search_query:
                search_filter = Q(user__email__iexact=search_query)
            else:
                try:
                    user_id_int = int(search_query)
                    search_filter = Q(user_id=user_id_int)
                except ValueError:
                    search_filter = Q(user__username__iexact=search_query)

            if search_filter:
                found_creator = Creator.objects.select_related('user').get(search_filter)

            if found_creator:
                application_logs = found_creator.application_logs.select_related(
                    'processed_by'
                ).order_by('-application_date')

        except Creator.DoesNotExist:
            messages.warning(request, f"No creator found matching '{search_query}'.")
        except User.DoesNotExist:
            messages.warning(request, f"No user found matching '{search_query}'.")
        except Exception as e:
            messages.error(request, f"An error occurred during search: {e}")

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


@admin_role_required('manage_creators')
def admin_all_creators_list(request):
    admin_user = request.admin_user
    search_query = request.GET.get('q', '').strip()

    creators_qs = Creator.objects.select_related('user').order_by('user__date_joined')

    filter_title = "All Creators"

    if search_query:
        search_filter = (
            Q(user__user_id__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__full_name__icontains=search_query) |
            Q(creator_name__icontains=search_query) |
            Q(creator_unique_name__icontains=search_query) |
            Q(cid__icontains=search_query) |
            Q(verification_status__icontains=search_query) |
            Q(ban_reason__icontains=search_query) |
            Q(rejection_reason__icontains=search_query)
        )
        if 'banned' in search_query.lower():
            search_filter |= Q(is_banned=True)
        elif 'active' in search_query.lower() or 'approved' in search_query.lower():
            search_filter |= Q(is_banned=False, verification_status='approved')
        elif 'pending' in search_query.lower():
            search_filter |= Q(verification_status='pending')
        elif 'rejected' in search_query.lower():
            search_filter |= Q(is_banned=False, verification_status='rejected')

        creators_qs = creators_qs.filter(search_filter)
        filter_title += f" matching '{search_query}'"

    context = {
        'admin_user': admin_user,
        'all_creators': creators_qs,
        'filter_title': filter_title,
        'search_query': search_query,
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'all_creators',
        'is_creator_management_page': True,
    }
    return render(request, 'admin/creators_list.html', context)


@admin_role_required('manage_creators')
def admin_banned_creators_list(request):
    admin_user = request.admin_user
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
            Q(banned_by__username__icontains=search_query)
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


@admin_role_required('manage_creators')
def admin_view_creator_detail(request, user_id):
    admin_user = request.admin_user
    creator = get_object_or_404(
        Creator.objects.select_related('user', 'approved_by', 'banned_by'),
        user_id=user_id
    )

    total_audiobooks = Audiobook.objects.filter(creator=creator).count()
    recent_logs = creator.application_logs.select_related('processed_by').order_by('-application_date')[:5]

    context = {
        'admin_user': admin_user,
        'creator': creator,
        'total_audiobooks': total_audiobooks,
        'recent_logs': recent_logs,
        'is_banned': creator.is_banned,
        'is_pending': creator.verification_status == 'pending',
        'is_approved': creator.verification_status == 'approved',
        'is_rejected': creator.verification_status == 'rejected',
        'TIME_ZONE': settings.TIME_ZONE,
        'active_page': 'all_creators',
        'is_creator_management_page': True,
    }
    return render(request, 'admin/creator_detail.html', context)
