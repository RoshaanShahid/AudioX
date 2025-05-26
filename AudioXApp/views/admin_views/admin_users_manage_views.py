# AudioXApp/views/admin_views/admin_users_manage_views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import json
import logging
from django.db.models import Q, Prefetch, OuterRef, Subquery, Count, Value, CharField
from django.db.models.functions import Concat
from django.core.exceptions import FieldError
from django.core.paginator import Paginator

from ..decorators import admin_role_required
# Ensure all relevant models are imported correctly based on your models.py
from ...models import User, Admin, Creator, Subscription, CoinTransaction, AudiobookPurchase, Audiobook

logger = logging.getLogger(__name__)

@admin_role_required('manage_users')
def admin_manage_users(request):
    current_admin_user = getattr(request, 'admin_user', None) # Ensure admin_user is available
    total_user_count = User.objects.count()

    thirty_days_ago = timezone.now() - timedelta(days=30)
    active_user_count = User.objects.filter(
        is_active=True,
        is_banned_by_admin=False, # Assuming you only count non-banned users as active
        last_login__gte=thirty_days_ago
    ).count()

    new_users_count = User.objects.filter(date_joined__gte=timezone.now() - timedelta(days=7)).count()

    subscribed_user_count = 0
    try:
        # Efficiently count distinct users with an active subscription
        subscribed_user_count = User.objects.filter(
            subscription__status='active',
            subscription__end_date__gte=timezone.now() # Optional: ensure subscription is currently valid
        ).distinct().count()
    except FieldError:
        logger.warning("Could not filter User by subscription__status directly in admin_manage_users. Falling back to Subscription query.")
        # Fallback if direct spanning relation isn't working as expected or model structure differs
        subscribed_user_count = Subscription.objects.filter(
            status='active',
            user__isnull=False,
            end_date__gte=timezone.now() # Optional
        ).values('user').distinct().count()
    except Exception as e:
        logger.error(f"Error counting subscribed users in admin_manage_users: {e}")


    users_with_balance_count = User.objects.filter(coins__gt=0).count()
    banned_user_count = User.objects.filter(is_banned_by_admin=True).count()
    today = timezone.now().date()
    date_labels = [(today - timedelta(days=i)).strftime("%a") for i in range(6, -1, -1)] # Mon, Tue, Wed...
    daily_registrations_data = []
    daily_active_users_data = []

    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        next_day = day + timedelta(days=1) # Use next_day for exclusive upper bound
        daily_registrations_data.append(User.objects.filter(date_joined__gte=day, date_joined__lt=next_day).count())
        daily_active_users_data.append(User.objects.filter(
            last_login__gte=day,
            last_login__lt=next_day,
            is_active=True,
            is_banned_by_admin=False
        ).distinct().count()) # distinct() in case a user logs in multiple times on the same day

    context = {
        'active_page': 'manage_users_overview',
        'admin_user': current_admin_user,
        'total_user_count': total_user_count,
        'active_user_count': active_user_count,
        'new_users_count': new_users_count,
        'subscribed_user_count': subscribed_user_count,
        'users_with_balance_count': users_with_balance_count,
        'banned_user_count': banned_user_count,
        'daily_chart_labels_json': json.dumps(date_labels),
        'daily_registrations_data_json': json.dumps(daily_registrations_data),
        'daily_active_users_data_json': json.dumps(daily_active_users_data),
    }
    return render(request, 'admin/manage_users/manage_users.html', context)

@admin_role_required('manage_users')
def admin_all_users_list(request):
    current_admin_user = getattr(request, 'admin_user', None)
    users_queryset = User.objects.all()

    try:
        # Get the status of the latest subscription for each user
        latest_subscription_status = Subscription.objects.filter(
            user=OuterRef("pk")
        ).order_by("-start_date").values("status")[:1]

        users_queryset = users_queryset.annotate(
            current_subscription_status=Subquery(latest_subscription_status)
        )
    except Exception as e:
        logger.error(f"Could not annotate User queryset with subscription status: {e}")
        # Continue without annotation if it fails
        users_queryset = users_queryset.prefetch_related(
            Prefetch('subscription_set', queryset=Subscription.objects.order_by('-start_date'), to_attr='subscriptions_ordered')
        )


    users_queryset = users_queryset.order_by('-date_joined').prefetch_related(
        Prefetch('creator_profile', queryset=Creator.objects.all())
    )

    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')

    if search_query:
        users_queryset = users_queryset.filter(
            Q(email__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(user_id__icontains=search_query)
        )

    if status_filter:
        if status_filter == 'active':
            users_queryset = users_queryset.filter(is_active=True, is_banned_by_admin=False)
        elif status_filter == 'platform_banned':
            users_queryset = users_queryset.filter(is_banned_by_admin=True)
        elif status_filter == 'creators':
            users_queryset = users_queryset.filter(creator_profile__isnull=False, creator_profile__is_banned=False)
        elif status_filter == 'creators_banned':
            users_queryset = users_queryset.filter(creator_profile__isnull=False, creator_profile__is_banned=True)
        elif status_filter == 'subscribed':
            users_queryset = users_queryset.filter(current_subscription_status='active')
        elif status_filter == 'not_subscribed':
            users_queryset = users_queryset.filter(
                Q(current_subscription_status__isnull=True) | ~Q(current_subscription_status='active')
            )

    paginator = Paginator(users_queryset, 25)
    page_number = request.GET.get('page')
    users_list = paginator.get_page(page_number)

    if not hasattr(users_list.object_list[0] if users_list.object_list else None, 'current_subscription_status'):
        for user_instance in users_list:
            latest_sub = user_instance.subscriptions_ordered[0] if hasattr(user_instance, 'subscriptions_ordered') and user_instance.subscriptions_ordered else None
            user_instance.current_subscription_status = latest_sub.status if latest_sub else None


    context = {
        'active_page': 'manage_users_all',
        'admin_user': current_admin_user,
        'users_list': users_list,
        'search_query': search_query,
        'status_filter': status_filter,
    }
    return render(request, 'admin/manage_users/admin_total_users_list.html', context)


@admin_role_required('manage_users')
def admin_active_users_list(request):
    current_admin_user = getattr(request, 'admin_user', None)
    thirty_days_ago = timezone.now() - timedelta(days=30)

    users_queryset = User.objects.filter(
        is_active=True,
        is_banned_by_admin=False,
        last_login__gte=thirty_days_ago
    ).order_by('-last_login')

    users_queryset = users_queryset.select_related('subscription').prefetch_related(
        Prefetch('creator_profile', queryset=Creator.objects.all())
    )

    search_query = request.GET.get('q', '')
    if search_query:
        users_queryset = users_queryset.filter(
            Q(email__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(user_id__icontains=search_query)
        )

    paginator = Paginator(users_queryset, 25)
    page_number = request.GET.get('page')
    active_users = paginator.get_page(page_number)

    context = {
        'active_page': 'manage_users_active',
        'list_title': 'Active Users (Last 30 Days)',
        'admin_user': current_admin_user,
        'users_list': active_users,
        'search_query': search_query,
    }
    return render(request, 'admin/manage_users/admin_active_users_list.html', context)


@admin_role_required('manage_users')
def admin_new_users_list(request):
    current_admin_user = getattr(request, 'admin_user', None)
    seven_days_ago = timezone.now() - timedelta(days=7)

    users_queryset = User.objects.filter(
        date_joined__gte=seven_days_ago
    ).order_by('-date_joined')

    users_queryset = users_queryset.select_related('subscription').prefetch_related(
        Prefetch('creator_profile', queryset=Creator.objects.all())
    )

    search_query = request.GET.get('q', '')
    if search_query:
        users_queryset = users_queryset.filter(
            Q(email__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(user_id__icontains=search_query)
        )

    paginator = Paginator(users_queryset, 25)
    page_number = request.GET.get('page')
    new_users = paginator.get_page(page_number)

    context = {
        'active_page': 'manage_users_new',
        'list_title': 'New Users (Last 7 Days)',
        'admin_user': current_admin_user,
        'users_list': new_users,
        'search_query': search_query,
    }
    return render(request, 'admin/manage_users/admin_new_users_list.html', context)


@admin_role_required('manage_users')
def admin_subscribed_users_list(request):
    current_admin_user = getattr(request, 'admin_user', None)
    users_queryset = User.objects.filter(
        subscription__status='active'
    ).distinct().order_by('-subscription__start_date')

    users_queryset = users_queryset.select_related('subscription').prefetch_related(
        Prefetch('creator_profile', queryset=Creator.objects.all()),
        Prefetch(
            'coin_transactions',
            queryset=CoinTransaction.objects.filter(
                Q(description__icontains='subscription for plan') | Q(pack_name__icontains='Subscription')
            ).order_by('-transaction_date'),
            to_attr='subscription_payment_coin_transactions'
        )
    )

    search_query = request.GET.get('q', '')
    if search_query:
        users_queryset = users_queryset.filter(
            Q(email__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(user_id__icontains=search_query)
        )

    paginator = Paginator(users_queryset, 25)
    page_number = request.GET.get('page')
    subscribed_users = paginator.get_page(page_number)

    context = {
        'active_page': 'manage_users_subscribed',
        'list_title': 'Subscribed Users (Active)',
        'admin_user': current_admin_user,
        'users_list': subscribed_users,
        'search_query': search_query,
    }
    return render(request, 'admin/manage_users/admin_subscribed_users_list.html', context)

@admin_role_required('manage_users')
def admin_wallet_balances_list(request):
    current_admin_user = getattr(request, 'admin_user', None)

    users_queryset = User.objects.filter(coins__gt=0).order_by('-coins')

    users_queryset = users_queryset.select_related('subscription').prefetch_related(
        Prefetch('creator_profile', queryset=Creator.objects.all()),
        Prefetch('coin_transactions', queryset=CoinTransaction.objects.order_by('-transaction_date'))
    )

    search_query = request.GET.get('q', '')
    if search_query:
        users_queryset = users_queryset.filter(
            Q(email__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(user_id__icontains=search_query)
        )

    paginator = Paginator(users_queryset, 25)
    page_number = request.GET.get('page')
    users_with_balance = paginator.get_page(page_number)

    context = {
        'active_page': 'manage_users_wallet_balances',
        'list_title': 'Users with Wallet Balances',
        'admin_user': current_admin_user,
        'users_list': users_with_balance,
        'search_query': search_query,
    }
    return render(request, 'admin/manage_users/admin_users_wallet_balances.html', context)

@admin_role_required('manage_users')
def admin_banned_users_platform_list(request):
    current_admin_user = getattr(request, 'admin_user', None)

    users_queryset = User.objects.filter(is_banned_by_admin=True).order_by('-platform_banned_at')

    users_queryset = users_queryset.select_related('subscription', 'platform_banned_by').prefetch_related(
        Prefetch('creator_profile', queryset=Creator.objects.all())
    )

    search_query = request.GET.get('q', '')
    if search_query:
        users_queryset = users_queryset.filter(
            Q(email__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(user_id__icontains=search_query) |
            Q(platform_ban_reason__icontains=search_query) |
            Q(platform_banned_by__username__icontains=search_query)
        )

    paginator = Paginator(users_queryset, 25)
    page_number = request.GET.get('page')
    banned_users = paginator.get_page(page_number)

    context = {
        'active_page': 'manage_users_banned_platform',
        'list_title': 'Platform Banned Users',
        'admin_user': current_admin_user,
        'users_list': banned_users,
        'search_query': search_query,
    }
    return render(request, 'admin/manage_users/admin_banned_users_platform_list.html', context)


@admin_role_required('manage_users')
def admin_ban_user(request, user_id):
    if request.method == 'POST':
        user_to_ban = get_object_or_404(User, user_id=user_id)
        admin_user = getattr(request, 'admin_user', None)

        if not admin_user:
            messages.error(request, "Admin user not identified. Action cannot be performed.")
            return redirect(request.POST.get('next', reverse('AudioXApp:admin_all_users_list')))

        reason = request.POST.get('ban_reason', 'No reason provided.')

        if user_to_ban.is_superuser:
            messages.error(request, "Superusers cannot be banned from this panel.")
            return redirect(request.POST.get('next', reverse('AudioXApp:admin_all_users_list')))

        if user_to_ban.email == admin_user.email:
            messages.error(request, "You cannot ban the user account associated with your admin identity.")
            return redirect(request.POST.get('next', reverse('AudioXApp:admin_all_users_list')))

        user_to_ban.is_banned_by_admin = True
        user_to_ban.platform_ban_reason = reason
        user_to_ban.platform_banned_at = timezone.now()
        user_to_ban.platform_banned_by = admin_user
        user_to_ban.is_active = False
        user_to_ban.save()
        try:
            if hasattr(user_to_ban, 'creator_profile'):
                creator_profile = user_to_ban.creator_profile
                if creator_profile:
                    creator_profile.is_banned = True
                    creator_profile.ban_reason = f"Platform ban: {reason}"
                    creator_profile.banned_at = timezone.now()
                    creator_profile.banned_by = admin_user
                    creator_profile.save()
                    messages.success(request, f"User '{user_to_ban.username}' and their creator profile have been banned.")
                else:
                    messages.success(request, f"User '{user_to_ban.username}' has been banned from the platform.")
            else:
                 messages.success(request, f"User '{user_to_ban.username}' has been banned from the platform (no creator profile link found).")
        except Creator.DoesNotExist:
            messages.success(request, f"User '{user_to_ban.username}' has been banned from the platform (was not a creator).")
        except Exception as e:
            logger.error(f"Error during creator profile ban for user {user_to_ban.user_id}: {e}")
            messages.warning(request, f"User '{user_to_ban.username}' banned, but there was an issue updating creator status: {e}")

        redirect_url = request.POST.get('next', reverse('AudioXApp:admin_all_users_list'))
        return redirect(redirect_url)
    else:
        return redirect(reverse('AudioXApp:admin_all_users_list'))

@admin_role_required('manage_users')
def admin_unban_user(request, user_id):
    if request.method == 'POST':
        user_to_unban = get_object_or_404(User, user_id=user_id)
        admin_user = getattr(request, 'admin_user', None)
        if not admin_user:
            messages.error(request, "Admin user not identified. Action cannot be performed.")
            return redirect(request.POST.get('next', reverse('AudioXApp:admin_all_users_list')))

        user_to_unban.is_banned_by_admin = False
        user_to_unban.platform_ban_reason = None
        user_to_unban.platform_banned_at = None
        user_to_unban.platform_banned_by = None
        user_to_unban.is_active = True
        user_to_unban.save()
        try:
            if hasattr(user_to_unban, 'creator_profile'):
                creator_profile = user_to_unban.creator_profile
                if creator_profile and creator_profile.is_banned :
                    if "Platform ban:" in (creator_profile.ban_reason or ""):
                        creator_profile.is_banned = False
                        creator_profile.ban_reason = None
                        creator_profile.banned_at = None
                        creator_profile.banned_by = None
                        creator_profile.save()
                        messages.success(request, f"User '{user_to_unban.username}' and their creator profile have been unbanned.")
                    else:
                        messages.success(request, f"User '{user_to_unban.username}' has been unbanned. Creator profile ban reason was not 'Platform ban', so it was not automatically unbanned.")
                else:
                    messages.success(request, f"User '{user_to_unban.username}' has been unbanned from the platform.")
            else:
                messages.success(request, f"User '{user_to_unban.username}' has been unbanned from the platform (no creator profile link found).")

        except Creator.DoesNotExist:
            messages.success(request, f"User '{user_to_unban.username}' has been unbanned from the platform (was not a creator).")
        except Exception as e:
            logger.error(f"Error during creator profile unban for user {user_to_unban.user_id}: {e}")
            messages.warning(request, f"User '{user_to_unban.username}' unbanned, but there was an issue updating creator status: {e}")

        redirect_url = request.POST.get('next', reverse('AudioXApp:admin_all_users_list'))
        return redirect(redirect_url)
    else:
        return redirect(reverse('AudioXApp:admin_all_users_list'))

@admin_role_required('manage_users')
def admin_view_user_detail(request, user_id):
    try:
        user_id_int = int(user_id)
    except ValueError:
        messages.error(request, "Invalid User ID format.")
        return redirect(reverse('AudioXApp:admin_all_users_list'))

    user_to_view = get_object_or_404(User.objects.select_related('subscription'), user_id=user_id_int)
    creator_profile = None
    try:
        creator_profile = user_to_view.creator_profile
    except Creator.DoesNotExist:
        creator_profile = None
    except AttributeError:
        logger.warning(f"User model does not have 'creator_profile' attribute for user {user_id_int}.")
        creator_profile = None

    subscription_payment_q = (
        Q(description__icontains='subscription') |
        Q(pack_name__icontains='subscription') |
        Q(description__icontains='plan') |
        Q(pack_name__icontains='plan') |
        Q(transaction_type='subscription_payment')
    )

    subscription_coin_transactions_qs = user_to_view.coin_transactions.filter(
        subscription_payment_q
    ).order_by('-transaction_date')

    sub_tx_paginator = Paginator(subscription_coin_transactions_qs, 10)
    sub_tx_page_number = request.GET.get('sub_tx_page')
    paginated_subscription_transactions = sub_tx_paginator.get_page(sub_tx_page_number)

    other_coin_transactions_qs = user_to_view.coin_transactions.exclude(
        subscription_payment_q
    ).order_by('-transaction_date')

    coin_paginator = Paginator(other_coin_transactions_qs, 10)
    coin_page_number = request.GET.get('coin_page')
    paginated_other_coin_transactions = coin_paginator.get_page(coin_page_number)

    all_audiobook_purchases_qs = user_to_view.audiobook_purchases.filter(status='COMPLETED').order_by('-purchase_date').select_related('audiobook')
    purchase_paginator = Paginator(all_audiobook_purchases_qs, 10)
    purchase_page_number = request.GET.get('purchase_page')
    paginated_audiobook_purchases = purchase_paginator.get_page(purchase_page_number)

    context = {
        'active_page': 'manage_users_detail',
        'admin_user': getattr(request, 'admin_user', None),
        'user_to_view': user_to_view,
        'creator_profile': creator_profile,
        'subscription_info': getattr(user_to_view, 'subscription', None),
        'all_coin_transactions': paginated_other_coin_transactions,
        'all_subscription_transactions': paginated_subscription_transactions,
        'all_audiobook_purchases': paginated_audiobook_purchases,
    }
    return render(request, 'admin/manage_users/admin_user_detail.html', context)

@admin_role_required('manage_users')
def admin_user_payment_details_view(request):
    current_admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()

    users_found = User.objects.none()
    subscriptions_list = Subscription.objects.none()
    audiobook_purchases_list = AudiobookPurchase.objects.none()
    coin_purchases_list = CoinTransaction.objects.none()

    if search_query:
        # Case-insensitive exact match for both username and email
        user_filter = Q(username__iexact=search_query) | Q(email__iexact=search_query)
        users_found = User.objects.filter(user_filter)

        if not users_found.exists():
            messages.info(request, f"No users found with an exact match for '{search_query}'.")
    
    if users_found.exists():
        user_ids_to_fetch_transactions = [user.user_id for user in users_found]

        subscriptions_qs = Subscription.objects.filter(
            user_id__in=user_ids_to_fetch_transactions
        ).select_related('user').order_by('-user__email', '-start_date')
        
        sub_paginator = Paginator(subscriptions_qs, 10) 
        sub_page_number = request.GET.get('sub_page')
        subscriptions_list = sub_paginator.get_page(sub_page_number)

        audiobook_purchases_qs = AudiobookPurchase.objects.filter(
            user_id__in=user_ids_to_fetch_transactions,
            status='COMPLETED' 
        ).select_related('user', 'audiobook').order_by('-user__email', '-purchase_date')

        ab_purchase_paginator = Paginator(audiobook_purchases_qs, 10)
        ab_purchase_page_number = request.GET.get('abp_page')
        audiobook_purchases_list = ab_purchase_paginator.get_page(ab_purchase_page_number)

        coin_purchases_qs = CoinTransaction.objects.filter(
            user_id__in=user_ids_to_fetch_transactions,
            transaction_type='purchase', 
            status='completed' 
        ).select_related('user').order_by('-user__email', '-transaction_date')
        
        coin_purchase_paginator = Paginator(coin_purchases_qs, 10)
        coin_purchase_page_number = request.GET.get('cp_page')
        coin_purchases_list = coin_purchase_paginator.get_page(coin_purchase_page_number)
        
        if not (subscriptions_list.object_list or audiobook_purchases_list.object_list or coin_purchases_list.object_list):
             messages.info(request, "No payment transaction records found for the specified user(s).")
    elif not search_query and request.GET: 
        if 'q' in request.GET: 
             messages.info(request, "Please enter an email or username to search for payment details.")

    context = {
        'active_page': 'manage_users_payment_details', 
        'admin_user': current_admin_user,
        'search_query': search_query,
        'users_found_count': users_found.count() if users_found.exists() else 0,
        'subscriptions': subscriptions_list,
        'audiobook_purchases': audiobook_purchases_list,
        'coin_purchases': coin_purchases_list,
    }
    return render(request, 'admin/manage_users/admin_user_payment_details.html', context)