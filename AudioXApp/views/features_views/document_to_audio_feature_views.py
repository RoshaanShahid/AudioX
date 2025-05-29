# AudioXApp/views/audio_views.py

import fitz  # PyMuPDF for PDF text extraction
import os
from dotenv import load_dotenv
import tempfile
import io
from PIL import Image
import pytesseract      # For OCR
import asyncio
import edge_tts # For Edge TTS
from typing import Optional # Changed from Union, or just use Optional

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse

from ...forms import DocumentUploadForm

load_dotenv()

# --- Edge TTS Helper ---
async def generate_edge_tts_audio_async(text: str, voice_name: str, output_path: str) -> bool:
    """
    Asynchronously generates audio using edge-tts and saves it to output_path.
    Returns True on success, False on failure.
    """
    try:
        communicate = edge_tts.Communicate(text, voice_name)
        await communicate.save(output_path)
        print(f"DEBUG EDGE-TTS: Successfully saved audio to {output_path} using voice {voice_name}")
        return True
    except Exception as e:
        print(f"DEBUG EDGE-TTS: Error during generation with voice {voice_name}: {e}")
        import traceback
        traceback.print_exc()
        return False

# --- Text Extraction Helper Functions ---

def extract_text_from_pdf(pdf_content: bytes) -> Optional[str]:
    """Extracts text from PDF content."""
    text = ""
    print("DEBUG PDF: Attempting to extract text from PDF...")
    try:
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            page_text = page.get_text("text")
            text += page_text + "\n"
        doc.close()
        stripped_text = text.strip()
        print(f"DEBUG PDF: Total extracted PDF text length (stripped): {len(stripped_text)}")
        if stripped_text:
            print(f"DEBUG PDF: Extracted PDF text snippet (first 200 chars): '{stripped_text[:200]}'")
        if len(stripped_text) < 5:
            print("DEBUG PDF: Extracted PDF text very short or empty.")
        return stripped_text if stripped_text else None
    except Exception as e:
        print(f"DEBUG PDF: Error extracting text from PDF: {e}")
        return None

def extract_text_from_image(image_content: bytes, language_code: str = 'eng') -> Optional[str]:
    """Extracts text from image content using OCR."""
    print(f"DEBUG OCR: Attempting to extract text from image with language_code: {language_code}")
    try:
        image = Image.open(io.BytesIO(image_content))
        image = image.convert('L')
        threshold = 150
        image = image.point(lambda x: 0 if x < threshold else 255, '1')

        tess_lang = language_code

        custom_config = f'--oem 3 --psm 3 -l {tess_lang}'
        print(f"DEBUG OCR: Tesseract config: {custom_config}")

        text = pytesseract.image_to_string(image, config=custom_config)
        stripped_text = text.strip()

        print(f"DEBUG OCR: Total extracted OCR text length (stripped): {len(stripped_text)}")
        if stripped_text:
            print(f"DEBUG OCR: Extracted OCR text snippet (first 200 chars): '{stripped_text[:200]}'")

        if len(stripped_text) < 5:
            print(f"DEBUG OCR: Extracted OCR text for lang '{tess_lang}' is very short or empty.")
            return None
        return stripped_text
    except pytesseract.TesseractNotFoundError:
        print(f"DEBUG OCR: TesseractNotFoundError for language '{tess_lang}'. Ensure Tesseract is installed and '{tess_lang}.traineddata' is available in tessdata directory.")
        raise
    except Exception as e:
        print(f"DEBUG OCR: Error extracting text from image (lang: {language_code}): {e}")
        return None

# --- Text-to-Speech Conversion Function ---

def convert_text_to_audio(text: str, language: str, narrator_gender: Optional[str] = None) -> Optional[bytes]:
    """
    Converts text to audio using appropriate TTS engine based on language and gender.
    The narrator_gender parameter expects 'male' or 'female' (from the form).
    This function maps these generic values to specific voice names/configurations
    for the selected TTS engine and language.
    """
    audio_data = None
    print(f"DEBUG TTS: Request for lang: {language}, gender: {narrator_gender}")

    if not text or not text.strip():
        print("DEBUG TTS: No text provided to convert (text is empty or whitespace).")
        return None

    edge_voice_name = None

    if language == 'en':
        print(f"DEBUG TTS: Using edge-tts for English, gender: {narrator_gender}")
        if narrator_gender == 'female':
            edge_voice_name = 'en-US-AriaNeural'
        elif narrator_gender == 'male':
            edge_voice_name = 'en-US-AndrewNeural'
        else:
            edge_voice_name = 'en-US-AriaNeural'
            print(f"DEBUG TTS: Narrator gender for English not specified or invalid ('{narrator_gender}'), defaulting to {edge_voice_name}.")

    elif language == 'ur':
        print(f"DEBUG TTS: Using edge-tts for Urdu, gender: {narrator_gender}")
        if narrator_gender == 'female':
            edge_voice_name = 'ur-PK-UzmaNeural'
        elif narrator_gender == 'male':
            edge_voice_name = 'ur-PK-AsadNeural'
        else:
            edge_voice_name = 'ur-PK-UzmaNeural'
            print(f"DEBUG TTS: Narrator gender for Urdu not specified or invalid ('{narrator_gender}'), defaulting to {edge_voice_name}.")
    else:
        print(f"DEBUG TTS: Unsupported language for TTS: {language}")
        return None

    if edge_voice_name:
        temp_audio_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmpfile:
                temp_audio_path = tmpfile.name

            print(f"DEBUG EDGE-TTS: Attempting to generate '{language}' audio with voice '{edge_voice_name}' to '{temp_audio_path}'")
            generation_successful = asyncio.run(generate_edge_tts_audio_async(text, edge_voice_name, temp_audio_path))

            if generation_successful and os.path.exists(temp_audio_path) and os.path.getsize(temp_audio_path) > 0:
                with open(temp_audio_path, 'rb') as f:
                    audio_data = f.read()
                print(f"DEBUG TTS: '{language}' audio generated by edge-tts ({edge_voice_name}, size: {os.path.getsize(temp_audio_path)} bytes).")
            else:
                print(f"DEBUG TTS: edge-tts failed to create/write temp audio file or generation failed for '{language}': {temp_audio_path}")
                audio_data = None

        except Exception as e:
            print(f"DEBUG TTS: General error during edge-tts processing for '{language}': {e}")
            import traceback
            traceback.print_exc()
            audio_data = None
        finally:
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                    print(f"DEBUG TTS: Temp file {temp_audio_path} removed.")
                except Exception as e_rem:
                    print(f"DEBUG TTS: Error removing temp file {temp_audio_path}: {e_rem}")
    else:
        print(f"DEBUG TTS: Could not determine a voice name for edge-tts '{language}'.")
        audio_data = None

    if audio_data:
        print(f"DEBUG TTS: Audio data successfully prepared for language {language}.")
    else:
        print(f"DEBUG TTS: Failed to generate audio data for language {language}.")
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

            print(f"DEBUG VIEW: POST. Lang: {selected_language_for_tts}, Gender: {narrator_gender}, File: {uploaded_file.name}")

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
                    error_msg = "Could not extract text from the document. It might be empty, a scanned image (if PDF), or unsupported format/content."
                    if selected_language_for_tts == 'ur' and file_type.startswith('image/'):
                        error_msg += " For Urdu images, please ensure Tesseract OCR has 'urd.traineddata' installed and the image is clear."
                    print(f"DEBUG VIEW: Text extraction failed. Error: {error_msg}")
                    return HttpResponse(error_msg, status=400)

                audio_data = convert_text_to_audio(extracted_text, selected_language_for_tts, narrator_gender)

                if audio_data:
                    print("DEBUG VIEW: Audio data generated. Returning audio response.")
                    return HttpResponse(audio_data, content_type='audio/mpeg')
                else:
                    print("DEBUG VIEW: convert_text_to_audio returned None (TTS failed).")
                    error_message_tts = f"Could not generate audio. The TTS service for '{selected_language_for_tts}'"
                    if selected_language_for_tts in ['en', 'ur'] and narrator_gender:
                            error_message_tts += f" (Gender: {narrator_gender})"
                    error_message_tts += " might be unavailable, the text was unsuitable (e.g., too short after OCR), or the specified voice was not found."
                    return HttpResponse(error_message_tts, status=500)

            except pytesseract.TesseractNotFoundError:
                error_msg = "Tesseract OCR engine not found or not configured correctly on the server. Please ensure Tesseract is installed and in your system's PATH, and that language data (e.g., 'urd.traineddata' for Urdu) is available."
                print(f"DEBUG VIEW: ERROR - {error_msg}")
                return HttpResponse(error_msg + " Please contact the site administrator.", status=500)
            except Exception as e:
                print(f"DEBUG VIEW: An unexpected internal error occurred: {str(e)}")
                import traceback
                traceback.print_exc()
                return HttpResponse(f"An internal server error occurred. Please try again later. Details: {str(e)}", status=500)
        else:
            print(f"DEBUG VIEW: Form validation errors: {form.errors.as_json()}")
            return JsonResponse({'errors': form.errors}, status=400)

    else:
        form = DocumentUploadForm()
        print("DEBUG VIEW: GET request for generate_audiobook page.")

    return render(request, 'features/document_to_audio/document_to_audio_feature.html', {'form': form})