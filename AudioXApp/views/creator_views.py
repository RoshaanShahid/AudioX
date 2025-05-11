import json
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
import os
from collections import defaultdict, OrderedDict

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden, Http404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods, require_GET
from django.views.decorators.csrf import csrf_protect
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

from ..models import User, Creator, Audiobook, Chapter, WithdrawalRequest, CreatorApplicationLog, Admin, WithdrawalAccount, CreatorEarning, AudiobookViewLog
from .utils import _get_full_context
from .decorators import admin_role_required

PLATFORM_COMMISSION_RATE = Decimal('10.00')
EARNING_PER_VIEW = Decimal('1.00')
MIN_WITHDRAWAL_AMOUNT = Decimal('50.00')
CANCELLATION_WINDOW_MINUTES = 30

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
            messages.error(request, f"An error occurred accessing creator information for user {user_identifier}: {type(e).__name__} - {e}")
            return redirect('AudioXApp:home')
    return _wrapped_view

@login_required
@require_POST
@csrf_protect
def log_audiobook_view(request):
    audiobook_id = request.POST.get('audiobook_id')

    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'User not authenticated.'}, status=401)

    if not audiobook_id:
        return JsonResponse({'status': 'error', 'message': 'Audiobook ID is required.'}, status=400)

    try:
        audiobook = get_object_or_404(
            Audiobook.objects.select_related('creator'),
            pk=audiobook_id
        )

        twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
        recent_view_exists = AudiobookViewLog.objects.filter(
            audiobook=audiobook,
            user=request.user,
            viewed_at__gte=twenty_four_hours_ago
        ).exists()

        if recent_view_exists:
            return JsonResponse({'status': 'success', 'message': 'View already logged recently for earnings and view count purposes.'})

        with transaction.atomic():
            audiobook_locked = Audiobook.objects.select_for_update().get(pk=audiobook.pk)

            AudiobookViewLog.objects.create(
                audiobook=audiobook_locked,
                user=request.user
            )

            audiobook_locked.total_views = F('total_views') + 1
            audiobook_locked.save(update_fields=['total_views'])
            audiobook_locked.refresh_from_db(fields=['total_views'])

            if not audiobook_locked.is_paid:
                creator = audiobook_locked.creator
                earned_amount_for_view = EARNING_PER_VIEW

                Creator.objects.filter(pk=creator.pk).update(
                    available_balance=F('available_balance') + earned_amount_for_view,
                    total_earning=F('total_earning') + earned_amount_for_view
                )

                CreatorEarning.objects.create(
                    creator=creator,
                    audiobook=audiobook_locked,
                    earning_type='view',
                    amount_earned=earned_amount_for_view,
                    transaction_date=timezone.now(),
                    audiobook_title_at_transaction=audiobook_locked.title,
                    notes=f"Earning from 1 view on '{audiobook_locked.title}' (24hr rule applied)."
                )
        return JsonResponse({'status': 'success', 'message': 'View logged, total views updated, and earnings updated (if applicable).'})

    except Http404:
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': 'An internal error occurred.'}, status=500)


@creator_required
def creator_dashboard_view(request):
    try:
        creator_profile = request.creator
    except AttributeError:
        messages.error(request, "Creator profile not available. Please log in again.")
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
        messages.error(request, f"A data error occurred while loading the dashboard (missing field: {fe.args[0]}). Please ensure migrations are complete and the database schema is up to date. If the issue persists, contact support.")
        return redirect('AudioXApp:home')
    except Creator.DoesNotExist:
        messages.error(request, "Creator profile not found. Please log in again.")
        return redirect('AudioXApp:home')
    except Exception as e:
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
            error_message = 'An error occurred.'
            errors = {}
            if 'creator_unique_name' in str(e).lower():
                error_message = 'That unique name is already taken.'
                errors['creator_unique_name'] = error_message
            else:
                error_message = "A database error occurred."; errors['__all__'] = error_message
            return JsonResponse({ 'status': 'error', 'message': error_message, 'errors': errors }, status=400)
        except Exception as e:
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
                    except Exception as del_e: pass # Silently fail on delete error
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
                    except Exception as del_e: pass # Silently fail
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
                        messages.warning(request, "An internal inconsistency occurred. Please try again.")
                    else: messages.info(request, "No changes were detected.")
                return redirect('AudioXApp:update_creator_profile')
            except IntegrityError:
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
        messages.error(request, "Could not load your audiobooks.")
        return redirect('AudioXApp:creator_dashboard')

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

        if not title: form_errors['title'] = "Audiobook title is required."
        if not author: form_errors['author'] = "Author name is required."
        if not narrator: form_errors['narrator'] = "Narrator name is required."
        if not genre: form_errors['genre'] = "Genre is required."
        if not language: form_errors['language'] = "Language is required."
        if not description: form_errors['description'] = "Audiobook description is required."

        if not cover_image_file:
            form_errors['cover_image'] = "Cover image is required."
        else:
            max_cover_size = 2 * 1024 * 1024
            allowed_cover_types = ['image/jpeg', 'image/png', 'image/jpg']
            if cover_image_file.size > max_cover_size:
                form_errors['cover_image'] = "Cover image too large (Max 2MB)."
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

        chapters_to_save = []
        chapter_indices = set()

        for key in request.POST:
            if key.startswith('chapters[') and '][title]' in key:
                try:
                    index_str = key.split('[')[1].split(']')[0]
                    chapter_indices.add(int(index_str))
                except (IndexError, ValueError):
                    continue

        if not chapter_indices:
            form_errors['chapters_general'] = "At least one chapter is required."
        else:
            sorted_indices = sorted(list(chapter_indices))
            for index in sorted_indices:
                chapter_title = submitted_values.get(f'chapters[{index}][title]', '').strip()
                chapter_audio_file = request.FILES.get(f'chapters[{index}][audio]')
                try:
                    chapter_order = int(submitted_values.get(f'chapters[{index}][order]', index + 1))
                except ValueError:
                    chapter_order = index + 1

                current_chapter_errors = {}
                if not chapter_title:
                    current_chapter_errors['title'] = "Chapter title is required."
                if not chapter_audio_file:
                    current_chapter_errors['audio'] = "Audio file is required for this chapter."
                else:
                    max_audio_size = 50 * 1024 * 1024
                    allowed_audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg']
                    if chapter_audio_file.size > max_audio_size:
                        current_chapter_errors['audio'] = f"Audio file too large (Max 50MB)."
                    if chapter_audio_file.content_type not in allowed_audio_types:
                        current_chapter_errors['audio'] = f"Invalid audio file type (MP3, WAV, OGG)."

                if current_chapter_errors:
                    form_errors[f'chapter_{index}'] = current_chapter_errors

                submitted_chapters_for_template.append({
                    'original_index': index,
                    'title': chapter_title,
                    'audio_filename': chapter_audio_file.name if chapter_audio_file else "No file chosen",
                    'order': chapter_order,
                    'errors': current_chapter_errors
                })

                if not current_chapter_errors:
                    chapters_to_save.append({
                        'title': chapter_title,
                        'audio_file': chapter_audio_file,
                        'order': chapter_order
                    })

            if form_errors and any(key.startswith('chapter_') for key in form_errors):
                form_errors.setdefault('chapters_general', "Please correct errors in the chapter details below.")


        if not form_errors:
            try:
                with transaction.atomic():
                    new_audiobook = Audiobook(
                        creator=creator, title=title, author=author, narrator=narrator, language=language,
                        genre=genre, description=description, cover_image=cover_image_file,
                        is_paid=is_paid, price=price if is_paid else Decimal('0.00')
                    )
                    try:
                        new_audiobook.full_clean()
                    except ValidationError as e: # DjangoValidationError
                        for field, error_list in e.message_dict.items():
                            form_errors[field] = " ".join(error_list)
                        if hasattr(e, 'non_field_errors') and e.non_field_errors():
                            form_errors['general_error'] = " ".join(e.non_field_errors())
                        raise
                    new_audiobook.save()
                    chapters_to_save.sort(key=lambda c: c['order'])

                    for chapter_data_item in chapters_to_save:
                        Chapter.objects.create(
                            audiobook=new_audiobook,
                            chapter_name=chapter_data_item['title'],
                            chapter_order=chapter_data_item['order'],
                            audio_file=chapter_data_item['audio_file']
                        )
                    messages.success(request, f"Audiobook '{title}' uploaded and published successfully! It is now in your library.")
                    return redirect('AudioXApp:creator_my_audiobooks')
            except ValidationError: # DjangoValidationError
                messages.error(request, "Please correct the validation errors found.")
            except IntegrityError as e:
                messages.error(request, f"Database Error: Could not save audiobook. It might conflict with existing data (e.g., duplicate title/slug).")
                form_errors['general_error'] = "A database error occurred. Please check for duplicate titles or ensure slug uniqueness."
            except Exception as e:
                messages.error(request, f"An unexpected error occurred during upload: {e}")
                form_errors['general_error'] = f"An unexpected server error occurred: {e}"
        else:
            messages.error(request, "Please correct the errors highlighted below.")

        submitted_values['chapters'] = submitted_chapters_for_template

    context = _get_full_context(request)
    context.update({
        'creator': creator,
        'available_balance': creator.available_balance,
        'form_errors': form_errors,
        'submitted_values': submitted_values,
    })
    return render(request, 'creator/creator_upload_audiobooks.html', context)


@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_manage_upload_detail_view(request, audiobook_slug):
    creator = request.creator
    audiobook = get_object_or_404(Audiobook, slug=audiobook_slug, creator=creator)

    form_errors = {}
    submitted_values = {}
    chapters_context_list = []

    creator_allowed_statuses_for_toggle = [
        ('PUBLISHED', 'Published (Visible to users)'),
        ('INACTIVE', 'Inactive (Hidden from public, earnings paused)'),
    ]
    can_creator_change_status = audiobook.status not in ['REJECTED', 'PAUSED_BY_ADMIN']

    if request.method == 'POST':
        action = request.POST.get('action')
        submitted_values = request.POST.copy()

        if action == 'edit_audiobook_details':
            title = submitted_values.get('title', '').strip()
            author = submitted_values.get('author', '').strip()
            narrator = submitted_values.get('narrator', '').strip()
            genre = submitted_values.get('genre', '').strip()
            language = submitted_values.get('language', '').strip()
            description = submitted_values.get('description', '').strip()
            cover_image_file = request.FILES.get('cover_image')

            if not title: form_errors['title'] = "Audiobook title is required."
            if not author: form_errors['author'] = "Author name is required."
            if not narrator: form_errors['narrator'] = "Narrator name is required."
            if not genre: form_errors['genre'] = "Genre is required."
            if not language: form_errors['language'] = "Language is required."
            if not description: form_errors['description'] = "Description is required."

            if cover_image_file:
                max_cover_size = 2 * 1024 * 1024
                allowed_cover_types = ['image/jpeg', 'image/png', 'image/jpg']
                if cover_image_file.size > max_cover_size:
                    form_errors['cover_image'] = "Cover image too large (Max 2MB)."
                if cover_image_file.content_type not in allowed_cover_types:
                    form_errors['cover_image'] = "Invalid cover image type (PNG, JPG/JPEG only)."

            if not form_errors:
                try:
                    with transaction.atomic():
                        audiobook.title = title
                        audiobook.author = author
                        audiobook.narrator = narrator
                        audiobook.genre = genre
                        audiobook.language = language
                        audiobook.description = description
                        if cover_image_file:
                            if audiobook.cover_image and hasattr(audiobook.cover_image, 'name') and audiobook.cover_image.name:
                                if default_storage.exists(audiobook.cover_image.name):
                                    default_storage.delete(audiobook.cover_image.name)
                            audiobook.cover_image = cover_image_file

                        new_slug_candidate = slugify(title)
                        if audiobook.slug != new_slug_candidate:
                            temp_slug = new_slug_candidate
                            counter = 1
                            while Audiobook.objects.filter(slug=temp_slug).exclude(pk=audiobook.pk).exists():
                                temp_slug = f"{new_slug_candidate}-{counter}"
                                counter += 1
                            audiobook.slug = temp_slug

                        audiobook.save()
                        messages.success(request, f"Audiobook '{audiobook.title}' details updated successfully.")
                        return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook.slug)
                except Exception as e:
                    messages.error(request, f"An error occurred while saving details: {e}")
                    form_errors['general_error'] = f"An unexpected error occurred: {e}"
            else:
                messages.error(request, "Please correct the errors in the audiobook details.")

        elif action == 'add_chapter':
            chapter_title = submitted_values.get('new_chapter_title', '').strip()
            chapter_audio_file = request.FILES.get('new_chapter_audio')

            if not chapter_title: form_errors['new_chapter_title'] = "New chapter title is required."
            if not chapter_audio_file:
                form_errors['new_chapter_audio'] = "Audio file for the new chapter is required."
            else:
                max_audio_size = 50 * 1024 * 1024
                allowed_audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg']
                if chapter_audio_file.size > max_audio_size:
                    form_errors['new_chapter_audio'] = "Audio file too large (Max 50MB)."
                if chapter_audio_file.content_type not in allowed_audio_types:
                    form_errors['new_chapter_audio'] = "Invalid audio file type."

            if not form_errors.get('new_chapter_title') and not form_errors.get('new_chapter_audio'):
                try:
                    with transaction.atomic():
                        max_order = audiobook.chapters.aggregate(Max('chapter_order'))['chapter_order__max'] or 0
                        Chapter.objects.create(
                            audiobook=audiobook,
                            chapter_name=chapter_title,
                            audio_file=chapter_audio_file,
                            chapter_order=max_order + 1
                        )
                        messages.success(request, f"Chapter '{chapter_title}' added successfully.")
                        return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook.slug)
                except Exception as e:
                    messages.error(request, f"Error adding chapter: {e}")
                    form_errors['add_chapter_general'] = f"An unexpected error: {e}"
            else:
                messages.error(request, "Please correct errors in the new chapter form.")

        elif action.startswith('edit_chapter_'):
            try:
                chapter_id_str = action.split('edit_chapter_')[-1]
                chapter_id = int(chapter_id_str)
                chapter_to_edit = get_object_or_404(Chapter, chapter_id=chapter_id, audiobook=audiobook)

                updated_title = submitted_values.get(f'chapter_title_{chapter_id}', '').strip()
                updated_audio_file = request.FILES.get(f'chapter_audio_{chapter_id}')

                edit_error_key_title = f'chapter_edit_{chapter_id_str}_title'
                edit_error_key_audio = f'chapter_edit_{chapter_id_str}_audio'

                if not updated_title: form_errors[edit_error_key_title] = "Chapter title cannot be empty."

                if updated_audio_file:
                    max_audio_size = 50 * 1024 * 1024
                    allowed_audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg']
                    if updated_audio_file.size > max_audio_size:
                        form_errors[edit_error_key_audio] = "Audio file too large (Max 50MB)."
                    if updated_audio_file.content_type not in allowed_audio_types:
                        form_errors[edit_error_key_audio] = "Invalid audio file type."

                if not form_errors.get(edit_error_key_title) and not form_errors.get(edit_error_key_audio):
                    with transaction.atomic():
                        chapter_to_edit.chapter_name = updated_title
                        if updated_audio_file:
                            if chapter_to_edit.audio_file and hasattr(chapter_to_edit.audio_file, 'name') and chapter_to_edit.audio_file.name:
                               if default_storage.exists(chapter_to_edit.audio_file.name):
                                    default_storage.delete(chapter_to_edit.audio_file.name)
                            chapter_to_edit.audio_file = updated_audio_file
                        chapter_to_edit.save()
                        messages.success(request, f"Chapter '{chapter_to_edit.chapter_name}' updated.")
                        return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook.slug)
                else:
                    messages.error(request, f"Please correct errors for chapter '{chapter_to_edit.chapter_name}'.")
            except (ValueError, Http404):
                messages.error(request, "Invalid chapter specified for editing.")
            except Exception as e:
                messages.error(request, f"Error editing chapter: {e}")
                form_errors[f'chapter_edit_{chapter_id_str}_general'] = f"Unexpected error: {e}"


        elif action.startswith('delete_chapter_'):
            try:
                chapter_id_str = action.split('delete_chapter_')[-1]
                chapter_id = int(chapter_id_str)
                chapter_to_delete = get_object_or_404(Chapter, chapter_id=chapter_id, audiobook=audiobook)
                chapter_name = chapter_to_delete.chapter_name

                with transaction.atomic():
                    if chapter_to_delete.audio_file and hasattr(chapter_to_delete.audio_file, 'name') and chapter_to_delete.audio_file.name:
                        if default_storage.exists(chapter_to_delete.audio_file.name):
                            default_storage.delete(chapter_to_delete.audio_file.name)
                    chapter_to_delete.delete()

                    remaining_chapters = audiobook.chapters.order_by('chapter_order')
                    for i, chap in enumerate(remaining_chapters):
                        if chap.chapter_order != i + 1:
                            chap.chapter_order = i + 1
                            chap.save(update_fields=['chapter_order'])

                messages.success(request, f"Chapter '{chapter_name}' deleted successfully.")
                return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook.slug)
            except ValueError:
                messages.error(request, "Invalid chapter ID for deletion.")
            except Http404:
                messages.error(request, "Chapter not found for deletion.")
            except Exception as e:
                messages.error(request, f"Error deleting chapter: {e}")

        elif action == 'update_status_only':
            new_status = submitted_values.get('status_only_select')
            allowed_status_values = [choice[0] for choice in creator_allowed_statuses_for_toggle]

            if not can_creator_change_status:
                messages.error(request, "This audiobook's status was set by an administrator and cannot be changed by you.")
            elif new_status and new_status in allowed_status_values:
                if audiobook.status != new_status:
                    audiobook.status = new_status
                    audiobook.save(update_fields=['status'])
                    messages.success(request, f"Audiobook status updated to '{audiobook.get_status_display()}'.")
                else:
                    messages.info(request, "Status is already set to the selected value.")
            else:
                form_errors['status_update_status'] = "Invalid status selected."
                messages.error(request, "Invalid status selected.")

            if not form_errors.get('status_update_status'):
                return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook.slug)

        audiobook.refresh_from_db()

    else: # GET Request
        submitted_values['title'] = audiobook.title
        submitted_values['author'] = audiobook.author
        submitted_values['narrator'] = audiobook.narrator
        submitted_values['genre'] = audiobook.genre
        submitted_values['language'] = audiobook.language
        submitted_values['description'] = audiobook.description
        submitted_values['status_only_select'] = audiobook.status

    db_chapters = audiobook.chapters.order_by('chapter_order')
    for chapter_instance in db_chapters:
        chapter_id_str = str(chapter_instance.chapter_id)
        submitted_title_for_this_chapter = submitted_values.get(f'chapter_title_{chapter_id_str}', chapter_instance.chapter_name)

        chapters_context_list.append({
            'instance': chapter_instance,
            'submitted_title_value': submitted_title_for_this_chapter,
            'errors': {
                'title': form_errors.get(f'chapter_edit_{chapter_id_str}_title'),
                'audio': form_errors.get(f'chapter_edit_{chapter_id_str}_audio'),
                'general': form_errors.get(f'chapter_edit_{chapter_id_str}_general')
            }
        })

    django_messages_list = []
    for msg in get_messages(request):
        django_messages_list.append({'message': str(msg), 'tags': msg.tags})

    context = _get_full_context(request)
    context.update({
        'creator': creator,
        'audiobook': audiobook,
        'chapters_context_list': chapters_context_list,
        'available_balance': creator.available_balance,
        'form_errors': form_errors,
        'submitted_values': submitted_values,
        'creator_allowed_status_choices_for_toggle': creator_allowed_statuses_for_toggle,
        'can_creator_change_status': can_creator_change_status,
        'django_messages_json': json.dumps(django_messages_list),
    })
    return render(request, 'creator/creator_manage_uploads.html', context)


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
        except CreatorApplicationLog.DoesNotExist: messages.warning(request, f"Could not find matching application log for creator {creator.user.username} to mark as approved.")
        except Exception as log_e:
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
        except CreatorApplicationLog.DoesNotExist: messages.warning(request, f"Could not find matching application log for creator {creator.user.username} to mark as rejected.")
        except Exception as log_e:
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
            except Exception as e: pass # Silently fail on file detail error
            chapter_data = {
                'id': chapter.chapter_id, 'name': chapter.chapter_name, 'order': chapter.chapter_order,
                'audio_filename': audio_filename, 'file_size': file_size,
            }
            chapters_list.append(chapter_data)
        return JsonResponse({'chapters': chapters_list}, status=200)
    except Http404: return JsonResponse({'error': 'Audiobook not found or permission denied.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': 'An internal server error occurred.'}, status=500)