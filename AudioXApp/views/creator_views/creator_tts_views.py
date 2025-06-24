import json
import uuid
import os
import datetime
import mimetypes
import logging
import asyncio
import io
from datetime import timedelta
from typing import Optional
import fitz

try:
    import docx
except ImportError:
    docx = None

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    AudioSegment = None

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.template.defaultfilters import filesizeformat
from ...models import User, Creator
from ..decorators import creator_required
from ...forms import DocumentUploadForm
import edge_tts
from ...tts_constants import EDGE_TTS_VOICES_BY_LANGUAGE, ALL_EDGE_TTS_VOICES_MAP

logger = logging.getLogger(__name__)

def extract_text_from_docx(file_content_bytes: bytes) -> Optional[str]:
    if docx is None:
        logger.error("python-docx library is not installed. Cannot process .docx files.")
        return None
    try:
        doc_stream = io.BytesIO(file_content_bytes)
        document = docx.Document(doc_stream)
        full_text = [para.text for para in document.paragraphs]
        text = "\n".join(full_text).strip()
        logger.info(f"DOCX Extraction: Extracted {len(text)} characters.")
        return text if text else None
    except Exception as e:
        logger.error(f"Error extracting text from DOCX: {e}", exc_info=True)
        return None

def extract_text_from_pdf(pdf_content_bytes: bytes) -> Optional[str]:
    text = ""
    try:
        doc = fitz.open(stream=pdf_content_bytes, filetype="pdf")
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            page_text = page.get_text("text")
            text += page_text + "\n"
        doc.close()
        stripped_text = text.strip()
        logger.info(f"PDF Extraction: Extracted {len(stripped_text)} characters.")
        return stripped_text if stripped_text else None
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}", exc_info=True)
        return None

async def generate_audio_edge_tts_async(text: str, voice_id: str, output_path: str):
    communicate = edge_tts.Communicate(text, voice_id)
    await communicate.save(output_path)
    logger.info(f"Edge TTS audio initially saved to {output_path}")

    if PYDUB_AVAILABLE and AudioSegment is not None:
        try:
            audio = AudioSegment.from_file(output_path, format="mp3")
            audio.export(output_path, format="mp3")
            logger.info(f"Successfully laundered TTS audio file at {output_path}")
        except Exception as e:
            logger.error(f"Could not launder TTS audio file at {output_path}. Error: {e}", exc_info=True)
    else:
        logger.warning("Pydub is not available. Skipping audio laundering for TTS file. Duration calculation might be inaccurate.")

@creator_required
@require_POST
@csrf_protect
def generate_tts_preview_audio(request):
    try:
        text_content = request.POST.get('text_content', '').strip()
        tts_voice_option_id = request.POST.get('tts_voice_id', '').strip()
        audiobook_language_selected = request.POST.get('audiobook_language', '').strip()
        logger.info(f"[TTS PREVIEW AJAX] User: {request.user.username}, Lang: {audiobook_language_selected}, VoiceID: '{tts_voice_option_id}', TextLen: {len(text_content)}")
        if not text_content:
            return JsonResponse({'status': 'error', 'message': 'Text content is required.'}, status=400)
        if len(text_content) < 10:
            return JsonResponse({'status': 'error', 'message': 'Text content too short (min 10 characters).'}, status=400)
        if len(text_content) > 5000:
            return JsonResponse({'status': 'error', 'message': 'Text content too long (max 5000 chars for preview).'}, status=400)
        if not audiobook_language_selected:
            return JsonResponse({'status': 'error', 'message': 'Audiobook language selection is missing.'}, status=400)
        voices_for_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(audiobook_language_selected)
        if not voices_for_lang:
            return JsonResponse({'status': 'error', 'message': f"TTS is not currently available for {audiobook_language_selected}."}, status=400)
        selected_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_option_id)
        actual_edge_tts_voice_id_to_use = None
        final_tts_voice_id_for_response = tts_voice_option_id
        if not selected_voice_details or selected_voice_details.get('edge_voice_id') not in [v.get('edge_voice_id') for v in voices_for_lang]:
            logger.warning(f"[TTS PREVIEW AJAX] Invalid voice '{tts_voice_option_id}' for lang '{audiobook_language_selected}'. Trying default if available.")
            if voices_for_lang:
                selected_voice_details = voices_for_lang[0]
                actual_edge_tts_voice_id_to_use = selected_voice_details['edge_voice_id']
                final_tts_voice_id_for_response = selected_voice_details['id']
            else:
                return JsonResponse({'status': 'error', 'message': f'No voices configured for {audiobook_language_selected}.'}, status=400)
        else:
            actual_edge_tts_voice_id_to_use = selected_voice_details['edge_voice_id']
        if not actual_edge_tts_voice_id_to_use:
            return JsonResponse({'status': 'error', 'message': 'Could not determine a valid TTS voice.'}, status=400)
        temp_tts_dir_name = getattr(settings, 'TEMP_TTS_PREVIEWS_DIR_NAME', 'temp_tts_previews')
        temp_tts_full_dir_path = os.path.join(settings.MEDIA_ROOT, temp_tts_dir_name)
        os.makedirs(temp_tts_full_dir_path, exist_ok=True)
        temp_audio_filename = f"preview_{request.user.user_id}_{uuid.uuid4().hex[:8]}.mp3"
        temp_audio_filepath_local = os.path.join(temp_tts_full_dir_path, temp_audio_filename)
        asyncio.run(generate_audio_edge_tts_async(text_content, actual_edge_tts_voice_id_to_use, temp_audio_filepath_local))
        temp_audio_url = os.path.join(settings.MEDIA_URL, temp_tts_dir_name, temp_audio_filename)
        temp_audio_url = temp_audio_url.replace(os.sep, '/')
        if not temp_audio_url.startswith('/'): temp_audio_url = '/' + temp_audio_url
        try:
            for old_file_name in os.listdir(temp_tts_full_dir_path):
                old_filepath = os.path.join(temp_tts_full_dir_path, old_file_name)
                if os.path.isfile(old_filepath) and old_filepath != temp_audio_filepath_local:
                    file_mod_time_naive = datetime.datetime.fromtimestamp(os.path.getmtime(old_filepath))
                    file_mod_time_aware = timezone.make_aware(file_mod_time_naive, timezone.get_default_timezone()) if timezone.is_naive(file_mod_time_naive) else file_mod_time_naive
                    if file_mod_time_aware < (timezone.now() - timedelta(hours=getattr(settings, 'TEMP_FILE_CLEANUP_HOURS', 2))):
                        os.remove(old_filepath)
                        logger.info(f"[EDGE_TTS PREVIEW] Deleted old temp file: {old_filepath}")
        except Exception as e_cleanup:
            logger.error(f"[EDGE_TTS PREVIEW] Error cleaning up old temp TTS files: {e_cleanup}", exc_info=True)
        return JsonResponse({'status': 'success', 'audio_url': temp_audio_url, 'voice_id_used': final_tts_voice_id_for_response, 'filename': temp_audio_filename})
    except Exception as e:
        logger.error(f"[TTS PREVIEW AJAX] Error for user {request.user.username}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500)

@creator_required
@require_POST
@csrf_protect
def generate_document_tts_preview_audio(request):
    try:
        form = DocumentUploadForm(request.POST, request.FILES)
        
        narrator_gender = request.POST.get('narrator_gender', '').strip()

        user_display_name = request.user.username if request.user.is_authenticated else 'AnonymousUser'
        document_file = form.cleaned_data.get('document_file') if form.is_valid() else request.FILES.get('document_file')
        language = form.cleaned_data.get('language') if form.is_valid() else request.POST.get('language')
        
        logger.info(
            f"[DOC_TTS] POST. User: {user_display_name}, "
            f"Lang: {language}, "
            f"NarratorGender: {narrator_gender}, "
            f"File: {document_file.name if document_file else 'No File'}"
        )

        if not form.is_valid():
            errors = form.errors.get_json_data()
            selected_language = request.POST.get('language')
            
            if selected_language in ['English', 'Urdu'] and not narrator_gender:
                if 'narrator_gender' not in errors:
                    errors['narrator_gender'] = [{'message': 'Please select a narrator gender for this language.', 'code': 'required'}]

            logger.warning(f"[DOC_TTS] Form validation failed for user {user_display_name}. Errors: {json.dumps(errors)}")
            return JsonResponse({'status': 'error', 'errors': errors}, status=400)
        
        document_file = form.cleaned_data['document_file']
        language = form.cleaned_data['language']

        voices_for_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(language, [])
        selected_voice_details = None

        if language in ['English', 'Urdu']:
            if not narrator_gender:
                return JsonResponse({'status': 'error', 'errors': {'narrator_gender': [{'message': 'Narrator gender is required for the selected language.'}]}}, status=400)
            
            for voice in voices_for_lang:
                if voice.get('gender') == narrator_gender:
                    selected_voice_details = voice
                    break
            
            if not selected_voice_details:
                logger.error(f"[DOC_TTS] No voice found for Lang: {language}, Gender: {narrator_gender}")
                return JsonResponse({'status': 'error', 'message': 'Internal configuration error: No voice found for the selected language and gender.'}, status=500)
        
        else:
            if voices_for_lang:
                selected_voice_details = voices_for_lang[0]
            else:
                return JsonResponse({'status': 'error', 'message': f"TTS is not available for the language: {language}."}, status=400)

        doc_content_bytes = document_file.read()
        doc_extension = os.path.splitext(document_file.name.lower())[1]
        extracted_text = None
        if doc_extension == '.pdf':
            extracted_text = extract_text_from_pdf(doc_content_bytes)
        elif doc_extension in ['.docx', '.doc']:
            extracted_text = extract_text_from_docx(doc_content_bytes)

        if not extracted_text or len(extracted_text.strip()) < 10:
            return JsonResponse({'status': 'error', 'errors': {'document_file': [{'message': 'Could not extract sufficient text. The document might be empty, password-protected, or purely image-based.'}]}}, status=400)

        text_for_preview = extracted_text.strip()[:5000]
        actual_edge_tts_voice_id = selected_voice_details['edge_voice_id']

        temp_tts_dir_name = getattr(settings, 'TEMP_DOC_TTS_PREVIEWS_DIR_NAME', 'temp_doc_tts_previews')
        temp_tts_full_dir_path = os.path.join(settings.MEDIA_ROOT, temp_tts_dir_name)
        os.makedirs(temp_tts_full_dir_path, exist_ok=True)
        
        user_id_part = request.user.pk if request.user.is_authenticated else 'public'
        temp_audio_filename = f"doc_preview_{user_id_part}_{uuid.uuid4().hex[:8]}.mp3"
        temp_audio_filepath_local = os.path.join(temp_tts_full_dir_path, temp_audio_filename)

        asyncio.run(generate_audio_edge_tts_async(text_for_preview, actual_edge_tts_voice_id, temp_audio_filepath_local))

        if not os.path.exists(temp_audio_filepath_local):
            logger.error(f"[DOC_TTS] Generated audio file not found at {temp_audio_filepath_local} after generation attempt.")
            return JsonResponse({'status': 'error', 'message': 'Audio generation failed on the server.'}, status=500)

        temp_audio_url = os.path.join(settings.MEDIA_URL, temp_tts_dir_name, temp_audio_filename).replace(os.sep, '/')
        if not temp_audio_url.startswith('/'):
            temp_audio_url = '/' + temp_audio_url
        
        logger.info(f"[DOC_TTS] Preview audio URL: {temp_audio_url}, Voice ID used: {selected_voice_details['id']}")
        
        try:
            for old_file_name in os.listdir(temp_tts_full_dir_path):
                old_filepath = os.path.join(temp_tts_full_dir_path, old_file_name)
                if os.path.isfile(old_filepath) and old_filepath != temp_audio_filepath_local:
                    file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(old_filepath))
                    if timezone.is_naive(file_mod_time):
                        file_mod_time = timezone.make_aware(file_mod_time, timezone.get_default_timezone())
                    
                    if file_mod_time < (timezone.now() - timedelta(hours=getattr(settings, 'TEMP_FILE_CLEANUP_HOURS', 2))):
                        os.remove(old_filepath)
                        logger.info(f"[DOC_TTS CLEANUP] Deleted old temp file: {old_filepath}")
        except Exception as e_cleanup:
            logger.error(f"[DOC_TTS CLEANUP] Error cleaning old temp files: {e_cleanup}", exc_info=True)

        return JsonResponse({
            'status': 'success',
            'audio_url': temp_audio_url,
            'voice_id_used': selected_voice_details['id'],
            'filename': temp_audio_filename,
            'source_filename': document_file.name
        })

    except Exception as e:
        logger.error(f"[DOC_TTS] General Error for User: {request.user.username if request.user.is_authenticated else 'UnknownUser'}. Error: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'An unexpected server error occurred. Please check the server logs.'}, status=500)