# AudioXApp/views/history_views.py

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Prefetch


from ..models import User, Audiobook, Chapter, ListeningHistory, Creator 

import logging
logger = logging.getLogger(__name__)

@login_required
@require_POST # Ensures this view only accepts POST requests
@csrf_protect   # Ensures CSRF token is present and valid for POST
def update_listening_progress(request):
    """
    Handles AJAX requests to update the listening progress for a user and an audiobook.
    Expects 'audiobook_id' and 'progress_seconds' in POST data.
    'chapter_id' is optional.
    """
    try:
        audiobook_id = request.POST.get('audiobook_id')
        # Convert progress_seconds to float first for flexibility, then to int
        progress_seconds_str = request.POST.get('progress_seconds', '0')
        progress_seconds = int(float(progress_seconds_str))
        
        chapter_id = request.POST.get('chapter_id', None)

        if not audiobook_id:
            logger.warning(f"Update progress attempt with no audiobook_id by user: {request.user.user_id}")
            return JsonResponse({'status': 'error', 'message': 'Audiobook ID is required.'}, status=400)

        # Use get_object_or_404 for cleaner handling of non-existent objects
        audiobook = get_object_or_404(Audiobook, audiobook_id=audiobook_id)
        
        current_chapter_obj = None
        if chapter_id and chapter_id != 'null' and chapter_id != 'undefined': # Check for JS null/undefined strings
            try:
                # Ensure chapter belongs to the audiobook for integrity
                current_chapter_obj = get_object_or_404(Chapter, chapter_id=chapter_id, audiobook=audiobook)
            except Chapter.DoesNotExist:
                logger.warning(f"Invalid chapter_id '{chapter_id}' provided for audiobook '{audiobook_id}' by user {request.user.user_id}")
                # Depending on strictness, you might choose to not fail the entire update
                # For now, we'll allow progress update without a valid chapter if chapter_id was problematic
                pass 
            except ValueError: # If chapter_id is not a valid integer
                logger.warning(f"Invalid format for chapter_id '{chapter_id}' for audiobook '{audiobook_id}' by user {request.user.user_id}")
                pass


        # update_or_create is efficient for this use case
        history_entry, created = ListeningHistory.objects.update_or_create(
            user=request.user,
            audiobook=audiobook,
            defaults={
                'progress_seconds': progress_seconds,
                'current_chapter': current_chapter_obj,
                'last_listened_at': timezone.now() # This will be set by auto_now=True on the model field as well
            }
        )
        
        action = "created" if created else "updated"
        logger.info(f"Listening progress {action} for user {request.user.username} on audiobook '{audiobook.title}'. Progress: {progress_seconds}s, Chapter: {current_chapter_obj.chapter_name if current_chapter_obj else 'N/A'}")
        return JsonResponse({'status': 'success', 'message': f'Progress {action}.'})

    except Audiobook.DoesNotExist:
        logger.error(f"Audiobook not found during progress update. ID: {audiobook_id}, User: {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except ValueError as ve: # Handles issues with converting progress_seconds
        logger.error(f"Invalid progress format during update. User: {request.user.username}, Progress: '{progress_seconds_str}'. Error: {ve}")
        return JsonResponse({'status': 'error', 'message': 'Invalid progress format.'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in update_listening_progress for user {request.user.username}: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred while updating progress.'}, status=500)


@login_required
@ensure_csrf_cookie # Good practice for pages that might contain forms or JS making POSTs, though not strictly needed if this page is read-only.
def listening_history_page(request):
    """
    Displays the listening history for the logged-in user.
    """
    try:
        # Eager load related Audiobook and Chapter data to reduce DB queries in the template
        # Also prefetch creator information if you display it on the history card
        history_items = ListeningHistory.objects.filter(user=request.user).select_related(
            'audiobook',          # Direct foreign key
            'current_chapter',    # Direct foreign key
            'audiobook__creator', # Nested foreign key (Audiobook -> Creator)
            'audiobook__creator__user' # Further nesting if you need User details of Creator
        ).order_by('-last_listened_at') # Already default ordering in model, but explicit here is fine

        # Example of prefetching only specific fields from related models for optimization:
        # history_items = ListeningHistory.objects.filter(user=request.user).prefetch_related(
        #     Prefetch('audiobook', queryset=Audiobook.objects.only('audiobook_id', 'title', 'slug', 'cover_image', 'author', 'duration')),
        #     Prefetch('current_chapter', queryset=Chapter.objects.only('chapter_id', 'chapter_name')),
        #     Prefetch('audiobook__creator', queryset=Creator.objects.only('creator_name')) 
        # ).order_by('-last_listened_at')


        context = {
            'history_items': history_items,
            'page_title': 'My Listening History',
            'meta_description': 'View your audiobook listening history and resume where you left off.' # For SEO
        }
        return render(request, 'user/listening_history.html', context)
    except Exception as e:
        logger.error(f"Error rendering listening_history_page for user {request.user.username}: {str(e)}", exc_info=True)
        context = {
            'history_items': [],
            'page_title': 'My Listening History',
            'error_message': 'Could not load your listening history at this time. Please try again later.'
        }
        return render(request, 'user/listening_history.html', context, status=500)

