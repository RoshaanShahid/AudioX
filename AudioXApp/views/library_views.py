# AudioXApp/views/library_views.py

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
import json
from .utils import _get_full_context
from ..models import User, Audiobook, UserLibraryItem, Creator
import logging

logger = logging.getLogger(__name__)

# --- Toggle Library Item (AJAX) ---

@login_required
@require_POST
def toggle_library_item(request):
    audiobook_id_for_error = 'Unknown ID'
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            audiobook_id = data.get('audiobook_id')
            audiobook_id_for_error = audiobook_id if audiobook_id else 'None provided in JSON'
        else:
            logger.warning(f"Toggle library item: Received non-JSON request from user {request.user.username}. Content-Type: {request.content_type}")
            return JsonResponse({'status': 'error', 'message': 'Invalid request format. Expected JSON.'}, status=400)

        if not audiobook_id:
            return JsonResponse({'status': 'error', 'message': 'Audiobook ID is required.'}, status=400)

        audiobook = get_object_or_404(Audiobook, audiobook_id=str(audiobook_id))
        user = request.user

        library_item, created = UserLibraryItem.objects.get_or_create(
            user=user,
            audiobook=audiobook
        )

        if created:
            action_taken = 'added'
            message = f"'{audiobook.title}' added to your library."
            is_in_library = True
        else:
            library_item.delete()
            action_taken = 'removed'
            message = f"'{audiobook.title}' removed from your library."
            is_in_library = False

        logger.info(f"Audiobook '{audiobook.title}' {action_taken} for user {user.username}'s library.")
        return JsonResponse({'status': 'success', 'message': message, 'action': action_taken, 'is_in_library': is_in_library})

    except Audiobook.DoesNotExist:
        logger.error(f"Toggle library item: Audiobook not found. ID: {audiobook_id_for_error}, User: {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except json.JSONDecodeError:
        logger.error(f"Toggle library item: Invalid JSON received for user {request.user.username}. Request body: {request.body[:200]}")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON format in request.'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in toggle_library_item for user {request.user.username}, audiobook_id: {audiobook_id_for_error}: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)

# --- My Library Page ---

@login_required
def my_library_page(request):
    try:
        library_items_qs = UserLibraryItem.objects.filter(user=request.user).select_related(
            'audiobook',
            'audiobook__creator', 
            'audiobook__creator__user'
        ).order_by('-added_at')

        saved_audiobooks = [item.audiobook for item in library_items_qs]

        page_specific_context = {
            'saved_audiobooks': saved_audiobooks,
            'page_title': 'My Library',
            'meta_description': 'Your saved audiobooks and playlists.'
        }
        
        common_context = _get_full_context(request)
        final_context = {**common_context, **page_specific_context}

        return render(request, 'user/my_library.html', final_context)
    except Exception as e:
        logger.error(f"Error rendering my_library_page for user {request.user.username}: {str(e)}", exc_info=True)
        
        page_specific_context_error = {
            'saved_audiobooks': [],
            'page_title': 'My Library',
            'error_message': 'Could not load your library at this time. Please try again later.'
        }
        common_context_error = _get_full_context(request)
        final_context_error = {**common_context_error, **page_specific_context_error}
        
        return render(request, 'user/my_library.html', final_context_error, status=500)