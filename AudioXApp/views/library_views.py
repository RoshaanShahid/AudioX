# AudioXApp/views/library_views.py

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
# from django.views.decorators.csrf import csrf_protect # CSRF is typically handled by middleware for AJAX
from django.contrib.auth.decorators import login_required
# from django.utils import timezone # Not used in this snippet
# from django.db.models import Prefetch # Not used in this snippet
import json # Import the json module

from ..models import User, Audiobook, UserLibraryItem, Creator # Adjust import if needed

import logging
logger = logging.getLogger(__name__)

@login_required
@require_POST # Ensures this view only accepts POST requests
# @csrf_protect # Django's CsrfViewMiddleware handles this for AJAX if X-CSRFToken header is sent
def toggle_library_item(request):
    """
    Adds or removes an audiobook from the user's library.
    Expects 'audiobook_id' in JSON POST data.
    """
    audiobook_id_for_error = 'Unknown ID' # For logging in case of early failure
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            audiobook_id = data.get('audiobook_id')
            audiobook_id_for_error = audiobook_id if audiobook_id else 'None provided in JSON'
        else:
            # Fallback or error if content type is not JSON, as JS is expected to send JSON
            logger.warning(f"Toggle library item: Received non-JSON request from user {request.user.username}. Content-Type: {request.content_type}")
            return JsonResponse({'status': 'error', 'message': 'Invalid request format. Expected JSON.'}, status=400)

        if not audiobook_id:
            return JsonResponse({'status': 'error', 'message': 'Audiobook ID is required.'}, status=400)

        # Ensure audiobook_id is of the correct type for querying, e.g., str or int.
        # If your Audiobook.audiobook_id is an IntegerField, you might need int(audiobook_id).
        # Assuming Audiobook.audiobook_id is a CharField or UUIDField that can be queried as a string.
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
            # If it already exists, remove it (toggle behavior)
            library_item.delete()
            action_taken = 'removed'
            message = f"'{audiobook.title}' removed from your library."
            is_in_library = False

        logger.info(f"Audiobook '{audiobook.title}' {action_taken} for user {user.username}'s library.")
        return JsonResponse({
            'status': 'success',
            'message': message,
            'action': action_taken, # 'added' or 'removed'
            'is_in_library': is_in_library # boolean indicating current state
        })

    except Audiobook.DoesNotExist:
        logger.error(f"Toggle library item: Audiobook not found. ID: {audiobook_id_for_error}, User: {request.user.username}")
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except json.JSONDecodeError:
        logger.error(f"Toggle library item: Invalid JSON received for user {request.user.username}. Request body: {request.body[:200]}") # Log part of the body
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON format in request.'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in toggle_library_item for user {request.user.username}, audiobook_id: {audiobook_id_for_error}: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)


@login_required
def my_library_page(request):
    """
    Displays the audiobooks saved in the user's library.
    """
    try:
        library_items_qs = UserLibraryItem.objects.filter(user=request.user).select_related(
            'audiobook',
            'audiobook__creator', 
            'audiobook__creator__user' 
        ).order_by('-added_at')

        saved_audiobooks = [item.audiobook for item in library_items_qs]

        context = {
            'saved_audiobooks': saved_audiobooks,
            'page_title': 'My Library',
            'meta_description': 'Your saved audiobooks and playlists.'
        }
        return render(request, 'user/my_library.html', context)
    except Exception as e:
        logger.error(f"Error rendering my_library_page for user {request.user.username}: {str(e)}", exc_info=True)
        context = {
            'saved_audiobooks': [],
            'page_title': 'My Library',
            'error_message': 'Could not load your library at this time. Please try again later.'
        }
        return render(request, 'user/my_library.html', context, status=500)