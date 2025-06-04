# AudioXApp/views/history_views.py

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect # Kept as per original
from django.contrib.auth.decorators import login_required
from django.utils import timezone
# from django.db.models import Prefetch # Not used in this snippet

# If utils.py is in the same directory (AudioXApp/views/utils.py):
from .utils import _get_full_context
# If utils.py is one level up (AudioXApp/utils.py) and views is AudioXApp/views/:
# from ..utils import _get_full_context

from ..models import User, Audiobook, Chapter, ListeningHistory 

import logging
import json

logger = logging.getLogger(__name__)

@login_required
@require_POST
@csrf_protect # Kept as per original
def update_listening_progress(request):
    # ... (Your existing update_listening_progress code remains unchanged) ...
    try:
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received for progress update by user: {request.user.username if request.user.is_authenticated else 'Anonymous'}")
                return JsonResponse({'status': 'error', 'message': 'Invalid JSON format.'}, status=400)
            
            audiobook_id = data.get('audiobook_id')
            progress_seconds_str = str(data.get('progress_seconds', '0')) 
            chapter_id_str = data.get('chapter_id') 
            if chapter_id_str is not None: 
                chapter_id_str = str(chapter_id_str)
        else: 
            logger.warning(f"Progress update received with unexpected content type: {request.content_type} by user: {request.user.username if request.user.is_authenticated else 'Anonymous'}")
            return JsonResponse({'status': 'error', 'message': 'Unsupported content type. Expected application/json.'}, status=415)

        if not audiobook_id: 
            logger.warning(f"Update progress attempt with no or invalid audiobook_id ('{audiobook_id}') by user: {request.user.username if request.user.is_authenticated else 'Anonymous'}")
            return JsonResponse({'status': 'error', 'message': 'Audiobook ID is required.'}, status=400)

        try:
            progress_seconds = int(float(progress_seconds_str))
            if progress_seconds < 0:
                progress_seconds = 0
        except ValueError:
            logger.warning(f"Invalid progress_seconds format: '{progress_seconds_str}' by user {request.user.username if request.user.is_authenticated else 'Anonymous'}")
            return JsonResponse({'status': 'error', 'message': 'Invalid progress format.'}, status=400)

        audiobook = get_object_or_404(Audiobook, audiobook_id=str(audiobook_id)) 
        
        current_chapter_obj = None
        if chapter_id_str and chapter_id_str not in ['null', 'undefined', '']:
            try:
                if chapter_id_str.startswith('ext-'):
                    logger.info(f"Received external chapter_id '{chapter_id_str}' for progress update. Current_chapter will not be set in DB. User: {request.user.username}")
                else:
                    current_chapter_obj = Chapter.objects.get(chapter_id=chapter_id_str, audiobook=audiobook)
            except Chapter.DoesNotExist:
                logger.warning(f"Chapter_id '{chapter_id_str}' not found or does not belong to audiobook '{audiobook_id}' for user {request.user.username if request.user.is_authenticated else 'Anonymous'}.")
            except ValueError:
                logger.warning(f"Invalid chapter_id format for DB lookup: '{chapter_id_str}' by user {request.user.username if request.user.is_authenticated else 'Anonymous'}")

        history_entry, created = ListeningHistory.objects.update_or_create(
            user=request.user,
            audiobook=audiobook,
            defaults={
                'progress_seconds': progress_seconds,
                'current_chapter': current_chapter_obj, 
                'last_listened_at': timezone.now()
            }
        )
        
        action = "created" if created else "updated"
        chapter_name_log = current_chapter_obj.chapter_name if current_chapter_obj else (chapter_id_str if chapter_id_str else 'N/A')
        logger.info(f"Listening progress {action} for user {request.user.username} on audiobook '{audiobook.title}'. Progress: {progress_seconds}s, Chapter: {chapter_name_log}")
        return JsonResponse({'status': 'success', 'message': f'Progress {action}.'})

    except Audiobook.DoesNotExist:
        logger.error(f"Audiobook not found during progress update. ID: {audiobook_id if 'audiobook_id' in locals() else 'Not Parsed'}, User: {request.user.username if request.user.is_authenticated else 'Anonymous'}")
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except Exception as e:
        logger.error(f"Unexpected error in update_listening_progress for user {request.user.username if request.user.is_authenticated else 'Anonymous'}: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred while updating progress.'}, status=500)


@login_required
def listening_history_page(request):
    """
    Displays the listening history for the logged-in user.
    """
    try:
        history_items = ListeningHistory.objects.filter(user=request.user).select_related(
            'audiobook',
            'audiobook__creator', 
            'current_chapter'
        ).order_by('-last_listened_at')

        # --- MODIFICATION START ---
        page_specific_context = {
            'history_items': history_items,
            'page_title': 'My Listening History',
            'meta_description': 'View your audiobook listening history and resume where you left off.'
        }

        common_context = _get_full_context(request)
        final_context = {**common_context, **page_specific_context}
        # --- MODIFICATION END ---

        return render(request, 'user/listening_history.html', final_context) # Use final_context

    except Exception as e:
        logger.error(f"Error rendering listening_history_page for user {request.user.username if request.user.is_authenticated else 'Anonymous'}: {str(e)}", exc_info=True)
        
        # --- MODIFICATION START (for error case too) ---
        page_specific_context_error = {
            'history_items': [],
            'page_title': 'My Listening History',
            'error_message': 'Could not load your listening history at this time. Please try again later.',
            'meta_description': 'View your audiobook listening history.' # Added meta_description
        }
        common_context_error = _get_full_context(request) # Still provide common context
        final_context_error = {**common_context_error, **page_specific_context_error}
        # --- MODIFICATION END ---
        
        return render(request, 'user/listening_history.html', final_context_error, status=500)