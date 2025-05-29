# AudioXApp/views/admin_views/admin_users_manage_views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import json
import logging
from django.db.models import Q, Prefetch, OuterRef, Subquery, Count # Removed unused Value, CharField, Case, When, BooleanField, Concat
from django.core.exceptions import FieldError
from django.core.paginator import Paginator
from django.http import Http404


from ..decorators import admin_role_required
from ...models import (
    User, Admin, Creator, Subscription, CoinTransaction, AudiobookPurchase, Audiobook,
    CreatorApplicationLog, UserLibraryItem, ListeningHistory, Review,
    WithdrawalAccount, WithdrawalRequest, Ticket, TicketMessage
)

logger = logging.getLogger(__name__)

@admin_role_required('manage_users')
def admin_manage_users(request):
    current_admin_user = getattr(request, 'admin_user', None)
    total_user_count = User.objects.count()

    thirty_days_ago = timezone.now() - timedelta(days=30)
    active_user_count = User.objects.filter(
        is_active=True,
        is_banned_by_admin=False,
        last_login__gte=thirty_days_ago
    ).count()

    new_users_count = User.objects.filter(date_joined__gte=timezone.now() - timedelta(days=7)).count()

    subscribed_user_count = 0
    try:
        subscribed_user_count = User.objects.filter(
            subscription__status='active',
            subscription__end_date__gte=timezone.now()
        ).distinct().count()
    except FieldError:
        logger.warning("Could not filter User by subscription__status directly in admin_manage_users. Falling back to Subscription query.")
        subscribed_user_count = Subscription.objects.filter(
            status='active',
            user__isnull=False,
            end_date__gte=timezone.now()
        ).values('user').distinct().count()
    except Exception as e:
        logger.error(f"Error counting subscribed users in admin_manage_users: {e}")


    users_with_balance_count = User.objects.filter(coins__gt=0).count()
    banned_user_count = User.objects.filter(is_banned_by_admin=True).count()
    today = timezone.now().date()
    date_labels = [(today - timedelta(days=i)).strftime("%a") for i in range(6, -1, -1)]
    daily_registrations_data = []
    daily_active_users_data = []

    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        next_day = day + timedelta(days=1)
        daily_registrations_data.append(User.objects.filter(date_joined__gte=day, date_joined__lt=next_day).count())
        daily_active_users_data.append(User.objects.filter(
            last_login__gte=day,
            last_login__lt=next_day,
            is_active=True,
            is_banned_by_admin=False
        ).distinct().count())

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
        latest_subscription_status = Subscription.objects.filter(
            user=OuterRef("pk")
        ).order_by("-start_date").values("status")[:1]
        users_queryset = users_queryset.annotate(
            current_subscription_status=Subquery(latest_subscription_status)
        )
    except Exception as e:
        logger.error(f"Could not annotate User queryset with subscription status: {e}")
        users_queryset = users_queryset.prefetch_related(
            Prefetch('subscription_set', queryset=Subscription.objects.order_by('-start_date'), to_attr='subscriptions_ordered')
        )

    users_queryset = users_queryset.order_by('-date_joined').prefetch_related(
        Prefetch('creator_profile', queryset=Creator.objects.all())
    )

    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')

    if search_query:
        users_queryset = users_queryset.filter(
            Q(email__iexact=search_query) | Q(phone_number__iexact=search_query)
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

    if users_list.object_list and not hasattr(users_list.object_list[0], 'current_subscription_status'):
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

    search_query = request.GET.get('q', '').strip()
    if search_query:
        users_queryset = users_queryset.filter(
            Q(email__iexact=search_query) | Q(phone_number__iexact=search_query)
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

    search_query = request.GET.get('q', '').strip()
    if search_query:
        users_queryset = users_queryset.filter(
            Q(email__iexact=search_query) | Q(phone_number__iexact=search_query)
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

    search_query = request.GET.get('q', '').strip()
    if search_query:
        users_queryset = users_queryset.filter(
            Q(email__iexact=search_query) | Q(phone_number__iexact=search_query)
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

    search_query = request.GET.get('q', '').strip()
    if search_query:
        users_queryset = users_queryset.filter(
            Q(email__iexact=search_query) | Q(phone_number__iexact=search_query)
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

    search_query = request.GET.get('q', '').strip()
    if search_query:
        user_filter = Q(email__iexact=search_query) | Q(phone_number__iexact=search_query)
        users_queryset = users_queryset.filter(
            user_filter |
            Q(platform_ban_reason__icontains=search_query) |
            Q(platform_banned_by__username__icontains=search_query)
        ).distinct()

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

        if isinstance(admin_user, Admin) and user_to_ban.email == admin_user.email :
             pass

        user_to_ban.is_banned_by_admin = True
        user_to_ban.platform_ban_reason = reason
        user_to_ban.platform_banned_at = timezone.now()
        if isinstance(admin_user, Admin):
             user_to_ban.platform_banned_by = admin_user
        else:
             user_to_ban.platform_banned_by = None
             logger.warning(f"Admin user type mismatch when banning. Admin user: {admin_user}")


        user_to_ban.is_active = False
        user_to_ban.save()
        try:
            if hasattr(user_to_ban, 'creator_profile'):
                creator_profile = user_to_ban.creator_profile
                if creator_profile:
                    creator_profile.is_banned = True
                    creator_profile.ban_reason = f"Platform ban: {reason}"
                    creator_profile.banned_at = timezone.now()
                    if isinstance(admin_user, Admin):
                        creator_profile.banned_by = admin_user
                    else:
                        creator_profile.banned_by = None
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
                    if creator_profile.ban_reason and "Platform ban:" in creator_profile.ban_reason:
                        creator_profile.is_banned = False
                        creator_profile.ban_reason = None
                        creator_profile.banned_at = None
                        creator_profile.banned_by = None
                        creator_profile.save()
                        messages.success(request, f"User '{user_to_unban.username}' and their creator profile have been unbanned.")
                    else:
                        messages.success(request, f"User '{user_to_unban.username}' has been unbanned. Creator profile ban was not (or not solely) due to platform ban and was not automatically unbanned. Please review creator status separately if needed.")
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
        creator_profile = getattr(user_to_view, 'creator_profile', None)
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
        Q(transaction_type='spent', description__icontains='subscription')
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

# THIS IS THE VIEW FUNCTION TO FOCUS ON FOR THE FIX
@admin_role_required('manage_users')
def admin_user_payment_details_view(request):
    current_admin_user = getattr(request, 'admin_user', None)
    search_query = request.GET.get('q', '').strip()

    users_found = User.objects.none()
    subscriptions_list = Subscription.objects.none()
    audiobook_purchases_list = AudiobookPurchase.objects.none()
    coin_purchases_list = CoinTransaction.objects.none()

    if search_query:
        user_filter = Q(email__iexact=search_query) | Q(phone_number__iexact=search_query)
        users_found = User.objects.filter(user_filter)

        if not users_found.exists():
            messages.info(request, f"No users found matching '{search_query}'.")

    if users_found.exists():
        user_ids_to_fetch_transactions = [user.user_id for user in users_found]

        # 1. Subscriptions (Direct Stripe Subscriptions from Subscription model)
        subscriptions_qs = Subscription.objects.filter(
            user_id__in=user_ids_to_fetch_transactions
        ).select_related('user').order_by('-user__email', '-start_date')
        sub_paginator = Paginator(subscriptions_qs, 10)
        sub_page_number = request.GET.get('sub_page')
        subscriptions_list = sub_paginator.get_page(sub_page_number)

        # 2. Audiobook Purchases (Direct Stripe Purchases from AudiobookPurchase model)
        audiobook_purchases_qs = AudiobookPurchase.objects.filter(
            user_id__in=user_ids_to_fetch_transactions,
            status='COMPLETED'
        ).select_related('user', 'audiobook').order_by('-user__email', '-purchase_date')
        ab_purchase_paginator = Paginator(audiobook_purchases_qs, 10)
        ab_purchase_page_number = request.GET.get('abp_page')
        audiobook_purchases_list = ab_purchase_paginator.get_page(ab_purchase_page_number)

        # 3. Coin Purchases (Users buying coin packs with real money)
        coin_purchases_qs = CoinTransaction.objects.filter(
            user_id__in=user_ids_to_fetch_transactions,
            transaction_type='purchase', # Only actual coin pack buys
            status='completed'
        ).exclude( # *** ADDED EXCLUSION based on the image and problem description ***
            Q(pack_name__icontains='subscription') | 
            Q(pack_name__icontains='plan') | # To catch "Monthly Plan" etc.
            Q(description__icontains='subscription purchase by admin') | # Example if admin logs it this way
            Q(description__icontains='subscription payment')
            # Add more specific known pack_names for subscriptions if they exist and are problematic:
            # Q(pack_name__iexact='Monthly Premium Subscription')
        ).select_related('user').order_by('-user__email', '-transaction_date')
        
        coin_purchase_paginator = Paginator(coin_purchases_qs, 10)
        coin_purchase_page_number = request.GET.get('cp_page')
        coin_purchases_list = coin_purchase_paginator.get_page(coin_purchase_page_number)

        if not (subscriptions_list.object_list or audiobook_purchases_list.object_list or coin_purchases_list.object_list):
            messages.info(request, "No payment transaction records (subscriptions, audiobook purchases, or coin purchases) found for the specified user(s).")
    elif not search_query and request.GET.get('q') is not None:
        messages.info(request, "Please enter an Email or Phone Number to search for payment details.")


    context = {
        'active_page': 'manage_users_payment_details',
        'admin_user': current_admin_user,
        'search_query': search_query,
        'users_found_count': users_found.count() if users_found else 0,
        'subscriptions': subscriptions_list,
        'audiobook_purchases': audiobook_purchases_list,
        'coin_purchases': coin_purchases_list, # This list is now more strictly coin pack purchases
    }
    return render(request, 'admin/manage_users/admin_user_payment_details.html', context)


@admin_role_required('manage_users')
def admin_user_activity_log_view(request, user_id=None):
    admin_user = getattr(request, 'admin_user', None)

    target_user_instance = None
    activities = []
    paginated_activities = None

    search_query_get = request.GET.get('q', '').strip()
    search_query_display = search_query_get

    if user_id:
        try:
            target_user_instance = User.objects.prefetch_related('creator_profile').get(user_id=user_id)
            search_query_display = target_user_instance.email
        except User.DoesNotExist:
            messages.error(request, f"User with ID '{user_id}' not found. Please search for a user.")
        except ValueError:
            messages.error(request, "Invalid User ID format provided in the URL.")

    if search_query_get:
        user_lookup = Q(email__iexact=search_query_get) | Q(phone_number__iexact=search_query_get)
        found_users = User.objects.filter(user_lookup).prefetch_related('creator_profile')

        if found_users.count() == 1:
            target_user_instance = found_users.first()
            search_query_display = search_query_get
        elif found_users.count() > 1:
            messages.warning(request, f"Multiple users found for query '{search_query_get}'. Please use a more specific Email or Phone Number.")
            target_user_instance = None
        else:
            if not (user_id and not target_user_instance):
                 messages.error(request, f"No user found matching query '{search_query_get}'.")
            target_user_instance = None
    elif not user_id and not search_query_get and 'q' in request.GET:
        messages.info(request, "Please enter an Email or Phone Number to search.")

    if target_user_instance:
        # --- Activity Fetching Logic (Same as provided in Response #12) ---
        # 1. User Registration
        activities.append({'timestamp': target_user_instance.date_joined, 'type': 'Account', 'details': f'User account created. Username: {target_user_instance.username}, Email: {target_user_instance.email}.','icon': 'fas fa-user-plus text-blue-500'})
        # 2. Platform Ban / Unban events
        if target_user_instance.platform_banned_at:
            banned_by_username = target_user_instance.platform_banned_by.username if target_user_instance.platform_banned_by else "Unknown Admin"
            activities.append({'timestamp': target_user_instance.platform_banned_at, 'type': 'Account','details': f'User was banned from the platform by {banned_by_username}. Reason: {target_user_instance.platform_ban_reason or "Not specified"}.','icon': 'fas fa-user-slash text-red-500'})
        # 3. Creator related activities
        creator_profile = getattr(target_user_instance, 'creator_profile', None)
        if creator_profile:
            if creator_profile.approved_at:
                approved_by_admin = creator_profile.approved_by.username if creator_profile.approved_by else "System/Unknown"
                activities.append({'timestamp': creator_profile.approved_at, 'type': 'Creator','details': f'Creator application approved by {approved_by_admin}. Creator ID: {creator_profile.cid or "N/A"}.','icon': 'fas fa-user-check text-green-500'})
            for log in CreatorApplicationLog.objects.filter(creator=creator_profile).select_related('processed_by').order_by('application_date'):
                processed_by_admin = log.processed_by.username if log.processed_by else "N/A"
                activity_detail_base = f'Creator application (submitted {log.application_date.strftime("%b %d, %Y")})'
                if log.status == 'submitted' and not log.processed_at: activity_detail = f'{activity_detail_base} was submitted. Name: {log.creator_name_submitted}, Handle: @{log.creator_unique_name_submitted}.'
                elif log.status == 'approved': activity_detail = f'{activity_detail_base} was approved by {processed_by_admin} on {log.processed_at.strftime("%b %d, %Y") if log.processed_at else "N/A"}.'
                elif log.status == 'rejected': activity_detail = f'{activity_detail_base} was rejected by {processed_by_admin} on {log.processed_at.strftime("%b %d, %Y") if log.processed_at else "N/A"}. Reason: {log.rejection_reason or "Not specified"}.'
                else: activity_detail = f'{activity_detail_base} has status: {log.get_status_display()}.'
                activities.append({'timestamp': log.application_date,'type': 'Creator Application','details': activity_detail,'icon': 'fas fa-file-signature text-purple-500'})
            if creator_profile.banned_at:
                banned_by_admin = creator_profile.banned_by.username if creator_profile.banned_by else "Unknown Admin"
                activities.append({'timestamp': creator_profile.banned_at,'type': 'Creator','details': f'Creator profile banned by {banned_by_admin}. Reason: {creator_profile.ban_reason or "Not specified"}.','icon': 'fas fa-user-tie-slash text-red-600'})
            if creator_profile.last_name_change_date: activities.append({'timestamp': creator_profile.last_name_change_date, 'type': 'Creator Profile', 'details': f'Creator display name changed. Current: {creator_profile.creator_name}.', 'icon': 'fas fa-id-badge text-purple-500'})
            if creator_profile.last_unique_name_change_date: activities.append({'timestamp': creator_profile.last_unique_name_change_date, 'type': 'Creator Profile', 'details': f'Creator unique name (@handle) changed. Current: @{creator_profile.creator_unique_name}.', 'icon': 'fas fa-at text-purple-500'})
            if creator_profile.profile_pic_updated_at: activities.append({'timestamp': creator_profile.profile_pic_updated_at, 'type': 'Creator Profile', 'details': 'Creator profile picture updated.', 'icon': 'fas fa-image text-purple-500'})
        # 4. Audiobook Purchases
        for purchase in AudiobookPurchase.objects.filter(user=target_user_instance).select_related('audiobook').order_by('purchase_date'):
            audiobook_title = purchase.audiobook.title if purchase.audiobook else "Audiobook (Deleted or ID missing)"
            activities.append({'timestamp': purchase.purchase_date,'type': 'Audiobook Purchase','details': f'Purchased "{audiobook_title}" for PKR {purchase.amount_paid:.2f}. Status: {purchase.get_status_display()}.','icon': 'fas fa-book-medical text-lime-600' if purchase.status == 'COMPLETED' else 'fas fa-book text-gray-500'})
        # 5. Library Additions
        for item in UserLibraryItem.objects.filter(user=target_user_instance).select_related('audiobook').order_by('added_at'):
            audiobook_title = item.audiobook.title if item.audiobook else "Audiobook (Deleted or ID missing)"
            activities.append({'timestamp': item.added_at,'type': 'Library','details': f'Added "{audiobook_title}" to library.','icon': 'fas fa-bookmark text-pink-500'})
        # 6. Listening History
        for history in ListeningHistory.objects.filter(user=target_user_instance).select_related('audiobook', 'current_chapter').order_by('-last_listened_at')[:50]:
            audiobook_title = history.audiobook.title if history.audiobook else "Audiobook (Deleted or ID missing)"
            chapter_name = f", Chapter: {history.current_chapter.chapter_name}" if history.current_chapter else ""
            activities.append({'timestamp': history.last_listened_at,'type': 'Listening','details': f'Listened to "{audiobook_title}"{chapter_name}. Progress: {timedelta(seconds=history.progress_seconds)} (Overall: {history.progress_percentage}%).','icon': 'fas fa-headphones-alt text-indigo-500'})
        # 7. Reviews
        for review in Review.objects.filter(user=target_user_instance).select_related('audiobook').order_by('created_at'):
            audiobook_title = review.audiobook.title if review.audiobook else "Audiobook (Deleted or ID missing)"
            activities.append({'timestamp': review.created_at,'type': 'Review','details': f'Reviewed "{audiobook_title}" with {review.rating} stars. Comment: "{review.comment[:100] if review.comment else "" }..."','icon': 'fas fa-star text-yellow-500'})
        # 8. Coin Transactions
        for ct in CoinTransaction.objects.filter(user=target_user_instance).select_related('sender', 'recipient').order_by('transaction_date'):
            details = f'{ct.get_transaction_type_display()}: {ct.amount} coins. Status: {ct.get_status_display()}.'
            if ct.pack_name: details += f' Pack: {ct.pack_name}.'
            if ct.price and ct.transaction_type == 'purchase': details += f' Price: PKR {ct.price:.2f}.'
            if ct.description: details += f' Desc: {ct.description}.'
            if ct.transaction_type == 'gift_sent' and ct.recipient: details += f' Sent to: {ct.recipient.username}.'
            if ct.transaction_type == 'gift_received' and ct.sender: details += f' Received from: {ct.sender.username}.'
            activities.append({'timestamp': ct.transaction_date,'type': 'Wallet','details': details,'icon': 'fas fa-coins text-yellow-600'})
        # 9. Subscriptions
        for sub in Subscription.objects.filter(user=target_user_instance).order_by('start_date'):
            activities.append({'timestamp': sub.start_date,'type': 'Subscription','details': f'Subscription for plan: {sub.get_plan_display()} started. Status: {sub.get_status_display()}. Ends: {sub.end_date.strftime("%Y-%m-%d") if sub.end_date else "N/A"}.','icon': 'fas fa-credit-card text-cyan-500'})
            if sub.status == 'canceled' and sub.end_date: activities.append({'timestamp': sub.end_date, 'type': 'Subscription Update','details': f'Subscription for plan: {sub.get_plan_display()} access ended after cancellation (or expired). Original end date: {sub.end_date.strftime("%Y-%m-%d")}.','icon': 'fas fa-calendar-times text-gray-500'})
        # 10. Withdrawal Accounts Added
        if creator_profile:
            for acc in WithdrawalAccount.objects.filter(creator=creator_profile).order_by('added_at'):
                activities.append({'timestamp': acc.added_at,'type': 'Withdrawal Account','details': f'Withdrawal account added: {acc.get_account_type_display()} - {acc.account_title} ({"Primary" if acc.is_primary else "Secondary"}). Identifier: ...{acc.account_identifier[-4:] if acc.account_identifier else ""}','icon': 'fas fa-university text-teal-500'})
        # 11. Withdrawal Requests
        if creator_profile:
            for req in WithdrawalRequest.objects.filter(creator=creator_profile).select_related('withdrawal_account', 'processed_by').order_by('request_date'):
                account_display = f"to {req.withdrawal_account.get_account_type_display()} ...{req.withdrawal_account.account_identifier[-4:]}" if req.withdrawal_account and req.withdrawal_account.account_identifier else "to [Account Details Missing]"
                activities.append({'timestamp': req.request_date,'type': 'Withdrawal Request','details': f'Withdrawal requested: PKR {req.amount:.2f} {account_display}. Status: {req.get_status_display()}. ID: {req.display_request_id}','icon': 'fas fa-money-check-alt text-teal-600'})
                if req.processed_date and req.status != 'PENDING':
                    processed_by_admin = req.processed_by.username if req.processed_by else "N/A"
                    activities.append({'timestamp': req.processed_date,'type': 'Withdrawal Update','details': f'Withdrawal ID {req.display_request_id} processed by {processed_by_admin}. Status: {req.get_status_display()}. Notes: {req.admin_notes or ""}','icon': 'fas fa-tasks text-teal-700'})
        # 12. Support Tickets & Messages
        for ticket in Ticket.objects.filter(user=target_user_instance).select_related('category').order_by('created_at'):
            activities.append({'timestamp': ticket.created_at,'type': 'Support Ticket','details': f'Ticket "{ticket.subject}" created in category "{ticket.category.name if ticket.category else "N/A"}". Status: {ticket.get_status_display()}. ID: {ticket.ticket_display_id}','icon': 'fas fa-life-ring text-orange-500'})
            if ticket.resolved_at and ticket.status == Ticket.StatusChoices.RESOLVED: activities.append({'timestamp': ticket.resolved_at, 'type': 'Support Update', 'details': f'Ticket ID {ticket.ticket_display_id} marked as Resolved.', 'icon': 'fas fa-check-circle text-green-500'})
            elif ticket.closed_at and ticket.status == Ticket.StatusChoices.CLOSED: activities.append({'timestamp': ticket.closed_at, 'type': 'Support Update', 'details': f'Ticket ID {ticket.ticket_display_id} Closed.', 'icon': 'fas fa-times-circle text-gray-600'})
            for message in TicketMessage.objects.filter(ticket=ticket).select_related('user').order_by('created_at'):
                sender = "Admin" if message.is_admin_reply else (target_user_instance.username)
                activities.append({'timestamp': message.created_at,'type': 'Support Message','details': f'Message on ticket {ticket.ticket_display_id} from {sender}: "{message.message[:150]}..."','icon': 'fas fa-comment-dots text-orange-600'})
        # --- End of Activity Fetching Logic ---

        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        paginator = Paginator(activities, 25)
        page_number = request.GET.get('page')
        paginated_activities = paginator.get_page(page_number)

    context = {
        'active_page': 'manage_users_activity_log',
        'admin_user': admin_user,
        'target_user_info': target_user_instance,
        'activities': paginated_activities,
        'search_query_display': search_query_display,
    }
    return render(request, 'admin/manage_users/admin_user_activity_log.html', context)