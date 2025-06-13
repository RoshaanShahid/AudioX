# AudioXApp/views/creator_views/creator_audiobook_views.py

import json
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
import os
import logging
import asyncio
from io import BytesIO # Import BytesIO
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, Http404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods, require_GET
from django.views.decorators.csrf import csrf_protect
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.db.models import Sum, F, Value, Case, When, DecimalField, OuterRef, Subquery, Exists, Count
from django.utils import timezone
from django.urls import reverse
from django.core.files.storage import default_storage
from django.template.defaultfilters import filesizeformat
from django.utils.text import slugify
from django.contrib.messages import get_messages
from django.core.serializers.json import DjangoJSONEncoder
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from mutagen.mp3 import MP3, HeaderNotFoundError as MP3HeaderNotFoundError
from mutagen.wave import WAVE, error as WaveError
from mutagen.mp4 import MP4, MP4StreamInfoError
from mutagen.oggvorbis import OggVorbis, OggVorbisHeaderError
from mutagen.flac import FLAC, FLACNoHeaderError
from typing import Optional
from ...models import (
    User, Creator, Audiobook, Chapter,
    CreatorEarning, AudiobookViewLog
)
from ..utils import _get_full_context
from ..decorators import creator_required
from .creator_tts_views import (
    EDGE_TTS_VOICES_BY_LANGUAGE,
    ALL_EDGE_TTS_VOICES_MAP,
    LANGUAGE_GENRE_MAPPING,
    generate_audio_edge_tts_async,
    extract_text_from_pdf,
    extract_text_from_docx
)

logger = logging.getLogger(__name__)

EARNING_PER_VIEW = Decimal(getattr(settings, 'CREATOR_EARNING_PER_FREE_VIEW', '1.00'))
GENRE_OTHER_VALUE = '_OTHER_'

# --- Helper Functions ---

def get_audio_duration(file_obj_or_path):
    """
    Extracts the duration of an audio file using mutagen.
    Supports file objects (like InMemoryUploadedFile) or file paths.
    
    If given a file-like object (e.g., InMemoryUploadedFile, ContentFile),
    it reads its content into BytesIO to avoid disturbing the original
    file pointer, preventing "I/O operation on closed file" errors.
    """
    duration = None
    filename = None
    file_to_read = None
    temp_file_for_mutagen = None # To hold BytesIO or a path to be opened by mutagen

    if isinstance(file_obj_or_path, str):
        filename = os.path.basename(file_obj_or_path)
        file_to_read = file_obj_or_path # This is a path, mutagen will open it
    elif hasattr(file_obj_or_path, 'name'):
        filename = file_obj_or_path.name
        if isinstance(file_obj_or_path, TemporaryUploadedFile):
            file_to_read = file_obj_or_path.temporary_file_path() # Get path for TemporaryUploadedFile
        elif isinstance(file_obj_or_path, (InMemoryUploadedFile, ContentFile)):
            # For in-memory files, read content into BytesIO to preserve original stream
            try:
                # Ensure the original file-like object is at the beginning
                original_position = file_obj_or_path.tell()
                file_obj_or_path.seek(0)
                temp_file_for_mutagen = BytesIO(file_obj_or_path.read())
                file_obj_or_path.seek(original_position) # Restore original position
            except Exception as e_copy:
                logger.warning(f"Could not read content from in-memory file '{filename}' into BytesIO for duration: {e_copy}")
                return None
        else:
            if hasattr(file_obj_or_path, 'path'): # Fallback for other file-like objects with a path attribute
                file_to_read = file_obj_or_path.path
            else:
                logger.error(f"Unsupported file object type for duration extraction: {type(file_obj_or_path)}")
                return None

    if file_to_read: # If it's a path (either original string or from TemporaryUploadedFile)
        temp_file_for_mutagen = file_to_read

    if temp_file_for_mutagen is None:
        logger.error(f"No valid readable source determined for duration extraction of '{filename}'.")
        return None

    try:
        ext = os.path.splitext(filename)[1].lower()
        audio = None
        if ext in ['.mp3']:
            audio = MP3(temp_file_for_mutagen)
        elif ext in ['.wav']:
            audio = WAVE(temp_file_for_mutagen)
        elif ext in ['.m4a', '.mp4', '.m4b', '.aac']:
            audio = MP4(temp_file_for_mutagen)
        elif ext in ['.ogg', '.oga']:
            audio = OggVorbis(temp_file_for_mutagen)
        elif ext in ['.flac']:
            audio = FLAC(temp_file_for_mutagen)
        else:
            logger.warning(f"Unsupported audio format for duration extraction: {filename} (extension: {ext})")
            return None
        
        if audio and audio.info and hasattr(audio.info, 'length'):
            duration = audio.info.length
        else:
            logger.warning(f"Could not retrieve audio info for {filename}. Mutagen may not have found a valid stream.")
            return None

        return float(duration) if duration is not None else None
    except (MP3HeaderNotFoundError, WaveError, MP4StreamInfoError, OggVorbisHeaderError, FLACNoHeaderError) as e:
        logger.warning(f"Mutagen error extracting duration for {filename}: {type(e).__name__} - {e}")
    except Exception as e:
        logger.error(f"Unexpected error extracting duration for {filename}: {e}", exc_info=True)
    finally:
        # Close BytesIO object if created
        if isinstance(temp_file_for_mutagen, BytesIO):
            temp_file_for_mutagen.close()
    return None

def _reorder_chapters(audiobook):
    """Re-orders the chapters of an audiobook sequentially starting from 1."""
    chapters = Chapter.objects.filter(audiobook=audiobook).order_by('chapter_order')
    for i, chapter in enumerate(chapters, 1):
        if chapter.chapter_order != i:
            Chapter.objects.filter(pk=chapter.pk).update(chapter_order=i)
    logger.info(f"Re-ordered chapters for audiobook '{audiobook.slug}'.")


# --- View Logging ---

@login_required
@require_POST
@csrf_protect
def log_audiobook_view(request):
    """
    Logs a view for an audiobook and potentially awards earnings to the creator.
    A view is logged only once per user per audiobook within a 24-hour period.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'User not authenticated.'}, status=401)
    try:
        data = json.loads(request.body)
        audiobook_id_str = data.get('audiobook_id')
    except json.JSONDecodeError:
        logger.warning(f"log_audiobook_view: Invalid JSON payload from user {request.user.username}.")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON payload.'}, status=400)
    if not audiobook_id_str:
        logger.warning(f"log_audiobook_view: Audiobook ID missing in payload from user {request.user.username}.")
        return JsonResponse({'status': 'error', 'message': 'Audiobook ID is required.'}, status=400)
    try:
        audiobook_id = int(audiobook_id_str)
    except ValueError:
        logger.warning(f"log_audiobook_view: Invalid Audiobook ID format '{audiobook_id_str}' from user {request.user.username}.")
        return JsonResponse({'status': 'error', 'message': 'Invalid Audiobook ID format.'}, status=400)
    try:
        audiobook = get_object_or_404(Audiobook.objects.select_related('creator'), pk=audiobook_id)
        twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
        recent_view_exists = AudiobookViewLog.objects.filter(audiobook=audiobook, user=request.user, viewed_at__gte=twenty_four_hours_ago).exists()
        if recent_view_exists:
            return JsonResponse({'status': 'success', 'message': 'View already logged recently.', 'total_views': audiobook.total_views})
        with transaction.atomic():
            audiobook_locked = Audiobook.objects.select_for_update().get(pk=audiobook.pk)
            AudiobookViewLog.objects.create(audiobook=audiobook_locked, user=request.user)
            audiobook_locked.total_views = F('total_views') + 1
            audiobook_locked.save(update_fields=['total_views'])
            audiobook_locked.refresh_from_db(fields=['total_views'])
            if not audiobook_locked.is_paid and audiobook_locked.creator and audiobook_locked.creator.is_approved:
                creator = audiobook_locked.creator
                earned_amount_for_view = EARNING_PER_VIEW
                Creator.objects.filter(pk=creator.pk).update(available_balance=F('available_balance') + earned_amount_for_view, total_earning=F('total_earning') + earned_amount_for_view)
                CreatorEarning.objects.create(creator=creator, audiobook=audiobook_locked, earning_type='view', amount_earned=earned_amount_for_view, transaction_date=timezone.now(), audiobook_title_at_transaction=audiobook_locked.title, notes=f"Earning from 1 view on '{audiobook_locked.title}' (24hr rule applied).")
                logger.info(f"View logged and earning processed for user {request.user.username}, audiobook ID {audiobook_id}.")
            else:
                logger.info(f"View logged for user {request.user.username}, audiobook ID {audiobook_id} (paid book or no active creator, no view earning).")
            return JsonResponse({'status': 'success', 'message': 'View logged successfully.', 'total_views': audiobook_locked.total_views})
    except Audiobook.DoesNotExist:
        logger.warning(f"log_audiobook_view: Audiobook not found for ID {audiobook_id}, user {request.user.username}.")
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except Exception as e:
        logger.error(f"log_audiobook_view: Internal error for user {request.user.username}, audiobook ID {audiobook_id}. Error: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An internal error occurred.'}, status=500)

# --- Audiobook Management Views ---

@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_upload_audiobook(request):
    """
    Handles the creation of a new audiobook, including its details and chapters.
    Supports uploading audio files, generating TTS from text, or generating TTS from documents.
    """
    creator = request.creator
    form_errors = {}
    submitted_values = {}
    submitted_chapters_for_template = []
    edge_tts_voices_by_lang_json = json.dumps(EDGE_TTS_VOICES_BY_LANGUAGE)
    language_genre_mapping_json = json.dumps(LANGUAGE_GENRE_MAPPING)

    if request.method == 'POST':
        submitted_values = request.POST.copy()
        title = submitted_values.get('title', '').strip()
        author = submitted_values.get('author', '').strip()
        narrator = submitted_values.get('narrator', '').strip()
        language = submitted_values.get('language', '').strip()
        genre_from_select = submitted_values.get('genre', '').strip()
        genre_other_text = submitted_values.get('genre_other_text', '').strip()
        actual_genre_to_save = ""
        description = submitted_values.get('description', '').strip()
        cover_image_file = request.FILES.get('cover_image')
        pricing_type = submitted_values.get('pricing_type')
        price_str = submitted_values.get('price', '0').strip()
        is_paid = (pricing_type == 'paid')
        price = Decimal('0.00')

        if not title: form_errors['title'] = "Audiobook title is required."
        if not author: form_errors['author'] = "Author name is required."
        if not narrator: form_errors['narrator'] = "Narrator name is required."
        if not language:
            form_errors['language'] = "Language is required."
        elif language not in LANGUAGE_GENRE_MAPPING:
            if not genre_from_select:
                form_errors['genre'] = f"Genre is required for language '{language}'."
            else:
                actual_genre_to_save = genre_from_select
        if language in LANGUAGE_GENRE_MAPPING:
            if not genre_from_select:
                form_errors['genre'] = "Genre selection is required."
            elif genre_from_select == GENRE_OTHER_VALUE:
                if not genre_other_text:
                    form_errors['genre_other_text'] = "Please specify your genre if 'Others' is selected."
                    form_errors.setdefault('genre', "Please specify your 'Other' genre.")
                else:
                    actual_genre_to_save = genre_other_text
            else:
                valid_genres_for_lang = [g['value'] for g in LANGUAGE_GENRE_MAPPING.get(language, [])]
                if genre_from_select not in valid_genres_for_lang:
                    form_errors['genre'] = f"Invalid genre '{genre_from_select}' selected for {language}."
                else:
                    actual_genre_to_save = genre_from_select
        submitted_values['genre'] = genre_from_select
        submitted_values['genre_other_text'] = genre_other_text

        if not description: form_errors['description'] = "Audiobook description is required."
        if not cover_image_file:
            form_errors['cover_image'] = "Cover image is required."
        elif cover_image_file:
            max_cover_size = 2 * 1024 * 1024
            allowed_cover_types = ['image/jpeg', 'image/png', 'image/jpg']
            if cover_image_file.size > max_cover_size:
                form_errors['cover_image'] = f"Cover image too large (Max {filesizeformat(max_cover_size)})."
            elif cover_image_file.content_type not in allowed_cover_types:
                form_errors['cover_image'] = "Invalid cover image type (PNG, JPG/JPEG only)."
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
                    elif price > Decimal('1000000.00'):
                        form_errors['price'] = "Price cannot exceed 1,000,000.00."
                except InvalidOperation:
                    form_errors['price'] = "Invalid price format. Please enter a number."

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

        if not chapter_indices and not form_errors.get('chapters_general'):
            form_errors['chapters_general'] = "At least one chapter is required."
        else:
            sorted_indices = sorted(list(chapter_indices))
            for index in sorted_indices:
                chapter_title = submitted_values.get(f'chapters[{index}][title]', '').strip()
                effective_chapter_input_type = submitted_values.get(f'chapters[{index}][input_type]', 'file')
                chapter_audio_file_from_form = request.FILES.get(f'chapters[{index}][audio_file]')
                chapter_text_content_input = submitted_values.get(f'chapters[{index}][text_content]', '').strip()
                chapter_tts_voice_option_id = submitted_values.get(f'chapters[{index}][tts_voice]', '').strip()
                generated_tts_audio_url_from_form = submitted_values.get(f'chapters[{index}][generated_tts_audio_url]', '').strip()
                chapter_document_file_from_form = request.FILES.get(f'chapters[{index}][document_file]')
                chapter_doc_tts_voice_option_id = submitted_values.get(f'chapters[{index}][doc_tts_voice]', '').strip()
                generated_document_tts_audio_url_from_form = submitted_values.get(f'chapters[{index}][generated_document_tts_audio_url]', '').strip()
                generated_document_filename_from_form = submitted_values.get(f'chapters[{index}][generated_document_filename]', '').strip() # Added

                try:
                    chapter_order = int(submitted_values.get(f'chapters[{index}][order]', index + 1))
                except ValueError: chapter_order = index + 1

                current_chapter_errors = {}
                temp_chapter_data_for_repopulation = {
                    'original_index': index, 'title': chapter_title, 'order': chapter_order,
                    'input_type': effective_chapter_input_type, 'text_content': chapter_text_content_input,
                    'tts_voice': chapter_tts_voice_option_id,
                    'tts_voice_display_name': ALL_EDGE_TTS_VOICES_MAP.get(chapter_tts_voice_option_id, {}).get('name', ''),
                    'audio_filename': "No file chosen",
                    'generated_tts_audio_url': generated_tts_audio_url_from_form,
                    'document_filename': "No document chosen",
                    'doc_tts_voice': chapter_doc_tts_voice_option_id,
                    'doc_tts_voice_display_name': ALL_EDGE_TTS_VOICES_MAP.get(chapter_doc_tts_voice_option_id, {}).get('name', ''),
                    'generated_document_tts_audio_url': generated_document_tts_audio_url_from_form,
                    'generated_document_filename': generated_document_filename_from_form, # Added
                    'errors': {}
                }
                if chapter_audio_file_from_form:
                    temp_chapter_data_for_repopulation['audio_filename'] = chapter_audio_file_from_form.name
                if chapter_document_file_from_form:
                    temp_chapter_data_for_repopulation['document_filename'] = chapter_document_file_from_form.name

                if not chapter_title: current_chapter_errors['title'] = "Chapter title is required."
                
                audio_file_to_process_for_db = None
                text_content_for_db = None
                is_tts_generated_for_db = False
                actual_edge_tts_voice_id_for_gen = None
                tts_option_id_for_model = None
                source_document_filename_for_db = None

                voices_available_for_main_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(language)

                # Chapter Source Validation and Preparation
                if effective_chapter_input_type == 'file':
                    if not chapter_audio_file_from_form:
                        current_chapter_errors['audio_file'] = "Audio file is required for 'Upload File' option."
                    else:
                        audio_file_to_process_for_db = chapter_audio_file_from_form
                        max_audio_size = 50 * 1024 * 1024
                        allowed_audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/x-m4a', 'audio/m4a']
                        if chapter_audio_file_from_form.size > max_audio_size:
                            current_chapter_errors['audio_file'] = f"Audio file too large (Max {filesizeformat(max_audio_size)})."
                        if chapter_audio_file_from_form.content_type not in allowed_audio_types:
                            current_chapter_errors['audio_file'] = f"Invalid audio file type. Allowed: MP3, WAV, OGG, M4A."
                
                elif effective_chapter_input_type == 'generated_tts':
                    if not language or not voices_available_for_main_lang:
                        current_chapter_errors['tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                    else:
                        selected_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(chapter_tts_voice_option_id)
                        if not selected_voice_details or selected_voice_details['id'] not in [v['id'] for v in voices_available_for_main_lang]:
                            current_chapter_errors['tts_voice'] = "Please select a valid narrator voice for generated TTS."
                        elif not generated_tts_audio_url_from_form:
                            current_chapter_errors['generated_tts'] = "Confirmed TTS audio URL is missing. Please re-generate or re-confirm."
                        else:
                            audio_file_to_process_for_db = generated_tts_audio_url_from_form # This is a URL to a temporary file
                            text_content_for_db = chapter_text_content_input # Text content is submitted with the form
                            is_tts_generated_for_db = True
                            tts_option_id_for_model = chapter_tts_voice_option_id
                            temp_chapter_data_for_repopulation['audio_filename'] = f"Generated: {os.path.basename(generated_tts_audio_url_from_form)}" # For display

                elif effective_chapter_input_type == 'generated_document_tts':
                    if not language or not voices_available_for_main_lang:
                        current_chapter_errors['document_tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                    else:
                        selected_doc_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(chapter_doc_tts_voice_option_id)
                        if not selected_doc_voice_details or selected_doc_voice_details['id'] not in [v['id'] for v in voices_available_for_main_lang]:
                            current_chapter_errors['doc_tts_voice'] = "Please select a valid narrator voice for document TTS."
                        elif not generated_document_tts_audio_url_from_form:
                            current_chapter_errors['generated_document_tts'] = "Confirmed Document TTS audio URL is missing. Please re-generate or re-confirm."
                        else:
                            audio_file_to_process_for_db = generated_document_tts_audio_url_from_form # This is a URL to a temporary file
                            is_tts_generated_for_db = True
                            tts_option_id_for_model = chapter_doc_tts_voice_option_id
                            source_document_filename_for_db = generated_document_filename_from_form # Get original document filename
                            temp_chapter_data_for_repopulation['audio_filename'] = f"From Doc: {os.path.basename(generated_document_tts_audio_url_from_form)}" # For display

                elif effective_chapter_input_type == 'tts': # User submits text for direct TTS generation
                    if not language or not voices_available_for_main_lang:
                        current_chapter_errors['tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                    else:
                        selected_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(chapter_tts_voice_option_id)
                        if not selected_voice_details or selected_voice_details['id'] not in [v['id'] for v in voices_available_for_main_lang]:
                            current_chapter_errors['tts_voice'] = "Please select a valid narrator voice."
                        elif not chapter_text_content_input:
                            current_chapter_errors['text_content'] = "Text content for TTS is required."
                        elif len(chapter_text_content_input) < 10: current_chapter_errors['text_content'] = "Text too short (min 10 chars)."
                        elif len(chapter_text_content_input) > 20000: current_chapter_errors['text_content'] = "Text too long (max 20k chars)."
                        else:
                            text_content_for_db = chapter_text_content_input
                            is_tts_generated_for_db = True
                            actual_edge_tts_voice_id_for_gen = selected_voice_details['edge_voice_id']
                            tts_option_id_for_model = selected_voice_details['id']
                            # Audio generation will happen in the transaction block below

                elif effective_chapter_input_type == 'document_tts': # User submits document for direct TTS generation
                    doc_file_obj = request.FILES.get('new_chapter_document_file')
                    tts_voice_id = post_data.get('new_chapter_doc_tts_voice', '').strip()

                    voices_available_for_main_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(audiobook_locked.language)
                    if not audiobook_locked.language or not voices_available_for_main_lang:
                        current_chapter_errors['document_tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                    else:
                        selected_doc_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_id)
                        if not selected_doc_voice_details or selected_doc_voice_details['id'] not in [v['id'] for v in voices_available_for_main_lang]:
                            current_chapter_errors['doc_tts_voice'] = "Please select a valid narrator voice for the document."
                        elif not doc_file_obj:
                            current_chapter_errors['document_file'] = "Document (PDF/Word) is required for this option."
                        else:
                            doc_file = doc_file_obj
                            max_doc_size = 10 * 1024 * 1024
                            allowed_doc_mime_types = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
                            allowed_doc_extensions = ['.pdf', '.doc', '.docx']
                            doc_filename_lower = doc_file.name.lower()
                            doc_extension = os.path.splitext(doc_filename_lower)[1]
                            
                            if doc_file.size > max_doc_size:
                                current_chapter_errors['document_file'] = f"Document too large (Max {filesizeformat(max_doc_size)})."
                            elif not (doc_file.content_type in allowed_doc_mime_types or doc_extension in allowed_doc_extensions):
                                current_chapter_errors['document_file'] = "Invalid document type. Allowed: PDF, DOC, DOCX."
                            
                            if not current_chapter_errors.get('document_file'):
                                try:
                                    doc_content_bytes = doc_file.read()
                                    doc_file.seek(0)
                                    extracted_doc_text = None
                                    if doc_extension == '.pdf': extracted_doc_text = extract_text_from_pdf(doc_content_bytes)
                                    elif doc_extension in ['.docx', '.doc']: extracted_doc_text = extract_text_from_docx(doc_content_bytes)
                                    
                                    if not extracted_doc_text or len(extracted_doc_text.strip()) < 10:
                                        current_chapter_errors['document_tts_general'] = "Could not extract sufficient text from the document."
                                    else:
                                        text_content_for_db = extracted_doc_text.strip()[:20000] # Trim if too long for TTS engine
                                        is_tts_generated_for_db = True
                                        actual_edge_tts_voice_id_for_gen = selected_doc_voice_details['edge_voice_id']
                                        tts_option_id_for_model = selected_doc_voice_details['id']
                                        source_document_filename_for_db = doc_file.name
                                        # Audio generation will happen in the transaction block below
                                except Exception as e_doc_extract:
                                    logger.error(f"Error processing document for chapter {index} on final save: {e_doc_extract}", exc_info=True)
                                    current_chapter_errors['document_tts_general'] = "Error processing document. Please ensure it's a valid text-based file."
                else:
                    current_chapter_errors['input_type'] = "Invalid audio source type for chapter."

                if current_chapter_errors:
                    form_errors[f'chapter_{index}'] = current_chapter_errors
                    temp_chapter_data_for_repopulation['errors'] = current_chapter_errors
                submitted_chapters_for_template.append(temp_chapter_data_for_repopulation)
                
                # Only add to chapters_to_save_data if no errors for this chapter
                if not current_chapter_errors:
                    chapters_to_save_data.append({
                        'title': chapter_title,
                        'order': chapter_order,
                        'input_type_final': effective_chapter_input_type,
                        'audio_file_obj_or_temp_url': audio_file_to_process_for_db,
                        'text_content_for_tts': text_content_for_db,
                        'is_tts_final': is_tts_generated_for_db,
                        'actual_edge_tts_voice_id_for_gen': actual_edge_tts_voice_id_for_gen,
                        'tts_option_id_for_model': tts_option_id_for_model,
                        'source_document_filename': source_document_filename_for_db, # Added for add chapter
                    })
            if any(key.startswith('chapter_') for key in form_errors):
                form_errors.setdefault('chapters_general', "Please correct errors in the chapter details.")

        if not form_errors:
            try:
                with transaction.atomic():
                    new_audiobook = Audiobook(creator=creator, title=title, author=narrator, narrator=narrator, language=language, genre=actual_genre_to_save, description=description, cover_image=cover_image_file, is_paid=is_paid, price=price if is_paid else Decimal('0.00'), status='PUBLISHED')
                    new_audiobook.full_clean()
                    new_audiobook.save()
                    chapters_to_save_data.sort(key=lambda c: c['order'])
                    for ch_data_to_save in chapters_to_save_data:
                        final_ch_audio_file_field_val = None
                        current_ch_text_content = ch_data_to_save['text_content_for_tts']
                        current_ch_is_tts_generated = ch_data_to_save['is_tts_final']
                        current_ch_tts_voice_id = ch_data_to_save['tts_option_id_for_model']
                        current_ch_source_document_filename = ch_data_to_save['source_document_filename'] # Get source doc filename here

                        ch_input_type = ch_data_to_save['input_type_final']
                        perm_ch_audio_dir = os.path.join('chapters_audio', new_audiobook.slug)
                        perm_ch_filename_base = f"ch_{ch_data_to_save['order']}_{slugify(ch_data_to_save['title'])}_{uuid.uuid4().hex[:6]}"
                        
                        if ch_input_type == 'file':
                            final_ch_audio_file_field_val = ch_data_to_save['audio_file_obj_or_temp_url']

                        elif ch_input_type.startswith('generated_'): # This covers 'generated_tts' and 'generated_document_tts'
                            temp_preview_url = ch_data_to_save['audio_file_obj_or_temp_url']
                            
                            if not temp_preview_url or not temp_preview_url.startswith(settings.MEDIA_URL):
                                logger.error(f"Invalid temp preview URL scheme: {temp_preview_url} for chapter '{ch_data_to_save['title']}'")
                                raise ValidationError(f"Invalid temporary audio URL for chapter '{ch_data_to_save['title']}'.")
                            
                            rel_path_from_media_url = temp_preview_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
                            if default_storage.exists(rel_path_from_media_url):
                                try:
                                    with default_storage.open(rel_path_from_media_url, 'rb') as f_preview:
                                        perm_ch_filename = f"{perm_ch_filename_base}.mp3" # No "_preview" suffix needed for permanent
                                        perm_ch_path_rel_media_for_save = os.path.join(perm_ch_audio_dir, perm_ch_filename)
                                        # Create ContentFile from read content, it will be automatically saved by FileField
                                        final_ch_audio_file_field_val = ContentFile(f_preview.read(), name=perm_ch_path_rel_media_for_save)
                                        try:
                                            default_storage.delete(rel_path_from_media_url)
                                        except OSError as e_remove:
                                            logger.warning(f"Could not remove temp preview file {rel_path_from_media_url} from storage: {e_remove}")
                                        logger.info(f"Moved preview TTS from {rel_path_from_media_url} to {final_ch_audio_file_field_val.name}")
                                except Exception as e_save:
                                    logger.error(f"Error saving preview TTS file for chapter '{ch_data_to_save['title']}': {e_save}", exc_info=True)
                                    form_errors['chapters_general'] = f"Error saving preview audio for chapter '{ch_data_to_save['title']}': {e_save}"
                                    raise ValidationError(form_errors) # Re-raise to prevent chapter creation
                            else:
                                logger.error(f"Preview TTS file {rel_path_from_media_url} not found for chapter: {ch_data_to_save['title']}")
                                form_errors['chapters_general'] = f"Preview audio for chapter '{ch_data_to_save['title']}' was not found."
                                raise ValidationError(form_errors) # Re-raise to prevent chapter creation
                                
                        elif ch_input_type == 'tts' or ch_input_type == 'document_tts': # Direct generation on form submission
                            actual_edge_voice_to_use = ch_data_to_save['actual_edge_tts_voice_id_for_gen']
                            text_for_generation = ch_data_to_save['text_content_for_tts']

                            if not text_for_generation or not actual_edge_voice_to_use:
                                logger.error(f"Internal logic error: Missing text or voice for NEW TTS gen. Chapter: {ch_data_to_save['title']}, InputType: {ch_input_type}")
                                raise ValidationError(f"Internal error: Missing text or voice for new TTS for chapter '{ch_data_to_save['title']}'.")
                            
                            perm_ch_filename = f"{perm_ch_filename_base}_directgen.mp3"
                            perm_ch_path_rel_media_for_save = os.path.join(perm_ch_audio_dir, perm_ch_filename)
                            
                            # Use default_storage for path to handle both local and cloud storage correctly
                            temp_output_path = default_storage.path(perm_ch_path_rel_media_for_save) if hasattr(default_storage, 'path') else os.path.join(settings.MEDIA_ROOT, perm_ch_path_rel_media_for_save)
                            os.makedirs(os.path.dirname(temp_output_path), exist_ok=True)
                            
                            try:
                                asyncio.run(generate_audio_edge_tts_async(text_for_generation, actual_edge_voice_to_use, temp_output_path))
                                
                                # Read generated content into ContentFile
                                with open(temp_output_path, 'rb') as f_upload:
                                    final_ch_audio_file_field_val = ContentFile(f_upload.read(), name=perm_ch_path_rel_media_for_save)
                                
                                os.remove(temp_output_path) # Clean up local temp file
                                logger.info(f"Generated and prepared TTS for saving: {final_ch_audio_file_field_val.name}")

                            except Exception as e_gen_final_ch:
                                logger.error(f"Final TTS gen failed for '{ch_data_to_save['title']}': {e_gen_final_ch}", exc_info=True)
                                form_errors['chapters_general'] = f"TTS generation failed for chapter '{ch_data_to_save['title']}'. Error: {e_gen_final_ch}"
                                raise ValidationError(form_errors) # Re-raise to prevent chapter creation
                        else:
                            raise ValidationError(f"Unknown chapter input type during save: {ch_input_type}")
                        
                        chapter_duration_val = None
                        chapter_size_bytes_val = None

                        if final_ch_audio_file_field_val:
                            # Pass the ContentFile object to get_audio_duration
                            if isinstance(final_ch_audio_file_field_val, (InMemoryUploadedFile, ContentFile, TemporaryUploadedFile)):
                                file_for_duration_extraction = final_ch_audio_file_field_val
                                chapter_size_bytes_val = final_ch_audio_file_field_val.size
                            # If it's a string path, open it from default_storage
                            elif isinstance(final_ch_audio_file_field_val, str): # This branch is likely not taken with ContentFile assignments above
                                file_for_duration_extraction_path = default_storage.path(final_ch_audio_file_field_val) if hasattr(default_storage, 'path') else os.path.join(settings.MEDIA_ROOT, final_ch_audio_file_field_val)
                                if default_storage.exists(final_ch_audio_file_field_val):
                                    with default_storage.open(final_ch_audio_file_field_val, 'rb') as f_read:
                                        file_for_duration_extraction = ContentFile(f_read.read(), name=os.path.basename(final_ch_audio_file_field_val))
                                    chapter_size_bytes_val = default_storage.size(final_ch_audio_file_field_val)
                                else:
                                    logger.warning(f"File for duration extraction not found: {final_ch_audio_file_field_val}")
                                    file_for_duration_extraction = None
                            
                            if file_for_duration_extraction:
                                chapter_duration_val = get_audio_duration(file_for_duration_extraction)
                                if chapter_duration_val is None:
                                    logger.warning(f"Could not determine duration for audio file: {final_ch_audio_file_field_val.name if hasattr(final_ch_audio_file_field_val, 'name') else final_ch_audio_file_field_val}")

                        Chapter.objects.create(
                            audiobook=new_audiobook,
                            chapter_name=ch_data_to_save['title'],
                            chapter_order=ch_data_to_save['order'],
                            audio_file=final_ch_audio_file_field_val,
                            duration_seconds=chapter_duration_val,
                            size_bytes=chapter_size_bytes_val,
                            text_content=current_ch_text_content,
                            is_tts_generated=current_ch_is_tts_generated,
                            tts_voice_id=current_ch_tts_voice_id,
                            source_document_filename=current_ch_source_document_filename
                        )
                        logger.info(f"Chapter '{ch_data_to_save['title']}' created with duration_seconds: {chapter_duration_val} and size_bytes: {chapter_size_bytes_val}")
                    messages.success(request, f"Audiobook '{new_audiobook.title}' and its chapters published successfully!")
                    return redirect('AudioXApp:creator_my_audiobooks')
            except ValidationError as e:
                logger.error(f"Saving Error (Validation): {e.message_dict if hasattr(e, 'message_dict') else e}", exc_info=True)
                if hasattr(e, 'message_dict'):
                    for field, error_list in e.message_dict.items():
                        form_errors[field if field != '__all__' else 'general_error'] = " ".join(error_list)
                else:
                    form_errors['general_error'] = str(e)
                messages.error(request, "Please correct the validation errors.")
            except IntegrityError as e:
                logger.error(f"Saving Error (Integrity): {e}", exc_info=True)
                if 'audiobook_slug' in str(e).lower() or ('audiobook' in str(e).lower() and 'slug' in str(e).lower()):
                    form_errors['title'] = "This title (or its generated slug) already exists. Please choose a different title."
                else:
                    form_errors['general_error'] = "A database error occurred. It's possible some data conflicts with existing entries."
                messages.error(request, form_errors.get('title', form_errors.get('general_error', "Database error.")))
            except Exception as e:
                logger.error(f"Unexpected Saving Error: {e}", exc_info=True)
                form_errors['general_error'] = f"An unexpected server error occurred: {str(e)[:100]}"
                messages.error(request, form_errors['general_error'])

        submitted_values['chapters'] = submitted_chapters_for_template

    context = {'creator': creator, 'form_errors': form_errors, 'submitted_values': submitted_values, 'EDGE_TTS_VOICES_BY_LANGUAGE_JSON': json.dumps(EDGE_TTS_VOICES_BY_LANGUAGE), 'LANGUAGE_GENRE_MAPPING_JSON': json.dumps(LANGUAGE_GENRE_MAPPING), 'GENRE_OTHER_VALUE': GENRE_OTHER_VALUE, 'django_messages_json': json.dumps([{'message': str(m), 'tags': m.tags} for m in get_messages(request)])}
    return render(request, 'creator/creator_upload_audiobooks.html', context)


@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_manage_upload_detail_view(request, audiobook_slug):
    """
    Handles managing an existing audiobook's details and its chapters.
    Allows editing audiobook metadata, updating status, adding new chapters,
    editing existing chapters (replacing audio file, re-generating TTS from text or document),
    and deleting chapters.
    """
    creator = request.creator
    audiobook = get_object_or_404(Audiobook.objects.select_related('creator'), slug=audiobook_slug, creator=creator)

    view_form_errors = {}
    view_submitted_values = {}
    add_chapter_active_with_errors = False

    if request.method == "GET":
        is_standard_genre = False
        if audiobook.language and audiobook.language in LANGUAGE_GENRE_MAPPING:
            standard_genres_for_lang = [g['value'] for g in LANGUAGE_GENRE_MAPPING.get(audiobook.language, [])]
            if audiobook.genre in standard_genres_for_lang:
                is_standard_genre = True
        view_submitted_values = {
            'title': audiobook.title or '', 'author': audiobook.author or '', 'narrator': audiobook.narrator or '',
            'genre': audiobook.genre if is_standard_genre else GENRE_OTHER_VALUE,
            'genre_other_text': '' if is_standard_genre else audiobook.genre,
            'language': audiobook.language or '', 'description': audiobook.description or '',
            'status_only_select': audiobook.status or '',
            'current_cover_image_url': audiobook.cover_image.url if audiobook.cover_image else None,
        }

    if request.method == 'POST':
        post_data = request.POST.copy()
        view_submitted_values = post_data
        action = post_data.get('action')
        logger.info(f"POST Action: {action} for audiobook '{audiobook.slug}' by user '{request.user.username}'")

        try:
            with transaction.atomic():
                audiobook_locked = Audiobook.objects.select_for_update().get(pk=audiobook.pk)
                # Define language from audiobook_locked for use in validation
                language = audiobook_locked.language

                # --- ACTION: edit_audiobook_details ---
                if action == 'edit_audiobook_details':
                    updated_title = post_data.get('title', '').strip()
                    updated_author = post_data.get('author', '').strip()
                    updated_narrator = post_data.get('narrator', '').strip()
                    updated_description = post_data.get('description', '').strip()
                    new_cover_image = request.FILES.get('cover_image')

                    update_fields = []
                    
                    if not updated_title:
                        view_form_errors['title'] = "Audiobook title is required."
                    else:
                        audiobook_locked.title = updated_title
                        update_fields.append('title')

                    if not updated_author:
                        view_form_errors['author'] = "Author name is required."
                    else:
                        audiobook_locked.author = updated_author
                        update_fields.append('author')

                    if not updated_narrator:
                        view_form_errors['narrator'] = "Narrator name is required."
                    else:
                        audiobook_locked.narrator = updated_narrator
                        update_fields.append('narrator')

                    if not updated_description:
                        view_form_errors['description'] = "Audiobook description is required."
                    else:
                        audiobook_locked.description = updated_description
                        update_fields.append('description')

                    # Handle cover image update
                    if new_cover_image:
                        max_cover_size = 2 * 1024 * 1024
                        allowed_cover_types = ['image/jpeg', 'image/png', 'image/jpg']
                        if new_cover_image.size > max_cover_size:
                            view_form_errors['cover_image'] = f"Cover image too large (Max {filesizeformat(max_cover_size)})."
                        elif new_cover_image.content_type not in allowed_cover_types:
                            view_form_errors['cover_image'] = "Invalid cover image type (PNG, JPG/JPEG only)."
                        
                        if not view_form_errors.get('cover_image'):
                            # Delete old cover image if it exists and new one is valid
                            if audiobook_locked.cover_image:
                                old_cover_path = audiobook_locked.cover_image.name
                                if default_storage.exists(old_cover_path):
                                    default_storage.delete(old_cover_path)
                                    logger.info(f"Deleted old cover image: {old_cover_path}")
                            audiobook_locked.cover_image = new_cover_image
                            update_fields.append('cover_image')
                    # else: no new cover image, keep existing one. The HTML does not provide an option to remove the existing cover image.


                    if view_form_errors:
                        # If there are errors, make sure submitted values are passed back to template for re-display
                        view_submitted_values['title'] = updated_title
                        view_submitted_values['author'] = updated_author
                        view_submitted_values['narrator'] = updated_narrator
                        view_submitted_values['description'] = updated_description
                        
                        raise ValidationError(view_form_errors)

                    # Only save if there are changes and no errors
                    if update_fields:
                        audiobook_locked.save(update_fields=update_fields)
                        # CRITICAL FIX: Refresh slug after save, as it might have changed if title was updated
                        audiobook_locked.refresh_from_db(fields=['slug']) 
                        messages.success(request, f"Audiobook '{audiobook_locked.title}' details updated successfully.")
                    else:
                        messages.info(request, "No changes detected for audiobook details.")
                    
                    return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook_locked.slug)

                # --- ACTION: update_status_only ---
                elif action == 'update_status_only':
                    new_status = post_data.get('status_only_select')
                    
                    if not new_status:
                        view_form_errors['status_update_status'] = "Please select a status."
                    elif new_status == audiobook_locked.status:
                        messages.info(request, "Audiobook status is already set to the selected value. No change applied.")
                        return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook_locked.slug)
                    elif audiobook_locked.status in ['REJECTED', 'PAUSED_BY_ADMIN'] and new_status != audiobook_locked.status:
                        view_form_errors['status_update_status'] = f"Status cannot be changed from '{audiobook_locked.get_status_display()}' by creator."
                    
                    if view_form_errors:
                        view_submitted_values['status_only_select'] = new_status
                        raise ValidationError(view_form_errors)

                    audiobook_locked.status = new_status
                    audiobook_locked.save(update_fields=['status'])
                    messages.success(request, f"Audiobook status updated to '{audiobook_locked.get_status_display()}'.")
                    return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook_locked.slug)

                # --- ACTION: add_chapter ---
                elif action == 'add_chapter':
                    errors = {}
                    title = post_data.get('new_chapter_title', '').strip()
                    input_type = post_data.get('new_chapter_input_type_hidden', 'file').strip()
                    
                    if not title: errors['new_chapter_title'] = "Chapter title is required."
                    
                    audio_source, text_content, is_tts, tts_voice_id, doc_filename = None, None, False, None, None
                    
                    # Prepare data based on input_type for new chapter
                    if input_type == 'file':
                        audio_source = request.FILES.get('new_chapter_audio')
                        if not audio_source: errors['new_chapter_audio'] = "An audio file is required."
                        elif audio_source: # Validate file
                            max_audio_size = 50 * 1024 * 1024
                            allowed_audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/x-m4a', 'audio/m4a']
                            if audio_source.size > max_audio_size:
                                errors['new_chapter_audio'] = f"Audio file too large (Max {filesizeformat(max_audio_size)})."
                            elif audio_source.content_type not in allowed_audio_types:
                                errors['new_chapter_audio'] = f"Invalid audio file type. Allowed: MP3, WAV, OGG, M4A."
                    
                    elif input_type == 'generated_tts':
                        audio_source = post_data.get('new_chapter_generated_tts_url')
                        tts_voice_id = post_data.get('new_chapter_tts_voice')
                        text_content = post_data.get('new_chapter_text_content', '') # Store the text content

                        if not audio_source: errors['add_chapter_general'] = "A confirmed generated audio file (from text) is required."
                        if not tts_voice_id or tts_voice_id == 'default': errors['new_chapter_tts_voice'] = "A narrator voice must be selected."
                        else:
                            is_tts = True
                            voices_for_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(audiobook_locked.language)
                            selected_voice_detail = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_id)
                            if not voices_for_lang or not selected_voice_detail or selected_voice_detail['id'] not in [v['id'] for v in voices_for_lang]:
                                errors['new_chapter_tts_voice'] = "Invalid narrator voice selected for audiobook language."

                    elif input_type == 'generated_document_tts':
                        audio_source = post_data.get('new_chapter_generated_document_tts_url')
                        tts_voice_id = post_data.get('new_chapter_doc_tts_voice')
                        doc_filename = post_data.get('new_chapter_document_filename', '') # Original document filename
                        text_content = post_data.get('new_chapter_document_extracted_text', '') # Extracted text, if passed

                        if not audio_source: errors['add_chapter_general'] = "A confirmed generated audio file (from document) is required."
                        if not tts_voice_id or tts_voice_id == 'default': errors['new_chapter_doc_tts_voice'] = "A narrator voice must be selected."
                        else:
                            is_tts = True
                            voices_for_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(audiobook_locked.language)
                            selected_voice_detail = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_id)
                            if not voices_for_lang or not selected_voice_detail or selected_voice_detail['id'] not in [v['id'] for v in voices_for_lang]:
                                errors['new_chapter_doc_tts_voice'] = "Invalid narrator voice selected for audiobook language."

                    elif input_type == 'tts': # User submits text for direct TTS generation (no preview)
                        text_content = post_data.get('new_chapter_text_content', '').strip()
                        tts_voice_id = post_data.get('new_chapter_tts_voice', '').strip()

                        voices_available_for_main_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(audiobook_locked.language)
                        if not audiobook_locked.language or not voices_available_for_main_lang:
                            errors['tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                        else:
                            selected_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_id)
                            if not selected_voice_details or selected_voice_details['id'] not in [v['id'] for v in voices_available_for_main_lang]:
                                errors['new_chapter_tts_voice'] = "Please select a valid narrator voice."
                            elif not text_content:
                                errors['new_chapter_text_content'] = "Text content for TTS is required."
                            elif len(text_content) < 10: errors['new_chapter_text_content'] = "Text too short (min 10 chars)."
                            elif len(text_content) > 20000: errors['new_chapter_text_content'] = "Text too long (max 20k chars)."
                            else:
                                is_tts = True
                                actual_edge_tts_voice_id_for_gen = selected_voice_details['edge_voice_id']
                                # Audio will be generated below if no errors

                    elif input_type == 'document_tts': # User submits document for direct TTS generation (no preview)
                        doc_file_obj = request.FILES.get('new_chapter_document_file')
                        tts_voice_id = post_data.get('new_chapter_doc_tts_voice', '').strip()

                        voices_available_for_main_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(audiobook_locked.language)
                        if not audiobook_locked.language or not voices_available_for_main_lang:
                            errors['document_tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                        else:
                            selected_doc_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_id)
                            if not selected_doc_voice_details or selected_doc_voice_details['id'] not in [v['id'] for v in voices_available_for_main_lang]:
                                errors['new_chapter_doc_tts_voice'] = "Please select a valid narrator voice for the document."
                            elif not doc_file_obj:
                                errors['new_chapter_document_file'] = "Document (PDF/Word) is required for this option."
                            else:
                                doc_file = doc_file_obj
                                max_doc_size = 10 * 1024 * 1024
                                allowed_doc_mime_types = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
                                allowed_doc_extensions = ['.pdf', '.doc', '.docx']
                                doc_filename_lower = doc_file.name.lower()
                                doc_extension = os.path.splitext(doc_filename_lower)[1]
                                
                                if doc_file.size > max_doc_size:
                                    errors['new_chapter_document_file'] = f"Document too large (Max {filesizeformat(max_doc_size)})."
                                elif not (doc_file.content_type in allowed_doc_mime_types or doc_extension in allowed_doc_extensions):
                                    errors['new_chapter_document_file'] = "Invalid document type. Allowed: PDF, DOC, DOCX."
                            
                                if not errors.get('new_chapter_document_file'):
                                    try:
                                        doc_content_bytes = doc_file.read()
                                        doc_file.seek(0)
                                        extracted_doc_text = None
                                        if doc_extension == '.pdf': extracted_doc_text = extract_text_from_pdf(doc_content_bytes)
                                        elif doc_extension in ['.docx', '.doc']: extracted_doc_text = extract_text_from_docx(doc_content_bytes)
                                        
                                        if not extracted_doc_text or len(extracted_doc_text.strip()) < 10:
                                            errors['document_tts_general'] = "Could not extract sufficient text from the document."
                                        else:
                                            text_content = extracted_doc_text.strip()[:20000] # Trim if too long for TTS engine
                                            is_tts = True
                                            actual_edge_tts_voice_id_for_gen = selected_doc_voice_details['edge_voice_id']
                                            tts_voice_id = selected_doc_voice_details['id']
                                            doc_filename = doc_file.name
                                            # Audio will be generated below if no errors
                                    except Exception as e_doc_extract:
                                        logger.error(f"Error processing document for new chapter direct save: {e_doc_extract}", exc_info=True)
                                        errors['document_tts_general'] = "Error processing document for direct TTS generation."
                    else:
                        errors['add_chapter_general'] = "Invalid audio source type selected for new chapter."

                    if errors:
                        view_form_errors['add_chapter_errors'] = errors
                        add_chapter_active_with_errors = True
                        messages.error(request, "Please correct the errors to add the chapter.")
                        raise ValidationError(errors) # Raise to trigger error rendering

                    new_order = audiobook_locked.chapters.count() + 1
                    perm_ch_audio_dir = os.path.join('chapters_audio', audiobook_locked.slug)
                    perm_ch_filename_base = f"ch_{new_order}_{slugify(title)}_{uuid.uuid4().hex[:6]}"
                    
                    # Handle audio file based on processed type
                    final_audio_file_field_val = None
                    if input_type == 'file':
                        final_audio_file_field_val = audio_source # This is the UploadedFile object
                    elif input_type.startswith('generated_'): # 'generated_tts' or 'generated_document_tts'
                        temp_preview_url = audio_source # This is the URL to the temporary preview file
                        rel_path = temp_preview_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
                        if default_storage.exists(rel_path):
                            with default_storage.open(rel_path, 'rb') as f:
                                unique_filename = f"{perm_ch_filename_base}.mp3" # No "_preview" suffix needed for permanent
                                final_audio_file_field_val = ContentFile(f.read(), name=os.path.join(perm_ch_audio_dir, unique_filename))
                            try:
                                default_storage.delete(rel_path) # Delete temp file
                            except OSError as e_remove:
                                logger.warning(f"Could not remove temp preview file {rel_path} from storage: {e_remove}")
                            logger.info(f"Moved preview audio from {rel_path} to permanent: {final_audio_file_field_val.name}")
                        else:
                            logger.error(f"Temporary audio file not found for chapter add: {rel_path}")
                            errors['add_chapter_general'] = "Temporary audio file not found. Please re-generate or re-confirm."
                            raise ValidationError(errors)
                    elif input_type == 'tts' or input_type == 'document_tts': # Direct generation
                        final_file_name = f"{perm_ch_filename_base}_directgen.mp3"
                        full_path_for_gen = os.path.join(perm_ch_audio_dir, final_file_name)
                        
                        temp_output_path_for_gen = default_storage.path(full_path_for_gen) if hasattr(default_storage, 'path') else os.path.join(settings.MEDIA_ROOT, full_path_for_gen)
                        os.makedirs(os.path.dirname(temp_output_path_for_gen), exist_ok=True)
                        
                        try:
                            # Use the actual edge_voice_id mapped from the tts_voice_id
                            actual_edge_voice_to_use = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_id, {}).get('edge_voice_id')
                            if not actual_edge_voice_to_use:
                                raise ValueError(f"Edge TTS voice ID not found for {tts_voice_id}")

                            asyncio.run(generate_audio_edge_tts_async(text_content, actual_edge_voice_to_use, temp_output_path_for_gen))
                            
                            with open(temp_output_path_for_gen, 'rb') as f_upload:
                                final_audio_file_field_val = ContentFile(f_upload.read(), name=full_path_for_gen)
                            
                            os.remove(temp_output_path_for_gen)
                            logger.info(f"Generated and prepared TTS for saving: {final_audio_file_field_val.name}")

                        except Exception as e_gen:
                            logger.error(f"Direct TTS generation failed for '{title}': {e_gen}", exc_info=True)
                            errors['add_chapter_general'] = f"TTS generation failed: {e_gen}"
                            raise ValidationError(errors)

                    chapter = Chapter(
                        audiobook=audiobook_locked,
                        chapter_name=title,
                        chapter_order=new_order,
                        audio_file=final_audio_file_field_val, # Set the file here
                        text_content=text_content,
                        is_tts_generated=is_tts,
                        tts_voice_id=tts_voice_id,
                        source_document_filename=doc_filename
                    )
                    
                    chapter.full_clean() # Run model validation

                    # Calculate duration and size after audio_file is set
                    chapter_duration_val = None
                    chapter_size_bytes_val = None

                    if chapter.audio_file and chapter.audio_file.name:
                        if isinstance(chapter.audio_file.file, (InMemoryUploadedFile, ContentFile, TemporaryUploadedFile)):
                            file_for_duration_extraction = chapter.audio_file.file
                            chapter_size_bytes_val = chapter.audio_file.size
                        elif default_storage.exists(chapter.audio_file.name):
                            with default_storage.open(chapter.audio_file.name, 'rb') as f_read:
                                file_for_duration_extraction = ContentFile(f_read.read(), name=os.path.basename(chapter.audio_file.name))
                            chapter_size_bytes_val = default_storage.size(chapter.audio_file.name)
                        else:
                            logger.warning(f"File for duration extraction not found: {chapter.audio_file.name}")
                            file_for_duration_extraction = None
                            
                        if file_for_duration_extraction:
                            chapter_duration_val = get_audio_duration(file_for_duration_extraction)
                            if chapter_duration_val is None:
                                logger.warning(f"Could not determine duration for newly added chapter: {chapter.audio_file.name}")
                        else:
                            logger.warning(f"Could not open audio file for duration extraction after save: {chapter.audio_file.name}")
                    
                    chapter.duration_seconds = chapter_duration_val
                    chapter.size_bytes = chapter_size_bytes_val
                    chapter.save() # Save the chapter with all details

                    messages.success(request, f"Chapter '{title}' added successfully.")
                    return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook_locked.slug)

                # --- ACTION: edit_chapter_X ---
                elif action.startswith('edit_chapter_'):
                    chapter_id = action.replace('edit_chapter_', '')
                    chapter_locked = get_object_or_404(Chapter.objects.select_for_update(), chapter_id=chapter_id, audiobook=audiobook_locked)
                    
                    edit_errors = {}
                    new_chapter_title = post_data.get(f'chapter_title_{chapter_id}', '').strip()
                    edit_input_type = post_data.get(f'edit_chapter_input_type_hidden_{chapter_id}', '').strip()
                    
                    # New audio file, text, voice, doc file inputs
                    new_audio_file_from_form = request.FILES.get(f'chapter_audio_{chapter_id}')
                    new_text_content_input = post_data.get(f'chapter_text_content_{chapter_id}', '').strip()
                    new_tts_voice_option_id = post_data.get(f'chapter_tts_voice_{chapter_id}', '').strip()
                    new_document_file_from_form = request.FILES.get(f'chapter_document_edit_{chapter_id}')
                    new_doc_tts_voice_option_id = post_data.get(f'chapter_doc_tts_voice_edit_{chapter_id}', '').strip()
                    
                    # Generated preview URLs (if user confirmed preview)
                    generated_tts_audio_url_from_form = post_data.get(f'edit_chapter_generated_tts_url_{chapter_id}', '').strip()
                    generated_doc_tts_audio_url_from_form = post_data.get(f'edit_chapter_generated_document_tts_url_{chapter_id}', '').strip()
                    generated_doc_filename_from_form = post_data.get(f'edit_chapter_source_document_filename_{chapter_id}', '').strip() # Added

                    # Data for final chapter update
                    final_audio_file_for_save = None # This will be the UploadedFile object or a ContentFile
                    final_text_content = None
                    final_is_tts_generated = False
                    final_tts_voice_id = None
                    final_source_document_filename = None
                    delete_old_audio = False # Flag to delete the old audio file

                    voices_available_for_main_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(audiobook_locked.language)

                    # 1. Validate new_chapter_title
                    if not new_chapter_title: edit_errors['title'] = "Chapter title is required."

                    # 2. Determine and validate new audio source based on edit_input_type
                    if edit_input_type == 'file':
                        if new_audio_file_from_form: # Only if a new file is actually uploaded
                            final_audio_file_for_save = new_audio_file_from_form
                            max_audio_size = 50 * 1024 * 1024
                            allowed_audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/x-m4a', 'audio/m4a']
                            if new_audio_file_from_form.size > max_audio_size:
                                edit_errors['audio'] = f"Audio file too large (Max {filesizeformat(max_audio_size)})."
                            elif new_audio_file_from_form.content_type not in allowed_audio_types:
                                edit_errors['audio'] = "Invalid audio file type. Allowed: MP3, WAV, OGG, M4A."
                            
                            if not edit_errors.get('audio'):
                                delete_old_audio = True # If new file is valid, delete old one
                        elif not chapter_locked.audio_file: # If no new file and no existing file
                            edit_errors['audio'] = "An audio file is required if no existing file is present."
                        else:
                            # Keep current audio file if no new one provided for 'file' type
                            final_audio_file_for_save = chapter_locked.audio_file 
                            final_text_content = chapter_locked.text_content
                            final_is_tts_generated = chapter_locked.is_tts_generated
                            final_tts_voice_id = chapter_locked.tts_voice_id
                            final_source_document_filename = chapter_locked.source_document_filename


                    elif edit_input_type == 'generated_tts':
                        if not language or not voices_available_for_main_lang:
                            edit_errors['tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                        else:
                            selected_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(new_tts_voice_option_id)
                            if not selected_voice_details or selected_voice_details['id'] not in [v['id'] for v in voices_available_for_main_lang]:
                                edit_errors['voice'] = "Please select a valid narrator voice for generated TTS."
                            elif not generated_tts_audio_url_from_form:
                                edit_errors['generated_tts'] = "Confirmed TTS audio URL is missing. Please re-generate or re-confirm."
                            else:
                                final_audio_file_for_save = generated_tts_audio_url_from_form # This is a URL to a temporary file
                                final_text_content = new_text_content_input
                                final_is_tts_generated = True
                                final_tts_voice_id = new_tts_voice_option_id
                                final_source_document_filename = None
                                delete_old_audio = True


                    elif edit_input_type == 'generated_document_tts':
                        if not language or not voices_available_for_main_lang:
                            edit_errors['document_tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                        else:
                            selected_doc_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(new_doc_tts_voice_option_id)
                            if not selected_doc_voice_details or selected_doc_voice_details['id'] not in [v['id'] for v in voices_available_for_main_lang]:
                                edit_errors['doc_voice'] = "Please select a valid narrator voice for document TTS."
                            elif not generated_doc_tts_audio_url_from_form:
                                edit_errors['generated_document_tts'] = "Confirmed Document TTS audio URL is missing. Please re-generate or re-confirm."
                            else:
                                final_audio_file_for_save = generated_doc_tts_audio_url_from_form # This is a URL to a temporary file
                                final_text_content = new_text_content_input # (text content from document if passed)
                                final_is_tts_generated = True
                                final_tts_voice_id = new_doc_tts_voice_option_id
                                final_source_document_filename = generated_doc_filename_from_form
                                delete_old_audio = True


                    elif edit_input_type == 'tts': # Direct generation from text
                        if not language or not voices_available_for_main_lang:
                            edit_errors['tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                        else:
                            selected_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(new_tts_voice_option_id)
                            if not selected_voice_details or selected_voice_details['id'] not in [v['id'] for v in voices_available_for_main_lang]:
                                edit_errors['voice'] = "Please select a valid narrator voice."
                            elif not new_text_content_input:
                                edit_errors['text'] = "Text content for TTS is required."
                            elif len(new_text_content_input) < 10: edit_errors['text'] = "Text too short (min 10 chars)."
                            elif len(new_text_content_input) > 20000: edit_errors['text'] = "Text too long (max 20k chars)."
                            else:
                                final_text_content = new_text_content_input
                                final_is_tts_generated = True
                                final_tts_voice_id = new_tts_voice_option_id
                                # Actual generation will happen below if no errors
                                delete_old_audio = True

                    elif edit_input_type == 'document_tts': # Direct generation from document
                        doc_file = new_document_file_from_form
                        if not doc_file and chapter_locked.source_document_filename and chapter_locked.is_tts_generated:
                            # User is changing voice for an existing document-TTS chapter without re-uploading document.
                            # We need to re-use the stored text_content and source_document_filename.
                            final_text_content = chapter_locked.text_content # Assuming this stores the extracted text
                            final_is_tts_generated = True
                            final_tts_voice_id = new_doc_tts_voice_option_id
                            final_source_document_filename = chapter_locked.source_document_filename
                            delete_old_audio = True # Generate new audio from old text, so delete old audio

                        elif not language or not voices_available_for_main_lang:
                            edit_errors['document_tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                        else:
                            selected_doc_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(new_doc_tts_voice_option_id)
                            if not selected_doc_voice_details or selected_doc_voice_details['id'] not in [v['id'] for v in voices_available_for_main_lang]:
                                edit_errors['doc_voice'] = "Please select a valid narrator voice for the document."
                            elif not doc_file:
                                edit_errors['document_file_edit'] = "Document (PDF/Word) is required for this option."
                            else:
                                max_doc_size = 10 * 1024 * 1024
                                allowed_doc_mime_types = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
                                allowed_doc_extensions = ['.pdf', '.doc', '.docx']
                                doc_filename_lower = doc_file.name.lower()
                                doc_extension = os.path.splitext(doc_filename_lower)[1]
                                
                                if doc_file.size > max_doc_size:
                                    edit_errors['document_file_edit'] = f"Document too large (Max {filesizeformat(max_doc_size)})."
                                elif not (doc_file.content_type in allowed_doc_mime_types or doc_extension in allowed_doc_extensions):
                                    edit_errors['document_file_edit'] = "Invalid document type. Allowed: PDF, DOC, DOCX."
                                
                                if not edit_errors.get('document_file_edit'):
                                    try:
                                        doc_content_bytes = doc_file.read()
                                        doc_file.seek(0)
                                        extracted_doc_text = None
                                        if doc_extension == '.pdf': extracted_doc_text = extract_text_from_pdf(doc_content_bytes)
                                        elif doc_extension in ['.docx', '.doc']: extracted_doc_text = extract_text_from_docx(doc_content_bytes)
                                        
                                        if not extracted_doc_text or len(extracted_doc_text.strip()) < 10:
                                            edit_errors['document_tts_general'] = "Could not extract sufficient text from the document."
                                        else:
                                            final_text_content = extracted_doc_text.strip()[:20000]
                                            final_is_tts_generated = True
                                            final_tts_voice_id = new_doc_tts_voice_option_id
                                            final_source_document_filename = doc_file.name
                                            delete_old_audio = True
                                    except Exception as e_doc_extract:
                                        logger.error(f"Error processing document for chapter edit (direct save): {e_doc_extract}", exc_info=True)
                                        edit_errors['document_tts_general'] = "Error processing document for direct TTS generation."

                    else:
                        edit_errors['input_type'] = "Invalid audio source type selected for chapter."

                    if edit_errors:
                        view_form_errors[f'edit_chapter_{chapter_id}'] = edit_errors
                        messages.error(request, f"Please correct the errors for chapter '{new_chapter_title or chapter_id}'.")
                        raise ValidationError(edit_errors)

                    # --- Perform audio generation/moving for TTS/Document TTS if necessary ---
                    if (edit_input_type == 'tts' or edit_input_type == 'document_tts') and final_is_tts_generated:
                        perm_ch_audio_dir = os.path.join('chapters_audio', audiobook_locked.slug)
                        perm_ch_filename_base = f"ch_{chapter_locked.chapter_order}_{slugify(new_chapter_title)}_{uuid.uuid4().hex[:6]}"
                        perm_ch_filename = f"{perm_ch_filename_base}_editgen.mp3"
                        full_path_for_gen = os.path.join(perm_ch_audio_dir, perm_ch_filename)
                        
                        temp_output_path_for_gen = default_storage.path(full_path_for_gen) if hasattr(default_storage, 'path') else os.path.join(settings.MEDIA_ROOT, full_path_for_gen)
                        os.makedirs(os.path.dirname(temp_output_path_for_gen), exist_ok=True)
                        
                        try:
                            actual_edge_voice_to_use = ALL_EDGE_TTS_VOICES_MAP.get(final_tts_voice_id, {}).get('edge_voice_id')
                            if not actual_edge_voice_to_use:
                                raise ValueError(f"Edge TTS voice ID not found for {final_tts_voice_id}")

                            asyncio.run(generate_audio_edge_tts_async(final_text_content, actual_edge_voice_to_use, temp_output_path_for_gen))
                            
                            with open(temp_output_path_for_gen, 'rb') as f_generated:
                                final_audio_file_for_save = ContentFile(f_generated.read(), name=os.path.basename(temp_output_path_for_gen))
                            
                            os.remove(temp_output_path_for_gen)
                            logger.info(f"Generated and prepared TTS from {temp_output_path_for_gen}")

                        except Exception as e_gen:
                            logger.error(f"TTS generation failed for chapter '{new_chapter_title}': {e_gen}", exc_info=True)
                            edit_errors['tts_general'] = f"TTS generation failed: {e_gen}"
                            raise ValidationError(edit_errors)


                    elif edit_input_type.startswith('generated_'): # Move temp preview file to permanent location
                        temp_preview_url = final_audio_file_for_save
                        rel_path = temp_preview_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
                        if default_storage.exists(rel_path):
                            perm_ch_audio_dir = os.path.join('chapters_audio', audiobook_locked.slug)
                            perm_ch_filename_base = f"ch_{chapter_locked.chapter_order}_{slugify(new_chapter_title)}_{uuid.uuid4().hex[:6]}"
                            perm_ch_filename = f"{perm_ch_filename_base}_editconfirm.mp3"
                            full_path_for_move = os.path.join(perm_ch_audio_dir, perm_ch_filename)
                            
                            try:
                                with default_storage.open(rel_path, 'rb') as f_preview:
                                    final_audio_file_for_save = ContentFile(f_preview.read(), name=os.path.basename(full_path_for_move))
                                try:
                                    default_storage.delete(rel_path) # Delete temp preview file
                                except OSError as e_remove:
                                    logger.warning(f"Could not remove temp preview file {rel_path} from storage: {e_remove}")
                                logger.info(f"Moved confirmed preview audio from {rel_path} to ContentFile object.")
                            except Exception as e_move:
                                logger.error(f"Error moving confirmed preview audio for chapter '{new_chapter_title}': {e_move}", exc_info=True)
                                edit_errors['general'] = f"Error processing confirmed audio: {e_move}"
                                raise ValidationError(edit_errors)
                        else:
                            logger.error(f"Confirmed preview audio file not found: {rel_path}")
                            edit_errors['general'] = "Confirmed audio file not found. Please re-generate or re-confirm."
                            raise ValidationError(edit_errors)
                    
                    # --- Delete old audio file if a new one is being set ---
                    if delete_old_audio and chapter_locked.audio_file and chapter_locked.audio_file.name:
                        old_audio_path = chapter_locked.audio_file.name
                        if default_storage.exists(old_audio_path):
                            try:
                                default_storage.delete(old_audio_path)
                                logger.info(f"Deleted old audio file for chapter '{chapter_locked.chapter_name}': {old_audio_path}")
                            except OSError as e_del:
                                logger.warning(f"Could not delete old audio file {old_audio_path}: {e_del}")

                    # --- Update chapter fields ---
                    chapter_locked.chapter_name = new_chapter_title
                    chapter_locked.text_content = final_text_content
                    chapter_locked.is_tts_generated = final_is_tts_generated
                    chapter_locked.tts_voice_id = final_tts_voice_id
                    chapter_locked.source_document_filename = final_source_document_filename
                    
                    # Ensure the file-like object is seekable from beginning before assignment
                    if isinstance(final_audio_file_for_save, (InMemoryUploadedFile, ContentFile)):
                        final_audio_file_for_save.seek(0)
                        
                    chapter_locked.audio_file = final_audio_file_for_save 
                    
                    # Recalculate duration and size for the updated audio file
                    chapter_duration_val = None
                    chapter_size_bytes_val = None

                    if chapter_locked.audio_file and chapter_locked.audio_file.name:
                        if isinstance(final_audio_file_for_save, (InMemoryUploadedFile, ContentFile)):
                            # Use the in-memory object directly for size and duration
                            chapter_size_bytes_val = final_audio_file_for_save.size
                            file_for_duration_extraction = final_audio_file_for_save
                        elif chapter_locked.audio_file.name and default_storage.exists(chapter_locked.audio_file.name):
                            # If the file is on storage (e.g., from an existing file being kept, or a new file already saved)
                            chapter_size_bytes_val = default_storage.size(chapter_locked.audio_file.name)
                            with default_storage.open(chapter_locked.audio_file.name, 'rb') as f_read:
                                file_for_duration_extraction = ContentFile(f_read.read(), name=os.path.basename(chapter_locked.audio_file.name))
                        else:
                            logger.warning(f"Could not determine size for chapter {chapter_locked.chapter_id}'s audio file: {chapter_locked.audio_file.name}")
                            file_for_duration_extraction = None

                        if file_for_duration_extraction:
                            chapter_duration_val = get_audio_duration(file_for_duration_extraction)
                            if chapter_duration_val is None:
                                logger.warning(f"Could not determine duration for edited chapter: {chapter_locked.audio_file.name}")
                        else:
                            logger.warning(f"Could not open audio file for duration extraction after edit: {chapter_locked.audio_file.name}")
                    
                    chapter_locked.duration_seconds = chapter_duration_val
                    chapter_locked.size_bytes = chapter_size_bytes_val

                    chapter_locked.save() # Save the updated chapter
                    messages.success(request, f"Chapter '{new_chapter_title}' updated successfully.")
                    return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook_locked.slug)

                # --- ACTION: delete_chapter ---
                elif action.startswith('delete_chapter_'):
                    chapter_id = action.split('_')[-1]
                    chapter = get_object_or_404(Chapter, chapter_id=chapter_id, audiobook=audiobook_locked)
                    
                    chapter_name = chapter.chapter_name
                    audio_path = None
                    if chapter.audio_file:
                        audio_path = chapter.audio_file.name
                    
                    chapter.delete()
                    if audio_path and default_storage.exists(audio_path):
                        default_storage.delete(audio_path)
                    _reorder_chapters(audiobook_locked)
                    messages.success(request, f"Chapter '{chapter_name}' has been deleted.")
                    return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook_locked.slug)

                else:
                    messages.error(request, "Invalid action requested.")
                    raise ValidationError("Invalid action.")

        except ValidationError as e:
            error_dict = e.message_dict if hasattr(e, 'message_dict') else {'general_error': e.messages}
            if action == 'add_chapter':
                view_form_errors['add_chapter_errors'] = error_dict
                add_chapter_active_with_errors = True
            elif action and action.startswith('edit_chapter_'):
                chapter_id = action.replace('edit_chapter_', '')
                view_form_errors[f'edit_chapter_{chapter_id}'] = error_dict
            elif action == 'edit_audiobook_details':
                for field, errors_list in error_dict.items():
                    view_form_errors[field] = errors_list[0] if errors_list else "Invalid value."
            elif action == 'update_status_only':
                for field, errors_list in error_dict.items():
                    view_form_errors[field] = errors_list[0] if errors_list else "Invalid value."
            else:
                view_form_errors.update(error_dict)
            messages.error(request, "Please correct the validation errors.")
        except Exception as e:
            logger.error(f"Error processing POST for '{audiobook_slug}': {e}", exc_info=True)
            messages.error(request, f"An unexpected server error occurred: {e}")

    # --- Prepare context for rendering (for both GET and failed POST) ---
    db_chapters = audiobook.chapters.order_by('chapter_order')
    chapters_context_list = []
    for chapter_instance in db_chapters:
        tts_voice_display_name = ""
        if chapter_instance.is_tts_generated and chapter_instance.tts_voice_id:
            voice_detail = ALL_EDGE_TTS_VOICES_MAP.get(chapter_instance.tts_voice_id)
            tts_voice_display_name = voice_detail['name'] if voice_detail else f"Unknown Voice ({chapter_instance.tts_voice_id})"
        
        # Determine the input type for template display based on current chapter state
        input_type_for_template = 'file' # Default
        if chapter_instance.is_tts_generated:
            if chapter_instance.source_document_filename:
                input_type_for_template = 'generated_document_tts'
            elif chapter_instance.text_content:
                input_type_for_template = 'generated_tts'
            else:
                input_type_for_template = 'generated_tts' # Fallback to text TTS if no doc filename but is TTS generated

        file_size_display = None
        # Safely check for audio_file and its existence/size
        if chapter_instance.audio_file and chapter_instance.audio_file.name:
            try:
                # Check if the file actually exists on storage before trying to get its size
                if default_storage.exists(chapter_instance.audio_file.name):
                    file_size_display = filesizeformat(default_storage.size(chapter_instance.audio_file.name))
                else:
                    logger.warning(f"Audio file for chapter {chapter_instance.chapter_id} not found in storage: {chapter_instance.audio_file.name}")
            except Exception as e:
                logger.error(f"Error getting file size for chapter {chapter_instance.chapter_id}: {e}", exc_info=True)
        
        chapters_context_list.append({
            'instance': chapter_instance, 'tts_voice_display_name': tts_voice_display_name,
            'errors': view_form_errors.get(f'edit_chapter_{chapter_instance.chapter_id}', {}),
            'input_type_for_template': input_type_for_template, 'file_size_display': file_size_display,
            'existing_audio_file_url': chapter_instance.audio_file.url if chapter_instance.audio_file else None,
            'document_filename': chapter_instance.source_document_filename,
            # Pass original TTS voice for document-generated audio if applicable for repopulation
            'doc_tts_voice_id': chapter_instance.tts_voice_id if chapter_instance.is_tts_generated and chapter_instance.source_document_filename else None,
        })

    view_form_errors['add_chapter_active_with_errors'] = add_chapter_active_with_errors
    django_messages_list = [{'message': str(m), 'tags': m.tags} for m in get_messages(request)]
    final_context = {
        'creator': creator, 'audiobook': audiobook, 'chapters_context_list': chapters_context_list,
        'form_errors': view_form_errors, 'submitted_values': view_submitted_values,
        'creator_allowed_status_choices_for_toggle': [('PUBLISHED', 'Published (Visible to users)'), ('INACTIVE', 'Inactive (Hidden from public, earnings paused)')],
        'can_creator_change_status': audiobook.status not in ['REJECTED', 'PAUSED_BY_ADMIN'],
        'django_messages_json': json.dumps(django_messages_list, cls=DjangoJSONEncoder),
        'EDGE_TTS_VOICES_BY_LANGUAGE_JSON': json.dumps(EDGE_TTS_VOICES_BY_LANGUAGE),
        'GENRE_OTHER_VALUE': GENRE_OTHER_VALUE
    }
    logger.debug(f"Rendering manage_upload_detail. Context form_errors: {final_context.get('form_errors')}, Submitted: {final_context.get('submitted_values')}")
    return render(request, 'creator/creator_manage_uploads.html', final_context)


@creator_required
def creator_my_audiobooks_view(request):
    """
    Displays a list of all audiobooks uploaded by the current creator,
    along with their associated earnings from views for free audiobooks.
    """
    creator = request.creator
    try:
        audiobooks_queryset = Audiobook.objects.filter(creator=creator).order_by('-publish_date').prefetch_related('chapters')
        audiobooks_data_list = []
        for book in audiobooks_queryset:
            earnings_from_views = Decimal('0.00')
            if not book.is_paid:
                view_earnings_aggregation = CreatorEarning.objects.filter(creator=creator, audiobook=book, earning_type='view').aggregate(total_earnings=Sum('amount_earned'))
                earnings_from_views = view_earnings_aggregation['total_earnings'] or Decimal('0.00')
            audiobooks_data_list.append({'book': book, 'earnings_from_views': earnings_from_views})
        context = _get_full_context(request)
        context.update({'creator': creator, 'audiobooks_data': audiobooks_data_list, 'audiobooks_count': len(audiobooks_data_list), 'available_balance': creator.available_balance})
        return render(request, 'creator/creator_my_audiobooks.html', context)
    except Exception as e:
        logger.error(f"Could not load creator's audiobooks: {e}", exc_info=True)
    messages.error(request, "Could not load your audiobooks.")
    return redirect('AudioXApp:creator_dashboard')

# --- JSON API Views ---

@creator_required
@require_GET
def get_audiobook_chapters_json(request, audiobook_slug):
    """
    Returns a JSON response with a list of chapters for a given audiobook slug.
    Used for AJAX requests to populate chapter lists dynamically.
    """
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
                    if default_storage.exists(chapter.audio_file.name):
                        file_size = filesizeformat(default_storage.size(chapter.audio_file.name))
                    else:
                        logger.warning(f"Audio file for chapter {chapter.chapter_id} not found in storage: {chapter.audio_file.name}")
                        audio_filename = "File Missing"
            except Exception as e:
                logger.warning(f"Error getting file details for chapter {chapter.chapter_id} in get_audiobook_chapters_json: {e}")
            chapter_data = {'id': chapter.chapter_id, 'name': chapter.chapter_name, 'order': chapter.chapter_order, 'audio_filename': audio_filename, 'file_size': file_size}
            chapters_list.append(chapter_data)
        return JsonResponse({'chapters': chapters_list}, status=200)
    except Http404:
        logger.warning(f"Audiobook not found or permission denied in get_audiobook_chapters_json for slug {audiobook_slug}, user {request.user.username}")
        return JsonResponse({'error': 'Audiobook not found or permission denied.'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_audiobook_chapters_json for slug {audiobook_slug}: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal server error occurred.'}, status=500)
