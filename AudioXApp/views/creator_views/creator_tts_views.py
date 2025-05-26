# AudioXApp/views/creator_views/creator_tts_views.py

import json
import uuid
import os
import datetime # Python's built-in datetime
import mimetypes
import logging
import asyncio # Ensure asyncio is imported
import io

# For document processing
import fitz  # PyMuPDF for PDF text extraction
try:
    import docx # python-docx for .docx text extraction
except ImportError:
    docx = None

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone # Django's timezone
from django.conf import settings
from django.template.defaultfilters import filesizeformat
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from ...models import User, Creator # Relative imports
from ..decorators import creator_required # Relative import
from ...forms import DocumentUploadForm # Import the form

# --- Edge TTS Setup ---
import edge_tts

logger = logging.getLogger(__name__)

# --- Edge TTS Voice Mapping and Language/Genre Constants ---
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

def extract_text_from_docx(file_content_bytes: bytes) -> str | None:
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

def extract_text_from_pdf(pdf_content_bytes: bytes) -> str | None:
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
    await communicate.save(output_path) # This await is fine as it's inside an async function
    logger.info(f"Edge TTS audio saved to {output_path} for voice {voice_id}")

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
        final_tts_voice_option_id = tts_voice_option_id

        if not selected_voice_details or selected_voice_details not in voices_for_lang:
            logger.warning(f"[TTS PREVIEW AJAX] Invalid voice '{tts_voice_option_id}' for lang '{audiobook_language_selected}'. Trying default.")
            if voices_for_lang: # Ensure there are voices for the language
                selected_voice_details = voices_for_lang[0] # Default to first voice for the language
                actual_edge_tts_voice_id_to_use = selected_voice_details['edge_voice_id']
                final_tts_voice_option_id = selected_voice_details['id'] # Use the ID of the voice actually being used
            else: # Should not happen if previous check for voices_for_lang passed
                 return JsonResponse({'status': 'error', 'message': f'No voices configured for {audiobook_language_selected}.'}, status=400)
        else:
            actual_edge_tts_voice_id_to_use = selected_voice_details['edge_voice_id']

        if not actual_edge_tts_voice_id_to_use:
             return JsonResponse({'status': 'error', 'message': 'Could not determine a valid TTS voice.'}, status=400)

        temp_dir_name = getattr(settings, 'TEMP_TTS_PREVIEWS_DIR_NAME', 'temp_tts_previews')
        temp_full_dir = os.path.join(settings.MEDIA_ROOT, temp_dir_name)
        os.makedirs(temp_full_dir, exist_ok=True)

        temp_filename = f"preview_{request.user.user_id}_{uuid.uuid4().hex[:8]}.mp3"
        temp_filepath = os.path.join(temp_full_dir, temp_filename)
        
        # CORRECTED: Use asyncio.run() to call the async function
        asyncio.run(generate_audio_edge_tts_async(text_content, actual_edge_tts_voice_id_to_use, temp_filepath))

        audio_url = os.path.join(settings.MEDIA_URL, temp_dir_name, temp_filename).replace(os.sep, '/')
        if not audio_url.startswith('/'): audio_url = '/' + audio_url
        
        # ... (Optional cleanup logic) ...

        return JsonResponse({
            'status': 'success',
            'audio_url': audio_url,
            'voice_id_used': final_tts_voice_option_id, 
            'filename': temp_filename
        })
    except Exception as e:
        logger.error(f"[TTS PREVIEW AJAX] Error for user {request.user.username}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500)

@csrf_protect
def generate_document_tts_preview_audio(request):
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                document_file = form.cleaned_data['document_file']
                language_from_form = form.cleaned_data['language']
                narrator_gender_from_form = form.cleaned_data.get('narrator_gender', '')

                actual_edge_tts_voice_id = None
                voices_for_selected_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(language_from_form)

                if not voices_for_selected_lang:
                    logger.error(f"[DOC_TTS] No voices configured for language key: '{language_from_form}'.")
                    return JsonResponse({'status': 'error', 'message': f"TTS is not available for the selected language: {language_from_form}."}, status=400)

                if narrator_gender_from_form:
                    found_voice = next((v for v in voices_for_selected_lang if v['gender'].lower() == narrator_gender_from_form.lower()), None)
                    if found_voice:
                        actual_edge_tts_voice_id = found_voice['edge_voice_id']
                    else:
                        actual_edge_tts_voice_id = voices_for_selected_lang[0]['edge_voice_id']
                        logger.warning(f"[DOC_TTS] No specific voice for gender '{narrator_gender_from_form}' in lang '{language_from_form}'. Defaulting to {actual_edge_tts_voice_id}")
                else:
                    if voices_for_selected_lang:
                        actual_edge_tts_voice_id = voices_for_selected_lang[0]['edge_voice_id']
                    else:
                         logger.error(f"[DOC_TTS] Language '{language_from_form}' selected but no voices are listed for it.")
                         return JsonResponse({'status': 'error', 'message': f"No TTS voices available for {language_from_form}."}, status=400)

                if not actual_edge_tts_voice_id:
                    logger.error(f"[DOC_TTS] Critical: Could not determine TTS voice for lang '{language_from_form}', gender '{narrator_gender_from_form}'.")
                    return JsonResponse({'status': 'error', 'message': 'Could not determine a narrator voice for your selection.'}, status=400)

                user_display_name = request.user.username if request.user.is_authenticated else 'AnonymousUser'
                logger.info(f"[DOC_TTS] POST. User: {user_display_name}, Lang: {language_from_form}, Gender: {narrator_gender_from_form}, MappedVoice: {actual_edge_tts_voice_id}, File: {document_file.name}")

                doc_extension = os.path.splitext(document_file.name.lower())[1]
                extracted_text = None
                doc_content_bytes = document_file.read()

                if doc_extension == '.pdf':
                    extracted_text = extract_text_from_pdf(doc_content_bytes)
                elif doc_extension == '.docx' and docx:
                    extracted_text = extract_text_from_docx(doc_content_bytes)
                elif doc_extension == '.doc' and docx:
                    extracted_text = extract_text_from_docx(doc_content_bytes)
                else:
                    return JsonResponse({'status': 'error', 'message': 'Unsupported document type after form validation.'}, status=400)

                if not extracted_text or len(extracted_text.strip()) < 10:
                    msg = "Could not extract sufficient text. Document might be empty, image-based, or content not readable."
                    return JsonResponse({'status': 'error', 'message': msg}, status=400)

                text_for_preview = extracted_text.strip()[:5000]
                temp_tts_dir_name = getattr(settings, 'TEMP_DOC_TTS_PREVIEWS_DIR_NAME', 'temp_doc_tts_previews')
                temp_tts_full_dir_path = os.path.join(settings.MEDIA_ROOT, temp_tts_dir_name)
                os.makedirs(temp_tts_full_dir_path, exist_ok=True)
                user_id_part = request.user.pk if request.user.is_authenticated else 'public'
                temp_audio_filename = f"doc_preview_{user_id_part}_{uuid.uuid4().hex[:8]}.mp3"
                temp_audio_filepath_local = os.path.join(temp_tts_full_dir_path, temp_audio_filename)

                # CORRECTED: Use asyncio.run() to call the async function
                asyncio.run(generate_audio_edge_tts_async(text_for_preview, actual_edge_tts_voice_id, temp_audio_filepath_local))
                
                if os.path.exists(temp_audio_filepath_local):
                    with open(temp_audio_filepath_local, 'rb') as f_audio:
                        audio_content_blob = f_audio.read()
                    try:
                        os.remove(temp_audio_filepath_local)
                    except OSError as e_remove:
                        logger.error(f"[DOC_TTS] Could not delete temp audio file {temp_audio_filepath_local}: {e_remove}")
                    response = HttpResponse(audio_content_blob, content_type='audio/mpeg')
                    response['Content-Disposition'] = f'attachment; filename="{temp_audio_filename}"'
                    return response
                else:
                    logger.error(f"[DOC_TTS] Generated audio file not found at {temp_audio_filepath_local}")
                    return JsonResponse({'status': 'error', 'message': 'Generated audio file not found on server.'}, status=500)

            except Exception as e_post:
                logger.error(f"[DOC_TTS] POST Error for User: {user_display_name}. Error: {e_post}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': f'Server error during audio generation: {str(e_post)}'}, status=500)
        else:
            logger.warning(f"[DOC_TTS] POST Form Invalid. User: {request.user.username if request.user.is_authenticated else 'AnonymousUser'}. Errors: {form.errors.as_json()}")
            return JsonResponse({'status': 'error', 'message': 'Invalid data submitted. Please correct the errors below.', 'errors': form.errors.get_json_data()}, status=400)
    else: # GET request
        form = DocumentUploadForm()
        context = {'form': form}
        return render(request, 'generate_audiobook/generate_audiobook.html', context)