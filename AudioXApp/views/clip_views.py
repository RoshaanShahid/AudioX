# AudioXApp/views/clip_views.py

from django.shortcuts import get_object_or_404
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils.translation import gettext_lazy as G
from django.utils.translation import gettext
from django.core.files.storage import default_storage
from django.core.cache import cache
from django.urls import reverse
from urllib.parse import quote
import json
import os
import uuid
import logging
import requests
import re
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
from ..models import Chapter, Audiobook, User

# FFmpeg configuration - Docker and local compatibility
FFMPEG_PATH = os.getenv('FFMPEG_PATH', '/usr/bin/ffmpeg')  # Docker default

# Try to set FFmpeg path
try:
    if os.path.isfile(FFMPEG_PATH):
        AudioSegment.converter = FFMPEG_PATH
        print(f"FFmpeg found and configured at: {FFMPEG_PATH}")
    else:
        # Fallback for Windows development
        FFMPEG_INSTALL_ROOT = r"C:\Program Files\ffmpeg-2025-05-29-git-75960ac270-full_build"
        FFMPEG_BIN_PATH = os.path.join(FFMPEG_INSTALL_ROOT, "bin")
        FFMPEG_EXE = os.path.join(FFMPEG_BIN_PATH, "ffmpeg.exe")
        
        if os.path.isfile(FFMPEG_EXE):
            AudioSegment.converter = FFMPEG_EXE
            print(f"FFmpeg found and configured at: {FFMPEG_EXE}")
        else:
            print(f"WARNING: FFmpeg not found. Audio processing may be limited.")
except Exception as e:
    print(f"FFmpeg configuration error: {e}. Audio processing may be limited.")

logger = logging.getLogger(__name__)

TEMP_CLIP_DIR_NAME = 'generated_clips'
TEMP_CLIP_DIR_PATH = os.path.join(settings.MEDIA_ROOT, TEMP_CLIP_DIR_NAME)

if not os.path.exists(TEMP_CLIP_DIR_PATH):
    try:
        os.makedirs(TEMP_CLIP_DIR_PATH, exist_ok=True)
    except OSError as e:
        logger.error(f"Could not create temporary clip directory {TEMP_CLIP_DIR_PATH}: {e}")

# --- Generate Audio Clip View ---

@csrf_exempt
@require_POST
def generate_audio_clip(request):
    data = {}
    chapter_id_from_payload = "not_parsed_yet"
    msg_auth_required = gettext('Authentication required.')
    msg_invalid_json = gettext('Invalid JSON payload.')
    msg_missing_params = gettext('Missing required parameters (chapter_id, start_time_seconds, end_time_seconds).')
    msg_invalid_time_format = gettext('Invalid time format. Start and end times must be numbers.')
    msg_invalid_time_range = gettext('Invalid time range. End time must be after start time, and times cannot be negative.')
    msg_clip_too_long = gettext('Requested clip duration exceeds the maximum allowed limit (%(max_duration)s seconds).')
    msg_chapter_not_found_ext = gettext('Invalid chapter identifier format or chapter not found when parsing ext-ID.')
    msg_chapter_id_format_invalid = gettext('Invalid chapter identifier format.')
    msg_chapter_resolution_failed = gettext('Chapter resolution failed.')
    msg_chapter_not_found_generic = gettext('Chapter not found.')
    msg_permission_denied = gettext('You do not have permission to create a clip from this chapter.')
    msg_audio_source_missing_db = gettext('Audio source file missing.')
    msg_audio_source_missing_generic = gettext('No audio source available for this chapter.')
    msg_audio_source_no_access = gettext('Audio source file could not be accessed for processing.')
    msg_external_audio_retrieve_fail = gettext('Could not retrieve audio from external source.')
    msg_pydub_decode_error = gettext('Could not decode audio file. It might be corrupted or an unsupported format.')
    msg_pydub_file_not_found = gettext('Audio source file was not found during processing.')
    msg_pydub_processing_fail = gettext('Failed to process audio for clipping.')
    msg_audiobook_not_found_ext = gettext('Audiobook data for this chapter not found in cache.')
    msg_chapter_index_oob = gettext('Chapter index out of bounds.')
    msg_audio_url_missing_cache = gettext('Audio source URL missing for this external chapter.')
    msg_internal_resolve_error = gettext('Internal error resolving chapter data.')
    msg_unexpected_server_error = gettext('An unexpected server error occurred.')
    msg_ext_cache_empty = gettext('External chapter data temporarily unavailable.')
    msg_http404_generic = gettext('The requested chapter or audiobook was not found.')
    msg_clip_start_beyond_duration = gettext('Clip start time is beyond the chapter duration.')
    msg_clip_start_not_before_end = gettext('Clip start time must be before end time.')
    msg_clip_generated_successfully = gettext('Audio clip generated successfully.')

    try:
        if not request.user.is_authenticated:
            return JsonResponse({'status': 'error', 'message': msg_auth_required}, status=401)
        try:
            data = json.loads(request.body)
            chapter_id_from_payload = data.get('chapter_id')
            start_time_seconds = data.get('start_time_seconds')
            end_time_seconds = data.get('end_time_seconds')
        except json.JSONDecodeError:
            logger.warning("Invalid JSON payload for clip generation.")
            return JsonResponse({'status': 'error', 'message': msg_invalid_json}, status=400)

        if not all([chapter_id_from_payload, start_time_seconds is not None, end_time_seconds is not None]):
            logger.warning(f"Missing parameters for clip generation. Received: chapter_id={chapter_id_from_payload}, start={start_time_seconds}, end={end_time_seconds}")
            return JsonResponse({'status': 'error', 'message': msg_missing_params}, status=400)
        try:
            start_time_seconds = float(start_time_seconds)
            end_time_seconds = float(end_time_seconds)
        except ValueError:
            logger.warning(f"Invalid time format for clip generation: start={start_time_seconds}, end={end_time_seconds}")
            return JsonResponse({'status': 'error', 'message': msg_invalid_time_format}, status=400)

        if start_time_seconds < 0 or end_time_seconds <= start_time_seconds:
            logger.warning(f"Invalid time range for clip: start={start_time_seconds}, end={end_time_seconds}")
            return JsonResponse({'status': 'error', 'message': msg_invalid_time_range}, status=400)

        max_clip_duration = getattr(settings, 'MAX_AUDIO_CLIP_DURATION_SECONDS', 300)
        if (end_time_seconds - start_time_seconds) > max_clip_duration:
            logger.warning(f"Requested clip duration too long: {end_time_seconds - start_time_seconds}s for chapter {chapter_id_from_payload}") 
            return JsonResponse({'status': 'error', 'message': msg_clip_too_long % {'max_duration': max_clip_duration}}, status=400)
        
        chapter = None 
        audiobook_obj_for_perms = None 
        target_chapter_title_for_clip = "Unknown Chapter"
        target_audio_url_for_processing = None
        is_external_synthetic_id = False
        if isinstance(chapter_id_from_payload, str) and chapter_id_from_payload.startswith('ext-'):
            is_external_synthetic_id = True
        
        if not is_external_synthetic_id:
            try:
                parsed_pk = int(chapter_id_from_payload)
                db_chapter = get_object_or_404(Chapter.objects.select_related('audiobook'), pk=parsed_pk)
                audiobook_obj_for_perms = db_chapter.audiobook
                target_chapter_title_for_clip = db_chapter.chapter_name
                if db_chapter.external_audio_url:
                    target_audio_url_for_processing = db_chapter.external_audio_url
                elif db_chapter.audio_file and db_chapter.audio_file.name:
                    if default_storage.exists(db_chapter.audio_file.name):
                        target_audio_url_for_processing = db_chapter.audio_file.path 
                    else: raise FileNotFoundError(f"Local audio file {db_chapter.audio_file.name} not found for DB chapter {db_chapter.pk}.")
                else: raise ValueError(f"No audio source for DB chapter {db_chapter.pk}")
                logger.info(f"Processing DB Chapter PK: {db_chapter.pk} for Audiobook '{audiobook_obj_for_perms.title}'")
            except (ValueError, Chapter.DoesNotExist, FileNotFoundError) as e:
                logger.error(f"Error resolving DB chapter from ID '{chapter_id_from_payload}': {e}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': msg_chapter_not_found_generic}, status=404)
        else: 
            logger.info(f"Processing external chapter ID: {chapter_id_from_payload}")
            try:
                parts = chapter_id_from_payload.split('-')
                if len(parts) < 3: raise ValueError("Invalid ext ID format (not enough parts).")
                chapter_parsed_index = int(parts[-1])
                audiobook_slug = '-'.join(parts[1:-1]) 
                audiobook_obj_for_perms = get_object_or_404(Audiobook, slug=audiobook_slug)
                cache_key = 'librivox_archive_audiobooks_data_v7'
                external_data_cache = cache.get(cache_key)
                if not external_data_cache:
                    logger.error(f"External audiobook cache '{cache_key}' is empty.")
                    return JsonResponse({'status': 'error', 'message': msg_ext_cache_empty}, status=503)
                found_cached_book = None
                for source_key in ["librivox_audiobooks", "archive_genre_audiobooks", "archive_language_audiobooks"]:
                    if source_key == "librivox_audiobooks":
                        item_list = external_data_cache.get(source_key, [])
                        for book_dict in item_list:
                            if book_dict.get('slug') == audiobook_slug: found_cached_book = book_dict; break
                    else:
                        for _, book_list_items in external_data_cache.get(source_key, {}).items():
                            for book_dict in book_list_items:
                                if book_dict.get('slug') == audiobook_slug: found_cached_book = book_dict; break
                            if found_cached_book: break
                    if found_cached_book: break
                if not found_cached_book:
                    logger.error(f"Audiobook slug '{audiobook_slug}' not found in cache for {chapter_id_from_payload}.")
                    return JsonResponse({'status': 'error', 'message': msg_audiobook_not_found_ext}, status=404)
                cached_chapters = found_cached_book.get('chapters', [])
                if not (0 <= chapter_parsed_index < len(cached_chapters)):
                    logger.error(f"Chapter index {chapter_parsed_index} out of bounds for '{audiobook_slug}'.")
                    return JsonResponse({'status': 'error', 'message': msg_chapter_index_oob}, status=400)
                cached_chapter_info = cached_chapters[chapter_parsed_index]
                target_chapter_title_for_clip = cached_chapter_info.get('chapter_title', f"Chapter {chapter_parsed_index + 1}")
                target_audio_url_for_processing = cached_chapter_info.get('audio_url')
                if not target_audio_url_for_processing:
                    logger.error(f"No audio_url in cached chapter data for {chapter_id_from_payload}.")
                    return JsonResponse({'status': 'error', 'message': msg_audio_url_missing_cache}, status=500)
                logger.info(f"Using cached data for external chapter. Audiobook: '{audiobook_obj_for_perms.title}', Chapter: '{target_chapter_title_for_clip}'")
            except (IndexError, ValueError, Audiobook.DoesNotExist) as e_parse:
                logger.error(f"Error parsing ext ID '{chapter_id_from_payload}': {e_parse}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': msg_chapter_not_found_ext}, status=400)
        
        if not audiobook_obj_for_perms or not target_audio_url_for_processing:
            logger.error(f"Critical error: Failed to resolve audiobook or audio URL. Payload ID: '{chapter_id_from_payload}'.")
            return JsonResponse({'status': 'error', 'message': msg_internal_resolve_error}, status=500)
        
        audiobook_title_for_clip = audiobook_obj_for_perms.title
        is_accessible = False
        if request.user.is_staff: is_accessible = True
        elif audiobook_obj_for_perms.is_paid:
            if request.user.has_purchased_audiobook(audiobook_obj_for_perms): is_accessible = True
            elif request.user.subscription_type == 'PR': is_accessible = True 
        else: is_accessible = True
        if not is_accessible:
            logger.warning(f"User {request.user.username} forbidden to clip. Payload ID: {chapter_id_from_payload}.")
            return JsonResponse({'status': 'error', 'message': msg_permission_denied}, status=403)

        logger.info(f"User {request.user.username} creating clip for: '{audiobook_title_for_clip} - {target_chapter_title_for_clip}' from {start_time_seconds}s to {end_time_seconds}s. Source: {target_audio_url_for_processing}")
        
        actual_audio_file_path_for_pydub = None; temp_downloaded_file_path = None 
        try:
            if target_audio_url_for_processing.startswith('http://') or target_audio_url_for_processing.startswith('https://'):
                logger.info(f"Downloading external audio: {target_audio_url_for_processing}")
                try:
                    with requests.get(target_audio_url_for_processing, stream=True, timeout=60) as r: 
                        r.raise_for_status()
                        temp_filename = f"temp_dl_{uuid.uuid4().hex}.mp3" 
                        temp_downloaded_file_path = os.path.join(TEMP_CLIP_DIR_PATH, temp_filename)
                        with open(temp_downloaded_file_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                    actual_audio_file_path_for_pydub = temp_downloaded_file_path
                    logger.info(f"Successfully downloaded to {actual_audio_file_path_for_pydub}")
                except requests.exceptions.RequestException as e_req:
                    logger.error(f"Failed to download external audio {target_audio_url_for_processing}: {e_req}")
                    return JsonResponse({'status': 'error', 'message': msg_external_audio_retrieve_fail}, status=502)
            else: 
                actual_audio_file_path_for_pydub = target_audio_url_for_processing
                logger.info(f"Using local audio file: {actual_audio_file_path_for_pydub}")
            if not actual_audio_file_path_for_pydub or not os.path.exists(actual_audio_file_path_for_pydub):
                logger.error(f"Pydub source audio path invalid or DNE: {actual_audio_file_path_for_pydub}")
                return JsonResponse({'status': 'error', 'message': msg_audio_source_no_access}, status=500)

            logger.info(f"Pydub: Loading audio from: {actual_audio_file_path_for_pydub}")
            audio = AudioSegment.from_file(actual_audio_file_path_for_pydub)
            logger.info(f"Pydub: Loaded audio. Duration: {len(audio)/1000.0:.2f}s")
            start_ms = int(start_time_seconds * 1000); end_ms = int(end_time_seconds * 1000)
            actual_audio_duration_ms = len(audio)
            if start_ms >= actual_audio_duration_ms:
                logger.warning(f"Clip start time ({start_ms}ms) beyond audio duration ({actual_audio_duration_ms}ms).")
                return JsonResponse({'status': 'error', 'message': msg_clip_start_beyond_duration}, status=400)
            end_ms = min(end_ms, actual_audio_duration_ms)
            if start_ms >= end_ms:
                if start_ms == end_ms: logger.warning(f"Clip start and end times identical ({start_ms}ms).")
                else: 
                    logger.warning(f"Clip start time ({start_ms}ms) not before end time ({end_ms}ms).")
                    return JsonResponse({'status': 'error', 'message': msg_clip_start_not_before_end}, status=400)
            clip_segment = audio[start_ms:end_ms]
            chapter_pk_for_filename = chapter.pk if chapter and not is_external_synthetic_id else chapter_id_from_payload.replace("/", "_").replace(":", "_")
            safe_chapter_part = re.sub(r'[^\w_.)( -]', '', str(chapter_pk_for_filename))
            clip_filename = f"clip_{audiobook_obj_for_perms.slug}_{safe_chapter_part}_{uuid.uuid4().hex[:8]}.mp3"
            clip_filepath = os.path.join(TEMP_CLIP_DIR_PATH, clip_filename)
            os.makedirs(TEMP_CLIP_DIR_PATH, exist_ok=True)
            logger.info(f"Pydub: Exporting clip to {clip_filepath}")
            clip_segment.export(clip_filepath, format="mp3")
            logger.info(f"Pydub: Successfully exported clip to {clip_filepath}")
            clip_url_path = os.path.join(settings.MEDIA_URL, TEMP_CLIP_DIR_NAME, clip_filename)
            if clip_url_path.startswith("//"): clip_url_path = clip_url_path[1:]
            clip_full_url = request.build_absolute_uri(clip_url_path)

            return JsonResponse({'status': 'success', 'message': msg_clip_generated_successfully, 'clip_url': clip_full_url, 'filename': clip_filename, 'chapter_title': target_chapter_title_for_clip, 'audiobook_title': audiobook_title_for_clip})
        except CouldntDecodeError:
            logger.error(f"Pydub: Could not decode audio file {actual_audio_file_path_for_pydub}.", exc_info=True)
            return JsonResponse({'status': 'error', 'message': msg_pydub_decode_error}, status=500)
        except FileNotFoundError: 
            logger.error(f"Pydub: Audio file not found at {actual_audio_file_path_for_pydub}.", exc_info=True)
            return JsonResponse({'status': 'error', 'message': msg_pydub_file_not_found}, status=500)
        except Exception as e_process: 
            logger.error(f"Pydub or processing error for payload ID {chapter_id_from_payload}: {e_process}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': msg_pydub_processing_fail}, status=500)
        finally: 
            if temp_downloaded_file_path and os.path.exists(temp_downloaded_file_path):
                try: os.remove(temp_downloaded_file_path); logger.info(f"Cleaned up: {temp_downloaded_file_path}")
                except OSError as e_remove: logger.error(f"Error removing temp file {temp_downloaded_file_path}: {e_remove}")
    except Http404 as e: 
        logger.warning(f"Http404 resolving chapter/audiobook for payload ID '{chapter_id_from_payload}': {e}")
        return JsonResponse({'status': 'error', 'message': msg_http404_generic}, status=404)
    except Exception as e: 
        logger.error(f"Outer generic error in generate_audio_clip for payload chapter_id '{chapter_id_from_payload}': {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': msg_unexpected_server_error}, status=500)