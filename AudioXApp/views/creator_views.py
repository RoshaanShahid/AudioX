import json
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta # Corrected import for timedelta
import os
from collections import defaultdict, OrderedDict
import logging # Added logging import
from django.utils.text import capfirst # For capitalizing

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden, Http404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods, require_GET
from django.views.decorators.csrf import csrf_protect # csrf_protect for views that modify data
from django.core.exceptions import ValidationError, ObjectDoesNotExist, FieldError
from django.core.validators import RegexValidator
from django.db import transaction, IntegrityError
from django.db.models import Q, F, Max, Sum, Value, Case, When, DecimalField, OuterRef, Subquery, Exists, Count
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from django.urls import reverse
from django.core.files.storage import default_storage
from django.template.defaultfilters import filesizeformat
from django.utils.text import slugify
from django.contrib.messages import get_messages
from django.core.serializers.json import DjangoJSONEncoder
from django.conf import settings
from django.core.files.base import ContentFile
# from django.core.files.storage import default_storage # To save TTS audio # Already imported

from ..models import User, Creator, Audiobook, Chapter, WithdrawalRequest, CreatorApplicationLog, Admin, WithdrawalAccount, CreatorEarning, AudiobookViewLog
from .utils import _get_full_context
from .decorators import admin_role_required

# --- Logger Setup ---
logger = logging.getLogger(__name__) # Initialize logger

PLATFORM_COMMISSION_RATE = Decimal('10.00')
EARNING_PER_VIEW = Decimal('1.00')
MIN_WITHDRAWAL_AMOUNT = Decimal('50.00')
CANCELLATION_WINDOW_MINUTES = 30

# --- Google Cloud Text-to-Speech (TTS) Setup ---
try:
    from google.cloud import texttospeech
    google_tts_available = True
    logger.info("Google Cloud Text-to-Speech library loaded successfully in creator_views.")
except ImportError:
    logger.warning("Google Cloud Text-to-Speech library (google-cloud-texttospeech) not found. TTS functionality will be disabled in creator_views.")
    google_tts_available = False
except Exception as e:
    logger.error(f"Error importing Google Cloud Text-to-Speech library in creator_views: {e}")
    google_tts_available = False

# --- Google Cloud Text-to-Speech (TTS) Voice Mapping ---
TTS_VOICE_MAPPING = {
    'ali_narrator': { # Male
        'name': "en-US-Wavenet-D", 
        'language_code': "en-US"
    },
    'aisha_narrator': { # Female
        'name': "en-US-Wavenet-E", 
        'language_code': "en-US"
    },
}
DEFAULT_TTS_VOICE_PARAMS = {    
    'name': "en-US-Wavenet-A",    
    'language_code': "en-US"
}
# --- End Google Cloud TTS Setup ---


def creator_required(view_func):
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        try:
            creator = Creator.objects.select_related('user').get(user=request.user)
            if creator.is_banned:
                messages.error(request, "Your creator account is banned.")
                return redirect('AudioXApp:home')
            if creator.verification_status != 'approved':
                messages.warning(request, "Your creator profile is not approved.")
                return redirect('AudioXApp:home')
            request.creator = creator
            return view_func(request, *args, **kwargs)
        except Creator.DoesNotExist:
            messages.warning(request, "You do not have an active creator profile.")
            return redirect('AudioXApp:creator_welcome')
        except Exception as e:
            user_identifier = request.user.user_id if hasattr(request.user, 'user_id') else "Unknown User"
            logger.error(f"An error occurred accessing creator information for user {user_identifier}: {type(e).__name__} - {e}")
            messages.error(request, f"An error occurred accessing creator information for user {user_identifier}: {type(e).__name__} - {e}")
            return redirect('AudioXApp:home')
    return _wrapped_view

@login_required
@require_POST
@csrf_protect # Ensure CSRF protection for POST requests
def log_audiobook_view(request):
    """
    Logs a view for an audiobook.
    Ensures a user's view for the same audiobook is only counted for earnings/total_views once per 24 hours.
    Expects a JSON payload with 'audiobook_id'.
    """
    if not request.user.is_authenticated: # Should be redundant due to @login_required but good for clarity
        return JsonResponse({'status': 'error', 'message': 'User not authenticated.'}, status=401)

    try:
        data = json.loads(request.body)
        audiobook_id = data.get('audiobook_id')
    except json.JSONDecodeError:
        logger.warning(f"log_audiobook_view: Invalid JSON payload from user {request.user.username}.")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON payload.'}, status=400)

    if not audiobook_id:
        logger.warning(f"log_audiobook_view: Audiobook ID missing in payload from user {request.user.username}.")
        return JsonResponse({'status': 'error', 'message': 'Audiobook ID is required.'}, status=400)

    try:
        # Ensure audiobook_id is an integer or can be cast to one if your PK is integer
        audiobook_id = int(audiobook_id) 
    except ValueError:
        logger.warning(f"log_audiobook_view: Invalid Audiobook ID format '{audiobook_id}' from user {request.user.username}.")
        return JsonResponse({'status': 'error', 'message': 'Invalid Audiobook ID format.'}, status=400)

    try:
        audiobook = get_object_or_404(
            Audiobook.objects.select_related('creator'), # Select related creator for earnings logic
            pk=audiobook_id
        )

        # Check if this user has viewed this audiobook in the last 24 hours
        twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
        recent_view_exists = AudiobookViewLog.objects.filter(
            audiobook=audiobook,
            user=request.user,
            viewed_at__gte=twenty_four_hours_ago
        ).exists()

        if recent_view_exists:
            # View already logged for this user/audiobook within 24 hours.
            # Still return current total_views for UI consistency if needed.
            return JsonResponse({
                'status': 'success', 
                'message': 'View already logged recently.',
                'total_views': audiobook.total_views # Return current total_views
            })

        # If no recent view, proceed to log it and update counts/earnings
        with transaction.atomic():
            # Lock the audiobook row to prevent race conditions when updating total_views
            audiobook_locked = Audiobook.objects.select_for_update().get(pk=audiobook.pk)

            AudiobookViewLog.objects.create(
                audiobook=audiobook_locked,
                user=request.user
            )

            # Increment total views
            audiobook_locked.total_views = F('total_views') + 1
            audiobook_locked.save(update_fields=['total_views'])
            audiobook_locked.refresh_from_db(fields=['total_views']) # Get the updated value

            # Handle earnings for free audiobooks
            if not audiobook_locked.is_paid:
                creator = audiobook_locked.creator
                earned_amount_for_view = EARNING_PER_VIEW # Defined constant

                # Update creator's balances
                Creator.objects.filter(pk=creator.pk).update(
                    available_balance=F('available_balance') + earned_amount_for_view,
                    total_earning=F('total_earning') + earned_amount_for_view
                )

                # Log the earning event
                CreatorEarning.objects.create(
                    creator=creator,
                    audiobook=audiobook_locked,
                    earning_type='view',
                    amount_earned=earned_amount_for_view,
                    transaction_date=timezone.now(),
                    audiobook_title_at_transaction=audiobook_locked.title,
                    notes=f"Earning from 1 view on '{audiobook_locked.title}' (24hr rule applied)."
                )
                logger.info(f"View logged and earning processed for user {request.user.username}, audiobook ID {audiobook_id}.")
            else:
                logger.info(f"View logged for user {request.user.username}, audiobook ID {audiobook_id} (paid book, no view earning).")


            return JsonResponse({
                'status': 'success', 
                'message': 'View logged successfully.',
                'total_views': audiobook_locked.total_views # Return the new total_views
            })

    except Audiobook.DoesNotExist: # Changed from Http404 to Audiobook.DoesNotExist for more specific catch
        logger.warning(f"log_audiobook_view: Audiobook not found for ID {audiobook_id}, user {request.user.username}.")
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except Exception as e:
        logger.error(f"log_audiobook_view: Internal error for user {request.user.username}, audiobook ID {audiobook_id}. Error: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An internal error occurred.'}, status=500)


@creator_required
def creator_dashboard_view(request):
    try:
        creator_profile = request.creator
    except AttributeError:
        messages.error(request, "Creator profile not available. Please log in again.")
        logger.warning("Creator profile not found on request in creator_dashboard_view.") # Used logger
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
            Coalesce('publish_date', 'created_at', Value(now - timedelta(days=365*10)))
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
        for i in range(11, -1, -1):
            year = today.year
            month_offset = today.month - i
            final_month = month_offset
            final_year = year
            while final_month <= 0:
                final_month += 12
                final_year -= 1
            month_start_dt_naive = datetime(final_year, final_month, 1)
            if first_month_in_sequence is None:
                first_month_in_sequence = month_start_dt_naive
            month_key = month_start_dt_naive.strftime('%Y-%m')
            month_label = month_start_dt_naive.strftime('%b %Y')
            months_data[month_key] = {'label': month_label, 'earnings': Decimal('0.00'), 'uploads': 0}

        query_start_date = first_month_in_sequence
        if query_start_date:
            query_start_date = datetime.combine(query_start_date, datetime.min.time())
            if settings.USE_TZ:
                query_start_date = timezone.make_aware(query_start_date)
        else:
            fallback_date = datetime(today.year -1, today.month, 1)
            query_start_date = timezone.make_aware(fallback_date) if settings.USE_TZ else fallback_date

        earnings_by_month_qs = CreatorEarning.objects.filter(
            creator=creator_profile,
            transaction_date__gte=query_start_date
        ).annotate(
            month=TruncMonth('transaction_date')
        ).values('month').annotate(
            total_amount=Sum('amount_earned')
        ).order_by('month')

        for earning_entry in earnings_by_month_qs:
            month_obj = earning_entry['month']
            month_dt_naive = datetime(month_obj.year, month_obj.month, month_obj.day)
            month_key = month_dt_naive.strftime('%Y-%m')
            if month_key in months_data:
                months_data[month_key]['earnings'] = earning_entry['total_amount'] or Decimal('0.00')

        if hasattr(Audiobook, 'created_at'):
            uploads_by_month_qs = Audiobook.objects.filter(
                creator=creator_profile,
                created_at__gte=query_start_date
            ).annotate(
                month=TruncMonth('created_at')
            ).values('month').annotate(
                count=Count('audiobook_id')
            ).order_by('month')

            for upload_entry in uploads_by_month_qs:
                month_obj = upload_entry['month']
                month_dt_naive = datetime(month_obj.year, month_obj.month, month_obj.day)
                month_key = month_dt_naive.strftime('%Y-%m')
                if month_key in months_data:
                    months_data[month_key]['uploads'] = upload_entry['count'] or 0

        earnings_chart_labels = [data['label'] for data in months_data.values()]
        earnings_chart_values = [float(data['earnings']) for data in months_data.values()]
        uploads_chart_labels = [data['label'] for data in months_data.values()]
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
        logger.error(f"FieldError in creator_dashboard_view: {fe}", exc_info=True) # Used logger
        messages.error(request, f"A data error occurred while loading the dashboard (missing field: {fe.args[0]}). Please ensure migrations are complete and the database schema is up to date. If the issue persists, contact support.")
        return redirect('AudioXApp:home')
    except Creator.DoesNotExist:
        logger.warning("Creator.DoesNotExist in creator_dashboard_view after initial check.") # Used logger
        messages.error(request, "Creator profile not found. Please log in again.")
        return redirect('AudioXApp:home')
    except Exception as e:
        logger.error(f"Unexpected error in creator_dashboard_view: {e}", exc_info=True) # Used logger
        messages.error(request, "An unexpected error occurred while loading your dashboard. Please try again later.")
        return redirect('AudioXApp:home')


def creator_welcome_view(request):
    context = _get_full_context(request)
    if request.user.is_authenticated and hasattr(request.user, 'creator_profile') and request.user.creator_profile.is_approved:
        return redirect('AudioXApp:creator_dashboard')
    return render(request, 'creator/creator_welcome.html', context)

@login_required
@csrf_protect
def creator_apply_view(request):
    user = request.user
    creator_profile = None
    can_reapply = True
    application_status = None
    rejection_reason = None

    try:
        creator_profile = Creator.objects.get(user=user)
        application_status = creator_profile.verification_status

        if application_status == 'approved' and not getattr(creator_profile, 'is_banned', False):
            messages.info(request, "You are already an approved creator.")
            return redirect('AudioXApp:creator_dashboard')
        elif application_status == 'pending':
            messages.info(request, "Your creator application is currently pending review.")
        elif application_status == 'rejected':
            can_reapply = creator_profile.can_reapply()
            rejection_reason = creator_profile.rejection_reason
            if not can_reapply:
                messages.warning(request, "You have reached the maximum number of creator applications for this month.")

        if getattr(creator_profile, 'is_banned', False):
            messages.error(request, f"Your creator account is banned. Reason: {getattr(creator_profile, 'ban_reason', 'N/A')}")
            context = _get_full_context(request)
            context['is_banned_on_apply_page'] = True
            return render(request, 'creator/creator_apply.html', context)

    except Creator.DoesNotExist:
        application_status = None
    except Exception as e:
        logger.error(f"Error checking creator status in creator_apply_view for user {user.username}: {e}", exc_info=True) # Used logger
        messages.error(request, "An error occurred while checking your creator status.")
        return redirect('AudioXApp:home')

    if request.method == 'POST':
        if application_status == 'pending':
            return JsonResponse({'status': 'error', 'message': 'Your application is already pending review.'}, status=400)
        if application_status == 'rejected' and not can_reapply:
            return JsonResponse({'status': 'error', 'message': 'You have reached the application limit for this month.'}, status=400)
        if creator_profile and getattr(creator_profile, 'is_banned', False):
            return JsonResponse({'status': 'error', 'message': 'Banned users cannot apply.'}, status=403)

        creator_name = request.POST.get('creator_name', '').strip()
        creator_unique_name = request.POST.get('creator_unique_name', '').strip()
        terms_agree = request.POST.get('terms_agree') == 'on'
        content_rights = request.POST.get('content_rights') == 'on'
        legal_use = request.POST.get('legal_use') == 'on'
        accurate_info = request.POST.get('accurate_info') == 'on'
        cnic_front_file = request.FILES.get('cnic_front')
        cnic_back_file = request.FILES.get('cnic_back')

        errors = {}
        if not creator_name: errors['creator_name'] = 'Creator Name is required.'
        if not creator_unique_name: errors['creator_unique_name'] = 'Creator Unique Name (@handle) is required.'
        else:
            validator = RegexValidator(regex=r'^[a-zA-Z0-9_]+$', message='Unique name can only contain letters, numbers, and underscores.')
            try:
                validator(creator_unique_name)
                query = Creator.objects.filter(creator_unique_name__iexact=creator_unique_name)
                if creator_profile: query = query.exclude(pk=creator_profile.pk)
                if query.exists(): errors['creator_unique_name'] = 'This unique name is already taken.'
            except ValidationError as e: errors['creator_unique_name'] = e.message

        if not all([terms_agree, content_rights, legal_use, accurate_info]): errors['agreements'] = 'You must agree to all terms and conditions.'

        if not creator_profile or not creator_profile.cnic_front:
            if not cnic_front_file: errors['cnic_front'] = 'CNIC Front image is required.'
        if not creator_profile or not creator_profile.cnic_back:
            if not cnic_back_file: errors['cnic_back'] = 'CNIC Back image is required.'

        max_size = 2 * 1024 * 1024 # 2MB
        allowed_types = ['image/png', 'image/jpeg', 'image/jpg']
        def validate_image(file, field_name):
            if file:
                if file.size > max_size: errors[field_name] = f'{field_name.replace("_", " ").title()} too large (Max 2MB).'
                if file.content_type not in allowed_types: errors[field_name] = 'Invalid file type (PNG, JPG/JPEG only).'
        validate_image(cnic_front_file, 'cnic_front')
        validate_image(cnic_back_file, 'cnic_back')

        if errors:
            return JsonResponse({'status': 'error', 'message': 'Please correct the errors below.', 'errors': errors}, status=400)

        try:
            with transaction.atomic():
                now = timezone.now()
                current_attempts = creator_profile.get_attempts_this_month() if creator_profile else 0
                attempts_this_month = current_attempts + 1

                if attempts_this_month > 3:
                    return JsonResponse({'status': 'error', 'message': 'Application limit reached for this month.'}, status=400)

                creator_defaults = {
                    'creator_name': creator_name, 'creator_unique_name': creator_unique_name,
                    'terms_accepted_at': now, 'verification_status': 'pending',
                    'last_application_date': now, 'application_attempts_current_month': attempts_this_month,
                    'rejection_reason': None, 'rejection_popup_shown': False, 'welcome_popup_shown': False,
                    'approved_at': None, 'approved_by': None, 'attempts_at_approval': None,
                    'is_banned': False, 'ban_reason': None, 'banned_at': None, 'banned_by': None,
                    'last_name_change_date': None, 'last_unique_name_change_date': None,
                }
                if cnic_front_file: creator_defaults['cnic_front'] = cnic_front_file
                if cnic_back_file: creator_defaults['cnic_back'] = cnic_back_file

                creator, created = Creator.objects.update_or_create(user=user, defaults=creator_defaults)

                log_cnic_front = cnic_front_file if cnic_front_file else creator.cnic_front
                log_cnic_back = cnic_back_file if cnic_back_file else creator.cnic_back

                CreatorApplicationLog.objects.create(
                    creator=creator, application_date=now, attempt_number_monthly=attempts_this_month,
                    creator_name_submitted=creator_name, creator_unique_name_submitted=creator_unique_name,
                    cnic_front_submitted=log_cnic_front, cnic_back_submitted=log_cnic_back,
                    terms_accepted_at_submission=now, status='submitted'
                )

            redirect_url = reverse('AudioXApp:home')
            messages.success(request, 'Creator application submitted successfully! It is now pending review.')
            return JsonResponse({'status': 'success', 'message': 'Application submitted.', 'redirect_url': redirect_url})

        except IntegrityError as e:
            logger.error(f"IntegrityError in creator_apply_view: {e}", exc_info=True) # Used logger
            error_message = 'An error occurred.'
            errors = {}
            if 'creator_unique_name' in str(e).lower():
                error_message = 'That unique name is already taken.'
                errors['creator_unique_name'] = error_message
            else:
                error_message = "A database error occurred."; errors['__all__'] = error_message
            return JsonResponse({ 'status': 'error', 'message': error_message, 'errors': errors }, status=400)
        except Exception as e:
            logger.error(f"Unexpected error in creator_apply_view POST: {e}", exc_info=True) # Used logger
            return JsonResponse({ 'status': 'error', 'message': 'An unexpected error occurred.', 'errors': {'__all__': 'Server error.'} }, status=500)

    else: # GET Request
        context = _get_full_context(request)
        context['application_status'] = application_status
        context['can_reapply'] = can_reapply
        context['rejection_reason'] = rejection_reason
        context['creator_profile'] = creator_profile
        return render(request, 'creator/creator_apply.html', context)


@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def update_creator_profile(request):
    creator = request.creator
    user = request.user
    now = timezone.now()
    cooldown_period = timedelta(days=60)

    can_change_name = not creator.last_name_change_date or (now - creator.last_name_change_date) >= cooldown_period
    next_name_change_date = (creator.last_name_change_date + cooldown_period) if creator.last_name_change_date else None

    can_change_unique_name = not creator.last_unique_name_change_date or (now - creator.last_unique_name_change_date) >= cooldown_period
    next_unique_name_change_date = (creator.last_unique_name_change_date + cooldown_period) if creator.last_unique_name_change_date else None

    if request.method == 'POST':
        new_creator_name = request.POST.get('creator_name', '').strip()
        new_unique_name = request.POST.get('creator_unique_name', '').strip()
        profile_pic_file = request.FILES.get('creator_profile_pic')
        remove_profile_pic = request.POST.get('remove_profile_pic') == '1'

        errors = {}
        form_values = {'creator_name': new_creator_name, 'creator_unique_name': new_unique_name}
        update_fields = []
        made_changes = False

        old_profile_pic_path = creator.creator_profile_pic.name if creator.creator_profile_pic else None
        if remove_profile_pic and not profile_pic_file:
            if creator.creator_profile_pic:
                if old_profile_pic_path and default_storage.exists(old_profile_pic_path):
                    try: default_storage.delete(old_profile_pic_path)
                    except Exception as del_e: logger.warning(f"Failed to delete old profile pic {old_profile_pic_path}: {del_e}") # Used logger
                creator.creator_profile_pic = None
                update_fields.append('creator_profile_pic')
                made_changes = True
        elif profile_pic_file:
            max_size = 2 * 1024 * 1024; allowed_types = ['image/png', 'image/jpeg', 'image/jpg']
            if profile_pic_file.size > max_size: errors['creator_profile_pic'] = 'Picture too large (Max 2MB).'
            elif profile_pic_file.content_type not in allowed_types: errors['creator_profile_pic'] = 'Invalid file type (PNG, JPG/JPEG only).'
            else:
                if old_profile_pic_path and old_profile_pic_path != profile_pic_file.name and default_storage.exists(old_profile_pic_path):
                    try: default_storage.delete(old_profile_pic_path)
                    except Exception as del_e: logger.warning(f"Failed to delete old profile pic {old_profile_pic_path} during update: {del_e}") # Used logger
                creator.creator_profile_pic = profile_pic_file
                update_fields.append('creator_profile_pic')
                made_changes = True

        name_changed = creator.creator_name != new_creator_name
        if name_changed:
            if not can_change_name: errors['creator_name'] = f"You cannot change your display name again until {next_name_change_date.strftime('%b %d, %Y')}."
            elif not new_creator_name: errors['creator_name'] = "Display name cannot be empty."
            elif len(new_creator_name) > 100: errors['creator_name'] = "Display name is too long (max 100 characters)."
            else:
                creator.creator_name = new_creator_name
                creator.last_name_change_date = now
                update_fields.extend(['creator_name', 'last_name_change_date'])
                made_changes = True

        unique_name_changed = creator.creator_unique_name != new_unique_name
        if unique_name_changed:
            if not can_change_unique_name: errors['creator_unique_name'] = f"You cannot change your unique handle again until {next_unique_name_change_date.strftime('%b %d, %Y')}."
            elif not new_unique_name: errors['creator_unique_name'] = "Unique handle cannot be empty."
            elif len(new_unique_name) > 50: errors['creator_unique_name'] = "Unique handle is too long (max 50 characters)."
            else:
                validator = Creator.unique_name_validator
                try:
                    validator(new_unique_name)
                    if Creator.objects.filter(creator_unique_name__iexact=new_unique_name).exclude(user=user).exists():
                        errors['creator_unique_name'] = 'This unique name is already taken.'
                    else:
                        creator.creator_unique_name = new_unique_name
                        creator.last_unique_name_change_date = now
                        update_fields.extend(['creator_unique_name', 'last_unique_name_change_date'])
                        made_changes = True
                except ValidationError as e: errors['creator_unique_name'] = e.message

        if errors:
            messages.error(request, "Please correct the errors below.")
            context = {
                'user': user, 'creator': Creator.objects.get(pk=creator.pk),
                'form_errors': errors, 'form_values': form_values,
                'can_change_name': can_change_name, 'next_name_change_date': next_name_change_date,
                'can_change_unique_name': can_change_unique_name, 'next_unique_name_change_date': next_unique_name_change_date,
                'available_balance': creator.available_balance,
            }
            return render(request, 'creator/creator_profile.html', context)
        else:
            try:
                with transaction.atomic():
                    if update_fields:
                        update_fields = list(set(update_fields))
                        creator.save(update_fields=update_fields)
                        messages.success(request, "Creator profile updated successfully!")
                    elif made_changes and 'creator_profile_pic' in update_fields and len(update_fields) == 1 and creator.creator_profile_pic is None:
                        creator.save(update_fields=['creator_profile_pic'])
                        messages.success(request, "Profile picture removed successfully!")
                    elif made_changes:
                        logger.warning("Profile update: 'made_changes' was true but 'update_fields' was empty or inconsistent.") # Used logger
                        messages.warning(request, "An internal inconsistency occurred. Please try again.")
                    else: messages.info(request, "No changes were detected.")
                return redirect('AudioXApp:update_creator_profile')
            except IntegrityError:
                logger.warning(f"IntegrityError updating creator profile for {creator.user.username}", exc_info=True) # Used logger
                messages.error(request, "That unique name might already be taken. Please try another.")
                errors['creator_unique_name'] = 'This unique name is already taken.'
                context = {
                    'user': user, 'creator': Creator.objects.get(pk=creator.pk),
                    'form_errors': errors, 'form_values': form_values,
                    'can_change_name': can_change_name, 'next_name_change_date': next_name_change_date,
                    'can_change_unique_name': can_change_unique_name, 'next_unique_name_change_date': next_unique_name_change_date,
                    'available_balance': creator.available_balance,
                }
                return render(request, 'creator/creator_profile.html', context)
            except Exception as e:
                logger.error(f"Unexpected error updating creator profile for {creator.user.username}: {e}", exc_info=True) # Used logger
                messages.error(request, "An unexpected error occurred while updating your profile.")

    context = {
        'user': user, 'creator': creator, 'form_errors': {}, 'form_values': {},
        'can_change_name': can_change_name, 'next_name_change_date': next_name_change_date,
        'can_change_unique_name': can_change_unique_name, 'next_unique_name_change_date': next_unique_name_change_date,
        'available_balance': creator.available_balance,
    }
    return render(request, 'creator/creator_profile.html', context)

@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_manage_withdrawal_accounts_view(request):
    creator = request.creator
    withdrawal_accounts = WithdrawalAccount.objects.filter(creator=creator).order_by('-is_primary', '-added_at')
    can_add_more = withdrawal_accounts.count() < 3
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
                if account_identifier:
                    try:
                        WithdrawalAccount.iban_validator(account_identifier)
                    except ValidationError as e:
                        errors_from_post.setdefault('account_identifier', []).extend(e.messages)
            elif account_type in ['jazzcash', 'easypaisa', 'nayapay', 'upaisa']:
                if bank_name: bank_name = ''
                if account_identifier:
                    try:
                        WithdrawalAccount.mobile_account_validator(account_identifier)
                    except ValidationError as e:
                        errors_from_post.setdefault('account_identifier', []).extend(e.messages)

            if errors_from_post:
                for field, error_msg_or_list in errors_from_post.items():
                    if isinstance(error_msg_or_list, list):
                        messages.error(request, f"{field.replace('_', ' ').title()}: {' '.join(error_msg_or_list)}")
                    else:
                        messages.error(request, f"{field.replace('_', ' ').title()}: {error_msg_or_list}")
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
                        new_account.full_clean()
                        new_account.save()

                        if current_account_count == 0 and not new_account.is_primary:
                            new_account.is_primary = True
                            new_account.save(update_fields=['is_primary'])
                            messages.success(request, f"{new_account.get_account_type_display()} account added and set as primary.")
                        elif new_account.is_primary:
                            WithdrawalAccount.objects.filter(creator=creator).exclude(pk=new_account.pk).update(is_primary=False)
                            messages.success(request, f"{new_account.get_account_type_display()} account added and set as primary.")
                        else:
                            messages.success(request, f"{new_account.get_account_type_display()} account added successfully.")

                        next_url = request.GET.get('next')
                        if next_url:
                            return redirect(next_url)
                        return redirect('AudioXApp:creator_manage_withdrawal_accounts')

                except ValidationError as e:
                    if hasattr(e, 'message_dict'):
                        for field, error_list_val_err in e.message_dict.items():
                            messages.error(request, f"{field.replace('_', ' ').title()}: {' '.join(error_list_val_err)}")
                            errors_from_post[field] = ' '.join(error_list_val_err)
                    else:
                        messages.error(request, f"Validation Error: {e}")
                        errors_from_post['__all__'] = str(e)
                except IntegrityError as e:
                    messages.error(request, f"Database Error: Could not save account. It might conflict with existing data. {e}")
                    errors_from_post['__all__'] = "A database error occurred. The account might already exist or conflict with other data."
                except Exception as e:
                    messages.error(request, f"An unexpected error occurred: {e}")
                    errors_from_post['__all__'] = "An unexpected server error occurred."


        elif action == 'set_primary':
            account_id_to_set = request.POST.get('account_id')
            try:
                account_to_set = get_object_or_404(WithdrawalAccount, pk=account_id_to_set, creator=creator)
                if not account_to_set.is_primary:
                    with transaction.atomic():
                        WithdrawalAccount.objects.filter(creator=creator).exclude(pk=account_to_set.pk).update(is_primary=False)
                        account_to_set.is_primary = True
                        account_to_set.save(update_fields=['is_primary'])
                    messages.success(request, f"{account_to_set.get_account_type_display()} account ending in ...{account_to_set.account_identifier[-4:]} set as primary.")
                else:
                    messages.info(request, "This account is already set as primary.")
            except Http404:
                messages.error(request, "Account not found or you do not have permission.")
            except Exception as e:
                messages.error(request, f"An error occurred: {e}")
            return redirect('AudioXApp:creator_manage_withdrawal_accounts')
        else:
            messages.warning(request, "Invalid action submitted.")
            return redirect('AudioXApp:creator_manage_withdrawal_accounts')

    context = _get_full_context(request)
    context.update({
        'creator': creator,
        'withdrawal_accounts': WithdrawalAccount.objects.filter(creator=creator).order_by('-is_primary', '-added_at'),
        'can_add_more': WithdrawalAccount.objects.filter(creator=creator).count() < 3,
        'available_balance': creator.available_balance,
    })
    if request.method == 'POST' and action == 'add_account' and errors_from_post:
       context['submitted_values'] = request.POST
       context['form_errors'] = errors_from_post

    return render(request, 'creator/creator_withdrawal_account.html', context)

@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_request_withdrawal_list_view(request):
    creator_from_decorator = request.creator

    withdrawal_accounts = WithdrawalAccount.objects.filter(creator=creator_from_decorator).order_by('-is_primary', 'account_title')
    past_requests = WithdrawalRequest.objects.filter(creator=creator_from_decorator).order_by('-request_date')

    can_request_now, reason_cant_request_now = creator_from_decorator.can_request_withdrawal()
    has_active_request_flag = WithdrawalRequest.objects.filter(
        creator=creator_from_decorator,
        status__in=['pending', 'approved', 'processing']
    ).exists()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'request_withdrawal':
            try:
                with transaction.atomic():
                    creator_instance_for_post = Creator.objects.select_for_update().get(pk=creator_from_decorator.pk)

                    current_can_request, current_reason_cant = creator_instance_for_post.can_request_withdrawal()
                    if not current_can_request:
                        messages.error(request, current_reason_cant or "You are currently unable to make a withdrawal request.")
                        return redirect('AudioXApp:creator_request_withdrawal_list')

                    if not withdrawal_accounts.exists():
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
                        for error_msg in errors:
                            messages.error(request, error_msg)
                    else:
                        new_request = WithdrawalRequest.objects.create(
                            creator=creator_instance_for_post,
                            amount=amount_decimal,
                            withdrawal_account=selected_account,
                            status='pending'
                        )

                        creator_instance_for_post.available_balance = F('available_balance') - amount_decimal
                        creator_instance_for_post.last_withdrawal_request_date = new_request.request_date
                        creator_instance_for_post.save(update_fields=['available_balance', 'last_withdrawal_request_date'])

                        messages.success(request, f"Withdrawal request for Rs. {amount_decimal:,.2f} submitted successfully. It is now pending review.")
                        return redirect('AudioXApp:creator_request_withdrawal_list')
            except Creator.DoesNotExist:
                messages.error(request, "Creator profile not found during transaction.")
                return redirect('AudioXApp:home')
            except IntegrityError:
                messages.error(request, "A database error occurred. Please try again.")
            except Exception as e:
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
                    if not withdrawal_to_cancel.request_date:
                        messages.error(request, "Cannot determine request age. Please contact support.")
                        return redirect('AudioXApp:creator_request_withdrawal_list')

                    time_since_request = now - withdrawal_to_cancel.request_date

                    if time_since_request > timedelta(minutes=CANCELLATION_WINDOW_MINUTES):
                        messages.error(request, f"The cancellation window of {CANCELLATION_WINDOW_MINUTES} minutes for this request has expired.")
                        return redirect('AudioXApp:creator_request_withdrawal_list')

                    original_amount = withdrawal_to_cancel.amount

                    withdrawal_to_cancel.status = 'cancelled'
                    withdrawal_to_cancel.admin_notes = (withdrawal_to_cancel.admin_notes or "") + f"\nCancelled by creator on {now.strftime('%Y-%m-%d %H:%M')} within {CANCELLATION_WINDOW_MINUTES} min window."
                    withdrawal_to_cancel.processed_date = now
                    withdrawal_to_cancel.save(update_fields=['status', 'admin_notes', 'processed_date'])

                    creator_instance_for_post.available_balance = F('available_balance') + original_amount

                    if creator_instance_for_post.last_withdrawal_request_date == withdrawal_to_cancel.request_date:
                        creator_instance_for_post.last_withdrawal_request_date = None

                    creator_instance_for_post.save(update_fields=['available_balance', 'last_withdrawal_request_date'])

                    messages.success(request, f"Withdrawal request for Rs. {original_amount:,.2f} has been cancelled.")
            except Creator.DoesNotExist:
                messages.error(request, "Creator profile not found during transaction.")
                return redirect('AudioXApp:home')
            except Http404:
                messages.error(request, "Withdrawal request not found.")
            except Exception as e:
                messages.error(request, f"An error occurred while cancelling the request: {e}")
            return redirect('AudioXApp:creator_request_withdrawal_list')

    fresh_creator = Creator.objects.get(pk=creator_from_decorator.pk)
    can_request_now, reason_cant_request_now = fresh_creator.can_request_withdrawal()
    has_active_request_flag = WithdrawalRequest.objects.filter(
        creator=fresh_creator,
        status__in=['pending', 'approved', 'processing']
    ).exists()

    context = _get_full_context(request)
    context.update({
        'creator': fresh_creator,
        'withdrawal_accounts': withdrawal_accounts,
        'past_requests': past_requests,
        'can_request_withdrawal': can_request_now,
        'reason_cant_request': reason_cant_request_now,
        'has_active_request': has_active_request_flag,
        'available_balance': fresh_creator.available_balance,
        'min_withdrawal_amount': MIN_WITHDRAWAL_AMOUNT,
        'next_withdrawal_date': None,
    })

    if not can_request_now and fresh_creator.last_withdrawal_request_date and "after" in (reason_cant_request_now or "").lower():
        context['next_withdrawal_date'] = fresh_creator.last_withdrawal_request_date + timedelta(days=15)

    return render(request, 'creator/creator_withdrawal_request.html', context)


@creator_required
def creator_my_audiobooks_view(request):
    creator = request.creator
    try:
        audiobooks_queryset = Audiobook.objects.filter(creator=creator).order_by('-publish_date').prefetch_related('chapters')

        audiobooks_data_list = []
        for book in audiobooks_queryset:
            earnings_from_views = Decimal('0.00')
            if not book.is_paid:
                view_earnings_aggregation = CreatorEarning.objects.filter(
                    creator=creator,
                    audiobook=book,
                    earning_type='view'
                ).aggregate(total_earnings=Sum('amount_earned'))

                earnings_from_views = view_earnings_aggregation['total_earnings'] or Decimal('0.00')

            audiobooks_data_list.append({
                'book': book,
                'earnings_from_views': earnings_from_views
            })

        context = _get_full_context(request)
        context.update({
            'creator': creator,
            'audiobooks_data': audiobooks_data_list,
            'audiobooks_count': len(audiobooks_data_list),
            'available_balance': creator.available_balance
        })
        return render(request, 'creator/creator_my_audiobooks.html', context)
    except Exception as e:
        logger.error(f"Could not load creator's audiobooks: {e}", exc_info=True) # Used logger
        messages.error(request, "Could not load your audiobooks.")
        return redirect('AudioXApp:creator_dashboard')

@creator_required
@require_POST
@csrf_protect
def generate_tts_preview_audio(request):
    """
    Generates TTS audio from text for preview and returns a URL to the temporary audio file.
    Uses the centrally defined TTS_VOICE_MAPPING and TEMP_TTS_PREVIEWS_DIR_NAME from settings.
    Includes enhanced logging.
    """
    if not google_tts_available:
        logger.error("TTS generation requested (preview) but Google TTS library is not available.")
        return JsonResponse({'status': 'error', 'message': 'Text-to-Speech service is currently unavailable.'}, status=503)

    try:
        text_content = request.POST.get('text_content', '').strip()
        tts_voice_id_from_request = request.POST.get('tts_voice_id', 'default')

        logger.info(f"[TTS PREVIEW] Received request. User: {request.user.username}, Requested Voice ID: '{tts_voice_id_from_request}', Text Length: {len(text_content)}")

        if not text_content:
            logger.warning(f"[TTS PREVIEW] Text content missing for user {request.user.username}.")
            return JsonResponse({'status': 'error', 'message': 'Text content is required for TTS generation.'}, status=400)
        if len(text_content) < 10:
            logger.warning(f"[TTS PREVIEW] Text content too short for user {request.user.username}.")
            return JsonResponse({'status': 'error', 'message': 'Text content is too short (min 10 characters).'}, status=400)
        if len(text_content) > 5000:  # Max length for preview
            logger.warning(f"[TTS PREVIEW] Text content too long for user {request.user.username}.")
            return JsonResponse({'status': 'error', 'message': 'Text content is too long (max 5000 characters for preview).'}, status=400)
        
        if tts_voice_id_from_request == 'default' or tts_voice_id_from_request not in TTS_VOICE_MAPPING:
            logger.error(f"[TTS PREVIEW] Invalid or default voice_id '{tts_voice_id_from_request}' selected by user {request.user.username}. Available mapping keys: {list(TTS_VOICE_MAPPING.keys())}")
            return JsonResponse({'status': 'error', 'message': 'Please select a specific valid narrator voice for TTS preview.'}, status=400)

        selected_voice_params_dict = TTS_VOICE_MAPPING.get(tts_voice_id_from_request)
        if not selected_voice_params_dict: # Should not happen due to the check above
            logger.error(f"[TTS PREVIEW] CRITICAL: Voice ID '{tts_voice_id_from_request}' was in mapping keys but .get() returned None.")
            selected_voice_params_dict = DEFAULT_TTS_VOICE_PARAMS # Fallback
            logger.info(f"[TTS PREVIEW] Falling back to DEFAULT_TTS_VOICE_PARAMS: {selected_voice_params_dict}")

        logger.info(f"[TTS PREVIEW] For Voice ID '{tts_voice_id_from_request}', using mapped params: {selected_voice_params_dict}")

        tts_client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text_content)

        voice_params = texttospeech.VoiceSelectionParams(
            language_code=selected_voice_params_dict['language_code'],
            name=selected_voice_params_dict['name']
        )
        logger.info(f"[TTS PREVIEW] VoiceSelectionParams sent to Google: language_code='{selected_voice_params_dict['language_code']}', name='{selected_voice_params_dict['name']}'")

        audio_config_tts = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        response = tts_client.synthesize_speech(
            request={"input": synthesis_input, "voice": voice_params, "audio_config": audio_config_tts}
        )

        # Use TEMP_TTS_PREVIEWS_DIR_NAME from settings
        temp_tts_dir_name = getattr(settings, 'TEMP_TTS_PREVIEWS_DIR_NAME', 'temp_tts_previews') # Default if not set
        temp_tts_path = os.path.join(settings.MEDIA_ROOT, temp_tts_dir_name)
        os.makedirs(temp_tts_path, exist_ok=True)

        temp_audio_filename = f"preview_{request.user.user_id}_{uuid.uuid4().hex[:8]}.mp3"
        temp_audio_filepath = os.path.join(temp_tts_path, temp_audio_filename)
        
        with open(temp_audio_filepath, "wb") as out:
            out.write(response.audio_content)
        logger.info(f"[TTS PREVIEW] TTS preview audio saved to: {temp_audio_filepath}")

        # Construct URL using TEMP_TTS_PREVIEWS_DIR_NAME from settings
        temp_audio_url = os.path.join(settings.MEDIA_URL, temp_tts_dir_name, temp_audio_filename)
        temp_audio_url = temp_audio_url.replace(os.sep, '/') 
        if not temp_audio_url.startswith('/'): # Ensure it's a root-relative URL if MEDIA_URL is empty or relative
            temp_audio_url = '/' + temp_audio_url
        
        # Cleanup old temporary files (older than 2 hours)
        try:
            for old_file in os.listdir(temp_tts_path):
                old_filepath = os.path.join(temp_tts_path, old_file)
                if os.path.isfile(old_filepath):
                    # Compare file modification time with 2 hours ago
                    file_mod_time_aware = timezone.make_aware(datetime.fromtimestamp(os.path.getmtime(old_filepath)))
                    two_hours_ago = timezone.now() - timezone.timedelta(hours=2)
                    if file_mod_time_aware < two_hours_ago:
                        default_storage.delete(old_filepath) # Use default_storage for consistency if it handles remote storage
                        logger.info(f"[TTS PREVIEW] Deleted old temp file: {old_filepath}")
        except Exception as e_cleanup:
            logger.error(f"[TTS PREVIEW] Error cleaning up old temp TTS files: {e_cleanup}")

        return JsonResponse({
            'status': 'success',
            'audio_url': temp_audio_url,
            'voice_id_used': tts_voice_id_from_request, 
            'filename': temp_audio_filename 
        })

    except Exception as e:
        logger.error(f"[TTS PREVIEW] Unexpected error during TTS preview generation for user {request.user.username}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'An error occurred during TTS generation: {str(e)}'}, status=500)


@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_upload_audiobook(request):
    creator = request.creator
    form_errors = {}
    submitted_values = {} 
    submitted_chapters_for_template = [] 

    if request.method == 'POST':
        submitted_values = request.POST.copy() 

        title = submitted_values.get('title', '').strip()
        author = submitted_values.get('author', '').strip()
        narrator = submitted_values.get('narrator', '').strip()
        language = submitted_values.get('language', '').strip()
        genre = submitted_values.get('genre', '').strip()
        description = submitted_values.get('description', '').strip()
        cover_image_file = request.FILES.get('cover_image')
        pricing_type = submitted_values.get('pricing_type')
        price_str = submitted_values.get('price', '0').strip()

        is_paid = (pricing_type == 'paid')
        price = Decimal('0.00')

        # --- Basic Audiobook Detail Validation ---
        if not title: form_errors['title'] = "Audiobook title is required."
        if not author: form_errors['author'] = "Author name is required."
        if not narrator: form_errors['narrator'] = "Narrator name is required."
        if not genre: form_errors['genre'] = "Genre is required."
        if not language: form_errors['language'] = "Language is required."
        if not description: form_errors['description'] = "Audiobook description is required."

        if not cover_image_file:
            # If editing, this might not be an error if a cover already exists.
            # For new upload, it's an error. Assuming new upload context here.
            form_errors['cover_image'] = "Cover image is required."
        else:
            max_cover_size = 2 * 1024 * 1024 
            allowed_cover_types = ['image/jpeg', 'image/png', 'image/jpg']
            if cover_image_file.size > max_cover_size:
                form_errors['cover_image'] = f"Cover image too large (Max {filesizeformat(max_cover_size)})."
                submitted_values['cover_image_filename'] = f"{cover_image_file.name} (Too large)"
            elif cover_image_file.content_type not in allowed_cover_types:
                form_errors['cover_image'] = "Invalid cover image type (PNG, JPG/JPEG only)."
                submitted_values['cover_image_filename'] = f"{cover_image_file.name} (Invalid type)"
            else:
                submitted_values['cover_image_filename'] = cover_image_file.name
        
        if pricing_type not in ['free', 'paid']:
            form_errors['pricing_type'] = "Invalid pricing type selected."
        elif is_paid:
            if not price_str:
                form_errors['price'] = "Price is required for paid audiobooks."
            else:
                try:
                    price = Decimal(price_str)
                    if price <= Decimal('0.00'): 
                        form_errors['price'] = "Price must be a positive value for paid audiobooks."
                except InvalidOperation:
                    form_errors['price'] = "Invalid price format. Please enter a number."
        # --- End Basic Audiobook Detail Validation ---

        chapters_to_save_data = [] 
        chapter_indices = set()

        for key in request.POST: 
            if key.startswith('chapters[') and '][title]' in key:
                try:
                    index_str = key.split('[')[1].split(']')[0]
                    chapter_indices.add(int(index_str))
                except (IndexError, ValueError):
                    logger.warning(f"Could not parse chapter index from key: {key}")
                    continue
        
        if not chapter_indices:
            form_errors['chapters_general'] = "At least one chapter is required."
        else:
            sorted_indices = sorted(list(chapter_indices))
            for index in sorted_indices:
                chapter_title = submitted_values.get(f'chapters[{index}][title]', '').strip()
                # This is the type selected by the user: 'file' or 'tts' (which covers new and using previewed)
                chapter_input_type_from_toggle = submitted_values.get(f'chapters[{index}][input_type]', 'file') 
                # This hidden input is set by JS to 'file', 'tts' (for new generation), or 'generated_tts' (if preview was confirmed)
                # We should prioritize this hidden input if available, as it's more specific.
                effective_chapter_input_type = submitted_values.get(f'chapters[{index}][input_type_hidden]', chapter_input_type_from_toggle)


                chapter_audio_file_from_form = request.FILES.get(f'chapters[{index}][audio_file]') 
                chapter_text_content_input = submitted_values.get(f'chapters[{index}][text_content]', '').strip()
                chapter_tts_voice_id_from_form = submitted_values.get(f'chapters[{index}][tts_voice]', 'default') 
                generated_tts_audio_url_from_form = submitted_values.get(f'chapters[{index}][generated_tts_audio_url]', '').strip()
                
                try:
                    chapter_order = int(submitted_values.get(f'chapters[{index}][order]', index + 1))
                except ValueError:
                    chapter_order = index + 1 

                # Prepare display name for TTS voice for template repopulation
                tts_voice_display_name = ""
                if chapter_tts_voice_id_from_form and chapter_tts_voice_id_from_form != 'default':
                    # Ensure it's a string before calling replace
                    voice_str_for_display = str(chapter_tts_voice_id_from_form)
                    tts_voice_display_name = capfirst(voice_str_for_display.replace("_narrator", ""))

                current_chapter_errors = {}
                temp_chapter_data_for_repopulation = {
                    'original_index': index, 'title': chapter_title, 'order': chapter_order,
                    'input_type': effective_chapter_input_type, # Use the more specific type for repopulation logic
                    'text_content': chapter_text_content_input,
                    'tts_voice': chapter_tts_voice_id_from_form, 
                    'tts_voice_display_name': tts_voice_display_name, # Add pre-processed name
                    'audio_filename': "No file chosen", 
                    'generated_tts_audio_url': generated_tts_audio_url_from_form, # Store this for repopulation
                    'errors': {}
                }
                if chapter_audio_file_from_form:
                    temp_chapter_data_for_repopulation['audio_filename'] = chapter_audio_file_from_form.name


                if not chapter_title:
                    current_chapter_errors['title'] = "Chapter title is required."
                
                audio_source_valid_for_submission = False
                audio_file_to_process_for_db = None 
                text_content_for_db = None
                is_tts_generated_for_db = False
                final_tts_voice_id_for_db = 'default'

                # Use effective_chapter_input_type for logic
                if effective_chapter_input_type == 'file':
                    if not chapter_audio_file_from_form:
                        current_chapter_errors['audio_file'] = "Audio file is required for this chapter."
                    else:
                        audio_file_to_process_for_db = chapter_audio_file_from_form
                        max_audio_size = 50 * 1024 * 1024 
                        allowed_audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/x-m4a', 'audio/m4a']
                        if chapter_audio_file_from_form.size > max_audio_size:
                            current_chapter_errors['audio_file'] = f"Audio file too large (Max {filesizeformat(max_audio_size)})."
                        if chapter_audio_file_from_form.content_type not in allowed_audio_types:
                            current_chapter_errors['audio_file'] = f"Invalid audio file type. Allowed: MP3, WAV, OGG, M4A."
                        if not current_chapter_errors.get('audio_file'):
                            audio_source_valid_for_submission = True
                
                elif effective_chapter_input_type == 'generated_tts': 
                    if not generated_tts_audio_url_from_form:
                        current_chapter_errors['generated_tts'] = "Confirmed TTS audio URL is missing. Please re-generate and confirm."
                    elif chapter_tts_voice_id_from_form == 'default' or chapter_tts_voice_id_from_form not in TTS_VOICE_MAPPING: # Ensure voice is still valid
                         current_chapter_errors['tts_voice'] = "A valid narrator voice for the confirmed audio is missing."
                    else:
                        audio_file_to_process_for_db = generated_tts_audio_url_from_form 
                        text_content_for_db = chapter_text_content_input 
                        is_tts_generated_for_db = True
                        final_tts_voice_id_for_db = chapter_tts_voice_id_from_form
                        audio_source_valid_for_submission = True
                        # For repopulation, ensure audio_filename shows the generated one
                        if generated_tts_audio_url_from_form:
                             temp_chapter_data_for_repopulation['audio_filename'] = f"Generated: {os.path.basename(generated_tts_audio_url_from_form)}"


                elif effective_chapter_input_type == 'tts': 
                    if not chapter_text_content_input:
                        current_chapter_errors['text_content'] = "Text content is required for TTS generation."
                    elif len(chapter_text_content_input) < 10:
                        current_chapter_errors['text_content'] = "Text content is too short for TTS (min 10 characters)."
                    elif len(chapter_text_content_input) > 20000: 
                        current_chapter_errors['text_content'] = "Text content is too long for direct TTS generation (max 20000 characters)."

                    if chapter_tts_voice_id_from_form == 'default' or chapter_tts_voice_id_from_form not in TTS_VOICE_MAPPING:
                        current_chapter_errors['tts_voice'] = "Please select a valid narrator voice for TTS."
                    
                    if not google_tts_available:
                        current_chapter_errors['tts_general'] = "Text-to-Speech service is currently unavailable. Please upload an audio file instead."
                    
                    if not current_chapter_errors: 
                        audio_source_valid_for_submission = True 
                        text_content_for_db = chapter_text_content_input
                        is_tts_generated_for_db = True 
                        final_tts_voice_id_for_db = chapter_tts_voice_id_from_form
                else: # Should not happen if JS sets hidden input correctly
                    current_chapter_errors['input_type'] = "Invalid input type for chapter."

                if not audio_source_valid_for_submission and not current_chapter_errors:
                    current_chapter_errors.setdefault('audio_file', "Audio source is missing or invalid for this chapter.")


                if current_chapter_errors:
                    form_errors[f'chapter_{index}'] = current_chapter_errors
                    temp_chapter_data_for_repopulation['errors'] = current_chapter_errors
                
                submitted_chapters_for_template.append(temp_chapter_data_for_repopulation)
                
                if not current_chapter_errors:
                    chapters_to_save_data.append({
                        'title': chapter_title, 'order': chapter_order,
                        'input_type_final': effective_chapter_input_type, # Store the effective type
                        'audio_file_obj_or_temp_url': audio_file_to_process_for_db,
                        'text_content_for_tts': text_content_for_db,
                        'is_tts_final': is_tts_generated_for_db, 
                        'final_tts_voice_id': final_tts_voice_id_for_db,
                    })
            
            if form_errors and any(key.startswith('chapter_') for key in form_errors):
                form_errors.setdefault('chapters_general', "Please correct errors in the chapter details below.")

        if not form_errors:
            try:
                with transaction.atomic():
                    new_audiobook = Audiobook(
                        creator=creator, title=title, author=author, narrator=narrator, language=language,
                        genre=genre, description=description, cover_image=cover_image_file,
                        is_paid=is_paid, price=price if is_paid else Decimal('0.00'),
                        status='PUBLISHED' 
                    )
                    new_audiobook.full_clean() 
                    new_audiobook.save() 

                    chapters_to_save_data.sort(key=lambda c: c['order'])

                    for chapter_data_to_save in chapters_to_save_data:
                        final_audio_file_path_for_chapter_model = None 
                        db_text_content = chapter_data_to_save['text_content_for_tts']
                        db_is_tts_generated = chapter_data_to_save['is_tts_final']
                        db_tts_voice_id = chapter_data_to_save['final_tts_voice_id']

                        chapter_input_source_type = chapter_data_to_save['input_type_final']

                        if chapter_input_source_type == 'file':
                            final_audio_file_path_for_chapter_model = chapter_data_to_save['audio_file_obj_or_temp_url']
                            db_is_tts_generated = False 
                            db_tts_voice_id = 'default'
                            db_text_content = None 

                        elif chapter_input_source_type == 'generated_tts': # Audio was previewed and confirmed
                            temp_audio_url = chapter_data_to_save['audio_file_obj_or_temp_url'] 
                            relative_path_to_media_root = temp_audio_url.replace(settings.MEDIA_URL, '', 1)
                            full_temp_file_path = os.path.join(settings.MEDIA_ROOT, relative_path_to_media_root)

                            if default_storage.exists(full_temp_file_path):
                                chapter_audio_dir = os.path.join('chapters_audio', new_audiobook.slug)
                                new_filename = f"ch_{chapter_data_to_save['order']}_{slugify(chapter_data_to_save['title'])}_tts_{uuid.uuid4().hex[:6]}.mp3"
                                new_chapter_audio_path_rel_to_media_root = os.path.join(chapter_audio_dir, new_filename)
                                
                                with open(full_temp_file_path, 'rb') as temp_file_content_stream:
                                    saved_file_name = default_storage.save(new_chapter_audio_path_rel_to_media_root, ContentFile(temp_file_content_stream.read()))
                                final_audio_file_path_for_chapter_model = saved_file_name
                                
                                try:
                                    default_storage.delete(full_temp_file_path) 
                                    logger.info(f"Moved and deleted temporary TTS preview file: {full_temp_file_path} to {saved_file_name}")
                                except Exception as del_e:
                                    logger.warning(f"Could not delete temporary TTS preview file {full_temp_file_path} after moving: {del_e}")
                            else:
                                logger.error(f"Confirmed TTS file not found at expected path: {full_temp_file_path} (URL was {temp_audio_url}). Skipping audio for chapter '{chapter_data_to_save['title']}'.")
                                form_errors.setdefault('chapters_general', f"Audio for chapter '{chapter_data_to_save['title']}' (from preview) was missing. Please try generating it again.")
                                raise ValidationError(f"Missing confirmed TTS file for chapter '{chapter_data_to_save['title']}'.")
                        
                        elif chapter_input_source_type == 'tts': # Generate TTS now, on submit
                            if not google_tts_available:
                                form_errors.setdefault('chapters_general', "TTS service became unavailable during submission.")
                                raise ValidationError("TTS service unavailable.")

                            logger.info(f"Generating TTS for chapter (on submit): {chapter_data_to_save['title']}, voice: {db_tts_voice_id}")
                            tts_client = texttospeech.TextToSpeechClient()
                            synthesis_input = texttospeech.SynthesisInput(text=db_text_content)
                            
                            selected_voice_params = TTS_VOICE_MAPPING.get(db_tts_voice_id, DEFAULT_TTS_VOICE_PARAMS)

                            voice_params_gcp = texttospeech.VoiceSelectionParams(
                                language_code=selected_voice_params['language_code'],
                                name=selected_voice_params['name']
                            )
                            audio_config_gcp = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
                            
                            tts_response = tts_client.synthesize_speech(
                                request={"input": synthesis_input, "voice": voice_params_gcp, "audio_config": audio_config_gcp}
                            )
                            
                            tts_audio_dir = os.path.join('chapters_audio', new_audiobook.slug)
                            tts_audio_filename_final = f"ch_{chapter_data_to_save['order']}_{slugify(chapter_data_to_save['title'])}_tts_{uuid.uuid4().hex[:6]}.mp3"
                            tts_audio_path_rel_to_media = os.path.join(tts_audio_dir, tts_audio_filename_final)

                            saved_file_name = default_storage.save(tts_audio_path_rel_to_media, ContentFile(tts_response.audio_content))
                            final_audio_file_path_for_chapter_model = saved_file_name 
                            logger.info(f"TTS audio generated and saved as {saved_file_name} for chapter '{chapter_data_to_save['title']}' during submission.")
                            # db_is_tts_generated, db_tts_voice_id, db_text_content are already set correctly for this path

                        else:
                            logger.error(f"Unhandled audio source type '{chapter_input_source_type}' for chapter '{chapter_data_to_save['title']}'. Skipping chapter.")
                            form_errors.setdefault('chapters_general', f"Could not determine audio source for chapter '{chapter_data_to_save['title']}'.")
                            raise ValidationError(f"Audio source undetermined for chapter '{chapter_data_to_save['title']}'.")

                        Chapter.objects.create(
                            audiobook=new_audiobook,
                            chapter_name=chapter_data_to_save['title'],
                            chapter_order=chapter_data_to_save['order'],
                            audio_file=final_audio_file_path_for_chapter_model,
                            text_content=db_text_content, 
                            is_tts_generated=db_is_tts_generated,
                            tts_voice_id=db_tts_voice_id if db_is_tts_generated else 'default'
                        )
                        
                    messages.success(request, f"Audiobook '{new_audiobook.title}' and its chapters uploaded successfully!")
                    return redirect('AudioXApp:creator_my_audiobooks')

            except ValidationError as e: 
                logger.error(f"Validation Error during audiobook/chapter save: {e.message_dict if hasattr(e, 'message_dict') else e}", exc_info=True)
                if hasattr(e, 'message_dict'):
                    for field, error_list in e.message_dict.items():
                        if field == '__all__' or hasattr(Audiobook, field): # Check if error is for Audiobook model
                             form_errors[field if field != '__all__' else 'general_error'] = " ".join(error_list)
                        else: 
                            form_errors.setdefault('chapters_general', "An error occurred with one of the chapters. " + " ".join(error_list))
                else: 
                    if "Missing confirmed TTS file for chapter" in str(e) or "Audio source undetermined for chapter" in str(e):
                         form_errors.setdefault('chapters_general', str(e))
                    else:
                        form_errors['general_error'] = str(e)
                messages.error(request, "Please correct the validation errors found.")
            except IntegrityError as e: # Catch database integrity errors (e.g. unique constraint)
                logger.error(f"Integrity Error during audiobook/chapter save: {e}", exc_info=True)
                # Check if the error is related to the slug (common unique constraint)
                if 'audiobook_slug' in str(e).lower() or ('audiobook' in str(e).lower() and 'slug' in str(e).lower()):
                     form_errors['title'] = "This title (or its generated slug) already exists. Please choose a different title."
                     messages.error(request, "An audiobook with a similar title already exists. Please choose a different title.")
                else:
                    messages.error(request, f"Database Error: Could not save audiobook. It might conflict with existing data.")
                    form_errors['general_error'] = "A database error occurred. Please check for duplicate titles or ensure slug uniqueness."
            except Exception as e: # Catch any other unexpected errors
                logger.error(f"Unexpected error during audiobook upload: {e}", exc_info=True)
                messages.error(request, f"An unexpected error occurred during upload: {str(e)[:200]}") 
                form_errors['general_error'] = f"An unexpected server error occurred: {str(e)[:100]}"
        else: 
            messages.error(request, "Please correct the errors highlighted below.")
        
        # This ensures submitted_chapters_for_template is available when re-rendering with errors
        submitted_values['chapters'] = submitted_chapters_for_template


    context = _get_full_context(request)
    context.update({
        'creator': creator,
        'available_balance': creator.available_balance,
        'form_errors': form_errors,
        'submitted_values': submitted_values, 
        'google_tts_available': google_tts_available,
        'TTS_VOICE_CHOICES_FOR_JS': [{'id': k, 'name': f"{v['name']} ({v['language_code']})"} for k,v in TTS_VOICE_MAPPING.items()]
    })
    return render(request, 'creator/creator_upload_audiobooks.html', context)


@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_manage_upload_detail_view(request, audiobook_slug):
    creator = request.creator
    audiobook = get_object_or_404(Audiobook.objects.prefetch_related('chapters'), slug=audiobook_slug, creator=creator)

    view_form_errors = {}
    view_chapter_form_errors = defaultdict(dict) 

    view_submitted_values = {
        'title': audiobook.title or '',
        'author': audiobook.author or '',
        'narrator': audiobook.narrator or '',
        'genre': audiobook.genre or '',
        'language': audiobook.language or '',
        'description': audiobook.description or '',
        'status_only_select': audiobook.status or '',
        'current_cover_image_url': audiobook.cover_image.url if audiobook.cover_image else None,
        'new_chapter_title': '',
        'new_chapter_input_type_hidden': 'file',
        'new_chapter_generated_tts_url': '',
        'new_chapter_text_content': '',
        'new_chapter_tts_voice': 'default',
        'new_chapter_tts_voice_display_name': '',
    }

    creator_allowed_statuses_for_toggle = [
        ('PUBLISHED', 'Published (Visible to users)'),
        ('INACTIVE', 'Inactive (Hidden from public, earnings paused)'),
    ]
    can_creator_change_status = audiobook.status not in ['REJECTED', 'PAUSED_BY_ADMIN']

    if request.method == 'POST':
        post_data = request.POST.copy()
        for key in post_data:
            view_submitted_values[key] = post_data.get(key)

        action = view_submitted_values.get('action')
        logger.info(f"POST Action: {action} for audiobook '{audiobook.slug}' by user '{request.user.username}'")

        # --- Action: Edit Audiobook Details ---
        if action == 'edit_audiobook_details':
            logger.info(f"Processing 'edit_audiobook_details' for audiobook '{audiobook.slug}'")
            title_from_post = view_submitted_values.get('title', '').strip()
            author_from_post = view_submitted_values.get('author', '').strip()
            narrator_from_post = view_submitted_values.get('narrator', '').strip()
            genre_from_post = view_submitted_values.get('genre', '').strip()
            language_from_post = view_submitted_values.get('language', '').strip()
            description_from_post = view_submitted_values.get('description', '').strip()
            cover_image_file = request.FILES.get('cover_image')

            current_action_form_errors = {}
            if not title_from_post: current_action_form_errors['title'] = "Audiobook title is required."
            if not author_from_post: current_action_form_errors['author'] = "Author name is required."
            if not narrator_from_post: current_action_form_errors['narrator'] = "Narrator name is required."
            if not genre_from_post: current_action_form_errors['genre'] = "Genre is required."
            if not language_from_post: current_action_form_errors['language'] = "Language is required."
            if not description_from_post: current_action_form_errors['description'] = "Description is required."


            if cover_image_file:
                max_cover_size = 2 * 1024 * 1024
                allowed_cover_types = ['image/jpeg', 'image/png', 'image/jpg']
                if cover_image_file.size > max_cover_size:
                    current_action_form_errors['cover_image'] = f"Cover image too large (Max {filesizeformat(max_cover_size)})."
                if cover_image_file.content_type not in allowed_cover_types:
                    current_action_form_errors['cover_image'] = "Invalid cover image type (PNG, JPG/JPEG only)."

            if not current_action_form_errors:
                try:
                    with transaction.atomic():
                        audiobook_to_update = Audiobook.objects.select_for_update().get(pk=audiobook.pk)
                        audiobook_to_update.title = title_from_post
                        audiobook_to_update.author = author_from_post
                        audiobook_to_update.narrator = narrator_from_post
                        audiobook_to_update.genre = genre_from_post
                        audiobook_to_update.language = language_from_post
                        audiobook_to_update.description = description_from_post
                        
                        update_fields = ['title', 'author', 'narrator', 'genre', 'language', 'description', 'updated_at']

                        if cover_image_file:
                            if audiobook_to_update.cover_image and hasattr(audiobook_to_update.cover_image, 'name') and audiobook_to_update.cover_image.name:
                                if default_storage.exists(audiobook_to_update.cover_image.name):
                                    default_storage.delete(audiobook_to_update.cover_image.name)
                            audiobook_to_update.cover_image = cover_image_file
                            update_fields.append('cover_image')
                        
                        new_slug_candidate = slugify(title_from_post)
                        if audiobook_to_update.slug != new_slug_candidate:
                            temp_slug = new_slug_candidate
                            counter = 1
                            while Audiobook.objects.filter(slug=temp_slug).exclude(pk=audiobook_to_update.pk).exists():
                                temp_slug = f"{new_slug_candidate}-{counter}"
                                counter += 1
                            audiobook_to_update.slug = temp_slug
                            update_fields.append('slug')
                        
                        audiobook_to_update.updated_at = timezone.now()
                        audiobook_to_update.save(update_fields=list(set(update_fields)))
                        messages.success(request, f"Audiobook '{audiobook_to_update.title}' details updated successfully.")
                        return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook_to_update.slug)
                except Exception as e:
                    logger.error(f"Error saving audiobook details for '{audiobook.slug}': {e}", exc_info=True)
                    messages.error(request, f"An error occurred while saving details: {e}")
                    current_action_form_errors['general_error'] = f"An unexpected error occurred: {e}"
            
            if current_action_form_errors:
                view_form_errors.update(current_action_form_errors)
                messages.error(request, "Please correct the errors in the audiobook details.")

        # --- Action: Add Chapter ---
        elif action == 'add_chapter':
            logger.info(f"Processing 'add_chapter' for audiobook '{audiobook.slug}'")
            new_chapter_title_val = view_submitted_values.get('new_chapter_title', '').strip()
            new_chapter_effective_input_type = view_submitted_values.get('new_chapter_input_type_hidden', 'file')
            new_chapter_audio_file = request.FILES.get('new_chapter_audio')
            new_chapter_text_content_val = view_submitted_values.get('new_chapter_text_content', '').strip()
            new_chapter_tts_voice_id_val = view_submitted_values.get('new_chapter_tts_voice', 'default')
            new_chapter_generated_tts_url_val = view_submitted_values.get('new_chapter_generated_tts_url', '').strip()

            add_chapter_errors_local = {}
            if not new_chapter_title_val:
                add_chapter_errors_local['new_chapter_title'] = "New chapter title is required."

            final_audio_file_for_db = None
            is_tts_generated_for_db = False
            tts_voice_id_for_db = 'default'
            text_content_for_db = None

            if new_chapter_effective_input_type == 'file':
                if not new_chapter_audio_file:
                    add_chapter_errors_local['new_chapter_audio'] = "Audio file is required for 'Upload File' option."
                else:
                    max_audio_size = 50 * 1024 * 1024 
                    allowed_audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/x-m4a', 'audio/m4a']
                    if new_chapter_audio_file.size > max_audio_size:
                        add_chapter_errors_local['new_chapter_audio'] = f"Audio file too large (Max {filesizeformat(max_audio_size)})."
                    elif new_chapter_audio_file.content_type not in allowed_audio_types:
                        add_chapter_errors_local['new_chapter_audio'] = "Invalid audio file type (MP3, WAV, OGG, M4A)."
                    
                    if not add_chapter_errors_local.get('new_chapter_audio'):
                        final_audio_file_for_db = new_chapter_audio_file
            
            elif new_chapter_effective_input_type == 'generated_tts':
                if not new_chapter_generated_tts_url_val:
                    add_chapter_errors_local['new_chapter_generated_tts_url'] = "Confirmed TTS audio URL is missing."
                elif new_chapter_tts_voice_id_val == 'default' or new_chapter_tts_voice_id_val not in TTS_VOICE_MAPPING:
                     add_chapter_errors_local['new_chapter_tts_voice'] = "A valid narrator voice for the confirmed audio is missing."
                else:
                    try:
                        temp_preview_dir = getattr(settings, 'TEMP_TTS_PREVIEWS_DIR_NAME', 'temp_tts_previews')
                        temp_preview_url_segment = f"{settings.MEDIA_URL}{temp_preview_dir}/"
                        if not new_chapter_generated_tts_url_val.startswith(temp_preview_url_segment):
                            logger.error(f"Invalid 'generated_tts' URL for new chapter: {new_chapter_generated_tts_url_val}. Does not match temp preview path {temp_preview_url_segment}.")
                            add_chapter_errors_local['new_chapter_tts_general'] = "Invalid source for confirmed TTS audio."
                        else:
                            relative_path_to_media_root = new_chapter_generated_tts_url_val.replace(settings.MEDIA_URL, '', 1).lstrip('/')
                            full_temp_file_path = os.path.join(settings.MEDIA_ROOT, relative_path_to_media_root)

                            if default_storage.exists(full_temp_file_path):
                                chapter_audio_dir = os.path.join('chapters_audio', audiobook.slug)
                                new_filename_base = slugify(new_chapter_title_val) if new_chapter_title_val else "chapter"
                                new_filename = f"ch_new_{new_filename_base}_tts_{uuid.uuid4().hex[:6]}.mp3"
                                new_chapter_audio_path_rel_to_media_root = os.path.join(chapter_audio_dir, new_filename)
                                
                                with default_storage.open(full_temp_file_path, 'rb') as temp_file_content_stream:
                                    saved_file_name = default_storage.save(new_chapter_audio_path_rel_to_media_root, ContentFile(temp_file_content_stream.read()))
                                final_audio_file_for_db = saved_file_name
                                is_tts_generated_for_db = True
                                tts_voice_id_for_db = new_chapter_tts_voice_id_val
                                text_content_for_db = new_chapter_text_content_val 
                                default_storage.delete(full_temp_file_path) 
                                logger.info(f"Moved confirmed TTS preview {full_temp_file_path} to {saved_file_name} for new chapter.")
                            else:
                                add_chapter_errors_local['new_chapter_tts_general'] = "Confirmed TTS audio file not found. Please generate and confirm again."
                                logger.error(f"Confirmed TTS file not found at {full_temp_file_path} for new chapter.")
                    except Exception as e_tts_move:
                        logger.error(f"Error processing confirmed TTS file for new chapter: {e_tts_move}", exc_info=True)
                        add_chapter_errors_local['new_chapter_tts_general'] = "Error processing confirmed TTS audio."
            
            elif new_chapter_effective_input_type == 'tts': 
                if not new_chapter_text_content_val:
                    add_chapter_errors_local['new_chapter_text_content'] = "Text content is required for TTS generation."
                elif len(new_chapter_text_content_val) < 10:
                     add_chapter_errors_local['new_chapter_text_content'] = "Text too short (min 10 chars)."
                elif len(new_chapter_text_content_val) > 20000: 
                     add_chapter_errors_local['new_chapter_text_content'] = "Text too long (max 20000 chars)."
                if new_chapter_tts_voice_id_val == 'default' or new_chapter_tts_voice_id_val not in TTS_VOICE_MAPPING:
                    add_chapter_errors_local['new_chapter_tts_voice'] = "Please select a valid narrator voice."
                if not google_tts_available:
                    add_chapter_errors_local['new_chapter_tts_general'] = "TTS service is unavailable. Cannot generate audio."
                
                if not add_chapter_errors_local: 
                    try:
                        logger.info(f"Generating TTS on submit for new chapter: {new_chapter_title_val}, voice: {new_chapter_tts_voice_id_val}")
                        tts_client = texttospeech.TextToSpeechClient()
                        synthesis_input = texttospeech.SynthesisInput(text=new_chapter_text_content_val)
                        selected_voice_params = TTS_VOICE_MAPPING.get(new_chapter_tts_voice_id_val, DEFAULT_TTS_VOICE_PARAMS)
                        voice_params_gcp = texttospeech.VoiceSelectionParams(
                            language_code=selected_voice_params['language_code'], name=selected_voice_params['name']
                        )
                        audio_config_gcp = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
                        tts_response = tts_client.synthesize_speech(
                            request={"input": synthesis_input, "voice": voice_params_gcp, "audio_config": audio_config_gcp}
                        )
                        
                        tts_audio_dir = os.path.join('chapters_audio', audiobook.slug)
                        new_filename_base = slugify(new_chapter_title_val) if new_chapter_title_val else "chapter"
                        tts_audio_filename_final = f"ch_new_{new_filename_base}_tts_{uuid.uuid4().hex[:6]}.mp3"
                        tts_audio_path_rel_to_media = os.path.join(tts_audio_dir, tts_audio_filename_final)
                        saved_file_name = default_storage.save(tts_audio_path_rel_to_media, ContentFile(tts_response.audio_content))
                        
                        final_audio_file_for_db = saved_file_name
                        is_tts_generated_for_db = True
                        tts_voice_id_for_db = new_chapter_tts_voice_id_val
                        text_content_for_db = new_chapter_text_content_val
                        logger.info(f"TTS audio generated and saved as {saved_file_name} for new chapter '{new_chapter_title_val}' during submission.")
                    except Exception as e_tts_gen:
                        logger.error(f"Error generating TTS on submit for new chapter: {e_tts_gen}", exc_info=True)
                        add_chapter_errors_local['new_chapter_tts_general'] = f"TTS generation failed: {e_tts_gen}"
            else:
                 add_chapter_errors_local['new_chapter_input_type'] = "Invalid chapter input type specified."


            if not add_chapter_errors_local:
                try:
                    with transaction.atomic():
                        audiobook_for_chapter = Audiobook.objects.select_for_update().get(pk=audiobook.pk)
                        max_order = audiobook_for_chapter.chapters.aggregate(Max('chapter_order'))['chapter_order__max'] or 0
                        
                        Chapter.objects.create(
                            audiobook=audiobook_for_chapter,
                            chapter_name=new_chapter_title_val,
                            audio_file=final_audio_file_for_db,
                            chapter_order=max_order + 1,
                            is_tts_generated=is_tts_generated_for_db,
                            tts_voice_id=tts_voice_id_for_db,
                            text_content=text_content_for_db
                        )
                        messages.success(request, f"Chapter '{new_chapter_title_val}' added successfully.")
                        return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook.slug)
                except ValidationError as ve:
                    logger.error(f"Validation error saving new chapter: {ve}", exc_info=True)
                    add_chapter_errors_local['add_chapter_general'] = str(ve.message_dict if hasattr(ve, 'message_dict') else ve)
                except Exception as e:
                    logger.error(f"Error saving new chapter: {e}", exc_info=True)
                    add_chapter_errors_local['add_chapter_general'] = f"Unexpected error: {e}"
            
            if add_chapter_errors_local:
                view_form_errors['add_chapter_errors'] = add_chapter_errors_local
                view_form_errors['add_chapter_active_with_errors'] = True 
                messages.error(request, "Please correct errors in the new chapter form.")

        # --- Action: Edit Chapter ---
        elif action and action.startswith('edit_chapter_'):
            chapter_id_str = action.split('edit_chapter_')[-1]
            logger.info(f"Processing 'edit_chapter_{chapter_id_str}' for audiobook '{audiobook.slug}'")
            try:
                chapter_to_edit = Chapter.objects.get(pk=chapter_id_str, audiobook=audiobook)
                
                edit_chapter_title = view_submitted_values.get(f'chapter_title_{chapter_id_str}', '').strip()
                edit_effective_input_type = view_submitted_values.get(f'edit_chapter_input_type_hidden_{chapter_id_str}', 'file')
                edit_audio_file = request.FILES.get(f'chapter_audio_{chapter_id_str}')
                edit_text_content = view_submitted_values.get(f'chapter_text_content_{chapter_id_str}', '').strip()
                edit_tts_voice_id = view_submitted_values.get(f'chapter_tts_voice_{chapter_id_str}', 'default')
                edit_generated_tts_url = view_submitted_values.get(f'edit_chapter_generated_tts_url_{chapter_id_str}', '').strip()

                current_edit_errors_local = {}
                if not edit_chapter_title:
                    current_edit_errors_local['title'] = "Chapter title is required."

                update_audio_file_path = chapter_to_edit.audio_file.name if chapter_to_edit.audio_file else None
                update_is_tts = chapter_to_edit.is_tts_generated
                update_tts_voice = chapter_to_edit.tts_voice_id
                update_text_content = chapter_to_edit.text_content
                made_audio_change = False

                if edit_effective_input_type == 'file':
                    if edit_audio_file: 
                        max_audio_size = 50 * 1024 * 1024
                        allowed_audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/x-m4a', 'audio/m4a']
                        if edit_audio_file.size > max_audio_size:
                             current_edit_errors_local['audio'] = f"Audio file too large (Max {filesizeformat(max_audio_size)})."
                        elif edit_audio_file.content_type not in allowed_audio_types:
                             current_edit_errors_local['audio'] = "Invalid audio file type."
                        else:
                            if chapter_to_edit.audio_file and chapter_to_edit.audio_file.name and default_storage.exists(chapter_to_edit.audio_file.name):
                                default_storage.delete(chapter_to_edit.audio_file.name)
                            update_audio_file_path = edit_audio_file
                            update_is_tts = False
                            update_tts_voice = 'default'
                            update_text_content = None 
                            made_audio_change = True
                    elif chapter_to_edit.is_tts_generated: 
                        if chapter_to_edit.audio_file and chapter_to_edit.audio_file.name and default_storage.exists(chapter_to_edit.audio_file.name):
                            default_storage.delete(chapter_to_edit.audio_file.name)
                        update_audio_file_path = None
                        update_is_tts = False
                        update_tts_voice = 'default'
                        update_text_content = None
                        made_audio_change = True


                elif edit_effective_input_type == 'generated_tts':
                    if not edit_generated_tts_url:
                         current_edit_errors_local['generated_tts'] = "Confirmed TTS audio URL is missing."
                    elif edit_tts_voice_id == 'default' or edit_tts_voice_id not in TTS_VOICE_MAPPING:
                         current_edit_errors_local['voice'] = "A valid narrator voice for the confirmed audio is missing."
                    else:
                        is_new_temp_preview = False
                        temp_preview_dir = getattr(settings, 'TEMP_TTS_PREVIEWS_DIR_NAME', 'temp_tts_previews')
                        temp_preview_url_segment = f"{settings.MEDIA_URL}{temp_preview_dir}/"
                        
                        if edit_generated_tts_url.startswith(temp_preview_url_segment):
                            is_new_temp_preview = True
                        
                        current_chapter_audio_url = None
                        if chapter_to_edit.audio_file and chapter_to_edit.audio_file.name and default_storage.exists(chapter_to_edit.audio_file.name):
                            try:
                                current_chapter_audio_url = chapter_to_edit.audio_file.url
                            except Exception: # Handle cases where URL might not be generatable
                                logger.warning(f"Could not get URL for existing audio file of chapter {chapter_id_str}")
                        
                        if is_new_temp_preview and edit_generated_tts_url != current_chapter_audio_url:
                            logger.info(f"Processing new temporary TTS preview URL for chapter {chapter_id_str}: {edit_generated_tts_url}")
                            try:
                                relative_path_to_media_root = edit_generated_tts_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
                                full_temp_file_path = os.path.join(settings.MEDIA_ROOT, relative_path_to_media_root)

                                # Security check: Ensure the path is within the expected temp directory
                                expected_temp_dir_abs = os.path.abspath(os.path.join(settings.MEDIA_ROOT, temp_preview_dir))
                                if not os.path.abspath(full_temp_file_path).startswith(expected_temp_dir_abs):
                                    logger.error(f"Path traversal attempt or invalid temp path for chapter {chapter_id_str}: {full_temp_file_path}")
                                    raise FileNotFoundError("Path is not a valid temporary preview path.")

                                if default_storage.exists(full_temp_file_path):
                                    if chapter_to_edit.audio_file and chapter_to_edit.audio_file.name and default_storage.exists(chapter_to_edit.audio_file.name):
                                        default_storage.delete(chapter_to_edit.audio_file.name)
                                    
                                    chapter_audio_dir = os.path.join('chapters_audio', audiobook.slug)
                                    new_filename_base = slugify(edit_chapter_title) if edit_chapter_title else f"chapter-{chapter_to_edit.chapter_order}"
                                    new_filename = f"ch_{chapter_to_edit.chapter_order}_{new_filename_base}_tts_{uuid.uuid4().hex[:6]}.mp3"
                                    new_path_rel_media = os.path.join(chapter_audio_dir, new_filename)
                                    
                                    with default_storage.open(full_temp_file_path, 'rb') as temp_f:
                                        saved_name = default_storage.save(new_path_rel_media, ContentFile(temp_f.read()))
                                    
                                    update_audio_file_path = saved_name
                                    update_is_tts = True
                                    update_tts_voice = edit_tts_voice_id
                                    update_text_content = edit_text_content 
                                    made_audio_change = True
                                    default_storage.delete(full_temp_file_path)
                                else:
                                     current_edit_errors_local['general'] = "Confirmed TTS audio file (new preview) not found. Please regenerate."
                            except FileNotFoundError as fnf_err:
                                logger.error(f"FileNotFoundError while processing new TTS preview for chapter {chapter_id_str}: {fnf_err}", exc_info=True)
                                current_edit_errors_local['general'] = "Error accessing temporary TTS audio file."
                            except Exception as e_move_edit:
                                logger.error(f"Error processing new confirmed TTS preview for chapter {chapter_id_str}: {e_move_edit}", exc_info=True)
                                current_edit_errors_local['general'] = f"Error processing confirmed TTS audio: {e_move_edit}"
                        elif edit_generated_tts_url == current_chapter_audio_url: 
                            logger.info(f"TTS URL for chapter {chapter_id_str} is existing. Audio file unchanged. Checking text/voice.")
                            if chapter_to_edit.text_content != edit_text_content or chapter_to_edit.tts_voice_id != edit_tts_voice_id:
                                update_text_content = edit_text_content
                                update_tts_voice = edit_tts_voice_id
                                update_is_tts = True 
                                made_audio_change = True 
                        else: 
                             logger.warning(f"Ambiguous 'generated_tts' URL for chapter {chapter_id_str}: {edit_generated_tts_url}. Current: {current_chapter_audio_url}. This URL is not a recognized temporary preview and does not match the current audio. If you intended to use a new preview, please regenerate and confirm. If you intended to keep existing audio, ensure the URL matches or switch to 'file' mode if the audio was not originally TTS.")
                             # If the URL is different and not a temp preview, it's ambiguous.
                             # We will only update text/voice if they changed, assuming the user might have manually pasted a URL.
                             # The audio file itself won't be changed unless it was a temp preview.
                             if chapter_to_edit.text_content != edit_text_content or chapter_to_edit.tts_voice_id != edit_tts_voice_id:
                                update_text_content = edit_text_content
                                update_tts_voice = edit_tts_voice_id
                                update_is_tts = True # Assume it's still meant to be TTS if voice/text changed
                                made_audio_change = True


                elif edit_effective_input_type == 'tts': 
                    if not edit_text_content:
                         current_edit_errors_local['text'] = "Text content is required for TTS."
                    elif len(edit_text_content) < 10: current_edit_errors_local['text'] = "Text too short (min 10 chars)."
                    elif len(edit_text_content) > 20000: current_edit_errors_local['text'] = "Text too long (max 20000 chars)."

                    if edit_tts_voice_id == 'default' or edit_tts_voice_id not in TTS_VOICE_MAPPING:
                         current_edit_errors_local['voice'] = "Please select a valid narrator voice."
                    if not google_tts_available:
                         current_edit_errors_local['general'] = "TTS service unavailable."

                    if not current_edit_errors_local:
                        try:
                            logger.info(f"Generating TTS on submit for edited chapter: {edit_chapter_title}, voice: {edit_tts_voice_id}")
                            tts_client = texttospeech.TextToSpeechClient()
                            synthesis_input = texttospeech.SynthesisInput(text=edit_text_content)
                            selected_voice_params = TTS_VOICE_MAPPING.get(edit_tts_voice_id, DEFAULT_TTS_VOICE_PARAMS)
                            voice_params_gcp = texttospeech.VoiceSelectionParams(language_code=selected_voice_params['language_code'], name=selected_voice_params['name'])
                            audio_config_gcp = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
                            tts_response = tts_client.synthesize_speech(request={"input": synthesis_input, "voice": voice_params_gcp, "audio_config": audio_config_gcp})
                            
                            if chapter_to_edit.audio_file and chapter_to_edit.audio_file.name and default_storage.exists(chapter_to_edit.audio_file.name):
                                default_storage.delete(chapter_to_edit.audio_file.name)

                            tts_audio_dir = os.path.join('chapters_audio', audiobook.slug)
                            new_filename_base = slugify(edit_chapter_title) if edit_chapter_title else f"chapter-{chapter_to_edit.chapter_order}"
                            tts_filename = f"ch_{chapter_to_edit.chapter_order}_{new_filename_base}_tts_{uuid.uuid4().hex[:6]}.mp3"
                            tts_path_rel_media = os.path.join(tts_audio_dir, tts_filename)
                            saved_name = default_storage.save(tts_path_rel_media, ContentFile(tts_response.audio_content))

                            update_audio_file_path = saved_name
                            update_is_tts = True
                            update_tts_voice = edit_tts_voice_id
                            update_text_content = edit_text_content
                            made_audio_change = True
                        except Exception as e_gen_edit:
                             current_edit_errors_local['general'] = f"TTS generation failed: {e_gen_edit}"
                
                if not current_edit_errors_local:
                    with transaction.atomic():
                        chapter_to_edit_locked = Chapter.objects.select_for_update().get(pk=chapter_to_edit.pk)
                        chapter_to_edit_locked.chapter_name = edit_chapter_title
                        if made_audio_change: 
                            chapter_to_edit_locked.audio_file = update_audio_file_path
                            chapter_to_edit_locked.is_tts_generated = update_is_tts
                            chapter_to_edit_locked.tts_voice_id = update_tts_voice
                            chapter_to_edit_locked.text_content = update_text_content
                        
                        chapter_to_edit_locked.save() 
                        messages.success(request, f"Chapter '{edit_chapter_title}' updated successfully.")
                        return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook.slug)
                else:
                    view_chapter_form_errors[f'edit_chapter_{chapter_id_str}'].update(current_edit_errors_local)
                    messages.error(request, f"Could not update chapter '{chapter_to_edit.chapter_name}'. Please correct errors.")

            except Chapter.DoesNotExist:
                messages.error(request, "Chapter not found for editing.")
            except Exception as e_edit_chapter:
                logger.error(f"Error editing chapter {chapter_id_str}: {e_edit_chapter}", exc_info=True)
                messages.error(request, f"An unexpected error occurred while editing chapter: {e_edit_chapter}")
                view_chapter_form_errors[f'edit_chapter_{chapter_id_str}']['general'] = f"Unexpected error: {e_edit_chapter}"


        # --- Action: Delete Chapter ---
        elif action and action.startswith('delete_chapter_'):
            chapter_id_to_delete_str = action.split('delete_chapter_')[-1]
            logger.info(f"Processing 'delete_chapter_{chapter_id_to_delete_str}' for audiobook '{audiobook.slug}'")
            try:
                with transaction.atomic():
                    chapter_to_delete = Chapter.objects.get(pk=chapter_id_to_delete_str, audiobook=audiobook)
                    chapter_name_deleted = chapter_to_delete.chapter_name
                    
                    if chapter_to_delete.audio_file and chapter_to_delete.audio_file.name and default_storage.exists(chapter_to_delete.audio_file.name):
                        default_storage.delete(chapter_to_delete.audio_file.name)
                        logger.info(f"Deleted audio file {chapter_to_delete.audio_file.name} for chapter '{chapter_name_deleted}'.")
                    
                    chapter_to_delete.delete()
                    
                    remaining_chapters = Chapter.objects.filter(audiobook=audiobook).order_by('chapter_order')
                    for i, ch_instance in enumerate(remaining_chapters): # Renamed ch to ch_instance
                        ch_instance.chapter_order = i + 1
                        ch_instance.save(update_fields=['chapter_order'])
                    
                    messages.success(request, f"Chapter '{chapter_name_deleted}' deleted successfully.")
                    return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook.slug)
            except Chapter.DoesNotExist:
                messages.error(request, "Chapter not found for deletion.")
            except Exception as e_delete:
                logger.error(f"Error deleting chapter {chapter_id_to_delete_str}: {e_delete}", exc_info=True)
                messages.error(request, f"An error occurred while deleting chapter: {e_delete}")
                view_form_errors['general_error_chapter'] = f"Error deleting chapter: {e_delete}"


        # --- Action: Update Status Only ---
        elif action == 'update_status_only':
            logger.info(f"Processing 'update_status_only' for audiobook '{audiobook.slug}'")
            new_status = view_submitted_values.get('status_only_select')
            allowed_statuses = [s[0] for s in creator_allowed_statuses_for_toggle]

            if not can_creator_change_status:
                messages.error(request, "You are not allowed to change the status of this audiobook currently.")
            elif new_status not in allowed_statuses:
                view_form_errors['status_update_status'] = "Invalid status selected."
                messages.error(request, "Invalid status selected.")
            elif new_status == audiobook.status:
                messages.info(request, "No change in audiobook status.")
            else:
                try:
                    with transaction.atomic():
                        audiobook_to_update_status = Audiobook.objects.select_for_update().get(pk=audiobook.pk)
                        audiobook_to_update_status.status = new_status
                        audiobook_to_update_status.updated_at = timezone.now()
                        audiobook_to_update_status.save(update_fields=['status', 'updated_at'])
                        messages.success(request, f"Audiobook status updated to '{audiobook_to_update_status.get_status_display()}'.")
                except Exception as e_status:
                    logger.error(f"Error updating status for '{audiobook.slug}': {e_status}", exc_info=True)
                    messages.error(request, f"An error occurred while updating status: {e_status}")
                    view_form_errors['status_update_status'] = f"Error: {e_status}"
        else:
            if action: 
                 logger.warning(f"Unhandled POST action: {action} for audiobook '{audiobook.slug}'")
                 messages.warning(request, f"Unknown action: {action}")

    # --- Prepare context for GET or after POST (if not redirected) ---
    audiobook = Audiobook.objects.prefetch_related('chapters').get(pk=audiobook.pk) 
    db_chapters = audiobook.chapters.order_by('chapter_order')
    chapters_context_list = []

    for chapter_instance in db_chapters:
        chapter_id_str_ctx = str(chapter_instance.chapter_id)
        current_chapter_edit_errors = view_chapter_form_errors.get(f'edit_chapter_{chapter_id_str_ctx}', {})
        
        tts_voice_display_name_existing = ""
        if chapter_instance.is_tts_generated and chapter_instance.tts_voice_id and chapter_instance.tts_voice_id != 'default':
            voice_str_existing = str(chapter_instance.tts_voice_id)
            tts_voice_display_name_existing = capfirst(voice_str_existing.replace("_narrator", ""))

        input_type_for_template = 'file' 
        if chapter_instance.is_tts_generated:
            input_type_for_template = 'generated_tts' if chapter_instance.audio_file and chapter_instance.audio_file.name and default_storage.exists(chapter_instance.audio_file.name) else 'tts'
        
        chapter_file_size_display = None
        existing_audio_file_url = None
        if chapter_instance.audio_file and hasattr(chapter_instance.audio_file, 'name') and chapter_instance.audio_file.name:
            try:
                if default_storage.exists(chapter_instance.audio_file.name):
                    chapter_file_size_display = filesizeformat(chapter_instance.audio_file.size)
                    existing_audio_file_url = chapter_instance.audio_file.url
                else:
                    logger.warning(f"Audio file for chapter '{chapter_instance.chapter_name}' (ID: {chapter_instance.pk}) not found at path: {chapter_instance.audio_file.name}. Size and URL will not be displayed accurately.")
            except Exception as e_file_details: 
                logger.warning(f"Could not get details for chapter '{chapter_instance.chapter_name}' audio file {chapter_instance.audio_file.name}: {e_file_details}")

        chapters_context_list.append({
            'instance': chapter_instance,
            'tts_voice_display_name': tts_voice_display_name_existing,
            'errors': current_chapter_edit_errors, 
            'input_type_for_template': input_type_for_template,
            'file_size_display': chapter_file_size_display,
            'existing_audio_file_url': existing_audio_file_url
        })

    add_chapter_specific_errors = view_form_errors.get('add_chapter_errors', {}) 
    if any(k.startswith('new_') or k == 'add_chapter_general' for k in add_chapter_specific_errors): 
        view_form_errors['add_chapter_active_with_errors'] = True 

    if view_form_errors.get('add_chapter_active_with_errors') and view_submitted_values.get('new_chapter_tts_voice'):
        raw_new_voice = view_submitted_values.get('new_chapter_tts_voice')
        if raw_new_voice and raw_new_voice != 'default':
            view_submitted_values['new_chapter_tts_voice_display_name'] = capfirst(str(raw_new_voice).replace("_narrator", ""))
        else:
            view_submitted_values['new_chapter_tts_voice_display_name'] = ""

    django_messages_list = []
    for msg in get_messages(request):
        django_messages_list.append({'message': str(msg), 'tags': msg.tags})

    final_context = _get_full_context(request)
    
    final_context.pop('form_errors', None)
    final_context.pop('submitted_values', None)
    
    final_context.update({
        'audiobook': audiobook,
        'chapters_context_list': chapters_context_list,
        'form_errors': view_form_errors, 
        'submitted_values': view_submitted_values, 
        'creator_allowed_status_choices_for_toggle': creator_allowed_statuses_for_toggle,
        'can_creator_change_status': can_creator_change_status,
        'django_messages_json': json.dumps(django_messages_list),
        'google_tts_available': google_tts_available,
        'TTS_VOICE_CHOICES_FOR_JS': Chapter.TTS_VOICE_CHOICES, 
        'creator': creator,
        'available_balance': creator.available_balance
    })
    
    logger.debug(f"Rendering manage_upload_detail. Context form_errors: {final_context.get('form_errors')}")
    logger.debug(f"Context submitted_values: {final_context.get('submitted_values')}")

    return render(request, 'creator/creator_manage_uploads.html', final_context)

@creator_required
def creator_my_earnings_view(request):
    creator = request.creator
    context = _get_full_context(request)

    try:
        creator = Creator.objects.get(pk=creator.pk)
    except Creator.DoesNotExist:
        messages.error(request, "Creator profile not found.")
        return redirect('AudioXApp:home')

    context['creator'] = creator
    context['available_balance'] = creator.available_balance
    now = timezone.now()

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

    overall_sales_earnings_query = CreatorEarning.objects.filter(
        creator=creator,
        earning_type='sale'
    ).select_related('purchase')

    if global_filter_start_date:
        overall_sales_earnings_query = overall_sales_earnings_query.filter(transaction_date__gte=global_filter_start_date)
    if global_filter_end_date:
        overall_sales_earnings_query = overall_sales_earnings_query.filter(transaction_date__lte=global_filter_end_date)

    overall_total_gross_earnings_from_sales_GLOBAL = Decimal('0.00')
    overall_total_net_earnings_from_sales_GLOBAL = Decimal('0.00')
    overall_platform_commission_from_sales_GLOBAL = Decimal('0.00')

    for earning in overall_sales_earnings_query:
        if earning.purchase:
            overall_total_gross_earnings_from_sales_GLOBAL += earning.purchase.amount_paid
            overall_total_net_earnings_from_sales_GLOBAL += earning.amount_earned
            overall_platform_commission_from_sales_GLOBAL += earning.purchase.platform_fee_amount

    view_earnings_query_global = CreatorEarning.objects.filter(
        creator=creator,
        earning_type='view'
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

    aggregated_earnings_for_list = defaultdict(lambda: {
        'title': 'Unknown (Possibly Deleted Audiobook)', 'slug': None, 'cover_image_url': None,
        'is_active': False, 'is_paid': True, 'publish_date': None, 'audiobook_object': None, 'status_display': 'N/A',
        'paid_details': {'sales': 0, 'gross': Decimal('0.00'), 'commission': Decimal('0.00'), 'net': Decimal('0.00')},
        'free_details': {'views': 0, 'earnings': Decimal('0.00')}
    })

    all_creator_audiobooks = Audiobook.objects.filter(creator=creator)
    audiobook_id_to_object_map = {book.audiobook_id: book for book in all_creator_audiobooks}

    for book_id, book_obj in audiobook_id_to_object_map.items():
        agg_data = aggregated_earnings_for_list[book_id]
        is_book_active = book_obj.status == 'PUBLISHED'

        agg_data.update({
            'title': book_obj.title,
            'slug': book_obj.slug,
            'cover_image_url': book_obj.cover_image.url if book_obj.cover_image else None,
            'is_active': is_book_active,
            'is_paid': book_obj.is_paid,
            'publish_date': book_obj.publish_date,
            'audiobook_object': book_obj,
            'status_display': book_obj.get_status_display()
        })

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

        if not book_obj.is_paid:
            views_for_book_query = AudiobookViewLog.objects.filter(audiobook_id=book_id)
            if current_item_filter_start_date:
                views_for_book_query = views_for_book_query.filter(viewed_at__gte=current_item_filter_start_date)
            if current_item_filter_end_date:
                views_for_book_query = views_for_book_query.filter(viewed_at__lte=current_item_filter_end_date)

            period_views = views_for_book_query.count()
            agg_data['free_details']['views'] = period_views
            agg_data['free_details']['earnings'] = Decimal(period_views) * EARNING_PER_VIEW

    deleted_audiobook_earnings_query = CreatorEarning.objects.filter(
        creator=creator, audiobook__isnull=True, earning_type='sale'
    ).select_related('purchase')

    if ab_filter_start_date:
        deleted_audiobook_earnings_query = deleted_audiobook_earnings_query.filter(transaction_date__gte=ab_filter_start_date)
    if ab_filter_end_date:
        deleted_audiobook_earnings_query = deleted_audiobook_earnings_query.filter(transaction_date__lte=ab_filter_end_date)

    for earning in deleted_audiobook_earnings_query:
        unique_deleted_key = f"deleted_{slugify(earning.audiobook_title_at_transaction or 'unknown-title')}_{earning.earning_id}"
        agg_data = aggregated_earnings_for_list[unique_deleted_key]
        agg_data.update({
            'title': earning.audiobook_title_at_transaction or 'Unknown (Deleted Audiobook)',
            'slug': slugify(agg_data['title'] + str(earning.earning_id)),
            'is_active': False,
            'is_paid': True,
            'status_display': 'Deleted'
        })
        if earning.purchase:
            agg_data['paid_details']['sales'] += 1
            agg_data['paid_details']['gross'] += earning.purchase.amount_paid
            agg_data['paid_details']['commission'] += earning.purchase.platform_fee_amount
            agg_data['paid_details']['net'] += earning.amount_earned

    temp_list = list(aggregated_earnings_for_list.values())
    temp_list.sort(key=lambda x: x['title'].lower() if x['title'] else '')
    min_date_for_sorting = timezone.datetime.min.replace(tzinfo=timezone.get_default_timezone()) if timezone.is_aware(now) else timezone.datetime.min
    temp_list.sort(key=lambda x: x['publish_date'] if x['publish_date'] else min_date_for_sorting, reverse=True)
    temp_list.sort(key=lambda x: x['is_active'], reverse=True)
    earnings_list_final = temp_list

    context.update({
        'earnings_list': earnings_list_final,
        'PLATFORM_COMMISSION_RATE_DISPLAY': PLATFORM_COMMISSION_RATE,
        'EARNING_PER_VIEW': EARNING_PER_VIEW,
    })
    return render(request, 'creator/creator_myearnings.html', context)


@login_required
@require_POST
@csrf_protect
def mark_welcome_popup_shown(request):
    try:
        with transaction.atomic():
            creator = Creator.objects.select_for_update().get(user=request.user)
            if creator.verification_status == 'approved' and not creator.is_banned and not creator.welcome_popup_shown:
                creator.welcome_popup_shown = True
                creator.save(update_fields=['welcome_popup_shown'])
                return JsonResponse({'status': 'success', 'message': 'Welcome popup marked as shown.'})
            else:
                return JsonResponse({'status': 'ignored', 'message': 'Popup status not applicable or already updated.'})
    except Creator.DoesNotExist: return JsonResponse({'status': 'error', 'message': 'Creator profile not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error marking welcome popup shown for {request.user.username}: {e}", exc_info=True) # Used logger
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)

@login_required
@require_POST
@csrf_protect
def mark_rejection_popup_shown(request):
    try:
        with transaction.atomic():
            creator = Creator.objects.select_for_update().get(user=request.user)
            if creator.verification_status == 'rejected' and not creator.rejection_popup_shown:
                creator.rejection_popup_shown = True
                creator.save(update_fields=['rejection_popup_shown'])
                return JsonResponse({'status': 'success', 'message': 'Rejection popup marked as shown.'})
            else:
                return JsonResponse({'status': 'ignored', 'message': 'Popup status not applicable or already updated.'})
    except Creator.DoesNotExist: return JsonResponse({'status': 'error', 'message': 'Creator profile not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error marking rejection popup shown for {request.user.username}: {e}", exc_info=True) # Used logger
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)

@admin_role_required('manage_creators')
@require_POST
@csrf_protect
@transaction.atomic
def admin_approve_creator(request, user_id):
    creator = get_object_or_404(Creator, user_id=user_id)
    admin_user = request.admin_user
    if creator.verification_status == 'pending':
        creator_cid = f"cid-{creator.user_id}"
        approval_time = timezone.now()
        attempts_when_submitted = creator.application_attempts_current_month
        creator.verification_status = 'approved'
        creator.cid = creator_cid
        creator.approved_at = approval_time
        creator.approved_by = admin_user
        creator.attempts_at_approval = attempts_when_submitted
        creator.rejection_reason = None
        creator.welcome_popup_shown = False
        creator.rejection_popup_shown = False
        creator.is_banned = False
        creator.ban_reason = None
        creator.banned_at = None
        creator.banned_by = None
        creator.last_name_change_date = None
        creator.last_unique_name_change_date = None
        fields_to_update = [
            'verification_status', 'cid', 'approved_at', 'approved_by', 'attempts_at_approval',
            'rejection_reason', 'welcome_popup_shown', 'rejection_popup_shown', 'is_banned',
            'ban_reason', 'banned_at', 'banned_by', 'last_name_change_date', 'last_unique_name_change_date',
        ]
        creator.save(update_fields=fields_to_update)
        try:
            latest_log = CreatorApplicationLog.objects.filter(creator=creator, status='submitted').latest('application_date')
            latest_log.status = 'approved'
            latest_log.processed_at = approval_time
            latest_log.processed_by = admin_user
            latest_log.rejection_reason = None
            latest_log.save(update_fields=['status', 'processed_at', 'processed_by', 'rejection_reason'])
        except CreatorApplicationLog.DoesNotExist:
            logger.warning(f"Could not find matching application log for creator {creator.user.username} to mark as approved.") # Used logger
            messages.warning(request, f"Could not find matching application log for creator {creator.user.username} to mark as approved.")
        except Exception as log_e:
            logger.error(f"Error updating application log for approval: {log_e}", exc_info=True) # Used logger
            messages.error(request, f"Error updating application log for approval: {log_e}")
        messages.success(request, f"Creator '{creator.creator_name}' approved successfully by {admin_user.username} with CID: {creator_cid}.")
    else: messages.warning(request, f"Creator '{creator.creator_name}' is not pending approval (Status: {creator.get_verification_status_display()}).")
    return redirect(request.META.get('HTTP_REFERER', reverse('AudioXApp:admin_pending_creator_applications')))

@admin_role_required('manage_creators')
@require_POST
@csrf_protect
@transaction.atomic
def admin_reject_creator(request, user_id):
    creator = get_object_or_404(Creator, user_id=user_id)
    admin_user = request.admin_user
    rejection_reason_input = request.POST.get('rejection_reason', '').strip()
    rejection_time = timezone.now()
    if not rejection_reason_input:
        messages.error(request, "Rejection reason is required.")
        referer = request.META.get('HTTP_REFERER', reverse('AudioXApp:admin_pending_creator_applications'))
        return redirect(referer)
    if creator.verification_status == 'pending':
        creator.verification_status = 'rejected'
        creator.rejection_reason = rejection_reason_input
        creator.rejection_popup_shown = False
        creator.welcome_popup_shown = False
        creator.approved_at = None
        creator.approved_by = None
        creator.attempts_at_approval = None
        creator.cid = None
        fields_to_update = [
            'verification_status', 'rejection_reason', 'rejection_popup_shown', 'welcome_popup_shown',
            'approved_at', 'approved_by', 'attempts_at_approval', 'cid',
        ]
        creator.save(update_fields=fields_to_update)
        try:
            latest_log = CreatorApplicationLog.objects.filter(creator=creator, status='submitted').latest('application_date')
            latest_log.status = 'rejected'
            latest_log.processed_at = rejection_time
            latest_log.processed_by = admin_user
            latest_log.rejection_reason = rejection_reason_input
            latest_log.save(update_fields=['status', 'processed_at', 'processed_by', 'rejection_reason'])
        except CreatorApplicationLog.DoesNotExist:
            logger.warning(f"Could not find matching application log for creator {creator.user.username} to mark as rejected.") # Used logger
            messages.warning(request, f"Could not find matching application log for creator {creator.user.username} to mark as rejected.")
        except Exception as log_e:
            logger.error(f"Error updating application log for rejection: {log_e}", exc_info=True) # Used logger
            messages.error(request, f"Error updating application log for rejection: {log_e}")
        messages.success(request, f"Creator '{creator.creator_name}' application rejected by {admin_user.username}.")
    else: messages.warning(request, f"Creator '{creator.creator_name}' is not pending rejection (Status: {creator.get_verification_status_display()}).")
    return redirect(request.META.get('HTTP_REFERER', reverse('AudioXApp:admin_pending_creator_applications')))

@admin_role_required('manage_creators')
@require_POST
@csrf_protect
@transaction.atomic
def admin_ban_creator(request, user_id):
    creator = get_object_or_404(Creator.objects.select_related('user'), user_id=user_id)
    admin_user = request.admin_user
    ban_reason = request.POST.get('ban_reason', '').strip()
    redirect_url = request.META.get('HTTP_REFERER', reverse('AudioXApp:admin_all_creators_list'))
    if not ban_reason:
        messages.error(request, "A reason is required to ban a creator.")
        return redirect(redirect_url)
    if not all(hasattr(creator, attr) for attr in ['is_banned', 'ban_reason', 'banned_at', 'banned_by']):
        messages.error(request, "Ban functionality requires 'is_banned', 'ban_reason', 'banned_at', 'banned_by' fields in the Creator model.")
        return redirect(redirect_url)
    if not creator.is_banned:
        creator.is_banned = True
        creator.ban_reason = ban_reason
        creator.banned_at = timezone.now()
        creator.banned_by = admin_user
        if creator.verification_status != 'rejected': creator.verification_status = 'rejected'
        creator.save(update_fields=['is_banned', 'ban_reason', 'banned_at', 'banned_by', 'verification_status'])
        messages.success(request, f"Creator '{creator.user.username}' ({creator.creator_name}) has been banned by {admin_user.username}.")
    else: messages.warning(request, f"Creator '{creator.user.username}' is already banned.")
    return redirect(redirect_url)

@admin_role_required('manage_creators')
@require_POST
@csrf_protect
@transaction.atomic
def admin_unban_creator(request, user_id):
    creator = get_object_or_404(Creator.objects.select_related('user'), user_id=user_id)
    admin_user = request.admin_user
    unban_reason = request.POST.get('unban_reason', '').strip()
    redirect_url = request.META.get('HTTP_REFERER', reverse('AudioXApp:admin_banned_creators_list'))
    if not unban_reason:
        messages.error(request, "A reason is required to unban a creator (for admin records).")
        return redirect(redirect_url)
    required_attrs = ['is_banned', 'ban_reason', 'banned_at', 'banned_by', 'admin_notes', 'verification_status', 'welcome_popup_shown', 'rejection_reason', 'rejection_popup_shown']
    if not all(hasattr(creator, attr) for attr in required_attrs):
        messages.error(request, "Unban functionality requires ban fields, admin_notes, and status/popup fields in the Creator model.")
        return redirect(redirect_url)
    if creator.is_banned:
        creator.is_banned = False
        creator.banned_at = None
        creator.banned_by = None
        unban_note = f"Unbanned by {admin_user.username} on {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}. Reason: {unban_reason}"
        if creator.admin_notes: creator.admin_notes = f"{creator.admin_notes}\n\n{unban_note}"
        else: creator.admin_notes = unban_note

        creator.verification_status = 'approved'
        creator.welcome_popup_shown = False

        creator.save(update_fields=[
            'is_banned', 'banned_at', 'banned_by', 'admin_notes', 'verification_status',
            'welcome_popup_shown',
        ])
        messages.success(request, f"Creator '{creator.user.username}' ({creator.creator_name}) has been unbanned and set to approved by {admin_user.username}.")
    else: messages.warning(request, f"Creator '{creator.user.username}' is not currently banned.")
    return redirect(redirect_url)


@creator_required
@require_GET
def get_audiobook_chapters_json(request, audiobook_slug):
    creator = request.creator
    try:
        audiobook = get_object_or_404(Audiobook, slug=audiobook_slug, creator=creator)
        chapters_queryset = Chapter.objects.filter(audiobook=audiobook).order_by('chapter_order')
        chapters_list = []
        for chapter in chapters_queryset:
            file_size = None
            audio_filename = "N/A"
            try:
                if chapter.audio_file and chapter.audio_file.name:
                    audio_filename = os.path.basename(chapter.audio_file.name)
                    if hasattr(chapter.audio_file, 'size') and chapter.audio_file.size is not None:
                        file_size = filesizeformat(chapter.audio_file.size)
            except Exception as e:
                 logger.warning(f"Error getting file details for chapter {chapter.chapter_id} in get_audiobook_chapters_json: {e}") # Used logger
                 pass # Silently fail on file detail error
            chapter_data = {
                'id': chapter.chapter_id, 'name': chapter.chapter_name, 'order': chapter.chapter_order,
                'audio_filename': audio_filename, 'file_size': file_size,
            }
            chapters_list.append(chapter_data)
        return JsonResponse({'chapters': chapters_list}, status=200)
    except Http404:
        logger.warning(f"Audiobook not found or permission denied in get_audiobook_chapters_json for slug {audiobook_slug}, user {request.user.username}") # Used logger
        return JsonResponse({'error': 'Audiobook not found or permission denied.'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_audiobook_chapters_json for slug {audiobook_slug}: {e}", exc_info=True) # Used logger
        return JsonResponse({'error': 'An internal server error occurred.'}, status=500)
