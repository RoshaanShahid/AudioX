# AudioX/AudioXApp/views/audio_views.py

from django.shortcuts import render
from django.http import HttpResponse
from ..forms import PdfUploadForm # Note the relative import
import fitz # For PDF text extraction
import requests # For calling the Urdu TTS API
import os # For accessing environment variables
from dotenv import load_dotenv # To load environment variables from .env
import pyttsx3 # For English TTS
import io # For handling audio data in memory (less direct with pyttsx3)
import tempfile # For temporary file workaround with pyttsx3
import logging # For logging errors

# Load environment variables from the .env file
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

def upload_pdf(request):
    """
    View to handle PDF upload, text extraction, and audio conversion.
    """
    if request.method == 'POST':
        form = PdfUploadForm(request.POST, request.FILES)
        if form.is_valid():
            pdf_file = form.cleaned_data['pdf_file']
            language = form.cleaned_data['language'] # 'en' or 'ur'

            # Basic file size check (optional but recommended)
            if pdf_file.size > 10 * 1024 * 1024: # Limit to 10MB as an example
                 return HttpResponse("File size exceeds the limit.", status=400)

            try:
                # Read the file content
                pdf_content = pdf_file.read()

                # 1. Extract text from PDF
                text = extract_text_from_pdf(pdf_content)

                if not text:
                     logger.warning("Could not extract text from the uploaded PDF.")
                     return HttpResponse("Could not extract text from the PDF. It might be a scanned image or have a complex structure.", status=400)

                # 2. Convert text to audio using the hybrid approach
                audio_data = convert_text_to_audio(text, language)

                if audio_data:
                    # 3. Serve the audio to the user
                    # Determine content type based on expected audio format (assuming mp3 from API and workaround)
                    content_type = 'audio/mpeg'
                    response = HttpResponse(audio_data, content_type=content_type)
                    response['Content-Disposition'] = 'attachment; filename="audio_output.mp3"' # Suggest a filename
                    return response
                else:
                    logger.error(f"Failed to generate audio for language: {language}")
                    return HttpResponse("Could not generate audio from the text. Please try again later.", status=500)

            except Exception as e:
                # Log the error for debugging
                logger.exception("An error occurred during PDF processing:")
                # In a production environment, avoid exposing raw error details to the user
                return HttpResponse(f"An internal error occurred.", status=500)
    else:
        form = PdfUploadForm()

    # Render the upload form template
    return render(request, 'upload_pdf.html', {'form': form})

def extract_text_from_pdf(pdf_content):
    """
    Extracts text from PDF content using PyMuPDF.
    Returns extracted text or None if extraction fails or yields little text.
    """
    text = ""
    try:
        # Open the PDF from bytes
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            # Use 'text' output for basic extraction
            page_text = page.get_text("text")
            text += page_text + "\n" # Add newline for page separation

        doc.close()

        # Basic check: if no significant text is extracted, it might be a scanned PDF
        if len(text.strip()) < 50: # Threshold can be adjusted
             logger.warning(f"Extracted very little text ({len(text.strip())} characters). Might be a scanned PDF.")
             return None # Indicate potential scanned PDF or extraction issue

    except Exception as e:
        logger.exception("Error extracting text from PDF:")
        return None # Indicate extraction failure

    return text.strip() # Return stripped text

def convert_text_to_audio(text, language):
    """
    Converts text to audio using a hybrid approach:
    - English: Uses a local Python TTS engine (pyttsx3).
    - Urdu: Uses an external TTS API.
    Returns audio data as bytes or None if conversion fails.
    """
    audio_data = None

    if language == 'en':
        try:
            engine = pyttsx3.init()
            # You can configure engine properties here if needed:
            # rate = engine.getProperty('rate')
            # engine.setProperty('rate', rate - 50) # Example: Slow down the speech

            # Select an English voice (optional, will use default if not set)
            # voices = engine.getProperty('voices')
            # for voice in voices:
            #     if 'english' in voice.name.lower():
            #         engine.setProperty('voice', voice.id)
            #         break

            # *** Workaround using a temporary file to get audio data as bytes ***
            # pyttsx3 doesn't easily provide audio data directly in memory in a non-blocking way
            fd, temp_audio_path = tempfile.mkstemp(suffix=".mp3") # Use .mp3 as suffix
            os.close(fd) # Close the file descriptor immediately

            engine.save_to_file(text, temp_audio_path)
            engine.runAndWait()

            with open(temp_audio_path, 'rb') as f:
                audio_data = f.read()

            os.remove(temp_audio_path) # Clean up the temporary file
            # *** End Workaround ***

            logger.info("Successfully generated English audio with pyttsx3.")

        except Exception as e:
            logger.exception("Error generating English audio with pyttsx3:")
            audio_data = None # Ensure audio_data is None on error

    elif language == 'ur':
        # Logic for calling the Urdu TTS API
        tts_api_url = os.environ.get("TTS_API_URL")
        api_key = os.environ.get("TTS_API_KEY")

        if not tts_api_url or not api_key:
            logger.error("TTS_API_URL or TTS_API_KEY not configured in environment variables.")
            return None

        headers = {
            "Authorization": f"Bearer {api_key}", # Or whatever authentication the API uses
            "Content-Type": "application/json" # Or whatever content type the API expects
        }

        # Get the Urdu voice ID from environment variables
        voice_id = os.environ.get("TTS_URDU_VOICE_ID")

        if not voice_id:
             logger.error(f"TTS_URDU_VOICE_ID not configured in environment variables.")
             return None

        payload = {
            "text": text,
            "language_code": language, # Should be 'ur'
            "voice_id": voice_id,
            "audio_config": {
                 "audio_encoding": "MP3" # Request MP3 format
                 # Add other audio configuration like speaking rate, pitch if supported by the API
            }
        }

        try:
            response = requests.post(tts_api_url, json=payload, headers=headers)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

            # Assuming the API returns audio data directly in the response body
            audio_data = response.content
            logger.info("Successfully generated Urdu audio from API.")

        except requests.exceptions.RequestException as e:
            logger.exception("Error calling Urdu TTS API:")
            audio_data = None # Ensure audio_data is None on error
        except Exception as e:
            logger.exception("An unexpected error occurred during Urdu TTS conversion:")
            audio_data = None # Ensure audio_data is None on error

    else:
        logger.warning(f"Unsupported language requested for TTS: {language}")
        audio_data = None # Ensure audio_data is None for unsupported languages

    return audio_data