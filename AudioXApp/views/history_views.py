from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from django.db.models import F
from .utils import _get_full_context
from ..models import Chapter, ListeningHistory, Audiobook, AudiobookViewLog
import logging
import json

logger = logging.getLogger(__name__)


@login_required
@require_POST
@csrf_protect
def update_listening_progress(request):
    """
    Updates or creates a listening history record for a specific chapter.
    This is called periodically by the audio player.
    """
    try:
        data = json.loads(request.body)
        chapter_id = data.get('chapter_id')
        position = float(data.get('position'))
        is_completed = bool(data.get('is_completed', False))

        logger.debug(f"Received progress update: chapter_id={chapter_id}, position={position}, completed={is_completed}")

        if not chapter_id or position is None:
            logger.warning(f"Missing chapter ID or position in progress update: chapter_id={chapter_id}, position={position}")
            return JsonResponse({'status': 'error', 'message': 'Chapter ID and position are required.'}, status=400)

        chapter = get_object_or_404(Chapter, pk=chapter_id)
        logger.debug(f"Chapter found for PK {chapter_id}: Title='{chapter.chapter_name}', Audiobook='{chapter.audiobook.title}'")

        history_obj, created = ListeningHistory.objects.update_or_create(
            user=request.user,
            chapter=chapter,
            defaults={
                'last_position_seconds': position,
                'is_completed': is_completed,
                'last_listened_at': timezone.now()
            }
        )

        action = "created" if created else "updated"
        logger.info(f"SUCCESS: Chapter history {action} for user {request.user.username} on chapter '{chapter.chapter_name}'. Position: {position}s, Completed: {is_completed}")
        
        return JsonResponse({'status': 'success', 'message': f'Progress {action}.'})

    except Chapter.DoesNotExist:
        logger.error(f"Chapter not found for received chapter_id: {chapter_id}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Chapter not found.'}, status=404)
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        logger.error(f"Invalid data format for update_listening_progress from user {request.user.username}: {e}, Raw body: {request.body.decode()}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Invalid data format.'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in update_listening_progress for user {request.user.username}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected server error occurred.'}, status=500)


@login_required
@require_POST
@csrf_protect
def record_audiobook_visit(request):
    """
    Records a user's visit to an audiobook detail page.
    Increments the view count only once per user per 24 hours.
    Ensures a listening history entry exists for the first chapter on the first countable visit.
    """
    try:
        data = json.loads(request.body)
        audiobook_id = data.get('audiobook_id')
        
        if not audiobook_id:
            return JsonResponse({'status': 'error', 'message': 'Audiobook ID is required.'}, status=400)

        audiobook = get_object_or_404(Audiobook, pk=audiobook_id)
        
        twenty_four_hours_ago = timezone.now() - timezone.timedelta(hours=24)
        recent_view_exists = AudiobookViewLog.objects.filter(
            audiobook=audiobook,
            user=request.user,
            viewed_at__gte=twenty_four_hours_ago
        ).exists()
        
        view_counted = False
        if not recent_view_exists:
            with transaction.atomic():
                # Create the view log to prevent re-counting for 24 hours
                AudiobookViewLog.objects.create(audiobook=audiobook, user=request.user)
                # Increment the audiobook's total views
                Audiobook.objects.filter(pk=audiobook.pk).update(total_views=F('total_views') + 1)
                view_counted = True
                
                # Find the first chapter of the audiobook
                first_chapter = audiobook.chapters.filter(chapter_order=1).first()
                if not first_chapter:
                    first_chapter = audiobook.chapters.order_by('chapter_order').first()

                # On a new, countable view, ensure a history record exists for the first chapter
                # without overwriting progress if it already exists (e.g., if user listened before).
                # This places the audiobook in their history without resetting progress.
                if first_chapter:
                    ListeningHistory.objects.get_or_create(
                        user=request.user,
                        chapter=first_chapter,
                        defaults={
                            'last_position_seconds': 0,
                            'is_completed': False,
                            'last_listened_at': timezone.now()
                        }
                    )
        
        # This will now correctly log whether the view was new or a repeat visit within 24h
        logger.info(f"Audiobook visit recorded for user {request.user.username} on audiobook '{audiobook.title}'. View counted: {view_counted}")
        
        return JsonResponse({
            'status': 'success', 
            'message': 'Visit recorded.',
            'view_counted': view_counted
        })

    except Audiobook.DoesNotExist:
        logger.error(f"Audiobook not found for ID: {audiobook_id}")
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        logger.error(f"Invalid data format for record_audiobook_visit: {e}, Raw body: {request.body.decode()}")
        return JsonResponse({'status': 'error', 'message': 'Invalid data format.'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in record_audiobook_visit: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected server error occurred.'}, status=500)


@login_required
@require_POST
@csrf_protect
def clear_listening_history(request):
    """
    Deletes all listening history records for the currently logged-in user.
    """
    try:
        deleted_count, _ = ListeningHistory.objects.filter(user=request.user).delete()
        
        logger.info(f"Cleared {deleted_count} listening history entries for user {request.user.username}")
        
        return JsonResponse({
            'status': 'success', 
            'message': f'Successfully cleared {deleted_count} history entries.',
            'deleted_count': deleted_count
        })

    except Exception as e:
        logger.error(f"Unexpected error in clear_listening_history for user {request.user.username}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected server error occurred.'}, status=500)


@login_required
def listening_history_page(request):
    """
    Renders the user's listening history page, showing the most recently
    listened-to audiobooks.
    """
    try:
        # Get all history items for the user, pre-fetching related data for efficiency
        history_items = ListeningHistory.objects.filter(user=request.user).select_related(
            'chapter', 
            'chapter__audiobook',
            'chapter__audiobook__creator'
        ).order_by('-last_listened_at')

        # Use a dictionary to group history by audiobook, ensuring we only show the latest progress per book
        audiobook_history = {}
        for item in history_items:
            audiobook = item.chapter.audiobook
            if audiobook.audiobook_id not in audiobook_history:
                progress_percentage = 0
                if audiobook.duration_in_seconds and audiobook.duration_in_seconds > 0:
                    progress_percentage = min(100, (item.last_position_seconds / audiobook.duration_in_seconds) * 100)
                
                audiobook_history[audiobook.audiobook_id] = {
                    'audiobook': audiobook,
                    'current_chapter': item.chapter,
                    'progress_seconds': item.last_position_seconds,
                    'progress_percentage': round(progress_percentage, 1),
                    'last_listened_at': item.last_listened_at,
                    'is_completed': item.is_completed
                }

        # Convert the dictionary to a list and sort by the most recent listen time
        history_list = list(audiobook_history.values())
        history_list.sort(key=lambda x: x['last_listened_at'], reverse=True)

        page_specific_context = {
            'history_items': history_list,
            'page_title': 'My Listening History',
            'meta_description': 'View your audiobook listening history and resume where you left off.'
        }
        common_context = _get_full_context(request)
        final_context = {**common_context, **page_specific_context}
        return render(request, 'user/listening_history.html', final_context)
        
    except Exception as e:
        logger.error(f"Error rendering listening_history_page for user {request.user.username}: {e}", exc_info=True)
        return render(request, 'user/listening_history.html', {'error_message': 'Could not load history.'}, status=500)