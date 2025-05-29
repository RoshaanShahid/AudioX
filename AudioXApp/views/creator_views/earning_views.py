# AudioXApp/views/creator_views/earning_views.py

from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta # Keep timedelta for potential future use or other logic
import logging
from collections import defaultdict

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, Http404 # Keep JsonResponse for potential future AJAX
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.db import transaction, IntegrityError
from django.db.models import Sum, F # Sum and F are correctly from django.db.models
from django.core.exceptions import ValidationError as DjangoValidationError # Corrected import
from django.utils import timezone
from django.urls import reverse
from django.conf import settings
from django.utils.text import slugify # Added for my_earnings_view

from ...models import Creator, WithdrawalAccount, WithdrawalRequest, CreatorEarning, Audiobook, AudiobookViewLog # Relative imports, added AudiobookViewLog
from ..utils import _get_full_context # Relative import
from ..decorators import creator_required # Relative import

logger = logging.getLogger(__name__)

# Constants specific to earnings and withdrawals
PLATFORM_COMMISSION_RATE = Decimal(getattr(settings, 'PLATFORM_FEE_PERCENTAGE_AUDIOBOOK', '10.00'))
EARNING_PER_VIEW = Decimal(getattr(settings, 'CREATOR_EARNING_PER_FREE_VIEW', '1.00'))

# MIN_WITHDRAWAL_AMOUNT is fetched from settings directly in the methods where needed,
# or from the Creator model which also fetches from settings.
# This avoids potential stale values if settings are changed without restarting server,
# though for most Django settings that's not an issue.


@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_manage_withdrawal_accounts_view(request):
    creator = request.creator
    # Fetch fresh accounts list each time
    withdrawal_accounts = WithdrawalAccount.objects.filter(creator=creator).order_by('-is_primary', '-added_at')
    can_add_more = withdrawal_accounts.count() < 3 # Max 3 accounts
    errors_from_post = {} # To store form errors for re-rendering

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'delete_account':
            account_id_to_delete = request.POST.get('account_id')
            try:
                account_to_delete = get_object_or_404(WithdrawalAccount, pk=account_id_to_delete, creator=creator)

                # Check if account is linked to PENDING or PROCESSING requests
                linked_active_withdrawals = WithdrawalRequest.objects.filter(
                    withdrawal_account=account_to_delete,
                    status__in=['PENDING', 'PROCESSING'] # Cannot delete if pending or processing
                ).exists()

                if linked_active_withdrawals:
                    messages.error(request, "Cannot delete this account as it is linked to withdrawal requests that are currently pending or being processed.")
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
            current_account_count = WithdrawalAccount.objects.filter(creator=creator).count() # Re-check count before adding
            if current_account_count >= 3:
                messages.error(request, "You have reached the maximum limit of 3 withdrawal accounts.")
                return redirect('AudioXApp:creator_manage_withdrawal_accounts')

            account_type = request.POST.get('account_type')
            account_title = request.POST.get('account_title', '').strip()
            account_identifier = request.POST.get('account_identifier', '').strip()
            bank_name = request.POST.get('bank_name', '').strip()
            is_primary = request.POST.get('is_primary') == 'on'

            # Server-side validation (though model's clean will also run)
            errors_from_post = {}
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
                if account_identifier: # Validate only if provided, model clean will catch empty
                    try: WithdrawalAccount.iban_validator(account_identifier)
                    except DjangoValidationError as e: errors_from_post.setdefault('account_identifier', []).extend(e.messages)
            elif account_type in ['jazzcash', 'easypaisa', 'nayapay', 'upaisa']:
                if bank_name: bank_name = '' # Ensure bank name is cleared
                if account_identifier:
                    try: WithdrawalAccount.mobile_account_validator(account_identifier)
                    except DjangoValidationError as e: errors_from_post.setdefault('account_identifier', []).extend(e.messages)
            
            if errors_from_post:
                for field, error_msg_or_list in errors_from_post.items():
                    error_message = ' '.join(error_msg_or_list) if isinstance(error_msg_or_list, list) else error_msg_or_list
                    messages.error(request, f"{field.replace('_', ' ').title()}: {error_message}")
                # Fall through to render the form again with errors and submitted values
            else:
                try:
                    with transaction.atomic():
                        new_account = WithdrawalAccount(
                            creator=creator,
                            account_type=account_type,
                            account_title=account_title,
                            account_identifier=account_identifier,
                            bank_name=bank_name if account_type == 'bank' else None, # Ensure bank_name is None if not bank
                            is_primary=is_primary
                        )
                        new_account.full_clean() # Run model's clean method
                        new_account.save() # Model's save handles primary constraint

                        # If it's the first account and not explicitly set as primary, make it primary.
                        if WithdrawalAccount.objects.filter(creator=creator).count() == 1 and not new_account.is_primary:
                            new_account.is_primary = True
                            new_account.save(update_fields=['is_primary'])
                            messages.success(request, f"{new_account.get_account_type_display()} account added and set as primary.")
                        elif new_account.is_primary:
                            messages.success(request, f"{new_account.get_account_type_display()} account added and set as primary.")
                        else:
                            messages.success(request, f"{new_account.get_account_type_display()} account added successfully.")
                        
                        next_url = request.GET.get('next')
                        if next_url:
                            return redirect(next_url)
                        return redirect('AudioXApp:creator_manage_withdrawal_accounts')

                except DjangoValidationError as e: # Catch model validation errors
                    logger.warning(f"DjangoValidationError adding withdrawal account for {creator.user.username}: {e.message_dict if hasattr(e, 'message_dict') else e}")
                    if hasattr(e, 'message_dict'):
                        for field, error_list_val_err in e.message_dict.items():
                            messages.error(request, f"{field.replace('_', ' ').title()}: {' '.join(error_list_val_err)}")
                            errors_from_post[field] = ' '.join(error_list_val_err) # Store for re-rendering
                    else:
                        messages.error(request, f"Validation Error: {e}")
                        errors_from_post['__all__'] = str(e)
                except IntegrityError as e: # e.g., unique_primary constraint if not handled by model save (should be)
                    logger.error(f"IntegrityError adding withdrawal account for {creator.user.username}: {e}", exc_info=True)
                    messages.error(request, "Database Error: Could not save account. It might conflict with existing data or primary account settings.")
                    errors_from_post['__all__'] = "A database error occurred. Please check your input."
                except Exception as e:
                    logger.error(f"Unexpected error adding withdrawal account for {creator.user.username}: {e}", exc_info=True)
                    messages.error(request, f"An unexpected error occurred: {e}")
                    errors_from_post['__all__'] = "An unexpected server error occurred."
                # If errors occurred, fall through to render the form again.

        elif action == 'set_primary':
            account_id_to_set = request.POST.get('account_id')
            try:
                account_to_set = get_object_or_404(WithdrawalAccount, pk=account_id_to_set, creator=creator)
                if not account_to_set.is_primary:
                    # Model's save method handles unsetting other primaries
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

    # For GET request or if POST had errors for 'add_account'
    context = _get_full_context(request)
    context.update({
        'creator': creator,
        'withdrawal_accounts': WithdrawalAccount.objects.filter(creator=creator).order_by('-is_primary', '-added_at'), # Re-fetch for fresh data
        'can_add_more': WithdrawalAccount.objects.filter(creator=creator).count() < 3,
        'available_balance': creator.available_balance, # Though this page is more about managing accounts
    })
    if request.method == 'POST' and action == 'add_account' and errors_from_post:
        context['submitted_values'] = request.POST # Repopulate form with submitted values on error
        context['form_errors'] = errors_from_post # Pass specific errors to template

    return render(request, 'creator/creator_withdrawal_account.html', context)


@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_request_withdrawal_list_view(request):
    creator_from_decorator = request.creator
    form_data_on_error = {} 

    # Fetch a fresh instance of the creator for checks, as request.creator might be stale
    # if other operations have modified it during the request lifecycle.
    # This also ensures we get the latest available_balance.
    try:
        fresh_creator_for_check = Creator.objects.get(pk=creator_from_decorator.pk)
    except Creator.DoesNotExist:
        messages.error(request, "Creator profile not found.")
        # Redirect to a safe page, e.g., creator dashboard or home
        return redirect(reverse('AudioXApp:creator_dashboard')) # Ensure you have a 'creator_dashboard' URL

    withdrawal_accounts_qs = WithdrawalAccount.objects.filter(creator=fresh_creator_for_check).order_by('-is_primary', 'account_title')
    past_requests_for_context = WithdrawalRequest.objects.filter(creator=fresh_creator_for_check).order_by('-request_date')
    
    # Use the can_request_withdrawal method from the fresh creator instance
    can_request_now, reason_cant_request_now = fresh_creator_for_check.can_request_withdrawal()
    
    # This flag indicates if there's any request being actively worked on by admin or pending.
    # It's for informational purposes on the frontend now, not a blocker.
    has_ongoing_request_flag = WithdrawalRequest.objects.filter(
        creator=fresh_creator_for_check,
        status__in=['PENDING', 'PROCESSING']
    ).exists()
    
    # Get MIN_WITHDRAWAL_AMOUNT from settings, ensuring it's a Decimal
    min_withdrawal_amount_setting = getattr(settings, 'MIN_CREATOR_WITHDRAWAL_AMOUNT', '50.00')
    try:
        MIN_WITHDRAWAL_AMOUNT_DECIMAL = Decimal(min_withdrawal_amount_setting)
    except InvalidOperation:
        logger.error(f"Invalid MIN_CREATOR_WITHDRAWAL_AMOUNT setting: '{min_withdrawal_amount_setting}'. Defaulting to Decimal('50.00').")
        MIN_WITHDRAWAL_AMOUNT_DECIMAL = Decimal('50.00')


    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'request_withdrawal':
            form_data_on_error['amount'] = request.POST.get('amount', '')
            form_data_on_error['withdrawal_account_id'] = request.POST.get('withdrawal_account_id', '')
            
            creator_instance_for_post = None 
            selected_account_obj = None 
            amount_decimal = None 

            try:
                with transaction.atomic():
                    # Lock the creator row for update to prevent race conditions on available_balance
                    creator_instance_for_post = Creator.objects.select_for_update().get(pk=fresh_creator_for_check.pk)
                    
                    # Re-check eligibility with the locked instance
                    current_can_request, current_reason_cant = creator_instance_for_post.can_request_withdrawal()
                    
                    if not current_can_request:
                        messages.error(request, current_reason_cant or "You are currently unable to make a withdrawal request.")
                    elif not withdrawal_accounts_qs.exists(): # Check if creator has any withdrawal accounts
                        messages.warning(request, "You need to add a payout method before requesting a withdrawal.")
                        # Optionally redirect to add account page
                        return redirect(reverse('AudioXApp:creator_manage_withdrawal_accounts') + '?next=' + reverse('AudioXApp:creator_request_withdrawal_list'))
                    else:
                        amount_str = form_data_on_error['amount']
                        account_id_from_form = form_data_on_error['withdrawal_account_id']
                        
                        errors = []
                        
                        if not amount_str:
                            errors.append("Withdrawal amount is required.")
                        else:
                            try:
                                amount_decimal = Decimal(amount_str)
                                if amount_decimal <= Decimal('0.00'):
                                    errors.append("Withdrawal amount must be positive.")
                                if amount_decimal < MIN_WITHDRAWAL_AMOUNT_DECIMAL:
                                    errors.append(f"Minimum withdrawal amount is Rs. {MIN_WITHDRAWAL_AMOUNT_DECIMAL:,.2f}.")
                                # Use the available_balance from the locked creator_instance_for_post
                                if amount_decimal > creator_instance_for_post.available_balance:
                                    errors.append(f"Requested amount (Rs. {amount_decimal:,.2f}) exceeds your available balance (Rs. {creator_instance_for_post.available_balance:,.2f}).")
                            except InvalidOperation:
                                errors.append("Invalid amount format. Please enter a valid number.")
                        
                        if not account_id_from_form:
                            errors.append("Please select a withdrawal account.")
                        else:
                            try:
                                selected_account_obj = WithdrawalAccount.objects.get(account_id=account_id_from_form, creator=creator_instance_for_post)
                            except WithdrawalAccount.DoesNotExist:
                                errors.append("Selected withdrawal account is invalid or does not belong to you.")

                        if errors:
                            for error_msg in errors: messages.error(request, error_msg)
                        else:
                            # All Python-level validations passed, attempt to create the request
                            new_request = WithdrawalRequest.objects.create(
                                creator=creator_instance_for_post,
                                amount=amount_decimal,
                                withdrawal_account=selected_account_obj,
                                status='PENDING' # Initial status
                            )
                            # Deduct balance and update last request date
                            creator_instance_for_post.available_balance = F('available_balance') - amount_decimal
                            creator_instance_for_post.last_withdrawal_request_date = new_request.request_date 
                            creator_instance_for_post.save(update_fields=['available_balance', 'last_withdrawal_request_date'])
                            
                            messages.success(request, f"Withdrawal request for Rs. {amount_decimal:,.2f} (ID: {new_request.display_request_id}) submitted successfully. It is now pending review.")
                            return redirect('AudioXApp:creator_request_withdrawal_list')
            
            except IntegrityError as e:
                logger.error(
                    f"IntegrityError during withdrawal for {creator_instance_for_post.user.username if creator_instance_for_post else 'UnknownCreator'} "
                    f"with account PK {selected_account_obj.pk if selected_account_obj else 'NoneSelected/Invalid'}. "
                    f"Amount: {amount_decimal if amount_decimal else 'Invalid'}. Exception: {e}", exc_info=True
                )
                account_still_exists = False
                if selected_account_obj:
                    try:
                        WithdrawalAccount.objects.get(pk=selected_account_obj.pk, creator=creator_instance_for_post if creator_instance_for_post else fresh_creator_for_check)
                        account_still_exists = True
                    except WithdrawalAccount.DoesNotExist:
                        account_still_exists = False
                    except Exception: 
                        pass 
                
                if selected_account_obj and not account_still_exists:
                    messages.error(request, "The selected payout account may have been deleted or modified during processing. Please refresh, select a valid account, and try again.")
                else:
                    messages.error(request, "A database error occurred while submitting your request. This could be due to a temporary issue or invalid data. Please check your input and try again. If the problem persists, contact support.")
            
            except Creator.DoesNotExist: 
                messages.error(request, "Creator profile not found during transaction. Please try again.")
                # No redirect here, will fall through to render the page with error message
            except Exception as e: 
                logger.error(f"Unexpected error requesting withdrawal for {fresh_creator_for_check.user.username}: {e}", exc_info=True)
                messages.error(request, f"An unexpected error occurred: {e}. Please try again or contact support if the issue continues.")
            
            # After POST, re-fetch creator and their ability to request for accurate context rendering
            try:
                fresh_creator_for_context_after_post = Creator.objects.get(pk=fresh_creator_for_check.pk)
            except Creator.DoesNotExist: # Should ideally not happen if initial check passed
                messages.error(request, "Error refreshing creator data. Please reload the page.")
                # Redirect to a safe page as context might be inconsistent
                return redirect(reverse('AudioXApp:creator_dashboard'))

            can_request_now_final = fresh_creator_for_context_after_post.can_request_withdrawal()[0]
            reason_cant_request_now_final = fresh_creator_for_context_after_post.can_request_withdrawal()[1]
            current_available_balance_final = fresh_creator_for_context_after_post.available_balance
            has_ongoing_request_flag_final = WithdrawalRequest.objects.filter(
                creator=fresh_creator_for_context_after_post,
                status__in=['PENDING', 'PROCESSING']
            ).exists()
        
        # This 'else' corresponds to `if action == 'request_withdrawal':`
        # If action was not 'request_withdrawal' but was a POST, handle appropriately or redirect.
        # For now, assuming only 'request_withdrawal' or 'cancel_withdrawal' (if re-added) are main POST actions.
        # If it's another action or no action, simply fall through to render the page.
        # If you add other POST actions (like cancel), you'll need specific logic here or ensure they redirect.
        
        # Fall through to render page for POST if errors occurred or if it's another action not redirecting

    # For GET requests or if POST had errors and needs to re-render the page
    # Re-fetch necessary data for context if not already updated after a POST error
    # This logic block is for GET or when POST doesn't redirect.
    
    # Use the latest fetched data if available from a POST that didn't redirect
    creator_for_context = fresh_creator_for_context_after_post if 'fresh_creator_for_context_after_post' in locals() else fresh_creator_for_check
    
    # If not already set by a POST error block, set them for GET request
    if 'can_request_now_final' not in locals():
        can_request_now_final, reason_cant_request_now_final = creator_for_context.can_request_withdrawal()
        current_available_balance_final = creator_for_context.available_balance
        has_ongoing_request_flag_final = has_ongoing_request_flag # Use the one calculated earlier for GET

    context = _get_full_context(request)
    context.update({
        'creator': creator_for_context, 
        'withdrawal_accounts': withdrawal_accounts_qs, # Use originally fetched QS, assume no new accounts added in same request
        'past_requests': past_requests_for_context.select_related('withdrawal_account'), # Add select_related
        'can_request_withdrawal': can_request_now_final,
        'reason_cant_request': reason_cant_request_now_final,
        'has_ongoing_request': has_ongoing_request_flag_final, # This is now informational
        'available_balance': current_available_balance_final,
        'min_withdrawal_amount': MIN_WITHDRAWAL_AMOUNT_DECIMAL, # Use the decimal constant
        'form_data': form_data_on_error # Contains submitted values if POST had errors
    })
    
    return render(request, 'creator/creator_withdrawal_request.html', context)


@creator_required
def creator_my_earnings_view(request):
    creator = request.creator # This is from @creator_required decorator
    context = _get_full_context(request)

    try:
        # It's good practice to re-fetch the creator object if you need the absolute latest data
        # especially if other operations might modify it.
        creator_instance = Creator.objects.get(pk=creator.pk) 
    except Creator.DoesNotExist:
        messages.error(request, "Creator profile not found.")
        return redirect(reverse('AudioXApp:home')) # Or a more appropriate redirect

    context['creator'] = creator_instance # Use the fresh instance
    context['available_balance'] = creator_instance.available_balance
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
        # Correctly calculate end of month
        if global_filter_start_date.month == 12:
            global_filter_end_date = global_filter_start_date.replace(year=global_filter_start_date.year + 1, month=1, day=1) - timedelta(microseconds=1)
        else:
            global_filter_end_date = global_filter_start_date.replace(month=global_filter_start_date.month + 1, day=1) - timedelta(microseconds=1)
    elif global_selected_period == 'custom_range':
        if global_start_date_str:
            try:
                dt_start = datetime.strptime(global_start_date_str, '%Y-%m-%d')
                global_filter_start_date = timezone.make_aware(dt_start.replace(hour=0, minute=0, second=0, microsecond=0), timezone.get_default_timezone()) if timezone.is_naive(dt_start) else dt_start.replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError: messages.error(request, "Invalid global start date format. Please use YYYY-MM-DD.")
        if global_end_date_str:
            try:
                dt_end = datetime.strptime(global_end_date_str, '%Y-%m-%d')
                global_filter_end_date = timezone.make_aware(dt_end.replace(hour=23, minute=59, second=59, microsecond=999999), timezone.get_default_timezone()) if timezone.is_naive(dt_end) else dt_end.replace(hour=23, minute=59, second=59, microsecond=999999)
            except ValueError: messages.error(request, "Invalid global end date format. Please use YYYY-MM-DD.")

    context['start_date_str'] = global_filter_start_date.strftime('%Y-%m-%d') if global_filter_start_date else global_start_date_str
    context['end_date_str'] = global_filter_end_date.strftime('%Y-%m-%d') if global_filter_end_date else global_end_date_str
    context['selected_period'] = global_selected_period

    overall_sales_earnings_query = CreatorEarning.objects.filter(
        creator=creator_instance, earning_type='sale'
    ).select_related('purchase') # Use creator_instance

    if global_filter_start_date:
        overall_sales_earnings_query = overall_sales_earnings_query.filter(transaction_date__gte=global_filter_start_date)
    if global_filter_end_date:
        overall_sales_earnings_query = overall_sales_earnings_query.filter(transaction_date__lte=global_filter_end_date)
    
    overall_total_gross_earnings_from_sales_GLOBAL = Decimal('0.00')
    overall_total_net_earnings_from_sales_GLOBAL = Decimal('0.00')
    overall_platform_commission_from_sales_GLOBAL = Decimal('0.00')

    for earning in overall_sales_earnings_query:
        if earning.purchase: # Ensure purchase exists
            overall_total_gross_earnings_from_sales_GLOBAL += earning.purchase.amount_paid
            overall_total_net_earnings_from_sales_GLOBAL += earning.amount_earned
            overall_platform_commission_from_sales_GLOBAL += earning.purchase.platform_fee_amount

    view_earnings_query_global = CreatorEarning.objects.filter(
        creator=creator_instance, earning_type='view' # Use creator_instance
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
    ab_selected_period = request.GET.get('ab_period', 'all_time')
    ab_start_date_str = request.GET.get('ab_start_date')
    ab_end_date_str = request.GET.get('ab_end_date')
    filtered_book_slug_from_url = request.GET.get('filtered_book_slug')

    ab_filter_start_date = None
    ab_filter_end_date = None

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
                dt_ab_start = datetime.strptime(ab_start_date_str, '%Y-%m-%d')
                ab_filter_start_date = timezone.make_aware(dt_ab_start.replace(hour=0, minute=0, second=0, microsecond=0), timezone.get_default_timezone()) if timezone.is_naive(dt_ab_start) else dt_ab_start.replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError: messages.error(request, "Invalid audiobook start date format. Please use YYYY-MM-DD.")
        if ab_end_date_str:
            try:
                dt_ab_end = datetime.strptime(ab_end_date_str, '%Y-%m-%d')
                ab_filter_end_date = timezone.make_aware(dt_ab_end.replace(hour=23, minute=59, second=59, microsecond=999999), timezone.get_default_timezone()) if timezone.is_naive(dt_ab_end) else dt_ab_end.replace(hour=23, minute=59, second=59, microsecond=999999)
            except ValueError: messages.error(request, "Invalid audiobook end date format. Please use YYYY-MM-DD.")

    context['ab_start_date_str_audiobook_filter'] = ab_filter_start_date.strftime('%Y-%m-%d') if ab_filter_start_date else ab_start_date_str
    context['ab_end_date_str_audiobook_filter'] = ab_filter_end_date.strftime('%Y-%m-%d') if ab_filter_end_date else ab_end_date_str
    context['ab_selected_period'] = ab_selected_period
    context['filtered_book_slug'] = filtered_book_slug_from_url


    aggregated_earnings_for_list = defaultdict(lambda: {
        'title': 'Unknown (Possibly Deleted Audiobook)', 'slug': None, 'cover_image_url': None,
        'is_active': False, 'is_paid': True, 'publish_date': None, 'audiobook_object': None, 'status_display': 'N/A',
        'paid_details': {'sales': 0, 'gross': Decimal('0.00'), 'commission': Decimal('0.00'), 'net': Decimal('0.00')},
        'free_details': {'views': 0, 'earnings': Decimal('0.00')}
    })

    all_creator_audiobooks_qs = Audiobook.objects.filter(creator=creator_instance) # Use creator_instance
    if filtered_book_slug_from_url:
        all_creator_audiobooks_qs = all_creator_audiobooks_qs.filter(slug=filtered_book_slug_from_url)
    
    audiobook_id_to_object_map = {book.audiobook_id: book for book in all_creator_audiobooks_qs}

    for book_id, book_obj in audiobook_id_to_object_map.items():
        agg_data = aggregated_earnings_for_list[book_id]
        is_book_active = book_obj.status == 'PUBLISHED'

        agg_data.update({
            'title': book_obj.title, 'slug': book_obj.slug,
            'cover_image_url': book_obj.cover_image.url if book_obj.cover_image else None,
            'is_active': is_book_active, 'is_paid': book_obj.is_paid,
            'publish_date': book_obj.publish_date, 'audiobook_object': book_obj,
            'status_display': book_obj.get_status_display()
        })

        current_item_filter_start_date = ab_filter_start_date
        current_item_filter_end_date = ab_filter_end_date

        if book_obj.is_paid:
            sales_for_book_query = CreatorEarning.objects.filter(
                creator=creator_instance, audiobook_id=book_id, earning_type='sale' # Use creator_instance
            ).select_related('purchase')
            if current_item_filter_start_date:
                sales_for_book_query = sales_for_book_query.filter(transaction_date__gte=current_item_filter_start_date)
            if current_item_filter_end_date:
                sales_for_book_query = sales_for_book_query.filter(transaction_date__lte=current_item_filter_end_date)
            
            for sale_earning in sales_for_book_query:
                if sale_earning.purchase: # Ensure purchase exists
                    agg_data['paid_details']['sales'] += 1
                    agg_data['paid_details']['gross'] += sale_earning.purchase.amount_paid
                    agg_data['paid_details']['commission'] += sale_earning.purchase.platform_fee_amount
                    agg_data['paid_details']['net'] += sale_earning.amount_earned
        
        if not book_obj.is_paid: 
            # Ensure AudiobookViewLog is imported
            views_for_book_query = AudiobookViewLog.objects.filter(audiobook_id=book_id) 
            view_earnings_for_this_book_query = CreatorEarning.objects.filter( 
                creator=creator_instance, audiobook_id=book_id, earning_type='view' # Use creator_instance
            )

            if current_item_filter_start_date:
                views_for_book_query = views_for_book_query.filter(viewed_at__gte=current_item_filter_start_date)
                view_earnings_for_this_book_query = view_earnings_for_this_book_query.filter(transaction_date__gte=current_item_filter_start_date)
            if current_item_filter_end_date:
                views_for_book_query = views_for_book_query.filter(viewed_at__lte=current_item_filter_end_date)
                view_earnings_for_this_book_query = view_earnings_for_this_book_query.filter(transaction_date__lte=current_item_filter_end_date)

            period_views = views_for_book_query.count()
            agg_data['free_details']['views'] = period_views
            
            period_view_earnings_sum = view_earnings_for_this_book_query.aggregate(total=Sum('amount_earned'))['total'] or Decimal('0.00')
            agg_data['free_details']['earnings'] = period_view_earnings_sum


    deleted_audiobook_earnings_query = CreatorEarning.objects.filter(
        creator=creator_instance, audiobook__isnull=True, earning_type='sale' # Use creator_instance
    ).select_related('purchase')

    if ab_filter_start_date: 
        deleted_audiobook_earnings_query = deleted_audiobook_earnings_query.filter(transaction_date__gte=ab_filter_start_date)
    if ab_filter_end_date:
        deleted_audiobook_earnings_query = deleted_audiobook_earnings_query.filter(transaction_date__lte=ab_filter_end_date)

    for earning in deleted_audiobook_earnings_query:
        # Ensure slugify is imported
        unique_deleted_key = f"deleted_{slugify(earning.audiobook_title_at_transaction or 'unknown-title')}_{earning.earning_id.hex[:8]}"
        agg_data = aggregated_earnings_for_list[unique_deleted_key] 
        
        agg_data.update({
            'title': earning.audiobook_title_at_transaction or 'Unknown (Deleted Audiobook)',
            'slug': slugify(agg_data['title'] + earning.earning_id.hex[:4]), 
            'is_active': False, 
            'is_paid': True, 
            'status_display': 'Deleted',
            'audiobook_object': None 
        })
        if earning.purchase: 
            agg_data['paid_details']['sales'] += 1
            agg_data['paid_details']['gross'] += earning.purchase.amount_paid
            agg_data['paid_details']['commission'] += earning.purchase.platform_fee_amount
            agg_data['paid_details']['net'] += earning.amount_earned
            
    temp_list = list(aggregated_earnings_for_list.values())
    # Ensure timezone.datetime is available or use datetime.datetime
    min_date_for_sorting = datetime.min.replace(tzinfo=timezone.get_default_timezone()) if timezone.is_aware(now) else datetime.min
    
    temp_list.sort(key=lambda x: x['title'].lower() if x['title'] else '')
    temp_list.sort(key=lambda x: x.get('publish_date') or min_date_for_sorting, reverse=True)
    temp_list.sort(key=lambda x: x.get('is_active', False), reverse=True) 
    earnings_list_final = temp_list


    context.update({
        'earnings_list': earnings_list_final,
        'PLATFORM_COMMISSION_RATE_DISPLAY': PLATFORM_COMMISSION_RATE,
        'EARNING_PER_VIEW': EARNING_PER_VIEW,
        'all_creator_audiobooks_for_filter': all_creator_audiobooks_qs.order_by('title') # This uses the potentially filtered QS
    })
    return render(request, 'creator/creator_myearnings.html', context)