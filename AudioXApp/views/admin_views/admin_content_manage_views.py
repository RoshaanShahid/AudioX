# AudioXApp/views/admin_views/admin_content_manage_views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required # Keep this import for now, as other admin_views files might still use it
from django.views.decorators.http import require_POST, require_GET
from django.contrib import messages
from django.urls import reverse
from django.core.cache import cache
from .. import decorators
from AudioXApp.models import Audiobook, Chapter, Admin, BannedKeyword, ContentReport
import json
from django.utils.timezone import now, timedelta
from django.db.models import Q, Prefetch, Count
from django.db import transaction, IntegrityError
from collections import defaultdict

# werkzeug can be removed if not used elsewhere, but we'll leave it for the add view
from werkzeug.datastructures import MultiDict


# ==============================================================================
# EXISTING VIEWS (No changes needed to these)
# ==============================================================================

# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_add_audiobook_view(request):
    """
    View for adding a new platform-managed audiobook using the premium custom HTML form.
    This view now handles dynamic chapter uploads.
    """
    admin_user = getattr(request, 'admin_user', None)
    context = {
        'active_page': 'manage_content',
        'admin_user': admin_user
    }

    if request.method == 'POST':
        context['submitted_data'] = request.POST
        title = request.POST.get('title')
        author = request.POST.get('author')
        narrator = request.POST.get('narrator')
        language = request.POST.get('language')
        genre = request.POST.get('genre')
        description = request.POST.get('description')
        cover_image = request.FILES.get('cover_image')

        if not all([title, author, narrator, language, genre, description, cover_image]):
            messages.error(request, "Please fill out all audiobook details and upload a cover image.")
            return render(request, 'admin/manage_content/admin_add_audiobook.html', context)
        try:
            form_data = MultiDict(request.POST)
            chapter_titles = [v for k, v in form_data.items(multi=True) if k.endswith('[title]')]
            if not chapter_titles:
                messages.error(request, "You must add at least one chapter to the audiobook.")
                return render(request, 'admin/manage_content/admin_add_audiobook.html', context)
            
            chapters_to_create = []
            for i in range(len(chapter_titles)):
                chapter_title = request.POST.get(f'chapters[{i}][title]')
                chapter_audio_file = request.FILES.get(f'chapters[{i}][audio_file]')
                if not chapter_title or not chapter_audio_file:
                    messages.error(request, f"Chapter {i+1} is missing a title or an audio file.")
                    return render(request, 'admin/manage_content/admin_add_audiobook.html', context)
                chapters_to_create.append({'order': i + 1,'title': chapter_title,'file': chapter_audio_file})
        except Exception as e:
            messages.error(request, f"There was an error processing chapter data: {e}")
            return render(request, 'admin/manage_content/admin_add_audiobook.html', context)
        try:
            with transaction.atomic():
                # For platform uploads, we can consider them pre-approved.
                new_audiobook = Audiobook(
                    title=title,author=author,narrator=narrator,language=language,
                    genre=genre,description=description,cover_image=cover_image,
                    creator=None,is_creator_book=False,source='platform',
                    status='PUBLISHED', 
                    moderation_status=Audiobook.ModerationStatusChoices.APPROVED
                )
                new_audiobook.save()
                for chap_info in chapters_to_create:
                    Chapter.objects.create(
                        audiobook=new_audiobook,chapter_order=chap_info['order'],
                        chapter_name=chap_info['title'],audio_file=chap_info['file'],
                        moderation_status=Chapter.ModerationStatusChoices.APPROVED
                    )
                messages.success(request, f"Successfully PUBLISHED the audiobook '{new_audiobook.title}' with {len(chapters_to_create)} chapters.")
                return redirect(reverse('AudioXApp:admin_creator_audiobook_detail', args=[new_audiobook.audiobook_id]))
        except Exception as e:
            messages.error(request, f"A database error occurred: {e}")
            return render(request, 'admin/manage_content/admin_add_audiobook.html', context)
    
    return render(request, 'admin/manage_content/admin_add_audiobook.html', context)


# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_edit_platform_audiobook(request, audiobook_id):
    """
    Handles editing a platform-managed audiobook with robust chapter management.
    """
    audiobook = get_object_or_404(Audiobook.objects.prefetch_related('chapters'), audiobook_id=audiobook_id, creator__isnull=True)
    admin_user = getattr(request, 'admin_user', None)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                # --- Step 1: Update Audiobook Details ---
                audiobook.title = request.POST.get('title', '').strip()
                audiobook.author = request.POST.get('author', '').strip()
                audiobook.narrator = request.POST.get('narrator', '').strip()
                audiobook.language = request.POST.get('language')
                audiobook.genre = request.POST.get('genre')
                audiobook.description = request.POST.get('description', '').strip()

                if 'cover_image' in request.FILES:
                    audiobook.cover_image = request.FILES['cover_image']
                
                audiobook.save()

                # --- Step 2: Handle Chapter Deletions ---
                chapters_to_delete_ids_str = request.POST.get('chapters_to_delete', '')
                if chapters_to_delete_ids_str:
                    chapters_to_delete_ids = [int(id) for id in chapters_to_delete_ids_str.split(',') if id.isdigit()]
                    if chapters_to_delete_ids:
                        Chapter.objects.filter(chapter_id__in=chapters_to_delete_ids, audiobook=audiobook).delete()

                # --- Step 3: Parse and Structure Submitted Chapter Data ---
                chapters_data = {}
                for key, value in request.POST.items():
                    if key.startswith('chapters[') and key.endswith('][title]'):
                        index = int(key.split('[')[1].split(']')[0])
                        if index not in chapters_data: chapters_data[index] = {}
                        chapters_data[index]['title'] = value.strip()
                    elif key.startswith('chapters[') and key.endswith('][id]'):
                        index = int(key.split('[')[1].split(']')[0])
                        if index not in chapters_data: chapters_data[index] = {}
                        chapters_data[index]['id'] = value

                for key, value in request.FILES.items():
                    if key.startswith('chapters['):
                        index = int(key.split('[')[1].split(']')[0])
                        if index not in chapters_data: chapters_data[index] = {}
                        chapters_data[index]['audio_file'] = value

                # --- Step 4: Process Structured Chapter Data (Updates and Creations) ---
                order_counter = 1
                for index in sorted(chapters_data.keys()):
                    data = chapters_data[index]
                    chapter_id = data.get('id')
                    chapter_title = data.get('title')
                    chapter_audio_file = data.get('audio_file')

                    if not chapter_title:
                        continue

                    if chapter_id and chapter_id.isdigit():
                        try:
                            chapter = Chapter.objects.get(chapter_id=chapter_id, audiobook=audiobook)
                            chapter.chapter_name = chapter_title
                            chapter.chapter_order = order_counter
                            if chapter_audio_file:
                                chapter.audio_file = chapter_audio_file
                            chapter.save()
                        except Chapter.DoesNotExist:
                            messages.warning(request, f"Could not find chapter with ID {chapter_id} to update.")
                            continue
                    else:
                        if not chapter_audio_file:
                            raise ValueError(f"A new chapter ('{chapter_title}') must have an audio file.")
                        Chapter.objects.create(
                            audiobook=audiobook,
                            chapter_name=chapter_title,
                            audio_file=chapter_audio_file,
                            chapter_order=order_counter
                        )
                    order_counter += 1
                
                messages.success(request, f"Successfully updated the audiobook '{audiobook.title}'.")
                return redirect(reverse('AudioXApp:admin_platform_content_list'))

        except Exception as e:
            messages.error(request, f"An unexpected error occurred: {e}")
            context = {'audiobook': audiobook, 'active_page': 'manage_content', 'admin_user': admin_user}
            return render(request, 'admin/manage_content/admin_edit_audiobook.html', context)

    context = {'audiobook': audiobook, 'active_page': 'manage_content', 'admin_user': admin_user}
    return render(request, 'admin/manage_content/admin_edit_audiobook.html', context)


# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_manage_content_view(request):
    total_audiobooks = Audiobook.objects.count()
    creator_content_count = Audiobook.objects.filter(creator__isnull=False).count()
    platform_content_count = Audiobook.objects.filter(creator__isnull=True).count()

    moderation_queue_count = Audiobook.objects.filter(
        Q(moderation_status=Audiobook.ModerationStatusChoices.NEEDS_REVIEW) |
        Q(chapters__moderation_status=Chapter.ModerationStatusChoices.NEEDS_REVIEW)
    ).distinct().count()
    
    user_reports_count = ContentReport.objects.filter(is_resolved=False).count()

    labels, uploads_data, published_data, pending_data = [], [], [], []
    for i in range(7):
        date = now().date() - timedelta(days=i)
        labels.append(date.strftime('%a'))
        uploads_data.append(Audiobook.objects.filter(created_at__date=date).count())
        published_data.append(Audiobook.objects.filter(status='PUBLISHED', created_at__date=date).count())
        pending_data.append(Audiobook.objects.filter(status='INACTIVE', created_at__date=date).count())
    
    labels.reverse(); uploads_data.reverse(); published_data.reverse(); pending_data.reverse()
    
    context = {
        'active_page': 'manage_content', 
        'admin_user': request.admin_user, 
        'total_audiobooks': total_audiobooks, 
        'creator_content_count': creator_content_count, 
        'platform_content_count': platform_content_count, 
        'daily_chart_labels_json': json.dumps(labels), 
        'daily_uploads_data_json': json.dumps(uploads_data), 
        'daily_published_data_json': json.dumps(published_data), 
        'daily_pending_data_json': json.dumps(pending_data),
        'moderation_queue_count': moderation_queue_count,
        'user_reports_count': user_reports_count,
    }
    return render(request, 'admin/manage_content/manage_content.html', context)


# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_creator_content_list_view(request):
    search_query = request.GET.get('q', '').strip()
    language_filter = request.GET.get('language', '').strip()
    status_filter = request.GET.get('status', '').strip()
    creator_audiobooks = Audiobook.objects.filter(creator__isnull=False, creator__user__isnull=False).select_related('creator__user', 'takedown_by').prefetch_related('chapters').order_by('-created_at')
    if search_query:
        creator_audiobooks = creator_audiobooks.filter(Q(title__icontains=search_query) | Q(creator__user__username__icontains=search_query) | Q(author__icontains=search_query))
    if language_filter:
        creator_audiobooks = creator_audiobooks.filter(language__iexact=language_filter)
    if status_filter:
        creator_audiobooks = creator_audiobooks.filter(status__iexact=status_filter)
    base_query = Audiobook.objects.filter(creator__isnull=False)
    language_choices = base_query.values_list('language', flat=True).distinct().order_by('language')
    status_choices = Audiobook.STATUS_CHOICES
    context = {'active_page': 'manage_content','admin_user': request.admin_user,'creator_audiobooks': creator_audiobooks,'search_query': search_query,'selected_language': language_filter,'selected_status': status_filter,'language_choices': language_choices,'status_choices': status_choices}
    return render(request, 'admin/manage_content/admin_creator_content_list.html', context)


# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_platform_content_list_view(request):
    search_query = request.GET.get('q', '').strip()
    language_filter = request.GET.get('language', '').strip()
    platform_audiobooks = Audiobook.objects.filter(creator__isnull=True).prefetch_related('chapters').order_by('-created_at')
    if search_query:
        platform_audiobooks = platform_audiobooks.filter(title__icontains=search_query)
    if language_filter:
        platform_audiobooks = platform_audiobooks.filter(language__iexact=language_filter)
    language_choices = Audiobook.objects.filter(creator__isnull=True).values_list('language', flat=True).distinct().order_by('language')
    context = {'active_page': 'manage_content','admin_user': request.admin_user,'platform_audiobooks': platform_audiobooks,'search_query': search_query,'selected_language': language_filter,'language_choices': language_choices}
    return render(request, 'admin/manage_content/admin_platform_content_list.html', context)


# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_all_content_list_view(request):
    search_query = request.GET.get('q', '').strip()
    language_filter = request.GET.get('language', '').strip()
    status_filter = request.GET.get('status', '').strip()
    source_filter = request.GET.get('source', '').strip()
    all_audiobooks = Audiobook.objects.select_related('creator__user', 'takedown_by').prefetch_related('chapters').order_by('-created_at')
    if search_query:
        all_audiobooks = all_audiobooks.filter(Q(title__icontains=search_query) | Q(creator__user__username__icontains=search_query) | Q(author__icontains=search_query))
    if language_filter:
        all_audiobooks = all_audiobooks.filter(language__iexact=language_filter)
    if status_filter:
        all_audiobooks = all_audiobooks.filter(status__iexact=status_filter)
    if source_filter == 'creator':
        all_audiobooks = all_audiobooks.filter(creator__isnull=False)
    elif source_filter == 'platform':
        all_audiobooks = all_audiobooks.filter(creator__isnull=True)
    language_choices = Audiobook.objects.values_list('language', flat=True).distinct().order_by('language')
    status_choices = Audiobook.STATUS_CHOICES
    context = {'active_page': 'manage_content','admin_user': request.admin_user,'audiobooks': all_audiobooks,'search_query': search_query,'selected_language': language_filter,'selected_status': status_filter,'selected_source': source_filter,'language_choices': language_choices,'status_choices': status_choices}
    return render(request, 'admin/manage_content/admin_all_content_list.html', context)


# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_creator_audiobook_detail_view(request, audiobook_id):
    audiobook = get_object_or_404(Audiobook.objects.select_related('creator__user', 'takedown_by').prefetch_related('chapters'), audiobook_id=audiobook_id)
    context = {'active_page': 'manage_content', 'admin_user': request.admin_user, 'audiobook': audiobook}
    return render(request, 'admin/manage_content/admin_creator_audiobook_detail.html', context)

@require_POST
# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_takedown_audiobook_view(request, audiobook_id):
    audiobook = get_object_or_404(Audiobook, audiobook_id=audiobook_id)
    admin_user = get_object_or_404(Admin, adminid=request.session.get('admin_id'))
    reason = request.POST.get('reason', 'Content taken down due to a violation of platform policies.')
    audiobook.status = 'TAKEDOWN'; audiobook.takedown_by = admin_user; audiobook.takedown_at = now(); audiobook.takedown_reason = reason; audiobook.save()
    messages.success(request, f"The audiobook '{audiobook.title}' has been taken down.")
    redirect_url = request.META.get('HTTP_REFERER', reverse('AudioXApp:admin_manage_content'))
    return redirect(redirect_url)


@require_POST
# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_reinstate_audiobook_view(request, audiobook_id):
    audiobook = get_object_or_404(Audiobook, audiobook_id=audiobook_id)
    audiobook.status = 'INACTIVE'; audiobook.takedown_by = None; audiobook.takedown_at = None; audiobook.takedown_reason = None; audiobook.save()
    messages.success(request, f"The audiobook '{audiobook.title}' has been reinstated and set to 'Inactive'.")
    redirect_url = request.META.get('HTTP_REFERER', reverse('AudioXApp:admin_manage_content'))
    return redirect(redirect_url)

@require_POST
# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def delete_platform_audiobook(request, audiobook_id):
    audiobook = get_object_or_404(Audiobook, audiobook_id=audiobook_id, creator__isnull=True)
    try:
        audiobook_title = audiobook.title
        audiobook.delete()
        messages.success(request, f"Successfully deleted the audiobook: '{audiobook_title}'.")
    except Exception as e:
        messages.error(request, f"An error occurred while trying to delete the audiobook. Error: {e}")
    return redirect('AudioXApp:admin_platform_content_list')


# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_moderation_queue_view(request):
    """
    Displays creator-uploaded content that requires manual moderation.
    This view correctly fetches audiobook and chapter data for the moderation queue template.
    """
    # This query correctly identifies audiobooks needing review and prefetches
    # only the chapters that are flagged, making them available in the template.
    flagged_audiobooks = Audiobook.objects.filter(
        Q(moderation_status=Audiobook.ModerationStatusChoices.NEEDS_REVIEW) |
        Q(chapters__moderation_status=Chapter.ModerationStatusChoices.NEEDS_REVIEW)
    ).distinct().select_related('creator__user').prefetch_related(
        Prefetch('chapters', 
                 queryset=Chapter.objects.filter(moderation_status=Chapter.ModerationStatusChoices.NEEDS_REVIEW), 
                 to_attr='flagged_chapters')
    )

    context = {
        'active_page': 'manage_content',
        'admin_user': request.admin_user,
        'flagged_audiobooks': flagged_audiobooks,
    }
    return render(request, 'admin/manage_content/admin_moderation_queue.html', context)


@require_POST
# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_approve_audiobook_view(request, audiobook_id):
    """
    Approves an entire audiobook and all its chapters.
    """
    audiobook = get_object_or_404(Audiobook, audiobook_id=audiobook_id)
    admin_user = getattr(request, 'admin_user', None)

    try:
        with transaction.atomic():
            audiobook.chapters.all().update(
                moderation_status=Chapter.ModerationStatusChoices.APPROVED,
                moderation_notes=f"Approved by admin '{admin_user.username}' as part of bulk audiobook approval."
            )
            
            audiobook.moderation_status = Audiobook.ModerationStatusChoices.APPROVED
            audiobook.status = 'PUBLISHED'
            audiobook.moderation_notes = f"Audiobook approved by admin '{admin_user.username}' on {now().strftime('%Y-%m-%d %H:%M:%S')}."
            audiobook.last_moderated_at = now()
            audiobook.save()
            
            messages.success(request, f"Audiobook '{audiobook.title}' has been approved and published.")
    except Exception as e:
        messages.error(request, f"An error occurred while approving the audiobook: {e}")

    return redirect('AudioXApp:admin_moderation_queue')


@require_POST
# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_reject_audiobook_view(request, audiobook_id):
    """
    Rejects an entire audiobook and all its chapters.
    """
    audiobook = get_object_or_404(Audiobook, audiobook_id=audiobook_id)
    admin_user = getattr(request, 'admin_user', None)
    rejection_reason = request.POST.get('reason', 'Content did not meet platform guidelines.').strip()

    if not rejection_reason:
        messages.error(request, "A reason is required to reject an audiobook.")
        return redirect('AudioXApp:admin_moderation_queue')

    try:
        with transaction.atomic():
            audiobook.chapters.all().update(
                moderation_status=Chapter.ModerationStatusChoices.REJECTED,
                moderation_notes=f"Rejected by admin '{admin_user.username}'. Reason: {rejection_reason}"
            )

            audiobook.moderation_status = Audiobook.ModerationStatusChoices.REJECTED
            audiobook.status = 'REJECTED'
            audiobook.moderation_notes = f"Audiobook rejected by admin '{admin_user.username}' on {now().strftime('%Y-%m-%d %H:%M:%S')}.\nReason: {rejection_reason}"
            audiobook.last_moderated_at = now()
            audiobook.save()

            messages.success(request, f"Audiobook '{audiobook.title}' has been rejected.")
    except Exception as e:
        messages.error(request, f"An error occurred while rejecting the audiobook: {e}")

    return redirect('AudioXApp:admin_moderation_queue')


# THIS VIEW IS UPDATED FOR THE NEW TABBED INTERFACE
# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_manage_keywords_view(request):
    """
    Handles both displaying the list of banned keywords by language (in tabs)
    and adding a new one.
    """
    admin_user = getattr(request, 'admin_user', None)
    
    if request.method == 'POST':
        keyword = request.POST.get('keyword', '').strip().lower()
        language = request.POST.get('language', '').strip()

        if keyword and language:
            try:
                BannedKeyword.objects.create(keyword=keyword, language=language, added_by=admin_user)
                messages.success(request, f"Keyword '{keyword}' for '{language}' added successfully.")
                # --- FIX: Clear the cache for the updated language ---
                cache_key = f'banned_keywords_{language}'
                cache.delete(cache_key)
                # --- END FIX ---
            except IntegrityError:
                messages.error(request, f"The keyword '{keyword}' already exists.")
            except Exception as e:
                messages.error(request, f"An error occurred: {e}")
        else:
            messages.error(request, "Both keyword and language fields are required.")
        
        return redirect('AudioXApp:admin_manage_keywords')

    # GET request logic: Group keywords by language for the tabbed interface
    keywords_by_language = defaultdict(list)
    all_keywords = BannedKeyword.objects.select_related('added_by').order_by('keyword')
    for kw in all_keywords:
        keywords_by_language[kw.get_language_display()].append(kw)
    
    # Sort the dictionary by language name for consistent order
    sorted_keywords = dict(sorted(keywords_by_language.items()))

    # Get the first language name for the active tab, with a default.
    active_tab = next(iter(sorted_keywords.keys()), None)

    context = {
        'active_page': 'manage_content',
        'admin_user': admin_user,
        'keywords_by_language': sorted_keywords, # Pass the grouped dictionary
        'language_choices': BannedKeyword.LanguageChoices.choices,
        'active_tab': active_tab, # Pass the first key to the template
    }
    return render(request, 'admin/manage_content/admin_manage_keywords.html', context)


# THIS VIEW IS UPDATED
@require_POST
# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content')
def admin_delete_keyword_view(request, keyword_id):
    """
    Deletes a banned keyword.
    """
    try:
        keyword = get_object_or_404(BannedKeyword, id=keyword_id)
        keyword_text = keyword.keyword
        language_code = keyword.language # Get language before deleting
        keyword.delete()
        # --- FIX: Clear the cache for the updated language ---
        cache_key = f'banned_keywords_{language_code}'
        cache.delete(cache_key)
        # --- END FIX ---
        messages.success(request, f"Keyword '{keyword_text}' has been deleted.")
    except Exception as e:
        messages.error(request, f"An error occurred while deleting the keyword: {e}")

    return redirect('AudioXApp:admin_manage_keywords')


# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content', 'manage_support')
def admin_content_reports_list_view(request):
    """
    Displays a list of user-submitted content reports that need action.
    """
    # Group reports by audiobook to make the UI cleaner
    unresolved_reports = ContentReport.objects.filter(is_resolved=False)\
        .select_related('audiobook', 'reported_by')\
        .order_by('audiobook__title', '-created_at')

    reports_by_audiobook = defaultdict(list)
    for report in unresolved_reports:
        reports_by_audiobook[report.audiobook].append(report)

    # Convert to a list of tuples for template iteration, with a count of reports per book
    # This structure is easier to work with in the Django template
    grouped_reports = [
        (audiobook, reports, len(reports)) 
        for audiobook, reports in reports_by_audiobook.items()
    ]
    
    context = {
        'active_page': 'manage_content',
        'admin_user': request.admin_user,
        'grouped_reports': grouped_reports,
    }
    return render(request, 'admin/manage_content/admin_view_content_reports.html', context)


@require_POST
# REMOVED @login_required
@decorators.admin_role_required('full_access', 'manage_content', 'manage_support')
def admin_resolve_reports_view(request, audiobook_id):
    """
    Marks all reports for a specific audiobook as resolved.
    """
    admin_user = getattr(request, 'admin_user', None)
    reports_to_resolve = ContentReport.objects.filter(audiobook_id=audiobook_id, is_resolved=False)
    
    if reports_to_resolve.exists():
        updated_count = reports_to_resolve.update(
            is_resolved=True,
            resolved_by=admin_user,
            resolved_at=now()
        )
        messages.success(request, f"Successfully resolved {updated_count} report(s) for the audiobook.")
    else:
        messages.info(request, "No unresolved reports found for this audiobook.")

    return redirect('AudioXApp:admin_content_reports_list')