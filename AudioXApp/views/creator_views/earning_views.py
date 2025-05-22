# AudioXApp/views/creator_views/earning_views.py

from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
import logging
from collections import defaultdict

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, Http404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.db import transaction, IntegrityError
from django.db.models import Sum, F
from django.utils import timezone
from django.urls import reverse
from django.conf import settings

from ...models import Creator, WithdrawalAccount, WithdrawalRequest, CreatorEarning, Audiobook # Relative imports
from ..utils import _get_full_context # Relative import
from ..decorators import creator_required # Relative import

logger = logging.getLogger(__name__)

# Constants specific to earnings and withdrawals
PLATFORM_COMMISSION_RATE = Decimal(getattr(settings, 'PLATFORM_FEE_PERCENTAGE_AUDIOBOOK', '10.00')) # Example, adjust as needed
EARNING_PER_VIEW = Decimal(getattr(settings, 'CREATOR_EARNING_PER_FREE_VIEW', '1.00'))
MIN_WITHDRAWAL_AMOUNT = Decimal(getattr(settings, 'MIN_CREATOR_WITHDRAWAL_AMOUNT', '50.00'))
CANCELLATION_WINDOW_MINUTES = getattr(settings, 'CREATOR_WITHDRAWAL_CANCELLATION_WINDOW_MINUTES', 30)


@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_manage_withdrawal_accounts_view(request):
    creator = request.creator
    withdrawal_accounts = WithdrawalAccount.objects.filter(creator=creator).order_by('-is_primary', '-added_at')
    can_add_more = withdrawal_accounts.count() < 3 # Max 3 accounts
    errors_from_post = {}

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'delete_account':
            account_id_to_delete = request.POST.get('account_id')
            try:
                account_to_delete = get_object_or_404(WithdrawalAccount, pk=account_id_to_delete, creator=creator)

                linked_pending_withdrawals = WithdrawalRequest.objects.filter(
                    withdrawal_account=account_to_delete,
                    status__in=['pending', 'approved', 'processing']
                ).exists()

                if linked_pending_withdrawals:
                    messages.error(request, "Cannot delete this account as it is linked to pending or processing withdrawal requests.")
                else:
                    account_title = account_to_delete.account_title
                    account_type_display = account_to_delete.get_account_type_display()
                    account_to_delete.delete()
                    messages.success(request, f"{account_type_display} account '{account_title}' deleted successfully.")
            except Http404:
                messages.error(request, "Withdrawal account not found or you do not have permission to delete it.")
            except Exception as e:
                logger.error(f"Error deleting withdrawal account {account_id_to_delete} for creator {creator.user.username}: {e}", exc_info=True)
                messages.error(request, f"An error occurred while trying to delete the account: {e}")
            return redirect('AudioXApp:creator_manage_withdrawal_accounts')

        elif action == 'add_account':
            current_account_count = WithdrawalAccount.objects.filter(creator=creator).count()
            if current_account_count >= 3:
                messages.error(request, "You have reached the maximum limit of 3 withdrawal accounts.")
                return redirect('AudioXApp:creator_manage_withdrawal_accounts')

            account_type = request.POST.get('account_type')
            account_title = request.POST.get('account_title', '').strip()
            account_identifier = request.POST.get('account_identifier', '').strip()
            bank_name = request.POST.get('bank_name', '').strip()
            is_primary = request.POST.get('is_primary') == 'on'

            errors_from_post = {} # Reset for this action
            valid_account_types = [choice[0] for choice in WithdrawalAccount.ACCOUNT_TYPE_CHOICES]
            if not account_type or account_type not in valid_account_types:
                errors_from_post['account_type'] = "Invalid account type selected."
            if not account_title:
                errors_from_post['account_title'] = "Account title is required."
            if not account_identifier:
                errors_from_post['account_identifier'] = "Identifier (IBAN/Mobile Number) is required."

            if account_type == 'bank':
                if not bank_name:
                    errors_from_post['bank_name'] = "Bank name is required for bank accounts."
                if account_identifier:
                    try:
                        WithdrawalAccount.iban_validator(account_identifier)
                    except ValidationError as e:
                        errors_from_post.setdefault('account_identifier', []).extend(e.messages)
            elif account_type in ['jazzcash', 'easypaisa', 'nayapay', 'upaisa']:
                if bank_name: bank_name = '' # Clear bank name if not bank type
                if account_identifier:
                    try:
                        WithdrawalAccount.mobile_account_validator(account_identifier)
                    except ValidationError as e:
                        errors_from_post.setdefault('account_identifier', []).extend(e.messages)

            if errors_from_post:
                for field, error_msg_or_list in errors_from_post.items():
                    error_message = ' '.join(error_msg_or_list) if isinstance(error_msg_or_list, list) else error_msg_or_list
                    messages.error(request, f"{field.replace('_', ' ').title()}: {error_message}")
            else:
                try:
                    with transaction.atomic():
                        new_account = WithdrawalAccount(
                            creator=creator,
                            account_type=account_type,
                            account_title=account_title,
                            account_identifier=account_identifier,
                            bank_name=bank_name if account_type == 'bank' else '',
                            is_primary=is_primary
                        )
                        new_account.full_clean() # Run model's clean method
                        new_account.save() # This will also handle the primary constraint via model's save

                        if current_account_count == 0 and not new_account.is_primary: # If first account, make it primary
                            new_account.is_primary = True
                            new_account.save(update_fields=['is_primary'])
                            messages.success(request, f"{new_account.get_account_type_display()} account added and set as primary.")
                        elif new_account.is_primary: # If explicitly set as primary, other primary accounts are unset by model's save method
                            messages.success(request, f"{new_account.get_account_type_display()} account added and set as primary.")
                        else:
                            messages.success(request, f"{new_account.get_account_type_display()} account added successfully.")
                        
                        next_url = request.GET.get('next')
                        if next_url:
                            return redirect(next_url)
                        return redirect('AudioXApp:creator_manage_withdrawal_accounts')

                except ValidationError as e:
                    logger.warning(f"ValidationError adding withdrawal account for {creator.user.username}: {e.message_dict if hasattr(e, 'message_dict') else e}")
                    if hasattr(e, 'message_dict'):
                        for field, error_list_val_err in e.message_dict.items():
                            messages.error(request, f"{field.replace('_', ' ').title()}: {' '.join(error_list_val_err)}")
                            errors_from_post[field] = ' '.join(error_list_val_err)
                    else:
                        messages.error(request, f"Validation Error: {e}")
                        errors_from_post['__all__'] = str(e)
                except IntegrityError as e:
                    logger.error(f"IntegrityError adding withdrawal account for {creator.user.username}: {e}", exc_info=True)
                    messages.error(request, f"Database Error: Could not save account. It might conflict with existing data.")
                    errors_from_post['__all__'] = "A database error occurred. The account might already exist or conflict with other data."
                except Exception as e:
                    logger.error(f"Unexpected error adding withdrawal account for {creator.user.username}: {e}", exc_info=True)
                    messages.error(request, f"An unexpected error occurred: {e}")
                    errors_from_post['__all__'] = "An unexpected server error occurred."

        elif action == 'set_primary':
            account_id_to_set = request.POST.get('account_id')
            try:
                account_to_set = get_object_or_404(WithdrawalAccount, pk=account_id_to_set, creator=creator)
                if not account_to_set.is_primary:
                    with transaction.atomic(): # Ensure atomicity
                        # WithdrawalAccount.save() method handles unsetting other primaries
                        account_to_set.is_primary = True
                        account_to_set.save(update_fields=['is_primary']) 
                    messages.success(request, f"{account_to_set.get_account_type_display()} account ending in ...{account_to_set.account_identifier[-4:]} set as primary.")
                else:
                    messages.info(request, "This account is already set as primary.")
            except Http404:
                messages.error(request, "Account not found or you do not have permission.")
            except Exception as e:
                logger.error(f"Error setting primary account {account_id_to_set} for creator {creator.user.username}: {e}", exc_info=True)
                messages.error(request, f"An error occurred: {e}")
            return redirect('AudioXApp:creator_manage_withdrawal_accounts')
        else:
            messages.warning(request, "Invalid action submitted.")
            return redirect('AudioXApp:creator_manage_withdrawal_accounts')

    context = _get_full_context(request)
    context.update({
        'creator': creator,
        'withdrawal_accounts': WithdrawalAccount.objects.filter(creator=creator).order_by('-is_primary', '-added_at'), # Re-fetch for fresh data
        'can_add_more': WithdrawalAccount.objects.filter(creator=creator).count() < 3,
        'available_balance': creator.available_balance, # For display
    })
    if request.method == 'POST' and action == 'add_account' and errors_from_post:
       context['submitted_values'] = request.POST # Repopulate form with submitted values on error
       context['form_errors'] = errors_from_post # Pass specific errors to template

    return render(request, 'creator/creator_withdrawal_account.html', context)


@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_request_withdrawal_list_view(request):
    creator_from_decorator = request.creator # Get creator from decorator

    # Fetch fresh data for display
    withdrawal_accounts = WithdrawalAccount.objects.filter(creator=creator_from_decorator).order_by('-is_primary', 'account_title')
    past_requests = WithdrawalRequest.objects.filter(creator=creator_from_decorator).order_by('-request_date')
    
    # Re-evaluate can_request_now with fresh creator data
    fresh_creator_for_check = Creator.objects.get(pk=creator_from_decorator.pk)
    can_request_now, reason_cant_request_now = fresh_creator_for_check.can_request_withdrawal()
    has_active_request_flag = WithdrawalRequest.objects.filter(
        creator=fresh_creator_for_check,
        status__in=['pending', 'approved', 'processing']
    ).exists()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'request_withdrawal':
            try:
                with transaction.atomic():
                    # Lock creator row for this transaction to prevent race conditions on available_balance
                    creator_instance_for_post = Creator.objects.select_for_update().get(pk=creator_from_decorator.pk)
                    
                    # Re-check eligibility within the transaction
                    current_can_request, current_reason_cant = creator_instance_for_post.can_request_withdrawal()
                    if not current_can_request:
                        messages.error(request, current_reason_cant or "You are currently unable to make a withdrawal request.")
                        return redirect('AudioXApp:creator_request_withdrawal_list')

                    if not withdrawal_accounts.exists(): # Check if any accounts exist for this creator
                        messages.warning(request, "You need to add a payout method before requesting a withdrawal.")
                        return redirect(reverse('AudioXApp:creator_manage_withdrawal_accounts') + '?next=' + reverse('AudioXApp:creator_request_withdrawal_list'))

                    amount_str = request.POST.get('amount', '').strip()
                    account_id = request.POST.get('withdrawal_account_id')
                    
                    errors = []
                    amount_decimal = None

                    if not amount_str:
                        errors.append("Withdrawal amount is required.")
                    else:
                        try:
                            amount_decimal = Decimal(amount_str)
                            if amount_decimal <= Decimal('0.00'):
                                errors.append("Withdrawal amount must be positive.")
                            if amount_decimal < MIN_WITHDRAWAL_AMOUNT:
                                errors.append(f"Minimum withdrawal amount is Rs. {MIN_WITHDRAWAL_AMOUNT:,.2f}.")
                            if amount_decimal > creator_instance_for_post.available_balance:
                                errors.append("Requested amount exceeds your available balance.")
                        except InvalidOperation:
                            errors.append("Invalid amount format. Please enter a valid number.")
                    
                    selected_account = None
                    if not account_id:
                        errors.append("Please select a withdrawal account.")
                    else:
                        try:
                            selected_account = WithdrawalAccount.objects.get(account_id=account_id, creator=creator_instance_for_post)
                        except WithdrawalAccount.DoesNotExist:
                            errors.append("Selected withdrawal account is invalid or does not belong to you.")

                    if errors:
                        for error_msg in errors: messages.error(request, error_msg)
                    else:
                        new_request = WithdrawalRequest.objects.create(
                            creator=creator_instance_for_post,
                            amount=amount_decimal,
                            withdrawal_account=selected_account,
                            status='pending' # Initial status
                        )
                        # Deduct from available balance and update last request date
                        creator_instance_for_post.available_balance = F('available_balance') - amount_decimal
                        creator_instance_for_post.last_withdrawal_request_date = new_request.request_date # Use the new request's date
                        creator_instance_for_post.save(update_fields=['available_balance', 'last_withdrawal_request_date'])
                        
                        messages.success(request, f"Withdrawal request for Rs. {amount_decimal:,.2f} submitted successfully. It is now pending review.")
                        return redirect('AudioXApp:creator_request_withdrawal_list') # Redirect to refresh page
            except Creator.DoesNotExist: # Should not happen if decorator works
                messages.error(request, "Creator profile not found during transaction.")
                return redirect('AudioXApp:home')
            except IntegrityError: # General database integrity issue
                messages.error(request, "A database error occurred. Please try again.")
            except Exception as e:
                logger.error(f"Unexpected error requesting withdrawal for {creator_from_decorator.user.username}: {e}", exc_info=True)
                messages.error(request, f"An unexpected error occurred: {e}")
        
        elif action == 'cancel_withdrawal':
            request_id_to_cancel = request.POST.get('request_id')
            try:
                with transaction.atomic():
                    creator_instance_for_post = Creator.objects.select_for_update().get(pk=creator_from_decorator.pk)
                    withdrawal_to_cancel = get_object_or_404(WithdrawalRequest, request_id=request_id_to_cancel, creator=creator_instance_for_post)

                    if withdrawal_to_cancel.status != 'pending':
                        messages.error(request, "This withdrawal request cannot be cancelled as it's no longer pending.")
                        return redirect('AudioXApp:creator_request_withdrawal_list')

                    now = timezone.now()
                    if not withdrawal_to_cancel.request_date: # Should always exist
                        messages.error(request, "Cannot determine request age. Please contact support.")
                        return redirect('AudioXApp:creator_request_withdrawal_list')
                    
                    time_since_request = now - withdrawal_to_cancel.request_date
                    
                    if time_since_request > timedelta(minutes=CANCELLATION_WINDOW_MINUTES):
                        messages.error(request, f"The cancellation window of {CANCELLATION_WINDOW_MINUTES} minutes for this request has expired.")
                        return redirect('AudioXApp:creator_request_withdrawal_list')

                    original_amount = withdrawal_to_cancel.amount
                    
                    withdrawal_to_cancel.status = 'cancelled'
                    withdrawal_to_cancel.admin_notes = (withdrawal_to_cancel.admin_notes or "") + f"\nCancelled by creator on {now.strftime('%Y-%m-%d %H:%M')} within {CANCELLATION_WINDOW_MINUTES} min window."
                    withdrawal_to_cancel.processed_date = now # Mark processed date as now for cancellation
                    withdrawal_to_cancel.save(update_fields=['status', 'admin_notes', 'processed_date'])

                    # Add amount back to creator's balance
                    creator_instance_for_post.available_balance = F('available_balance') + original_amount
                    
                    # If this cancelled request was the one setting last_withdrawal_request_date, reset it
                    # This requires checking if other non-cancelled requests exist to determine the true last request date
                    if creator_instance_for_post.last_withdrawal_request_date == withdrawal_to_cancel.request_date:
                        other_non_cancelled_requests = WithdrawalRequest.objects.filter(
                            creator=creator_instance_for_post,
                            status__in=['pending', 'approved', 'processing', 'completed', 'failed'] # Exclude 'cancelled'
                        ).exclude(pk=withdrawal_to_cancel.pk).order_by('-request_date').first()
                        creator_instance_for_post.last_withdrawal_request_date = other_non_cancelled_requests.request_date if other_non_cancelled_requests else None
                    
                    creator_instance_for_post.save(update_fields=['available_balance', 'last_withdrawal_request_date'])
                    
                    messages.success(request, f"Withdrawal request for Rs. {original_amount:,.2f} has been cancelled.")
            except Creator.DoesNotExist:
                messages.error(request, "Creator profile not found during transaction.")
                return redirect('AudioXApp:home')
            except Http404:
                messages.error(request, "Withdrawal request not found.")
            except Exception as e:
                logger.error(f"Error cancelling withdrawal for {creator_from_decorator.user.username}, request ID {request_id_to_cancel}: {e}", exc_info=True)
                messages.error(request, f"An error occurred while cancelling the request: {e}")
            return redirect('AudioXApp:creator_request_withdrawal_list') # Redirect to refresh list

    # For GET request or after POST action, re-fetch fresh data for context
    fresh_creator = Creator.objects.get(pk=creator_from_decorator.pk) # Get latest creator data
    can_request_now, reason_cant_request_now = fresh_creator.can_request_withdrawal()
    has_active_request_flag = WithdrawalRequest.objects.filter(
        creator=fresh_creator,
        status__in=['pending', 'approved', 'processing']
    ).exists()
    
    context = _get_full_context(request)
    context.update({
        'creator': fresh_creator, # Use the fresh creator data
        'withdrawal_accounts': withdrawal_accounts, # Already fetched
        'past_requests': WithdrawalRequest.objects.filter(creator=fresh_creator).order_by('-request_date'), # Re-fetch past requests
        'can_request_withdrawal': can_request_now,
        'reason_cant_request': reason_cant_request_now,
        'has_active_request': has_active_request_flag,
        'available_balance': fresh_creator.available_balance,
        'min_withdrawal_amount': MIN_WITHDRAWAL_AMOUNT,
        'next_withdrawal_date': None, # Initialize
        'cancellation_window_minutes': CANCELLATION_WINDOW_MINUTES,
    })

    if not can_request_now and fresh_creator.last_withdrawal_request_date and "after" in (reason_cant_request_now or "").lower():
        cooldown_days = getattr(settings, 'WITHDRAWAL_REQUEST_COOLDOWN_DAYS', 15) # Ensure this matches model logic
        context['next_withdrawal_date'] = fresh_creator.last_withdrawal_request_date + timedelta(days=cooldown_days)
        
    return render(request, 'creator/creator_withdrawal_request.html', context)


@creator_required
def creator_my_earnings_view(request):
    creator = request.creator
    context = _get_full_context(request)

    try:
        # Re-fetch creator to ensure latest balance is used, though decorator provides one
        creator = Creator.objects.get(pk=creator.pk) 
    except Creator.DoesNotExist:
        messages.error(request, "Creator profile not found.")
        return redirect('AudioXApp:home')

    context['creator'] = creator
    context['available_balance'] = creator.available_balance
    now = timezone.now()

    # --- Global Filters for Summary Cards ---
    global_selected_period = request.GET.get('period', 'all_time')
    global_start_date_str = request.GET.get('start_date')
    global_end_date_str = request.GET.get('end_date')

    global_filter_start_date = None
    global_filter_end_date = None

    if global_selected_period == 'today':
        global_filter_start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        global_filter_end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif global_selected_period == 'last_7_days':
        global_filter_start_date = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        global_filter_end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif global_selected_period == 'this_month':
        global_filter_start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if global_filter_start_date.month == 12:
            global_filter_end_date = global_filter_start_date.replace(year=global_filter_start_date.year + 1, month=1, day=1) - timedelta(microseconds=1)
        else:
            global_filter_end_date = global_filter_start_date.replace(month=global_filter_start_date.month + 1, day=1) - timedelta(microseconds=1)
    elif global_selected_period == 'custom_range':
        if global_start_date_str:
            try:
                dt = datetime.strptime(global_start_date_str, '%Y-%m-%d')
                global_filter_start_date = timezone.make_aware(dt.replace(hour=0, minute=0, second=0, microsecond=0), timezone.get_default_timezone()) if timezone.is_naive(dt) else dt.replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError: messages.error(request, "Invalid global start date format. Please use YYYY-MM-DD.")
        if global_end_date_str:
            try:
                dt = datetime.strptime(global_end_date_str, '%Y-%m-%d')
                global_filter_end_date = timezone.make_aware(dt.replace(hour=23, minute=59, second=59, microsecond=999999), timezone.get_default_timezone()) if timezone.is_naive(dt) else dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            except ValueError: messages.error(request, "Invalid global end date format. Please use YYYY-MM-DD.")

    context['start_date_str'] = global_filter_start_date.strftime('%Y-%m-%d') if global_filter_start_date else global_start_date_str
    context['end_date_str'] = global_filter_end_date.strftime('%Y-%m-%d') if global_filter_end_date else global_end_date_str
    context['selected_period'] = global_selected_period

    # Calculate overall earnings based on global filters
    overall_sales_earnings_query = CreatorEarning.objects.filter(
        creator=creator, earning_type='sale'
    ).select_related('purchase') # For accessing purchase.amount_paid and purchase.platform_fee_amount

    if global_filter_start_date:
        overall_sales_earnings_query = overall_sales_earnings_query.filter(transaction_date__gte=global_filter_start_date)
    if global_filter_end_date:
        overall_sales_earnings_query = overall_sales_earnings_query.filter(transaction_date__lte=global_filter_end_date)
    
    overall_total_gross_earnings_from_sales_GLOBAL = Decimal('0.00')
    overall_total_net_earnings_from_sales_GLOBAL = Decimal('0.00')
    overall_platform_commission_from_sales_GLOBAL = Decimal('0.00')

    for earning in overall_sales_earnings_query:
        if earning.purchase: # Ensure there's a related purchase
            overall_total_gross_earnings_from_sales_GLOBAL += earning.purchase.amount_paid
            overall_total_net_earnings_from_sales_GLOBAL += earning.amount_earned # This is the net amount for creator
            overall_platform_commission_from_sales_GLOBAL += earning.purchase.platform_fee_amount

    view_earnings_query_global = CreatorEarning.objects.filter(
        creator=creator, earning_type='view'
    )
    if global_filter_start_date:
        view_earnings_query_global = view_earnings_query_global.filter(transaction_date__gte=global_filter_start_date)
    if global_filter_end_date:
        view_earnings_query_global = view_earnings_query_global.filter(transaction_date__lte=global_filter_end_date)
    
    aggregated_view_earnings_for_period = view_earnings_query_global.aggregate(total_view_earn=Sum('amount_earned'))
    earnings_from_views_for_selected_period = aggregated_view_earnings_for_period['total_view_earn'] or Decimal('0.00')

    context['overall_total_gross_earnings'] = overall_total_gross_earnings_from_sales_GLOBAL + earnings_from_views_for_selected_period
    context['overall_total_net_earnings'] = overall_total_net_earnings_from_sales_GLOBAL + earnings_from_views_for_selected_period
    context['overall_platform_commission'] = overall_platform_commission_from_sales_GLOBAL
    context['earnings_from_views_for_selected_period'] = earnings_from_views_for_selected_period
    context['net_earnings_from_paid_sales'] = overall_total_net_earnings_from_sales_GLOBAL


    # --- Audiobook Specific Filters & Data ---
    ab_selected_period = request.GET.get('ab_period', 'all_time') # Audiobook specific period
    ab_start_date_str = request.GET.get('ab_start_date')
    ab_end_date_str = request.GET.get('ab_end_date')
    filtered_book_slug_from_url = request.GET.get('filtered_book_slug') # For filtering by a single book

    ab_filter_start_date = None
    ab_filter_end_date = None

    # Logic to parse ab_filter_start_date and ab_filter_end_date similar to global filters
    if ab_selected_period == 'today':
        ab_filter_start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        ab_filter_end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif ab_selected_period == 'last_7_days':
        ab_filter_start_date = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        ab_filter_end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif ab_selected_period == 'this_month':
        ab_filter_start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if ab_filter_start_date.month == 12:
            ab_filter_end_date = ab_filter_start_date.replace(year=ab_filter_start_date.year + 1, month=1, day=1) - timedelta(microseconds=1)
        else:
            ab_filter_end_date = ab_filter_start_date.replace(month=ab_filter_start_date.month + 1, day=1) - timedelta(microseconds=1)
    elif ab_selected_period == 'custom_range':
        if ab_start_date_str:
            try:
                dt = datetime.strptime(ab_start_date_str, '%Y-%m-%d')
                ab_filter_start_date = timezone.make_aware(dt.replace(hour=0, minute=0, second=0, microsecond=0), timezone.get_default_timezone()) if timezone.is_naive(dt) else dt.replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError: messages.error(request, "Invalid audiobook start date format. Please use YYYY-MM-DD.")
        if ab_end_date_str:
            try:
                dt = datetime.strptime(ab_end_date_str, '%Y-%m-%d')
                ab_filter_end_date = timezone.make_aware(dt.replace(hour=23, minute=59, second=59, microsecond=999999), timezone.get_default_timezone()) if timezone.is_naive(dt) else dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            except ValueError: messages.error(request, "Invalid audiobook end date format. Please use YYYY-MM-DD.")

    context['ab_start_date_str_audiobook_filter'] = ab_filter_start_date.strftime('%Y-%m-%d') if ab_filter_start_date else ab_start_date_str
    context['ab_end_date_str_audiobook_filter'] = ab_filter_end_date.strftime('%Y-%m-%d') if ab_filter_end_date else ab_end_date_str
    context['ab_selected_period'] = ab_selected_period
    context['filtered_book_slug'] = filtered_book_slug_from_url


    # Prepare data for the list of audiobooks and their earnings
    aggregated_earnings_for_list = defaultdict(lambda: {
        'title': 'Unknown (Possibly Deleted Audiobook)', 'slug': None, 'cover_image_url': None,
        'is_active': False, 'is_paid': True, 'publish_date': None, 'audiobook_object': None, 'status_display': 'N/A',
        'paid_details': {'sales': 0, 'gross': Decimal('0.00'), 'commission': Decimal('0.00'), 'net': Decimal('0.00')},
        'free_details': {'views': 0, 'earnings': Decimal('0.00')}
    })

    # Get all audiobooks for this creator
    all_creator_audiobooks_qs = Audiobook.objects.filter(creator=creator)
    if filtered_book_slug_from_url: # If filtering by a specific book
        all_creator_audiobooks_qs = all_creator_audiobooks_qs.filter(slug=filtered_book_slug_from_url)
    
    audiobook_id_to_object_map = {book.audiobook_id: book for book in all_creator_audiobooks_qs}

    for book_id, book_obj in audiobook_id_to_object_map.items():
        agg_data = aggregated_earnings_for_list[book_id] # Use book_id as key
        is_book_active = book_obj.status == 'PUBLISHED'

        agg_data.update({
            'title': book_obj.title, 'slug': book_obj.slug,
            'cover_image_url': book_obj.cover_image.url if book_obj.cover_image else None,
            'is_active': is_book_active, 'is_paid': book_obj.is_paid,
            'publish_date': book_obj.publish_date, 'audiobook_object': book_obj,
            'status_display': book_obj.get_status_display()
        })

        # Apply audiobook-specific date filters for earnings calculations
        current_item_filter_start_date = ab_filter_start_date
        current_item_filter_end_date = ab_filter_end_date

        if book_obj.is_paid:
            sales_for_book_query = CreatorEarning.objects.filter(
                creator=creator, audiobook_id=book_id, earning_type='sale'
            ).select_related('purchase')
            if current_item_filter_start_date:
                sales_for_book_query = sales_for_book_query.filter(transaction_date__gte=current_item_filter_start_date)
            if current_item_filter_end_date:
                sales_for_book_query = sales_for_book_query.filter(transaction_date__lte=current_item_filter_end_date)
            
            for sale_earning in sales_for_book_query:
                if sale_earning.purchase:
                    agg_data['paid_details']['sales'] += 1
                    agg_data['paid_details']['gross'] += sale_earning.purchase.amount_paid
                    agg_data['paid_details']['commission'] += sale_earning.purchase.platform_fee_amount
                    agg_data['paid_details']['net'] += sale_earning.amount_earned
        
        if not book_obj.is_paid: # Free book, calculate view earnings
            views_for_book_query = AudiobookViewLog.objects.filter(audiobook_id=book_id) # Get all views for this book
            # Note: The earning is logged at the time of view. Here we are just counting views for display.
            # The actual earning for these views is already in CreatorEarning table.
            
            view_earnings_for_this_book_query = CreatorEarning.objects.filter(
                creator=creator, audiobook_id=book_id, earning_type='view'
            )

            if current_item_filter_start_date:
                views_for_book_query = views_for_book_query.filter(viewed_at__gte=current_item_filter_start_date)
                view_earnings_for_this_book_query = view_earnings_for_this_book_query.filter(transaction_date__gte=current_item_filter_start_date)
            if current_item_filter_end_date:
                views_for_book_query = views_for_book_query.filter(viewed_at__lte=current_item_filter_end_date)
                view_earnings_for_this_book_query = view_earnings_for_this_book_query.filter(transaction_date__lte=current_item_filter_end_date)

            period_views = views_for_book_query.count()
            agg_data['free_details']['views'] = period_views
            
            # Sum up the actual logged earnings for views for this book in the period
            period_view_earnings_sum = view_earnings_for_this_book_query.aggregate(total=Sum('amount_earned'))['total'] or Decimal('0.00')
            agg_data['free_details']['earnings'] = period_view_earnings_sum


    # Handle earnings from deleted audiobooks (where audiobook is None but title_at_transaction exists)
    deleted_audiobook_earnings_query = CreatorEarning.objects.filter(
        creator=creator, audiobook__isnull=True, earning_type='sale' # Assuming only sales for now
    ).select_related('purchase')

    if ab_filter_start_date:
        deleted_audiobook_earnings_query = deleted_audiobook_earnings_query.filter(transaction_date__gte=ab_filter_start_date)
    if ab_filter_end_date:
        deleted_audiobook_earnings_query = deleted_audiobook_earnings_query.filter(transaction_date__lte=ab_filter_end_date)

    for earning in deleted_audiobook_earnings_query:
        # Create a unique key for each deleted audiobook earning record based on its original title and earning ID
        unique_deleted_key = f"deleted_{slugify(earning.audiobook_title_at_transaction or 'unknown-title')}_{earning.earning_id}"
        agg_data = aggregated_earnings_for_list[unique_deleted_key] # This creates a new entry if key doesn't exist
        agg_data.update({
            'title': earning.audiobook_title_at_transaction or 'Unknown (Deleted Audiobook)',
            'slug': slugify(agg_data['title'] + str(earning.earning_id)), # Make a somewhat unique slug
            'is_active': False, 'is_paid': True, # Assume paid if it was a sale
            'status_display': 'Deleted'
        })
        if earning.purchase: # Should always be true for 'sale' type
            agg_data['paid_details']['sales'] += 1
            agg_data['paid_details']['gross'] += earning.purchase.amount_paid
            agg_data['paid_details']['commission'] += earning.purchase.platform_fee_amount
            agg_data['paid_details']['net'] += earning.amount_earned
            
    # Convert defaultdict to list and sort
    temp_list = list(aggregated_earnings_for_list.values())
    # Sort by title first, then by active status, then by publish date (most recent first)
    temp_list.sort(key=lambda x: x['title'].lower() if x['title'] else '')
    min_date_for_sorting = timezone.datetime.min.replace(tzinfo=timezone.get_default_timezone()) if timezone.is_aware(now) else timezone.datetime.min
    temp_list.sort(key=lambda x: x['publish_date'] if x['publish_date'] else min_date_for_sorting, reverse=True)
    temp_list.sort(key=lambda x: x['is_active'], reverse=True) # Active books first
    earnings_list_final = temp_list


    context.update({
        'earnings_list': earnings_list_final,
        'PLATFORM_COMMISSION_RATE_DISPLAY': PLATFORM_COMMISSION_RATE, # For display in template
        'EARNING_PER_VIEW': EARNING_PER_VIEW, # For display
        'all_creator_audiobooks_for_filter': all_creator_audiobooks_qs.order_by('title') # For dropdown
    })
    return render(request, 'creator/creator_myearnings.html', context)