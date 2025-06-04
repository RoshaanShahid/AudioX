# AudioXApp/views/creator_views/creator_audiobook_views.py

import json
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta # Ensure timedelta is imported here if not already
import os
import logging
import asyncio

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

# Assuming creator_tts_views is in the same directory or adjust import path
from .creator_tts_views import (
    EDGE_TTS_VOICES_BY_LANGUAGE, 
    ALL_EDGE_TTS_VOICES_MAP, 
    LANGUAGE_GENRE_MAPPING,
    generate_audio_edge_tts_async, # Make sure this is the correct async function
    extract_text_from_pdf,
    extract_text_from_docx
)


logger = logging.getLogger(__name__)

EARNING_PER_VIEW = Decimal(getattr(settings, 'CREATOR_EARNING_PER_FREE_VIEW', '1.00'))
GENRE_OTHER_VALUE = '_OTHER_'


def get_audio_duration(file_obj_or_path):
    logger.info(f"[GET_DURATION] Received for duration extraction (type: {type(file_obj_or_path)}): '{file_obj_or_path}'")
    duration = None
    filename = None
    file_to_read = None
    reset_file_pointer_after = False 

    if isinstance(file_obj_or_path, str): 
        filename = os.path.basename(file_obj_or_path)
        file_to_read = file_obj_or_path
        logger.info(f"[GET_DURATION] Input is a path: '{file_to_read}' with filename: '{filename}'")
    elif hasattr(file_obj_or_path, 'name'): 
        filename = file_obj_or_path.name
        logger.info(f"[GET_DURATION] Input is a file object. Filename: '{filename}'")
        if isinstance(file_obj_or_path, TemporaryUploadedFile):
            file_to_read = file_obj_or_path.temporary_file_path()
            logger.info(f"[GET_DURATION] It's a TemporaryUploadedFile. Reading from path: '{file_to_read}'")
        elif isinstance(file_obj_or_path, InMemoryUploadedFile):
            file_to_read = file_obj_or_path
            try:
                original_position = file_to_read.tell()
                file_to_read.seek(0)
                reset_file_pointer_after = True 
                logger.info(f"[GET_DURATION] It's an InMemoryUploadedFile. Seeked to 0. Original pos: {original_position}")
            except Exception as e_seek:
                logger.warning(f"[GET_DURATION] Could not seek InMemoryUploadedFile '{filename}': {e_seek}")
        else: 
            file_to_read = file_obj_or_path
            if hasattr(file_to_read, 'path'): 
                file_to_read = file_to_read.path
                logger.info(f"[GET_DURATION] Input is a FileField-like object with path: '{file_to_read}'")
            else: 
                logger.info(f"[GET_DURATION] Input is a FileField-like object without a direct path, passing object itself.")


    if not filename or file_to_read is None:
        logger.error(f"[GET_DURATION] Could not determine a valid filename or readable source. Filename: '{filename}', File_to_read: '{file_to_read}'")
        return None

    logger.info(f"[GET_DURATION] Attempting to get duration for filename: '{filename}' using source: '{file_to_read}' (type: {type(file_to_read)})")

    try:
        if filename.lower().endswith(('.mp3')):
            logger.info("[GET_DURATION] Trying MP3 mutagen...")
            audio = MP3(file_to_read)
            duration = audio.info.length
        elif filename.lower().endswith(('.wav')):
            logger.info("[GET_DURATION] Trying WAVE mutagen...")
            audio = WAVE(file_to_read)
            duration = audio.info.length
        elif filename.lower().endswith(('.m4a', '.mp4', '.m4b', '.aac')):
            logger.info("[GET_DURATION] Trying MP4 mutagen...")
            audio = MP4(file_to_read)
            duration = audio.info.length
        elif filename.lower().endswith(('.ogg', '.oga')):
            logger.info("[GET_DURATION] Trying OggVorbis mutagen...")
            audio = OggVorbis(file_to_read)
            duration = audio.info.length
        elif filename.lower().endswith(('.flac')):
            logger.info("[GET_DURATION] Trying FLAC mutagen...")
            audio = FLAC(file_to_read)
            duration = audio.info.length
        else:
            logger.warning(f"[GET_DURATION] Unsupported audio format for duration extraction: {filename}")
            return None

        logger.info(f"[GET_DURATION] Successfully extracted duration for {filename}: {duration} seconds")
        return float(duration) if duration is not None else None

    except (MP3HeaderNotFoundError, WaveError, MP4StreamInfoError, OggVorbisHeaderError, FLACNoHeaderError) as e:
        logger.error(f"[GET_DURATION] Mutagen header/format error reading duration for {filename}: {e}")
    except Exception as e:
        logger.error(f"[GET_DURATION] General error extracting duration for {filename} with mutagen: {e}", exc_info=True)
    finally:
        if reset_file_pointer_after and hasattr(file_to_read, 'seek'): 
            try:
                file_to_read.seek(original_position) 
                logger.info(f"[GET_DURATION] Reset InMemoryUploadedFile pointer for '{filename}' to original position: {original_position}")
            except Exception as e_reseek:
                logger.warning(f"[GET_DURATION] Could not re-seek InMemoryUploadedFile '{filename}' to original position: {e_reseek}")
    return None


@login_required
@require_POST
@csrf_protect
def log_audiobook_view(request):
    # ... (your existing log_audiobook_view logic - unchanged) ...
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
            return JsonResponse({
                'status': 'success',
                'message': 'View already logged recently.',
                'total_views': audiobook.total_views
            })

        with transaction.atomic():
            audiobook_locked = Audiobook.objects.select_for_update().get(pk=audiobook.pk)
            AudiobookViewLog.objects.create(audiobook=audiobook_locked, user=request.user)
            audiobook_locked.total_views = F('total_views') + 1
            audiobook_locked.save(update_fields=['total_views'])
            audiobook_locked.refresh_from_db(fields=['total_views'])

            if not audiobook_locked.is_paid and audiobook_locked.creator and audiobook_locked.creator.is_approved:
                creator = audiobook_locked.creator
                earned_amount_for_view = EARNING_PER_VIEW

                Creator.objects.filter(pk=creator.pk).update(
                    available_balance=F('available_balance') + earned_amount_for_view,
                    total_earning=F('total_earning') + earned_amount_for_view
                )
                CreatorEarning.objects.create(
                    creator=creator, audiobook=audiobook_locked, earning_type='view',
                    amount_earned=earned_amount_for_view, transaction_date=timezone.now(),
                    audiobook_title_at_transaction=audiobook_locked.title,
                    notes=f"Earning from 1 view on '{audiobook_locked.title}' (24hr rule applied)."
                )
                logger.info(f"View logged and earning processed for user {request.user.username}, audiobook ID {audiobook_id}.")
            else:
                logger.info(f"View logged for user {request.user.username}, audiobook ID {audiobook_id} (paid book or no active creator, no view earning).")

            return JsonResponse({
                'status': 'success',
                'message': 'View logged successfully.',
                'total_views': audiobook_locked.total_views
            })
    except Audiobook.DoesNotExist:
        logger.warning(f"log_audiobook_view: Audiobook not found for ID {audiobook_id}, user {request.user.username}.")
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except Exception as e:
        logger.error(f"log_audiobook_view: Internal error for user {request.user.username}, audiobook ID {audiobook_id}. Error: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An internal error occurred.'}, status=500)


@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_upload_audiobook(request):
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

                try:
                    chapter_order = int(submitted_values.get(f'chapters[{index}][order]', index + 1))
                except ValueError: chapter_order = index + 1

                current_chapter_errors = {}
                temp_chapter_data_for_repopulation = {
                    'original_index': index, 'title': chapter_title, 'order': chapter_order,
                    'input_type': effective_chapter_input_type,
                    'text_content': chapter_text_content_input, 
                    'tts_voice': chapter_tts_voice_option_id, 
                    'tts_voice_display_name': ALL_EDGE_TTS_VOICES_MAP.get(chapter_tts_voice_option_id, {}).get('name', ''),
                    'audio_filename': "No file chosen", 
                    'generated_tts_audio_url': generated_tts_audio_url_from_form, 
                    'document_filename': "No document chosen", 
                    'doc_tts_voice': chapter_doc_tts_voice_option_id, 
                    'doc_tts_voice_display_name': ALL_EDGE_TTS_VOICES_MAP.get(chapter_doc_tts_voice_option_id, {}).get('name', ''), 
                    'generated_document_tts_audio_url': generated_document_tts_audio_url_from_form, 
                    'errors': {} 
                }
                if chapter_audio_file_from_form:
                    temp_chapter_data_for_repopulation['audio_filename'] = chapter_audio_file_from_form.name
                if chapter_document_file_from_form: 
                    temp_chapter_data_for_repopulation['document_filename'] = chapter_document_file_from_form.name
                
                if not chapter_title: current_chapter_errors['title'] = "Chapter title is required."

                audio_source_valid_for_submission = False
                audio_file_to_process_for_db = None 
                text_content_for_db = None
                is_tts_generated_for_db = False
                actual_edge_tts_voice_id_for_gen = None
                tts_option_id_for_model = None 

                voices_available_for_main_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(language)

                if effective_chapter_input_type == 'file':
                    # ... (existing file validation logic - seems okay) ...
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
                        if not current_chapter_errors.get('audio_file'):
                            audio_source_valid_for_submission = True
                
                elif effective_chapter_input_type == 'generated_tts': # Was part of a combined block
                    if not language or not voices_available_for_main_lang:
                        current_chapter_errors['tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                    else:
                        selected_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(chapter_tts_voice_option_id)
                        if not selected_voice_details or selected_voice_details not in voices_available_for_main_lang:
                            current_chapter_errors['tts_voice'] = "Please select a valid narrator voice for generated TTS."
                        elif not generated_tts_audio_url_from_form:
                            current_chapter_errors['generated_tts'] = "Confirmed TTS audio URL is missing. Please re-generate or re-confirm."
                        else:
                            audio_file_to_process_for_db = generated_tts_audio_url_from_form 
                            text_content_for_db = chapter_text_content_input # Keep original text if any
                            is_tts_generated_for_db = True
                            tts_option_id_for_model = selected_voice_details['id']
                            audio_source_valid_for_submission = True
                            if generated_tts_audio_url_from_form:
                                temp_chapter_data_for_repopulation['audio_filename'] = f"Generated: {os.path.basename(generated_tts_audio_url_from_form)}"
                
                elif effective_chapter_input_type == 'generated_document_tts': # NEW specific block
                    if not language or not voices_available_for_main_lang:
                        current_chapter_errors['document_tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                    else:
                        selected_doc_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(chapter_doc_tts_voice_option_id)
                        if not selected_doc_voice_details or selected_doc_voice_details not in voices_available_for_main_lang:
                            current_chapter_errors['doc_tts_voice'] = "Please select a valid narrator voice for document TTS."
                        elif not generated_document_tts_audio_url_from_form:
                            current_chapter_errors['generated_document_tts'] = "Confirmed Document TTS audio URL is missing. Please re-generate or re-confirm."
                        else:
                            audio_file_to_process_for_db = generated_document_tts_audio_url_from_form
                            # For document TTS, text_content might be a placeholder or the extracted text if needed
                            # For now, let's assume it's not critical for DB if audio is already generated.
                            # text_content_for_db = f"Audio generated from document: {temp_chapter_data_for_repopulation['document_filename']}"
                            text_content_for_db = None # Or a placeholder as above
                            is_tts_generated_for_db = True
                            tts_option_id_for_model = selected_doc_voice_details['id'] # Store the voice ID
                            audio_source_valid_for_submission = True
                            temp_chapter_data_for_repopulation['audio_filename'] = f"From Doc: {os.path.basename(generated_document_tts_audio_url_from_form)}"

                elif effective_chapter_input_type == 'tts': # Generate new TTS from text
                    if not language or not voices_available_for_main_lang:
                        current_chapter_errors['tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                    else:
                        selected_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(chapter_tts_voice_option_id)
                        if not selected_voice_details or selected_voice_details not in voices_available_for_main_lang:
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
                            audio_source_valid_for_submission = True
                
                elif effective_chapter_input_type == 'document_tts': # Generate new TTS from document
                    if not language or not voices_available_for_main_lang:
                        current_chapter_errors['document_tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                    else:
                        selected_doc_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(chapter_doc_tts_voice_option_id)
                        if not selected_doc_voice_details or selected_doc_voice_details not in voices_available_for_main_lang:
                            current_chapter_errors['doc_tts_voice'] = "Please select a valid narrator voice for the document."
                        elif not chapter_document_file_from_form:
                            current_chapter_errors['document_file'] = "Document (PDF/Word) is required for this option."
                        else:
                            doc_file = chapter_document_file_from_form
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
                                    doc_content_bytes = doc_file.read() # Read once
                                    doc_file.seek(0) # Reset pointer if it needs to be read again (e.g. by storage)
                                    extracted_doc_text = None
                                    if doc_extension == '.pdf': extracted_doc_text = extract_text_from_pdf(doc_content_bytes)
                                    elif doc_extension in ['.docx', '.doc']: extracted_doc_text = extract_text_from_docx(doc_content_bytes)
                                    
                                    if not extracted_doc_text or len(extracted_doc_text.strip()) < 10:
                                        current_chapter_errors['document_tts_general'] = "Could not extract sufficient text from the document."
                                    else:
                                        text_content_for_db = extracted_doc_text.strip()[:20000] # Limit length
                                        is_tts_generated_for_db = True
                                        actual_edge_tts_voice_id_for_gen = selected_doc_voice_details['edge_voice_id']
                                        tts_option_id_for_model = selected_doc_voice_details['id']
                                        audio_source_valid_for_submission = True
                                        # audio_file_to_process_for_db will be the generated file path/object later
                                except Exception as e_doc_extract:
                                    logger.error(f"Error processing document for chapter {index} on final save: {e_doc_extract}", exc_info=True)
                                    current_chapter_errors['document_tts_general'] = "Error processing document. Please ensure it's a valid text-based file."
                else: 
                    current_chapter_errors['input_type'] = "Invalid audio source type for chapter."

                if not audio_source_valid_for_submission and not current_chapter_errors:
                    current_chapter_errors.setdefault('audio_file', "Audio source is missing or invalid for this chapter.")

                if current_chapter_errors:
                    form_errors[f'chapter_{index}'] = current_chapter_errors 
                    temp_chapter_data_for_repopulation['errors'] = current_chapter_errors
                submitted_chapters_for_template.append(temp_chapter_data_for_repopulation)

                if not current_chapter_errors: 
                    chapters_to_save_data.append({
                        'title': chapter_title, 'order': chapter_order,
                        'input_type_final': effective_chapter_input_type, 
                        'audio_file_obj_or_temp_url': audio_file_to_process_for_db, 
                        'document_file_obj': chapter_document_file_from_form if effective_chapter_input_type == 'document_tts' else None, # Pass original doc for new generation
                        'text_content_for_tts': text_content_for_db, 
                        'is_tts_final': is_tts_generated_for_db,
                        'actual_edge_tts_voice_id_for_gen': actual_edge_tts_voice_id_for_gen, 
                        'tts_option_id_for_model': tts_option_id_for_model, 
                    })
            
            if any(key.startswith('chapter_') for key in form_errors): 
                form_errors.setdefault('chapters_general', "Please correct errors in the chapter details.")

        if not form_errors:
            try:
                with transaction.atomic():
                    new_audiobook = Audiobook(
                        creator=creator, title=title, author=author, narrator=narrator, language=language,
                        genre=actual_genre_to_save, 
                        description=description, cover_image=cover_image_file,
                        is_paid=is_paid, price=price if is_paid else Decimal('0.00'),
                        status='PUBLISHED' 
                    )
                    new_audiobook.full_clean() 
                    new_audiobook.save()    

                    chapters_to_save_data.sort(key=lambda c: c['order']) 

                    for ch_data_to_save in chapters_to_save_data:
                        final_ch_audio_file_field_val = None 
                        ch_text_content_model = ch_data_to_save['text_content_for_tts']
                        ch_is_tts_model = ch_data_to_save['is_tts_final']
                        ch_tts_option_id_model = ch_data_to_save['tts_option_id_for_model'] 
                        ch_input_type = ch_data_to_save['input_type_final']

                        perm_ch_audio_dir = os.path.join('chapters_audio', new_audiobook.slug)
                        perm_ch_filename_base = f"ch_{ch_data_to_save['order']}_{slugify(ch_data_to_save['title'])}_{uuid.uuid4().hex[:6]}"
                        
                        if ch_input_type == 'file':
                            final_ch_audio_file_field_val = ch_data_to_save['audio_file_obj_or_temp_url'] 
                            ch_is_tts_model = False
                            ch_tts_option_id_model = None
                            ch_text_content_model = None
                        
                        elif ch_input_type == 'generated_tts' or ch_input_type == 'generated_document_tts':
                            temp_preview_url = ch_data_to_save['audio_file_obj_or_temp_url'] 
                            if not temp_preview_url or not temp_preview_url.startswith(settings.MEDIA_URL):
                                logger.error(f"Invalid temp preview URL scheme: {temp_preview_url} for chapter '{ch_data_to_save['title']}'")
                                raise ValidationError(f"Invalid temporary audio URL for chapter '{ch_data_to_save['title']}'.")
                            
                            rel_path_from_media_url = temp_preview_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
                            
                            if default_storage.exists(rel_path_from_media_url):
                                with default_storage.open(rel_path_from_media_url, 'rb') as f_preview:
                                    # Use a more unique permanent filename
                                    perm_ch_filename = f"{perm_ch_filename_base}_preview.mp3"
                                    perm_ch_path_rel_media_for_save = os.path.join(perm_ch_audio_dir, perm_ch_filename)
                                    saved_file_name = default_storage.save(perm_ch_path_rel_media_for_save, ContentFile(f_preview.read()))
                                final_ch_audio_file_field_val = saved_file_name
                                try: 
                                    default_storage.delete(rel_path_from_media_url)
                                except OSError as e_remove: 
                                    logger.warning(f"Could not remove temp preview file {rel_path_from_media_url} from storage: {e_remove}")
                                logger.info(f"Moved preview TTS from {rel_path_from_media_url} to {saved_file_name}")
                            else:
                                logger.error(f"Preview TTS file {rel_path_from_media_url} not found for chapter: {ch_data_to_save['title']}")
                                raise ValidationError(f"Preview audio for chapter '{ch_data_to_save['title']}' was not found.")
                            # text_content for generated_document_tts might be a placeholder or derived from doc name
                            if ch_input_type == 'generated_document_tts' and not ch_text_content_model:
                                ch_text_content_model = f"Audio from document (preview used)."


                        elif ch_input_type == 'tts' or ch_input_type == 'document_tts': 
                            actual_edge_voice_to_use = ch_data_to_save['actual_edge_tts_voice_id_for_gen']
                            text_for_generation = ch_text_content_model 

                            if not text_for_generation or not actual_edge_voice_to_use:
                                # This was the error location, ensure it's correctly handled if this path is taken
                                logger.error(f"Internal logic error: Missing text or voice for NEW TTS gen. Chapter: {ch_data_to_save['title']}, InputType: {ch_input_type}")
                                raise ValidationError(f"Internal error: Missing text or voice for new TTS for chapter '{ch_data_to_save['title']}'.")

                            perm_ch_filename = f"{perm_ch_filename_base}_newtts.mp3"
                            perm_ch_path_rel_media_for_save = os.path.join(perm_ch_audio_dir, perm_ch_filename)
                            local_save_path = os.path.join(settings.MEDIA_ROOT, perm_ch_path_rel_media_for_save)
                            
                            os.makedirs(os.path.dirname(local_save_path), exist_ok=True)
                            try:
                                asyncio.run(generate_audio_edge_tts_async(text_for_generation, actual_edge_voice_to_use, local_save_path))
                                if hasattr(default_storage, 'bucket_name') and not default_storage.location == settings.MEDIA_ROOT: 
                                    with open(local_save_path, 'rb') as f_upload:
                                        final_ch_audio_file_field_val = default_storage.save(perm_ch_path_rel_media_for_save, ContentFile(f_upload.read()))
                                    os.remove(local_save_path) 
                                else: 
                                    final_ch_audio_file_field_val = perm_ch_path_rel_media_for_save
                            except Exception as e_gen_final_ch:
                                logger.error(f"Final TTS gen failed for '{ch_data_to_save['title']}': {e_gen_final_ch}", exc_info=True)
                                raise ValidationError(f"TTS generation failed for chapter '{ch_data_to_save['title']}'. Error: {e_gen_final_ch}")
                        else:
                            raise ValidationError(f"Unknown chapter input type during save: {ch_input_type}")
                        
                        chapter_duration_val = None
                        file_for_duration_extraction = None
                        
                        if isinstance(final_ch_audio_file_field_val, InMemoryUploadedFile) or isinstance(final_ch_audio_file_field_val, TemporaryUploadedFile):
                            file_for_duration_extraction = final_ch_audio_file_field_val
                        elif isinstance(final_ch_audio_file_field_val, str): # It's a path relative to MEDIA_ROOT
                            file_for_duration_extraction = os.path.join(settings.MEDIA_ROOT, final_ch_audio_file_field_val)
                        
                        if file_for_duration_extraction:
                            chapter_duration_val = get_audio_duration(file_for_duration_extraction)
                        
                        Chapter.objects.create(
                            audiobook=new_audiobook,
                            chapter_name=ch_data_to_save['title'],
                            chapter_order=ch_data_to_save['order'],
                            audio_file=final_ch_audio_file_field_val,
                            duration_seconds=chapter_duration_val,
                            text_content=ch_text_content_model, 
                            is_tts_generated=ch_is_tts_model,
                            tts_voice_id=ch_tts_option_id_model if ch_is_tts_model else None,
                        )
                        logger.info(f"[UPLOAD_VIEW] Chapter '{ch_data_to_save['title']}' created with duration_seconds: {chapter_duration_val}")
                    messages.success(request, f"Audiobook '{new_audiobook.title}' and its chapters published successfully!")
                    return redirect('AudioXApp:creator_my_audiobooks') 

            except ValidationError as e:
                # ... (existing error handling) ...
                logger.error(f"Saving Error (Validation): {e.message_dict if hasattr(e, 'message_dict') else e}", exc_info=True)
                if hasattr(e, 'message_dict'):
                    for field, error_list in e.message_dict.items():
                        form_errors[field if field != '__all__' else 'general_error'] = " ".join(error_list)
                else:
                    form_errors['general_error'] = str(e)
                messages.error(request, "Please correct the validation errors.")
            except IntegrityError as e:
                # ... (existing error handling) ...
                logger.error(f"Saving Error (Integrity): {e}", exc_info=True)
                if 'audiobook_slug' in str(e).lower() or ('audiobook' in str(e).lower() and 'slug' in str(e).lower()): 
                    form_errors['title'] = "This title (or its generated slug) already exists. Please choose a different title."
                else:
                    form_errors['general_error'] = "A database error occurred. It's possible some data conflicts with existing entries."
                messages.error(request, form_errors.get('title', form_errors.get('general_error', "Database error.")))
            except Exception as e:
                # ... (existing error handling) ...
                logger.error(f"Unexpected Saving Error: {e}", exc_info=True)
                form_errors['general_error'] = f"An unexpected server error occurred: {str(e)[:100]}"
                messages.error(request, form_errors['general_error'])
        
        submitted_values['chapters'] = submitted_chapters_for_template

    context = {
        'creator': creator,
        'form_errors': form_errors,
        'submitted_values': submitted_values, 
        'EDGE_TTS_VOICES_BY_LANGUAGE_JSON': edge_tts_voices_by_lang_json,
        'LANGUAGE_GENRE_MAPPING_JSON': language_genre_mapping_json, 
        'GENRE_OTHER_VALUE': GENRE_OTHER_VALUE,
        'django_messages_json': json.dumps([{'message': str(m), 'tags': m.tags} for m in get_messages(request)])
    }
    return render(request, 'creator/creator_upload_audiobooks.html', context)


@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_manage_upload_detail_view(request, audiobook_slug):
    # ... (your existing creator_manage_upload_detail_view logic - assumed unchanged for now) ...
    creator = request.creator
    audiobook = get_object_or_404(Audiobook.objects.prefetch_related('chapters'), slug=audiobook_slug, creator=creator)

    view_form_errors = {} 
    view_chapter_form_errors = {}

    initial_genre_value_for_display = audiobook.genre 
    initial_genre_other_text_for_display = ""
    
    is_standard_genre = False
    if audiobook.language and audiobook.language in LANGUAGE_GENRE_MAPPING:
        standard_genres_for_lang = [g['value'] for g in LANGUAGE_GENRE_MAPPING[audiobook.language]]
        if audiobook.genre in standard_genres_for_lang:
            is_standard_genre = True
    
    if not is_standard_genre and audiobook.genre: 
        initial_genre_value_for_display = GENRE_OTHER_VALUE 
        initial_genre_other_text_for_display = audiobook.genre
    elif is_standard_genre:
        initial_genre_value_for_display = audiobook.genre 
        initial_genre_other_text_for_display = ""


    view_submitted_values = {
        'title': request.POST.get('title', audiobook.title or ''),
        'author': request.POST.get('author', audiobook.author or ''),
        'narrator': request.POST.get('narrator', audiobook.narrator or ''),
        'genre': request.POST.get('genre', initial_genre_value_for_display or ''), 
        'genre_other_text': request.POST.get('genre_other_text', initial_genre_other_text_for_display or ''),
        'language': audiobook.language or '', 
        'description': request.POST.get('description', audiobook.description or ''),
        'status_only_select': request.POST.get('status_only_select', audiobook.status or ''),
        'current_cover_image_url': audiobook.cover_image.url if audiobook.cover_image else None,
        
        'new_chapter_title': request.POST.get('new_chapter_title', ''),
        'new_chapter_input_type_hidden': request.POST.get('new_chapter_input_type_hidden', 'file'),
        'new_chapter_text_content': request.POST.get('new_chapter_text_content', ''),
        'new_chapter_tts_voice': request.POST.get('new_chapter_tts_voice', ''),
        'new_chapter_generated_tts_url': request.POST.get('new_chapter_generated_tts_url', ''),
        'new_chapter_doc_tts_voice': request.POST.get('new_chapter_doc_tts_voice', ''),
        'new_chapter_generated_document_tts_url': request.POST.get('new_chapter_generated_document_tts_url', ''),
    }

    creator_allowed_statuses_for_toggle = [
        ('PUBLISHED', 'Published (Visible to users)'),
        ('INACTIVE', 'Inactive (Hidden from public, earnings paused)'),
    ]
    can_creator_change_status = audiobook.status not in ['REJECTED', 'PAUSED_BY_ADMIN']
    edge_tts_voices_by_lang_json = json.dumps(EDGE_TTS_VOICES_BY_LANGUAGE)
    language_genre_mapping_json = json.dumps(LANGUAGE_GENRE_MAPPING) 

    if request.method == 'POST':
        post_data = request.POST.copy() 
        for key in post_data: 
            view_submitted_values[key] = post_data.get(key)
        
        view_submitted_values['language'] = audiobook.language 
        if not is_standard_genre and audiobook.genre:
            view_submitted_values['genre'] = GENRE_OTHER_VALUE
            view_submitted_values['genre_other_text'] = audiobook.genre
        else:
            view_submitted_values['genre'] = audiobook.genre
            view_submitted_values['genre_other_text'] = ""


        action = view_submitted_values.get('action')
        logger.info(f"POST Action: {action} for audiobook '{audiobook.slug}' by user '{request.user.username}'")

        if action == 'edit_audiobook_details':
            logger.info(f"Processing 'edit_audiobook_details' for audiobook '{audiobook.slug}'")
            title_from_post = view_submitted_values.get('title', '').strip()
            author_from_post = view_submitted_values.get('author', '').strip()
            narrator_from_post = view_submitted_values.get('narrator', '').strip()
            description_from_post = view_submitted_values.get('description', '').strip()
            cover_image_file = request.FILES.get('cover_image') 

            current_action_form_errors = {}
            if not title_from_post: current_action_form_errors['title'] = "Audiobook title is required."
            if not author_from_post: current_action_form_errors['author'] = "Author name is required."
            if not narrator_from_post: current_action_form_errors['narrator'] = "Narrator name is required."
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
                        audiobook_to_update.description = description_from_post
                        
                        update_fields = ['title', 'author', 'narrator', 'description', 'updated_at']

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
                        audiobook = Audiobook.objects.prefetch_related('chapters').get(pk=audiobook.pk) 
                except Exception as e_status:
                    logger.error(f"Error updating status for '{audiobook.slug}': {e_status}", exc_info=True)
                    messages.error(request, f"An error occurred while updating status: {e_status}")
                    view_form_errors['status_update_status'] = f"Error: {e_status}" 

        elif action and (action.startswith('add_chapter') or action.startswith('edit_chapter_') or action.startswith('delete_chapter_')):
            logger.info(f"Chapter-related action '{action}' received. (Full chapter management logic would be here)")
            messages.info(request, f"Chapter action '{action}' was processed (placeholder).")

        else:
            if action: 
                logger.warning(f"Unhandled POST action: {action} for audiobook '{audiobook.slug}'")
                messages.warning(request, f"Unknown action: {action}")

    audiobook = Audiobook.objects.prefetch_related('chapters').get(pk=audiobook.pk) 
    db_chapters = audiobook.chapters.order_by('chapter_order')
    chapters_context_list = []

    if request.method == "GET" or view_form_errors: 
        current_book_genre_from_db = audiobook.genre
        current_book_lang_from_db = audiobook.language
        is_standard_genre_display = False
        if current_book_lang_from_db and current_book_lang_from_db in LANGUAGE_GENRE_MAPPING:
            standard_genres = [g['value'] for g in LANGUAGE_GENRE_MAPPING[current_book_lang_from_db]]
            if current_book_genre_from_db in standard_genres:
                is_standard_genre_display = True
        
        if not is_standard_genre_display and current_book_genre_from_db:
            view_submitted_values['genre'] = GENRE_OTHER_VALUE
            view_submitted_values['genre_other_text'] = current_book_genre_from_db
        elif is_standard_genre_display:
             view_submitted_values['genre'] = current_book_genre_from_db
             view_submitted_values['genre_other_text'] = ''
        else: 
            view_submitted_values['genre'] = current_book_genre_from_db 
            view_submitted_values['genre_other_text'] = ''


    for chapter_instance in db_chapters:
        chapter_id_str_ctx = str(chapter_instance.chapter_id)
        current_chapter_edit_errors = view_chapter_form_errors.get(f'edit_chapter_{chapter_id_str_ctx}', {})
        
        tts_voice_display_name_existing = ""
        if chapter_instance.is_tts_generated and chapter_instance.tts_voice_id:
            voice_detail = ALL_EDGE_TTS_VOICES_MAP.get(chapter_instance.tts_voice_id)
            if voice_detail:
                tts_voice_display_name_existing = voice_detail['name']
            else: 
                tts_voice_display_name_existing = f"Unknown Voice ({chapter_instance.tts_voice_id})"
        
        input_type_for_template = 'file' 
        if chapter_instance.is_tts_generated:
            if chapter_instance.text_content and chapter_instance.text_content.startswith("Audio generated from document:"):
                 input_type_for_template = 'generated_document_tts'
            elif chapter_instance.audio_file and chapter_instance.audio_file.name:
                 input_type_for_template = 'generated_tts'
            else: 
                 input_type_for_template = 'tts' # Should have text content

        chapter_file_size_display = None
        existing_audio_file_url = None
        if chapter_instance.audio_file and hasattr(chapter_instance.audio_file, 'name') and chapter_instance.audio_file.name:
            try:
                if default_storage.exists(chapter_instance.audio_file.name):
                    chapter_file_size_display = filesizeformat(chapter_instance.audio_file.size)
                    existing_audio_file_url = chapter_instance.audio_file.url
                else:
                    logger.warning(f"Audio file for chapter '{chapter_instance.chapter_name}' (ID: {chapter_instance.pk}) not found at path: {chapter_instance.audio_file.name}.")
                    existing_audio_file_url = None
            except Exception as e_file_details:
                logger.warning(f"Could not get details for chapter '{chapter_instance.chapter_name}' audio file {chapter_instance.audio_file.name}: {e_file_details}")

        chapters_context_list.append({
            'instance': chapter_instance,
            'tts_voice_display_name': tts_voice_display_name_existing,
            'errors': current_chapter_edit_errors, 
            'input_type_for_template': input_type_for_template, 
            'file_size_display': chapter_file_size_display,
            'existing_audio_file_url': existing_audio_file_url,
        })

    django_messages_list = [] 
    for msg_obj in get_messages(request): 
        django_messages_list.append({'message': str(msg_obj), 'tags': msg_obj.tags})

    final_context = { 
        'creator': creator,
        'audiobook': audiobook, 
        'chapters_context_list': chapters_context_list,
        'form_errors': view_form_errors,
        'submitted_values': view_submitted_values,
        'creator_allowed_status_choices_for_toggle': creator_allowed_statuses_for_toggle,
        'can_creator_change_status': can_creator_change_status,
        'django_messages_list': django_messages_list,
        'EDGE_TTS_VOICES_BY_LANGUAGE_JSON': edge_tts_voices_by_lang_json, 
        'LANGUAGE_GENRE_MAPPING_JSON': language_genre_mapping_json,
        'GENRE_OTHER_VALUE': GENRE_OTHER_VALUE, 
        'EDGE_TTS_VOICES_BY_LANGUAGE': EDGE_TTS_VOICES_BY_LANGUAGE, 
        'available_balance': creator.available_balance, 
    }
    final_context['submitted_values']['language'] = audiobook.language 

    logger.debug(f"Rendering manage_upload_detail. Context form_errors: {final_context.get('form_errors')}, Submitted: {final_context.get('submitted_values')}")
    return render(request, 'creator/creator_manage_uploads.html', final_context)


@creator_required
def creator_my_audiobooks_view(request):
    # ... (your existing creator_my_audiobooks_view logic - unchanged) ...
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
        logger.error(f"Could not load creator's audiobooks: {e}", exc_info=True)
        messages.error(request, "Could not load your audiobooks.")
        return redirect('AudioXApp:creator_dashboard')


@creator_required
@require_GET
def get_audiobook_chapters_json(request, audiobook_slug):
    # ... (your existing get_audiobook_chapters_json logic - unchanged) ...
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
                        if default_storage.exists(chapter.audio_file.name):
                                file_size = filesizeformat(chapter.audio_file.size)
                        else:
                            logger.warning(f"Audio file for chapter {chapter.chapter_id} not found in storage: {chapter.audio_file.name}")
                            audio_filename = "File Missing"
            except Exception as e:
                logger.warning(f"Error getting file details for chapter {chapter.chapter_id} in get_audiobook_chapters_json: {e}")

            chapter_data = {
                'id': chapter.chapter_id,
                'name': chapter.chapter_name,
                'order': chapter.chapter_order,
                'audio_filename': audio_filename,
                'file_size': file_size,
            }
            chapters_list.append(chapter_data)
            
        return JsonResponse({'chapters': chapters_list}, status=200)
        
    except Http404:
        logger.warning(f"Audiobook not found or permission denied in get_audiobook_chapters_json for slug {audiobook_slug}, user {request.user.username}")
        return JsonResponse({'error': 'Audiobook not found or permission denied.'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_audiobook_chapters_json for slug {audiobook_slug}: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal server error occurred.'}, status=500)