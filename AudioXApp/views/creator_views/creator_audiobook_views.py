# AudioXApp/views/creator_views/creator_audiobook_views.py

import json
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
import os
import logging
import asyncio
from io import BytesIO
from asgiref.sync import async_to_sync

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
from ...tasks import process_chapter_for_moderation


from ...tts_constants import (
    EDGE_TTS_VOICES_BY_LANGUAGE,
    ALL_EDGE_TTS_VOICES_MAP,
    LANGUAGE_GENRE_MAPPING,
)

from .creator_tts_views import (
    generate_audio_edge_tts_async,
    extract_text_from_pdf,
    extract_text_from_docx
)

logger = logging.getLogger(__name__)

EARNING_PER_VIEW = Decimal(getattr(settings, 'CREATOR_EARNING_PER_FREE_VIEW', '1.00'))
GENRE_OTHER_VALUE = '_OTHER_'



def _reorder_chapters(audiobook):
    chapters = Chapter.objects.filter(audiobook=audiobook).order_by('chapter_order')
    for i, chapter in enumerate(chapters, 1):
        if chapter.chapter_order != i:
            Chapter.objects.filter(pk=chapter.pk).update(chapter_order=i)
    logger.info(f"Re-ordered chapters for audiobook '{audiobook.slug}'.")


@login_required
@require_POST
@csrf_protect
def log_audiobook_view(request):
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
                generated_document_filename_from_form = submitted_values.get(f'chapters[{index}][generated_document_filename]', '').strip()

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
                    'generated_document_filename': generated_document_filename_from_form,
                    'errors': {}
                }
                if chapter_audio_file_from_form:
                    temp_chapter_data_for_repopulation['audio_filename'] = chapter_audio_file_from_form.name
                if chapter_document_file_from_form:
                    temp_chapter_data_for_repopulation['document_filename'] = chapter_document_file_from_form
                if not chapter_title: current_chapter_errors['title'] = "Chapter title is required."
                audio_file_to_process_for_db = None
                text_content_for_db = None
                is_tts_generated_for_db = False
                actual_edge_tts_voice_id_for_gen = None
                tts_option_id_for_model = None
                source_document_filename_for_db = None
                voices_available_for_main_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(language)
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
                            audio_file_to_process_for_db = generated_tts_audio_url_from_form
                            text_content_for_db = chapter_text_content_input
                            is_tts_generated_for_db = True
                            tts_option_id_for_model = chapter_tts_voice_option_id
                            temp_chapter_data_for_repopulation['audio_filename'] = f"Generated: {os.path.basename(generated_tts_audio_url_from_form)}"
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
                            audio_file_to_process_for_db = generated_document_tts_audio_url_from_form
                            is_tts_generated_for_db = True
                            tts_option_id_for_model = chapter_doc_tts_voice_option_id
                            source_document_filename_for_db = generated_document_filename_from_form
                            temp_chapter_data_for_repopulation['audio_filename'] = f"From Doc: {os.path.basename(generated_document_tts_audio_url_from_form)}"
                elif effective_chapter_input_type == 'tts':
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
                elif effective_chapter_input_type == 'document_tts':
                    doc_file_obj = request.FILES.get('new_chapter_document_file')
                    tts_voice_id_doc = submitted_values.get('new_chapter_doc_tts_voice', '').strip()
                    voices_available_for_main_lang_doc = EDGE_TTS_VOICES_BY_LANGUAGE.get(language)
                    if not language or not voices_available_for_main_lang_doc:
                        current_chapter_errors['document_tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                    else:
                        selected_doc_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_id_doc)
                        if not selected_doc_voice_details or selected_doc_voice_details['id'] not in [v['id'] for v in voices_available_for_main_lang_doc]:
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
                                        text_content_for_db = extracted_doc_text.strip()[:20000]
                                        is_tts_generated_for_db = True
                                        actual_edge_tts_voice_id_for_gen = selected_doc_voice_details['edge_voice_id']
                                        tts_option_id_for_model = selected_doc_voice_details['id']
                                        source_document_filename_for_db = doc_file.name
                                except Exception as e_doc_extract:
                                    logger.error(f"Error processing document for chapter {index} on final save: {e_doc_extract}", exc_info=True)
                                    current_chapter_errors['document_tts_general'] = "Error processing document. Please ensure it's a valid text-based file."
                else:
                    current_chapter_errors['input_type'] = "Invalid audio source type for chapter."

                if current_chapter_errors:
                    form_errors[f'chapter_{index}'] = current_chapter_errors
                    temp_chapter_data_for_repopulation['errors'] = current_chapter_errors
                submitted_chapters_for_template.append(temp_chapter_data_for_repopulation)
                
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
                        'source_document_filename': source_document_filename_for_db,
                    })
            if any(key.startswith('chapter_') for key in form_errors):
                form_errors.setdefault('chapters_general', "Please correct errors in the chapter details.")

        if not form_errors:
            try:
                with transaction.atomic():
                    new_audiobook = Audiobook(
                        creator=creator,
                        title=title,
                        author=author,
                        narrator=narrator,
                        language=language,
                        genre=actual_genre_to_save,
                        description=description,
                        cover_image=cover_image_file,
                        is_paid=is_paid,
                        price=price if is_paid else Decimal('0.00'),
                        status='INACTIVE'
                    )
                    new_audiobook.full_clean()
                    new_audiobook.save()
                    
                    chapters_to_save_data.sort(key=lambda c: c['order'])
                    
                    for ch_data_to_save in chapters_to_save_data:
                        final_ch_audio_file_field_val = None
                        current_ch_text_content = ch_data_to_save['text_content_for_tts']
                        current_ch_is_tts_generated = ch_data_to_save['is_tts_final']
                        current_ch_tts_voice_id = ch_data_to_save['tts_option_id_for_model']
                        current_ch_source_document_filename = ch_data_to_save['source_document_filename']
                        ch_input_type = ch_data_to_save['input_type_final']
                        perm_ch_audio_dir = os.path.join('chapters_audio', new_audiobook.slug)
                        perm_ch_filename_base = f"ch_{ch_data_to_save['order']}_{slugify(ch_data_to_save['title'])}_{uuid.uuid4().hex[:6]}"
                        if ch_input_type == 'file':
                            final_ch_audio_file_field_val = ch_data_to_save['audio_file_obj_or_temp_url']
                        elif ch_input_type.startswith('generated_'):
                            temp_preview_url = ch_data_to_save['audio_file_obj_or_temp_url']
                            if not temp_preview_url or not temp_preview_url.startswith(settings.MEDIA_URL):
                                raise ValidationError(f"Invalid temporary audio URL for chapter '{ch_data_to_save['title']}'.")
                            rel_path_from_media_url = temp_preview_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
                            if default_storage.exists(rel_path_from_media_url):
                                try:
                                    with default_storage.open(rel_path_from_media_url, 'rb') as f_preview:
                                        perm_ch_filename = f"{perm_ch_filename_base}.mp3"
                                        perm_ch_path_rel_media_for_save = os.path.join(perm_ch_audio_dir, perm_ch_filename)
                                        final_ch_audio_file_field_val = ContentFile(f_preview.read(), name=perm_ch_path_rel_media_for_save)
                                        try:
                                            default_storage.delete(rel_path_from_media_url)
                                        except OSError as e_remove:
                                            logger.warning(f"Could not remove temp preview file {rel_path_from_media_url} from storage: {e_remove}")
                                except Exception as e_save:
                                    raise ValidationError(f"Error saving preview audio for chapter '{ch_data_to_save['title']}': {e_save}")
                            else:
                                raise ValidationError(f"Preview audio for chapter '{ch_data_to_save['title']}' was not found.")
                        elif ch_input_type == 'tts' or ch_input_type == 'document_tts':
                            actual_edge_voice_to_use = ch_data_to_save['actual_edge_tts_voice_id_for_gen']
                            text_for_generation = ch_data_to_save['text_content_for_tts']
                            if not text_for_generation or not actual_edge_voice_to_use:
                                raise ValidationError(f"Internal error: Missing text or voice for new TTS for chapter '{ch_data_to_save['title']}'.")
                            perm_ch_filename = f"{perm_ch_filename_base}_directgen.mp3"
                            perm_ch_path_rel_media_for_save = os.path.join(perm_ch_audio_dir, perm_ch_filename)
                            temp_output_path = default_storage.path(perm_ch_path_rel_media_for_save) if hasattr(default_storage, 'path') else os.path.join(settings.MEDIA_ROOT, perm_ch_path_rel_media_for_save)
                            os.makedirs(os.path.dirname(temp_output_path), exist_ok=True)
                            try:
                                async_to_sync(generate_audio_edge_tts_async)(text_for_generation, actual_edge_voice_to_use, temp_output_path)
                                with open(temp_output_path, 'rb') as f_upload:
                                    final_ch_audio_file_field_val = ContentFile(f_upload.read(), name=perm_ch_path_rel_media_for_save)
                                os.remove(temp_output_path)
                            except Exception as e_gen_final_ch:
                                raise ValidationError(f"TTS generation failed for chapter '{ch_data_to_save['title']}'. Error: {e_gen_final_ch}")
                        else:
                            raise ValidationError(f"Unknown chapter input type during save: {ch_input_type}")

                        new_chapter = Chapter.objects.create(
                            audiobook=new_audiobook,
                            chapter_name=ch_data_to_save['title'],
                            chapter_order=ch_data_to_save['order'],
                            audio_file=final_ch_audio_file_field_val,
                            text_content=current_ch_text_content,
                            is_tts_generated=current_ch_is_tts_generated,
                            tts_voice_id=current_ch_tts_voice_id,
                            source_document_filename=current_ch_source_document_filename
                        )
                        logger.info(f"Chapter '{new_chapter.chapter_name}' created for Audiobook '{new_audiobook.title}'.")
                        
                        process_chapter_for_moderation.delay(new_chapter.chapter_id)
                        logger.info(f"Dispatched moderation task for Chapter ID: {new_chapter.chapter_id}")
                        
                    messages.success(request, f"Audiobook '{new_audiobook.title}' has been submitted for review. You will be notified once it's published.")
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

    context = {
        'creator': creator,
        'form_errors': form_errors,
        'submitted_values': submitted_values,
        'EDGE_TTS_VOICES_BY_LANGUAGE_JSON': json.dumps(EDGE_TTS_VOICES_BY_LANGUAGE),
        'LANGUAGE_GENRE_MAPPING_JSON': json.dumps(LANGUAGE_GENRE_MAPPING),
        'GENRE_OTHER_VALUE': GENRE_OTHER_VALUE,
        'django_messages_json': json.dumps([{'message': str(m), 'tags': m.tags} for m in get_messages(request)])
    }
    return render(request, 'creator/creator_upload_audiobooks.html', context)


@creator_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def creator_manage_upload_detail_view(request, audiobook_slug):
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
                language = audiobook_locked.language

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

                    if new_cover_image:
                        max_cover_size = 2 * 1024 * 1024
                        allowed_cover_types = ['image/jpeg', 'image/png', 'image/jpg']
                        if new_cover_image.size > max_cover_size:
                            view_form_errors['cover_image'] = f"Cover image too large (Max {filesizeformat(max_cover_size)})."
                        elif new_cover_image.content_type not in allowed_cover_types:
                            view_form_errors['cover_image'] = "Invalid cover image type (PNG, JPG/JPEG only)."
                        
                        if not view_form_errors.get('cover_image'):
                            if audiobook_locked.cover_image:
                                old_cover_path = audiobook_locked.cover_image.name
                                if default_storage.exists(old_cover_path):
                                    default_storage.delete(old_cover_path)
                                    logger.info(f"Deleted old cover image: {old_cover_path}")
                            audiobook_locked.cover_image = new_cover_image
                            update_fields.append('cover_image')

                    if view_form_errors:
                        view_submitted_values['title'] = updated_title
                        view_submitted_values['author'] = updated_author
                        view_submitted_values['narrator'] = updated_narrator
                        view_submitted_values['description'] = updated_description
                        
                        raise ValidationError(view_form_errors)

                    if update_fields:
                        audiobook_locked.save(update_fields=update_fields)
                        audiobook_locked.refresh_from_db(fields=['slug'])
                        messages.success(request, f"Audiobook '{audiobook_locked.title}' details updated successfully.")
                    else:
                        messages.info(request, "No changes detected for audiobook details.")
                    
                    return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook_locked.slug)

                elif action == 'update_status_only':
                    new_status = post_data.get('status_only_select')
                    old_status = audiobook_locked.status
                    
                    logger.info(f"Status update attempt: '{old_status}' -> '{new_status}' for audiobook '{audiobook_locked.slug}'")
                    logger.info(f"Audiobook ID: {audiobook_locked.pk}, Current status: {audiobook_locked.status}, Current moderation_status: {audiobook_locked.moderation_status}")
                    
                    if audiobook_locked.status in ['REJECTED', 'PAUSED_BY_ADMIN', 'UNDER_REVIEW']:
                        error_msg = f"The status '{audiobook_locked.get_status_display()}' cannot be changed at this time."
                        logger.warning(f"Status change blocked: {error_msg}")
                        messages.error(request, error_msg)
                        raise ValidationError("Creator attempted to change a locked status.")
                    
                    if not new_status:
                        view_form_errors['status_update_status'] = "Please select a status."
                        logger.warning("Status update failed: No status selected")
                    elif new_status == audiobook_locked.status:
                        logger.info(f"Status unchanged: already '{new_status}'")
                        messages.info(request, "Audiobook status is already set to the selected value. No change applied.")
                        return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook_locked.slug)
                    elif new_status not in ['PUBLISHED', 'INACTIVE']:
                        view_form_errors['status_update_status'] = "Invalid status selected."
                        logger.warning(f"Invalid status selected: '{new_status}'")

                    if view_form_errors:
                        view_submitted_values['status_only_select'] = new_status
                        raise ValidationError(view_form_errors)

                    logger.info("🎯 CUSTOM SAVE METHOD DETECTED - Using coordinated status + moderation_status update...")
                    
                    success = False
                    
                    # Method 1: Update both status and moderation_status to work WITH the custom save method
                    try:
                        logger.info("Method 1: Coordinated status + moderation_status update...")
                        
                        # Set the appropriate moderation_status to match the desired status
                        if new_status == 'PUBLISHED':
                            audiobook_locked.moderation_status = Audiobook.ModerationStatusChoices.APPROVED
                        elif new_status == 'INACTIVE':
                            # For INACTIVE, we need to set a moderation status that won't trigger auto-change
                            audiobook_locked.moderation_status = Audiobook.ModerationStatusChoices.PENDING_REVIEW
                        
                        # Set the status
                        audiobook_locked.status = new_status
                        
                        logger.info(f"Setting status='{new_status}' and moderation_status='{audiobook_locked.moderation_status}'")
                        
                        # Save both fields
                        audiobook_locked.save(update_fields=['status', 'moderation_status'])
                        
                        # Verify the change
                        audiobook_locked.refresh_from_db(fields=['status', 'moderation_status'])
                        logger.info(f"After save: status='{audiobook_locked.status}', moderation_status='{audiobook_locked.moderation_status}'")
                        
                        if audiobook_locked.status == new_status:
                            logger.info("✅ Method 1 successful - coordinated update worked!")
                            success = True
                        else:
                            logger.warning(f"❌ Method 1 failed: Expected '{new_status}', got '{audiobook_locked.status}'")
                            
                    except Exception as method1_error:
                        logger.error(f"Method 1 failed with error: {method1_error}", exc_info=True)
                    
                    # Method 2: Direct SQL update (bypasses Django ORM completely)
                    if not success:
                        try:
                            logger.info("Method 2: Direct SQL update (bypassing ORM)...")
                            from django.db import connection
                            
                            # Use the correct table name from your models
                            table_name = "AUDIOBOOKS"  # Your table name is uppercase
                            
                            # Determine the appropriate moderation_status
                            if new_status == 'PUBLISHED':
                                new_moderation_status = 'approved'
                            elif new_status == 'INACTIVE':
                                new_moderation_status = 'pending_review'
                            else:
                                new_moderation_status = 'pending_review'
                            
                            with connection.cursor() as cursor:
                                # Update both status and moderation_status directly
                                cursor.execute(
                                    f'UPDATE "{table_name}" SET status = %s, moderation_status = %s WHERE audiobook_id = %s',
                                    [new_status, new_moderation_status, audiobook_locked.pk]
                                )
                                rows_affected = cursor.rowcount
                                logger.info(f"Direct SQL update affected {rows_affected} rows")
                                
                                if rows_affected > 0:
                                    # Verify the change
                                    cursor.execute(f'SELECT status, moderation_status FROM "{table_name}" WHERE audiobook_id = %s', [audiobook_locked.pk])
                                    result = cursor.fetchone()
                                    db_status, db_moderation_status = result
                                    logger.info(f"After SQL update: status='{db_status}', moderation_status='{db_moderation_status}'")
                                    
                                    if db_status == new_status:
                                        logger.info("✅ Method 2 successful - direct SQL update worked!")
                                        success = True
                                        # Update the model instance to reflect the change
                                        audiobook_locked.status = new_status
                                        audiobook_locked.moderation_status = new_moderation_status
                                    else:
                                        logger.error(f"❌ Method 2 failed: Expected '{new_status}', got '{db_status}'")
                                else:
                                    logger.error("❌ Method 2 failed: No rows affected")
                                    
                        except Exception as method2_error:
                            logger.error(f"Method 2 failed with error: {method2_error}", exc_info=True)
                    
                    # Method 3: QuerySet update (if transaction isn't aborted)
                    if not success:
                        try:
                            logger.info("Method 3: QuerySet update...")
                            
                            # Determine the appropriate moderation_status
                            if new_status == 'PUBLISHED':
                                new_moderation_status = Audiobook.ModerationStatusChoices.APPROVED
                            elif new_status == 'INACTIVE':
                                new_moderation_status = Audiobook.ModerationStatusChoices.PENDING_REVIEW
                            else:
                                new_moderation_status = Audiobook.ModerationStatusChoices.PENDING_REVIEW
                            
                            rows_updated = Audiobook.objects.filter(pk=audiobook_locked.pk).update(
                                status=new_status,
                                moderation_status=new_moderation_status
                            )
                            logger.info(f"QuerySet update affected {rows_updated} rows")
                            
                            if rows_updated > 0:
                                # Verify the change
                                db_audiobook = Audiobook.objects.get(pk=audiobook_locked.pk)
                                logger.info(f"After QuerySet update: status='{db_audiobook.status}', moderation_status='{db_audiobook.moderation_status}'")
                                
                                if db_audiobook.status == new_status:
                                    logger.info("✅ Method 3 successful - QuerySet update worked!")
                                    success = True
                                    audiobook_locked.status = new_status
                                    audiobook_locked.moderation_status = new_moderation_status
                                else:
                                    logger.error(f"❌ Method 3 failed: Expected '{new_status}', got '{db_audiobook.status}'")
                            else:
                                logger.error("❌ Method 3 failed: No rows updated")
                                
                        except Exception as method3_error:
                            logger.error(f"Method 3 failed with error: {method3_error}", exc_info=True)
                    
                    if success:
                        logger.info(f"🎉 Status successfully updated from '{old_status}' to '{new_status}' for audiobook '{audiobook_locked.slug}'")
                        messages.success(request, f"Audiobook status updated from '{old_status}' to '{new_status}'.")
                    else:
                        logger.error(f"💥 All methods failed to update status for audiobook '{audiobook_locked.slug}'")
                        messages.error(request, "Status update failed. The custom save method is preventing status changes. Please contact support.")
                    
                    return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook_locked.slug)

                elif action == 'add_chapter':
                    errors = {}
                    title = post_data.get('new_chapter_title', '').strip()
                    input_type = post_data.get('new_chapter_input_type_hidden', 'file').strip()
                    
                    if not title: errors['new_chapter_title'] = "Chapter title is required."
                    
                    audio_source, text_content, is_tts, tts_voice_id, doc_filename = None, None, False, None, None
                    
                    if input_type == 'file':
                        audio_source = request.FILES.get('new_chapter_audio')
                        if not audio_source: errors['new_chapter_audio'] = "An audio file is required."
                        elif audio_source:
                            max_audio_size = 50 * 1024 * 1024
                            allowed_audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/x-m4a', 'audio/m4a']
                            if audio_source.size > max_audio_size:
                                errors['new_chapter_audio'] = f"Audio file too large (Max {filesizeformat(max_audio_size)})."
                            elif audio_source.content_type not in allowed_audio_types:
                                errors['new_chapter_audio'] = f"Invalid audio file type. Allowed: MP3, WAV, OGG, M4A."
                    
                    elif input_type == 'generated_tts':
                        audio_source = post_data.get('new_chapter_generated_tts_url')
                        tts_voice_id = post_data.get('new_chapter_tts_voice')
                        text_content = post_data.get('new_chapter_text_content', '')

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
                        doc_filename = post_data.get('new_chapter_document_filename', '')
                        text_content = post_data.get('new_chapter_document_extracted_text', '')

                        if not audio_source: errors['add_chapter_general'] = "A confirmed generated audio file (from document) is required."
                        if not tts_voice_id or tts_voice_id == 'default': errors['new_chapter_doc_tts_voice'] = "A narrator voice must be selected."
                        else:
                            is_tts = True
                            voices_for_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(audiobook_locked.language)
                            selected_voice_detail = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_id)
                            if not voices_for_lang or not selected_voice_detail or selected_voice_detail['id'] not in [v['id'] for v in voices_for_lang]:
                                errors['new_chapter_doc_tts_voice'] = "Invalid narrator voice selected for audiobook language."

                    elif input_type == 'tts':
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

                    elif input_type == 'document_tts':
                        doc_file_obj = request.FILES.get('new_chapter_document_file')
                        tts_voice_id_doc = post_data.get('new_chapter_doc_tts_voice', '').strip()
                        voices_available_for_main_lang_doc = EDGE_TTS_VOICES_BY_LANGUAGE.get(audiobook_locked.language)
                        if not audiobook_locked.language or not voices_available_for_main_lang_doc:
                            errors['document_tts_general'] = "Audiobook language is not set or TTS is unavailable for it."
                        else:
                            selected_doc_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_id_doc)
                            if not selected_doc_voice_details or selected_doc_voice_details['id'] not in [v['id'] for v in voices_available_for_main_lang_doc]:
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
                                            text_content = extracted_doc_text.strip()[:20000]
                                            is_tts = True
                                            actual_edge_tts_voice_id_for_gen = selected_doc_voice_details['edge_voice_id']
                                            tts_voice_id = selected_doc_voice_details['id']
                                            doc_filename = doc_file.name
                                    except Exception as e_doc_extract:
                                        logger.error(f"Error processing document for new chapter direct save: {e_doc_extract}", exc_info=True)
                                        errors['document_tts_general'] = "Error processing document for direct TTS generation."
                    else:
                        errors['add_chapter_general'] = "Invalid audio source type selected for new chapter."

                    if errors:
                        view_form_errors['add_chapter_errors'] = errors
                        add_chapter_active_with_errors = True
                        messages.error(request, "Please correct the errors to add the chapter.")
                        raise ValidationError(errors)

                    new_order = audiobook_locked.chapters.count() + 1
                    perm_ch_audio_dir = os.path.join('chapters_audio', audiobook_locked.slug)
                    perm_ch_filename_base = f"ch_{new_order}_{slugify(title)}_{uuid.uuid4().hex[:6]}"
                    
                    final_audio_file_field_val = None
                    if input_type == 'file':
                        final_audio_file_field_val = audio_source
                    elif input_type.startswith('generated_'):
                        temp_preview_url = audio_source
                        rel_path = temp_preview_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
                        if default_storage.exists(rel_path):
                            with default_storage.open(rel_path, 'rb') as f:
                                unique_filename = f"{perm_ch_filename_base}.mp3"
                                final_audio_file_field_val = ContentFile(f.read(), name=os.path.join(perm_ch_audio_dir, unique_filename))
                            try:
                                default_storage.delete(rel_path)
                            except OSError as e_remove:
                                logger.warning(f"Could not remove temp preview file {rel_path} from storage: {e_remove}")
                            logger.info(f"Moved preview audio from {rel_path} to permanent: {final_audio_file_field_val.name}")
                        else:
                            logger.error(f"Temporary audio file not found for chapter add: {rel_path}")
                            errors['add_chapter_general'] = "Temporary audio file not found. Please re-generate or re-confirm."
                            raise ValidationError(errors)
                    elif input_type == 'tts' or input_type == 'document_tts':
                        final_file_name = f"{perm_ch_filename_base}_directgen.mp3"
                        full_path_for_gen = os.path.join(perm_ch_audio_dir, final_file_name)
                        temp_output_path_for_gen = default_storage.path(full_path_for_gen) if hasattr(default_storage, 'path') else os.path.join(settings.MEDIA_ROOT, full_path_for_gen)
                        os.makedirs(os.path.dirname(temp_output_path_for_gen), exist_ok=True)
                        
                        try:
                            actual_edge_voice_to_use = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_id, {}).get('edge_voice_id')
                            if not actual_edge_voice_to_use:
                                raise ValueError(f"Edge TTS voice ID not found for {tts_voice_id}")
                            async_to_sync(generate_audio_edge_tts_async)(text_content, actual_edge_voice_to_use, temp_output_path_for_gen)
                            
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
                        audio_file=final_audio_file_field_val,
                        text_content=text_content,
                        is_tts_generated=is_tts,
                        tts_voice_id=tts_voice_id,
                        source_document_filename=doc_filename
                    )
                    
                    chapter.full_clean()
                    chapter.save()
                    messages.success(request, f"Chapter '{title}' added successfully.")
                    return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook_locked.slug)

                elif action.startswith('edit_chapter_'):
                    chapter_id = action.replace('edit_chapter_', '')
                    chapter_locked = get_object_or_404(Chapter.objects.select_for_update(), chapter_id=chapter_id, audiobook=audiobook_locked)
                    
                    edit_errors = {}
                    new_chapter_title = post_data.get(f'chapter_title_{chapter_id}', '').strip()
                    edit_input_type = post_data.get(f'edit_chapter_input_type_hidden_{chapter_id}', '').strip()
                    
                    new_audio_file_from_form = request.FILES.get(f'chapter_audio_{chapter_id}')
                    new_text_content_input = post_data.get(f'chapter_text_content_{chapter_id}', '').strip()
                    new_tts_voice_option_id = post_data.get(f'chapter_tts_voice_{chapter_id}', '').strip()
                    new_document_file_from_form = request.FILES.get(f'chapter_document_edit_{chapter_id}')
                    new_doc_tts_voice_option_id = post_data.get(f'chapter_doc_tts_voice_edit_{chapter_id}', '').strip()
                    
                    generated_tts_audio_url_from_form = post_data.get(f'edit_chapter_generated_tts_url_{chapter_id}', '').strip()
                    generated_doc_tts_audio_url_from_form = post_data.get(f'edit_chapter_generated_document_tts_url_{chapter_id}', '').strip()
                    generated_doc_filename_from_form = post_data.get(f'edit_chapter_source_document_filename_{chapter_id}', '').strip()

                    final_audio_file_for_save = None
                    final_text_content = chapter_locked.text_content
                    final_is_tts_generated = chapter_locked.is_tts_generated
                    final_tts_voice_id = chapter_locked.tts_voice_id
                    final_source_document_filename = chapter_locked.source_document_filename
                    delete_old_audio = False

                    voices_available_for_main_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(audiobook_locked.language)

                    if not new_chapter_title: edit_errors['title'] = "Chapter title is required."

                    if edit_input_type == 'file':
                        if new_audio_file_from_form:
                            final_audio_file_for_save = new_audio_file_from_form
                            max_audio_size = 50 * 1024 * 1024
                            allowed_audio_types = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/x-m4a', 'audio/m4a']
                            if new_audio_file_from_form.size > max_audio_size:
                                edit_errors['audio'] = f"Audio file too large (Max {filesizeformat(max_audio_size)})."
                            elif new_audio_file_from_form.content_type not in allowed_audio_types:
                                edit_errors['audio'] = "Invalid audio file type. Allowed: MP3, WAV, OGG, M4A."
                            
                            if not edit_errors.get('audio'):
                                delete_old_audio = True
                        elif not chapter_locked.audio_file:
                            edit_errors['audio'] = "An audio file is required if no existing file is present."
                        else:
                            final_audio_file_for_save = None

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
                                final_audio_file_for_save = generated_tts_audio_url_from_form
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
                                final_audio_file_for_save = generated_doc_tts_audio_url_from_form
                                final_text_content = None
                                final_is_tts_generated = True
                                final_tts_voice_id = new_doc_tts_voice_option_id
                                final_source_document_filename = generated_doc_filename_from_form
                                delete_old_audio = True

                    elif edit_input_type == 'tts':
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
                                final_source_document_filename = None
                                delete_old_audio = True

                    elif edit_input_type == 'document_tts':
                        doc_file = new_document_file_from_form
                        if not doc_file and chapter_locked.source_document_filename and chapter_locked.is_tts_generated:
                            final_text_content = chapter_locked.text_content
                            final_is_tts_generated = True
                            final_tts_voice_id = new_doc_tts_voice_option_id
                            final_source_document_filename = chapter_locked.source_document_filename
                            delete_old_audio = True
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
                            async_to_sync(generate_audio_edge_tts_async)(final_text_content, actual_edge_voice_to_use, temp_output_path_for_gen)
                            
                            with open(temp_output_path_for_gen, 'rb') as f_generated:
                                final_audio_file_for_save = ContentFile(f_generated.read(), name=os.path.basename(full_path_for_gen))
                            
                            os.remove(temp_output_path_for_gen)
                            logger.info(f"Generated and prepared TTS from {temp_output_path_for_gen}")
                        except Exception as e_gen:
                            logger.error(f"TTS generation failed for chapter '{new_chapter_title}': {e_gen}", exc_info=True)
                            edit_errors['tts_general'] = f"TTS generation failed: {e_gen}"
                            raise ValidationError(edit_errors)
                            
                    elif edit_input_type.startswith('generated_'):
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
                                    default_storage.delete(rel_path)
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
                    
                    if delete_old_audio and chapter_locked.audio_file and chapter_locked.audio_file.name:
                        old_audio_path = chapter_locked.audio_file.name
                        if default_storage.exists(old_audio_path):
                            try:
                                default_storage.delete(old_audio_path)
                                logger.info(f"Deleted old audio file for chapter '{chapter_locked.chapter_name}': {old_audio_path}")
                            except OSError as e_del:
                                logger.warning(f"Could not delete old audio file {old_audio_path}: {e_del}")
                    
                    chapter_locked.chapter_name = new_chapter_title
                    chapter_locked.text_content = final_text_content
                    chapter_locked.is_tts_generated = final_is_tts_generated
                    chapter_locked.tts_voice_id = final_tts_voice_id
                    chapter_locked.source_document_filename = final_source_document_filename
                    
                    if final_audio_file_for_save:
                        chapter_locked.audio_file = final_audio_file_for_save

                    chapter_locked.save()
                    messages.success(request, f"Chapter '{new_chapter_title}' updated successfully.")
                    return redirect('AudioXApp:creator_manage_upload_detail', audiobook_slug=audiobook_locked.slug)

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

    db_chapters = audiobook.chapters.order_by('chapter_order')
    chapters_context_list = []
    for chapter_instance in db_chapters:
        tts_voice_display_name = ""
        if chapter_instance.is_tts_generated and chapter_instance.tts_voice_id:
            voice_detail = ALL_EDGE_TTS_VOICES_MAP.get(chapter_instance.tts_voice_id)
            tts_voice_display_name = voice_detail['name'] if voice_detail else f"Unknown Voice ({chapter_instance.tts_voice_id})"
        
        input_type_for_template = 'file'
        if chapter_instance.is_tts_generated:
            if chapter_instance.source_document_filename:
                input_type_for_template = 'generated_document_tts'
            elif chapter_instance.text_content:
                input_type_for_template = 'generated_tts'
            else:
                input_type_for_template = 'generated_tts'

        file_size_display = None
        if chapter_instance.audio_file and chapter_instance.audio_file.name:
            try:
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
            'doc_tts_voice_id': chapter_instance.tts_voice_id if chapter_instance.is_tts_generated and chapter_instance.source_document_filename else None,
        })

    view_form_errors['add_chapter_active_with_errors'] = add_chapter_active_with_errors
    django_messages_list = [{'message': str(m), 'tags': m.tags} for m in get_messages(request)]

    can_creator_change_status = audiobook.status not in ['REJECTED', 'PAUSED_BY_ADMIN', 'UNDER_REVIEW']

    final_context = {
        'creator': creator, 'audiobook': audiobook, 'chapters_context_list': chapters_context_list,
        'form_errors': view_form_errors, 'submitted_values': view_submitted_values,
        'creator_allowed_status_choices_for_toggle': [('PUBLISHED', 'Published (Visible to users)'), ('INACTIVE', 'Inactive (Hidden from public, earnings paused)')],
        'can_creator_change_status': can_creator_change_status,
        'django_messages_json': json.dumps(django_messages_list, cls=DjangoJSONEncoder),
        'EDGE_TTS_VOICES_BY_LANGUAGE_JSON': json.dumps(EDGE_TTS_VOICES_BY_LANGUAGE),
        'GENRE_OTHER_VALUE': GENRE_OTHER_VALUE
    }
    logger.debug(f"Rendering manage_upload_detail. Context form_errors: {final_context.get('form_errors')}, Submitted: {final_context.get('submitted_values')}")
    return render(request, 'creator/creator_manage_uploads.html', final_context)


@creator_required
def creator_my_audiobooks_view(request):
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
                    if default_storage.exists(chapter.audio_file.name):
                        file_size = filesizeformat(default_storage.size(chapter.audio_file.name))
                    else:
                        logger.warning(f"Audio file for chapter {chapter.chapter_id} not found in storage: {chapter.audio_file.name}")
                        audio_filename = "File Missing"
            except Exception as e:
                logger.warning(f"Error getting file details for chapter {chapter.chapter_id} in get_audiobook_chapters_json: {e}")
            
            # Ensure duration_seconds is included in the JSON response
            chapter_data = {
                'id': chapter.chapter_id,
                'name': chapter.chapter_name,
                'order': chapter.chapter_order,
                'audio_filename': audio_filename,
                'file_size': file_size,
                'duration_seconds': chapter.duration_seconds # Added duration_seconds here
            }
            chapters_list.append(chapter_data)
        return JsonResponse({'chapters': chapters_list}, status=200)
    except Http404:
        logger.warning(f"Audiobook not found or permission denied in get_audiobook_chapters_json for slug {audiobook_slug}, user {request.user.username}")
        return JsonResponse({'error': 'Audiobook not found or permission denied.'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_audiobook_chapters_json for slug {audiobook_slug}: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal server error occurred.'}, status=500)