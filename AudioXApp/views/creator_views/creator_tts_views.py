# AudioXApp/views/creator_views/creator_tts_views.py

import json
import uuid
import os
import datetime # Python's built-in datetime
import mimetypes
import logging
import asyncio
import io
from datetime import timedelta
from typing import Optional

# For document processing
import fitz  # PyMuPDF for PDF text extraction
try:
    import docx # python-docx for .docx text extraction
except ImportError:
    docx = None

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse # HttpResponse might still be used by other functions if any
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone
from django.conf import settings
# from django.template.defaultfilters import filesizeformat # Not directly used in these functions after form validation
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from ...models import User, Creator
from ..decorators import creator_required
from ...forms import DocumentUploadForm

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
    logger.info(f"Edge TTS audio saved to {output_path} for voice {voice_id}")

@creator_required
@require_POST
@csrf_protect
def generate_tts_preview_audio(request):
    try:
        text_content = request.POST.get('text_content', '').strip()
        tts_voice_option_id = request.POST.get('tts_voice_id', '').strip() # This is the ID from ALL_EDGE_TTS_VOICES_MAP keys
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
        if not voices_for_lang: # Also implies voices_for_lang could be an empty list
            return JsonResponse({'status': 'error', 'message': f"TTS is not currently available for {audiobook_language_selected}."}, status=400)

        selected_voice_details = ALL_EDGE_TTS_VOICES_MAP.get(tts_voice_option_id)
        actual_edge_tts_voice_id_to_use = None
        final_tts_voice_id_for_response = tts_voice_option_id # This will be the ID returned to client (e.g. en-US-AriaNeural)

        # Validate if the selected tts_voice_option_id is valid for the audiobook_language_selected
        # and get the actual edge_voice_id for TTS generation
        if not selected_voice_details or selected_voice_details.get('edge_voice_id') not in [v.get('edge_voice_id') for v in voices_for_lang]:
            logger.warning(f"[TTS PREVIEW AJAX] Invalid voice '{tts_voice_option_id}' for lang '{audiobook_language_selected}'. Trying default if available.")
            if voices_for_lang: # If there are any voices for this language
                selected_voice_details = voices_for_lang[0]
                actual_edge_tts_voice_id_to_use = selected_voice_details['edge_voice_id']
                final_tts_voice_id_for_response = selected_voice_details['id'] # Use the primary ID for response
            else: # Should be caught by the earlier `if not voices_for_lang:`
                 return JsonResponse({'status': 'error', 'message': f'No voices configured for {audiobook_language_selected}.'}, status=400)
        else:
            actual_edge_tts_voice_id_to_use = selected_voice_details['edge_voice_id']

        if not actual_edge_tts_voice_id_to_use: # Fallback, should not be reached if logic is sound
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

        return JsonResponse({
            'status': 'success',
            'audio_url': temp_audio_url,
            'voice_id_used': final_tts_voice_id_for_response, 
            'filename': temp_audio_filename
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
                # narrator_gender is validated by the form's clean method if language requires it
                narrator_gender_from_form = form.cleaned_data.get('narrator_gender', '') 
                
                # Note: The form receives 'language' and 'narrator_gender'.
                # The JS sends the selected voice ID (e.g., 'ur-PK-UzmaNeural') as 'tts_voice_id' for TEXT TTS.
                # For DOCUMENT TTS, JS sends language and gender. The view then determines the 'edge_voice_id'.
                # We need to ensure the `tts_voice_id` from the POST (if any) is not confused here.
                # For Document TTS, the voice is chosen based on language and gender from the form.

                actual_edge_tts_voice_id = None # This is the voice like 'ur-PK-AsadNeural'
                final_voice_id_for_response = None # This is the ID like 'ur-PK-AsadNeural', which is also the key in ALL_EDGE_TTS_VOICES_MAP

                voices_for_selected_lang = EDGE_TTS_VOICES_BY_LANGUAGE.get(language_from_form)

                if not voices_for_selected_lang: # Also handles empty list
                    logger.error(f"[DOC_TTS] No voices configured or available for language key: '{language_from_form}'.")
                    return JsonResponse({'status': 'error', 'message': f"TTS is not available for the selected language: {language_from_form}."}, status=400)

                # Determine the voice to use based on language and gender
                if narrator_gender_from_form:
                    found_voice_details = next((v for v in voices_for_selected_lang if v['gender'].lower() == narrator_gender_from_form.lower()), None)
                    if found_voice_details:
                        actual_edge_tts_voice_id = found_voice_details['edge_voice_id']
                        final_voice_id_for_response = found_voice_details['id']
                    else: # Default to first voice of the language if gender not matched
                        actual_edge_tts_voice_id = voices_for_selected_lang[0]['edge_voice_id']
                        final_voice_id_for_response = voices_for_selected_lang[0]['id']
                        logger.warning(f"[DOC_TTS] No specific voice for gender '{narrator_gender_from_form}' in lang '{language_from_form}'. Defaulting to {actual_edge_tts_voice_id} (ID: {final_voice_id_for_response})")
                else: # No gender specified (e.g., for languages where gender isn't critical or only one voice)
                    actual_edge_tts_voice_id = voices_for_selected_lang[0]['edge_voice_id']
                    final_voice_id_for_response = voices_for_selected_lang[0]['id']
                
                if not actual_edge_tts_voice_id:
                    logger.error(f"[DOC_TTS] Critical: Could not determine TTS voice for lang '{language_from_form}', gender '{narrator_gender_from_form}'.")
                    return JsonResponse({'status': 'error', 'message': 'Could not determine a narrator voice for your selection.'}, status=400)

                user_display_name = request.user.username if request.user.is_authenticated else 'AnonymousUser'
                logger.info(f"[DOC_TTS] POST. User: {user_display_name}, Lang: {language_from_form}, Gender: {narrator_gender_from_form}, MappedEdgeVoice: {actual_edge_tts_voice_id}, MappedVoiceID: {final_voice_id_for_response}, File: {document_file.name}")

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
                    return JsonResponse({'status': 'error', 'message': 'Unsupported document type. Please use PDF or DOCX.'}, status=400)
                
                if not extracted_text or len(extracted_text.strip()) < 10:
                    msg = "Could not extract sufficient text from the document. It might be empty, image-based, or an unsupported format."
                    if doc_extension == '.doc' and not docx: 
                        msg += " For .doc files, ensure it's text-based or try converting to .docx or PDF. The server may also need a library to process .doc files."
                    elif doc_extension == '.doc' and docx:
                         msg += " For .doc files, ensure it's text-based or try converting to .docx or PDF."
                    return JsonResponse({'status': 'error', 'message': msg}, status=400)

                text_for_preview = extracted_text.strip()[:5000]
                temp_tts_dir_name = getattr(settings, 'TEMP_DOC_TTS_PREVIEWS_DIR_NAME', 'temp_doc_tts_previews')
                temp_tts_full_dir_path = os.path.join(settings.MEDIA_ROOT, temp_tts_dir_name)
                os.makedirs(temp_tts_full_dir_path, exist_ok=True)
                
                user_id_part = request.user.pk if request.user.is_authenticated else 'public'
                temp_audio_filename = f"doc_preview_{user_id_part}_{uuid.uuid4().hex[:8]}.mp3"
                temp_audio_filepath_local = os.path.join(temp_tts_full_dir_path, temp_audio_filename)

                asyncio.run(generate_audio_edge_tts_async(text_for_preview, actual_edge_tts_voice_id, temp_audio_filepath_local))
                
                # === Start of Modified Section for Returning JSON ===
                if os.path.exists(temp_audio_filepath_local):
                    temp_audio_url = os.path.join(settings.MEDIA_URL, temp_tts_dir_name, temp_audio_filename)
                    temp_audio_url = temp_audio_url.replace(os.sep, '/') 
                    if not temp_audio_url.startswith('/'): 
                        temp_audio_url = '/' + temp_audio_url
                    
                    logger.info(f"[DOC_TTS] Preview audio URL: {temp_audio_url}, Voice ID for response: {final_voice_id_for_response}")

                    # Cleanup old temporary files
                    try:
                        for old_file_name in os.listdir(temp_tts_full_dir_path):
                            old_filepath = os.path.join(temp_tts_full_dir_path, old_file_name)
                            if os.path.isfile(old_filepath) and old_filepath != temp_audio_filepath_local:
                                file_mod_time_naive = datetime.datetime.fromtimestamp(os.path.getmtime(old_filepath))
                                file_mod_time_aware = timezone.make_aware(file_mod_time_naive, timezone.get_default_timezone()) if timezone.is_naive(file_mod_time_naive) else file_mod_time_naive
                                
                                if file_mod_time_aware < (timezone.now() - timedelta(hours=getattr(settings, 'TEMP_FILE_CLEANUP_HOURS', 2))):
                                    os.remove(old_filepath)
                                    logger.info(f"[DOC_TTS PREVIEW CLEANUP] Deleted old temp file: {old_filepath}")
                    except Exception as e_cleanup:
                        logger.error(f"[DOC_TTS PREVIEW CLEANUP] Error cleaning old temp files: {e_cleanup}", exc_info=True)

                    return JsonResponse({
                        'status': 'success',
                        'audio_url': temp_audio_url,
                        'voice_id_used': final_voice_id_for_response, # The ID like 'ur-PK-UzmaNeural'
                        'filename': temp_audio_filename,
                        'source_filename': document_file.name
                    })
                else:
                    logger.error(f"[DOC_TTS] Generated audio file not found at {temp_audio_filepath_local} after generation attempt.")
                    return JsonResponse({'status': 'error', 'message': 'Generated audio file not found on server after attempt.'}, status=500)
                # === End of Modified Section ===

            except Exception as e_post:
                logger.error(f"[DOC_TTS] POST Error for User: {user_display_name if 'user_display_name' in locals() else 'UnknownUser'}. Error: {e_post}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': f'Server error during audio generation: {str(e_post)}'}, status=500)
        else: # Form is not valid
            logger.warning(f"[DOC_TTS] POST Form Invalid. User: {request.user.username if request.user.is_authenticated else 'AnonymousUser'}. Errors: {form.errors.as_json()}")
            return JsonResponse({'status': 'error', 'message': 'Invalid data submitted. Please correct the errors below.', 'errors': form.errors.get_json_data()}, status=400)
    else: # GET request
        form = DocumentUploadForm()
        context = {'form': form}
        return render(request, 'generate_audiobook/generate_audiobook.html', context) # Ensure this template exists or change it