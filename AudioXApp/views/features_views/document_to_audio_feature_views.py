# AudioXApp/views/features_views/document_to_audio_feature_views.py

import fitz
import os
from dotenv import load_dotenv
import tempfile
import io
from PIL import Image
import pytesseract
import asyncio
import edge_tts
from typing import Optional
import traceback

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse

from ...forms import DocumentUploadForm

load_dotenv()

# --- TTS and Text Extraction Helpers ---

async def generate_edge_tts_audio_async(text: str, voice_name: str, output_path: str) -> bool:
    """
    Asynchronously generates audio using edge-tts and saves it to output_path.
    Returns True on success, False on failure.
    """
    try:
        communicate = edge_tts.Communicate(text, voice_name)
        await communicate.save(output_path)
        return True
    except Exception as e:
        traceback.print_exc()
        return False

def extract_text_from_pdf(pdf_content: bytes) -> Optional[str]:
    """Extracts text from PDF content."""
    text = ""
    try:
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            page_text = page.get_text("text")
            text += page_text + "\n"
        doc.close()
        stripped_text = text.strip()
        return stripped_text if stripped_text else None
    except Exception:
        return None

def extract_text_from_image(image_content: bytes, language_code: str = 'eng') -> Optional[str]:
    """Extracts text from image content using OCR."""
    try:
        image = Image.open(io.BytesIO(image_content))
        image = image.convert('L')
        threshold = 150
        image = image.point(lambda x: 0 if x < threshold else 255, '1')
        tess_lang = language_code
        custom_config = f'--oem 3 --psm 3 -l {tess_lang}'
        text = pytesseract.image_to_string(image, config=custom_config)
        stripped_text = text.strip()
        if len(stripped_text) < 5:
            return None
        return stripped_text
    except pytesseract.TesseractNotFoundError:
        raise
    except Exception:
        return None

# --- Core Text-to-Speech Conversion ---

def convert_text_to_audio(text: str, language: str, narrator_gender: Optional[str] = None) -> Optional[bytes]:
    """
    Converts text to audio using the appropriate TTS engine based on language and gender.
    """
    audio_data = None
    if not text or not text.strip():
        return None

    edge_voice_name = None
    if language == 'en':
        edge_voice_name = 'en-US-AndrewNeural' if narrator_gender == 'male' else 'en-US-AriaNeural'
    elif language == 'ur':
        edge_voice_name = 'ur-PK-AsadNeural' if narrator_gender == 'male' else 'ur-PK-UzmaNeural'
    else:
        return None

    if edge_voice_name:
        temp_audio_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmpfile:
                temp_audio_path = tmpfile.name
            
            generation_successful = asyncio.run(generate_edge_tts_audio_async(text, edge_voice_name, temp_audio_path))

            if generation_successful and os.path.exists(temp_audio_path) and os.path.getsize(temp_audio_path) > 0:
                with open(temp_audio_path, 'rb') as f:
                    audio_data = f.read()
            else:
                audio_data = None
        except Exception:
            traceback.print_exc()
            audio_data = None
        finally:
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                except Exception:
                    pass
    return audio_data

# --- Main Django View ---

def generate_audio_from_document(request):
    """Handles document upload, text extraction, and audio generation."""
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data['document_file']
            selected_language_for_tts = form.cleaned_data['language']
            narrator_gender = form.cleaned_data.get('narrator_gender')

            try:
                file_content = uploaded_file.read()
                file_type = uploaded_file.content_type
                extracted_text = None

                if file_type == 'application/pdf':
                    extracted_text = extract_text_from_pdf(file_content)
                elif file_type.startswith('image/'):
                    ocr_lang_code = 'urd' if selected_language_for_tts == 'ur' else 'eng'
                    extracted_text = extract_text_from_image(file_content, language_code=ocr_lang_code)

                if not extracted_text:
                    error_msg = "Could not extract text from the document. It might be empty or a scanned image."
                    if selected_language_for_tts == 'ur' and file_type.startswith('image/'):
                        error_msg += " For Urdu images, ensure Tesseract OCR is correctly configured."
                    return HttpResponse(error_msg, status=400)

                audio_data = convert_text_to_audio(extracted_text, selected_language_for_tts, narrator_gender)
                if audio_data:
                    return HttpResponse(audio_data, content_type='audio/mpeg')
                else:
                    error_message_tts = f"Could not generate audio for the selected language ('{selected_language_for_tts}'). The TTS service may be unavailable."
                    return HttpResponse(error_message_tts, status=500)

            except pytesseract.TesseractNotFoundError:
                error_msg = "The Tesseract OCR engine is not installed or configured correctly on the server."
                return HttpResponse(error_msg + " Please contact the site administrator.", status=500)
            except Exception as e:
                traceback.print_exc()
                return HttpResponse(f"An internal server error occurred: {str(e)}", status=500)
        else:
            return JsonResponse({'errors': form.errors}, status=400)
    else:
        form = DocumentUploadForm()
    
    return render(request, 'features/document_to_audio/document_to_audio_feature.html', {'form': form})
