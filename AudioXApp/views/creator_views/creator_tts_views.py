# AudioXApp/views/creator_views/creator_tts_views.py

import json
import uuid
import os
import mimetypes
import logging
import asyncio
import io
from datetime import timedelta
import datetime
from typing import Optional # Keep this import

# For document processing
import fitz    # PyMuPDF for PDF text extraction
try:
    import docx # python-docx for .docx text extraction
except ImportError:
    docx = None 

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone
from django.conf import settings
from django.template.defaultfilters import filesizeformat
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


from ...models import User, Creator # Relative imports
from ..decorators import creator_required # Relative import

# --- Edge TTS Setup ---
import edge_tts

logger = logging.getLogger(__name__)

# --- Edge TTS Voice Mapping and Language/Genre Constants ---
# These constants are used by TTS views and potentially audiobook upload/management views.
# Consider moving to a shared constants.py if they grow or are widely used.

EDGE_TTS_VOICES_BY_LANGUAGE = {
    'English': [
        {'id': 'en-US-AriaNeural', 'name': 'Aria (Female)', 'gender': 'Female', 'edge_voice_id': 'en-US-AriaNeural'},
        {'id': 'en-US-GuyNeural', 'name': 'Guy (Male)', 'gender': 'Male', 'edge_voice_id': 'en-US-GuyNeural'},
        {'id': 'en-GB-LibbyNeural', 'name': 'Libby (Female, UK)', 'gender': 'Female', 'edge_voice_id': 'en-GB-LibbyNeural'},
        {'id': 'en-GB-RyanNeural', 'name': 'Ryan (Male, UK)', 'gender': 'Male', 'edge_voice_id': 'en-GB-RyanNeural'},
        {'id': 'en-AU-NatashaNeural', 'name': 'Natasha (Female, AU)', 'gender': 'Female', 'edge_voice_id': 'en-AU-NatashaNeural'},
        {'id': 'en-IN-NeerjaNeural', 'name': 'Neerja (Female, IN)', 'gender': 'Female', 'edge_voice_id': 'en-IN-NeerjaNeural'},
    ],
    'Urdu': [
        {'id': 'ur-PK-UzmaNeural', 'name': 'Uzma (Female)', 'gender': 'Female', 'edge_voice_id': 'ur-PK-UzmaNeural'},
        {'id': 'ur-PK-AsadNeural', 'name': 'Asad (Male)', 'gender': 'Male', 'edge_voice_id': 'ur-PK-AsadNeural'},
    ],
    'Punjabi': [], 
    'Sindhi': [],
}

ALL_EDGE_TTS_VOICES_MAP = {
    voice['id']: voice
    for lang_voices in EDGE_TTS_VOICES_BY_LANGUAGE.values()
    for voice in lang_voices
}
EDGE_TTS_DEFAULT_VOICE_ID_IF_INVALID = 'en-US-AriaNeural' # Fallback voice

LANGUAGE_GENRE_MAPPING = {
    "English": [
        {"value": "Fiction", "text": "Fiction"}, {"value": "Mystery", "text": "Mystery"},
        {"value": "Thriller", "text": "Thriller"}, {"value": "Sci-Fi", "text": "Sci-Fi"},
        {"value": "Fantasy", "text": "Fantasy"}, {"value": "Romance", "text": "Romance"},
        {"value": "Biography", "text": "Biography"}, {"value": "History", "text": "History"},
        {"value": "Self-Help", "text": "Self-Help"}, {"value": "Business", "text": "Business"},
        {"value": "Children", "text": "Children's Story"}, {"value": "Poetry", "text": "Poetry"},
        {"value": "Horror", "text": "Horror"}, {"value": "Comedy", "text": "Comedy"},
        {"value": "Education", "text": "Education"}, {"value": "Religion-Spirituality", "text": "Religion & Spirituality"},
        {"value": "Other", "text": "Other"}
    ],
    "Urdu": [
        {"value": "Novel", "text": "Novel (ناول)"}, {"value": "Afsana", "text": "Afsana (افسانہ)"},
        {"value": "Shayari", "text": "Shayari (شاعری)"}, {"value": "Tareekh", "text": "Tareekh (تاریخ)"},
        {"value": "Safarnama", "text": "Safarnama (سفرنامہ)"}, {"value": "Mazah", "text": "Mazah (مزاح)"},
        {"value": "Bachon ka Adab", "text": "Bachon ka Adab (بچوں کا ادب)"},
        {"value": "Mazhabi Adab", "text": "Mazhabi Adab (مذہبی ادب)"}, {"value": "Siyasi Adab", "text": "Siyasi Adab (سیاسی ادب)"},
        {"value": "Falsafa", "text": "Falsafa (فلسفہ)"}, {"value": "Deegar", "text": "Deegar (دیگر)"}
    ],
    "Punjabi": [
        {"value": "Qissa", "text": "Qissa (قصہ)"}, {"value": "Lok Geet", "text": "Lok Geet (لوک گیت)"},
        {"value": "Kafi", "text": "Kafi (کافی)"}, {"value": "Punjabi-Other", "text": "Other (ہور)"}
    ],
    "Sindhi": [
        {"value": "Lok Adab", "text": "Lok Adab (لوڪ ادب)"}, {"value": "Shayari", "text": "Shayari (شاعري)"},
        {"value": "Kahani", "text": "Kahani (ڪهاڻي)"}, {"value": "Sindhi-Other", "text": "Other (ٻيو)"}
    ]
}

# --- Helper functions for text extraction ---
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
    """Asynchronously generates audio using edge-tts and saves it."""
    communicate = edge_tts.Communicate(text, voice_id)
    await communicate.save(output_path)
    logger.info(f"Edge TTS audio saved to {output_path} for voice {voice_id}")

# --- TTS Preview Views ---

@creator_required
@require_POST
@csrf_protect
def generate_tts_preview_audio(request):
    try:
        text_content = request.POST.get('text_content', '').strip()
        tts_voice_option_id = request.POST.get('tts_voice_id', '').strip()
        audiobook_language_selected = request.POST.get('audiobook_language', '').strip()

        logger.info(f"[EDGE_TTS PREVIEW] Request. User: {request.user.username}, Lang: {audiobook_language_selected}, VoiceOptID: '{tts_voice_option_id}', TextLen: {len(text_content)}")

        if not text_content:
            return JsonResponse({'status': 'error', 'message': 'Text content is required.'}, status=400)
        if len(text_content) < 10:
            return JsonResponse({'status': 'error', 'message': 'Text content too short (min 10 characters).'}, status=400)
        if len(text_content) > 5000: # Max length for preview
            return JsonResponse({'status': 'error', 'message': 'Text content too long (max 5000 chars for preview).'}, status=400)

        if not audiobook_language_selected:
            return JsonResponse({'status': 'error', 'message': 'Audiobook language selection is missing.'}, status=400)

        voices_for_selected_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(audiobook_language_selected)
        if voices_for_selected_lang is None:
            return JsonResponse({'status': 'error', 'message': f"Invalid language selected for TTS."}, status=400)
        if not voices_for_selected_lang:
            return JsonResponse({'status': 'error', 'message': f"TTS is not currently available for {audiobook_language_selected}."}, status=400)

        selected_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_option_id)
        if not selected_voice_details or selected_voice_details not in voices_for_selected_lang:
            logger.error(f"[EDGE_TTS PREVIEW] Invalid voice option '{tts_voice_option_id}' for language '{audiobook_language_selected}'.")
            return JsonResponse({'status': 'error', 'message': 'Please select a valid narrator voice for the chosen language.'}, status=400)

        actual_edge_tts_voice_id = selected_voice_details['edge_voice_id']

        temp_tts_dir_name = getattr(settings, 'TEMP_TTS_PREVIEWS_DIR_NAME', 'temp_tts_previews')
        temp_tts_full_dir_path = os.path.join(settings.MEDIA_ROOT, temp_tts_dir_name)
        os.makedirs(temp_tts_full_dir_path, exist_ok=True)

        temp_audio_filename = f"preview_{request.user.user_id}_{uuid.uuid4().hex[:8]}.mp3"
        temp_audio_filepath_local = os.path.join(temp_tts_full_dir_path, temp_audio_filename)

        logger.info(f"[EDGE_TTS PREVIEW] Generating with Edge TTS voice: {actual_edge_tts_voice_id}")
        try:
            asyncio.run(generate_audio_edge_tts_async(text_content, actual_edge_tts_voice_id, temp_audio_filepath_local))
        except Exception as e_gen:
            logger.error(f"[EDGE_TTS PREVIEW] Generation failed for user {request.user.username} with voice {actual_edge_tts_voice_id}: {e_gen}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': f'TTS generation failed: {str(e_gen)}'}, status=500)

        temp_audio_url = os.path.join(settings.MEDIA_URL, temp_tts_dir_name, temp_audio_filename)
        temp_audio_url = temp_audio_url.replace(os.sep, '/') # Ensure forward slashes for URL
        if not temp_audio_url.startswith('/'): temp_audio_url = '/' + temp_audio_url

        # Cleanup old temporary files
        try:
            for old_file_name in os.listdir(temp_tts_full_dir_path):
                old_filepath = os.path.join(temp_tts_full_dir_path, old_file_name)
                if os.path.isfile(old_filepath):
                    file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(old_filepath)) # Use datetime.datetime
                    file_mod_time_aware = timezone.make_aware(file_mod_time, timezone.get_default_timezone()) if timezone.is_naive(file_mod_time) else file_mod_time
                    if file_mod_time_aware < (timezone.now() - timedelta(hours=getattr(settings, 'TEMP_FILE_CLEANUP_HOURS', 2))):
                        os.remove(old_filepath)
                        logger.info(f"[EDGE_TTS PREVIEW] Deleted old temp file: {old_filepath}")
        except Exception as e_cleanup:
            logger.error(f"[EDGE_TTS PREVIEW] Error cleaning up old temp TTS files: {e_cleanup}", exc_info=True)

        return JsonResponse({
            'status': 'success',
            'audio_url': temp_audio_url,
            'voice_id_used': tts_voice_option_id,
            'filename': temp_audio_filename
        })

    except Exception as e:
        logger.error(f"[EDGE_TTS PREVIEW] Unexpected error for user {request.user.username}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500)


@creator_required
@require_POST
@csrf_protect
def generate_document_tts_preview_audio(request):
    try:
        document_file = request.FILES.get('document_file')
        tts_voice_option_id = request.POST.get('tts_voice_id', '').strip()
        audiobook_language_selected = request.POST.get('audiobook_language', '').strip()

        logger.info(f"[DOC_TTS PREVIEW] Request. User: {request.user.username}, Lang: {audiobook_language_selected}, VoiceOptID: '{tts_voice_option_id}', File: {document_file.name if document_file else 'No File'}")

        if not document_file:
            return JsonResponse({'status': 'error', 'message': 'Document file is required.'}, status=400)
        
        max_doc_size = 10 * 1024 * 1024  # 10MB
        allowed_doc_mime_types = [
            'application/pdf', 
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        ]
        allowed_doc_extensions = ['.pdf', '.doc', '.docx']
        doc_filename_lower = document_file.name.lower()
        doc_extension = os.path.splitext(doc_filename_lower)[1]

        if document_file.size > max_doc_size:
            return JsonResponse({'status': 'error', 'message': f"Document file too large (Max {filesizeformat(max_doc_size)})."}, status=400)
        
        file_mime_type, _ = mimetypes.guess_type(document_file.name)
        if not (file_mime_type in allowed_doc_mime_types or doc_extension in allowed_doc_extensions):
            return JsonResponse({'status': 'error', 'message': 'Invalid document type. Allowed: PDF, DOC, DOCX.'}, status=400)
        
        if doc_extension == '.doc' and docx is None:
             return JsonResponse({'status': 'error', 'message': '.doc files are not supported for preview if the server cannot process them. Please use .docx or PDF.'}, status=400)

        if not audiobook_language_selected:
            return JsonResponse({'status': 'error', 'message': 'Audiobook language selection is missing.'}, status=400)

        voices_for_selected_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(audiobook_language_selected)
        if voices_for_selected_lang is None:
            return JsonResponse({'status': 'error', 'message': f"Invalid language selected for TTS: {audiobook_language_selected}"}, status=400)
        if not voices_for_selected_lang:
            return JsonResponse({'status': 'error', 'message': f"TTS is not currently available for {audiobook_language_selected}."}, status=400)

        selected_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_option_id)
        if not selected_voice_details or selected_voice_details not in voices_for_selected_lang:
            logger.error(f"[DOC_TTS PREVIEW] Invalid voice option '{tts_voice_option_id}' for language '{audiobook_language_selected}'.")
            return JsonResponse({'status': 'error', 'message': 'Please select a valid narrator voice for the chosen language.'}, status=400)

        actual_edge_tts_voice_id = selected_voice_details['edge_voice_id']

        extracted_text = None
        doc_content_bytes = document_file.read()
        if doc_extension == '.pdf':
            extracted_text = extract_text_from_pdf(doc_content_bytes)
        elif doc_extension == '.docx' and docx:
            extracted_text = extract_text_from_docx(doc_content_bytes)
        elif doc_extension == '.doc' and docx:
            extracted_text = extract_text_from_docx(doc_content_bytes)
        
        if not extracted_text or len(extracted_text.strip()) < 10:
            msg = "Could not extract sufficient text from the document. It might be empty, image-based, or an unsupported format."
            if doc_extension == '.doc': msg += " For .doc files, ensure it's text-based or try converting to .docx or PDF."
            return JsonResponse({'status': 'error', 'message': msg}, status=400)

        text_for_preview = extracted_text.strip()[:5000] # Limit text for preview

        temp_tts_dir_name = getattr(settings, 'TEMP_DOC_TTS_PREVIEWS_DIR_NAME', 'temp_doc_tts_previews')
        temp_tts_full_dir_path = os.path.join(settings.MEDIA_ROOT, temp_tts_dir_name)
        os.makedirs(temp_tts_full_dir_path, exist_ok=True)

        temp_audio_filename = f"doc_preview_{request.user.user_id}_{uuid.uuid4().hex[:8]}.mp3"
        temp_audio_filepath_local = os.path.join(temp_tts_full_dir_path, temp_audio_filename)

        logger.info(f"[DOC_TTS PREVIEW] Generating with Edge TTS voice: {actual_edge_tts_voice_id} from document: {document_file.name}")
        try:
            asyncio.run(generate_audio_edge_tts_async(text_for_preview, actual_edge_tts_voice_id, temp_audio_filepath_local))
        except Exception as e_gen:
            logger.error(f"[DOC_TTS PREVIEW] Generation failed for user {request.user.username} from doc with voice {actual_edge_tts_voice_id}: {e_gen}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': f'TTS generation from document failed: {str(e_gen)}'}, status=500)

        temp_audio_url = os.path.join(settings.MEDIA_URL, temp_tts_dir_name, temp_audio_filename)
        temp_audio_url = temp_audio_url.replace(os.sep, '/')
        if not temp_audio_url.startswith('/'): temp_audio_url = '/' + temp_audio_url
        
        # Optional: Cleanup old files (same logic as text preview)

        return JsonResponse({
            'status': 'success',
            'audio_url': temp_audio_url,
            'voice_id_used': tts_voice_option_id,
            'filename': temp_audio_filename,
            'source_filename': document_file.name
        })

    except Exception as e:
        logger.error(f"[DOC_TTS PREVIEW] Unexpected error for user {request.user.username}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'An unexpected server error occurred: {str(e)}'}, status=500)