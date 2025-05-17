# AudioX/AudioXApp/views/audio_views.py

import fitz
import requests
import os
from dotenv import load_dotenv
import pyttsx3
import tempfile
import io

from django.shortcuts import render
from django.http import HttpResponse

from ..forms import PdfUploadForm

# Load environment variables
load_dotenv()

# --- PDF Processing and Audio Conversion View ---

def upload_pdf(request):
    """
    View to handle PDF upload, text extraction, and audio conversion.
    """
    if request.method == 'POST':
        form = PdfUploadForm(request.POST, request.FILES)
        if form.is_valid():
            pdf_file = form.cleaned_data['pdf_file']
            language = form.cleaned_data['language']

            if pdf_file.size > 10 * 1024 * 1024:
                 return HttpResponse("File size exceeds the limit.", status=400)

            try:
                pdf_content = pdf_file.read()
                text = extract_text_from_pdf(pdf_content)

                if not text:
                     return HttpResponse("Could not extract text from the PDF. It might be a scanned image or have a complex structure.", status=400)

                audio_data = convert_text_to_audio(text, language)

                if audio_data:
                    content_type = 'audio/mpeg'
                    response = HttpResponse(audio_data, content_type=content_type)
                    response['Content-Disposition'] = 'attachment; filename="audio_output.mp3"'
                    return response
                else:
                    return HttpResponse("Could not generate audio from the text. Please try again later.", status=500)

            except Exception:
                return HttpResponse(f"An internal error occurred.", status=500)
    else:
        form = PdfUploadForm()

    return render(request, 'upload_pdf.html', {'form': form})

# --- Helper Functions ---

def extract_text_from_pdf(pdf_content):
    """
    Extracts text from PDF content using PyMuPDF.
    Returns extracted text or None if extraction fails or yields little text.
    """
    text = ""
    try:
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            page_text = page.get_text("text")
            text += page_text + "\n"

        doc.close()

        if len(text.strip()) < 50:
             return None

    except Exception:
        return None

    return text.strip()

def convert_text_to_audio(text, language):
    """
    Converts text to audio using a hybrid approach:
    - English: Uses pyttsx3.
    - Urdu: Uses an external TTS API.
    Returns audio data as bytes or None if conversion fails.
    """
    audio_data = None

    if language == 'en':
        try:
            engine = pyttsx3.init()

            # Workaround using a temporary file to get audio data as bytes
            fd, temp_audio_path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)

            engine.save_to_file(text, temp_audio_path)
            engine.runAndWait()

            with open(temp_audio_path, 'rb') as f:
                audio_data = f.read()

            os.remove(temp_audio_path)
            # End Workaround

        except Exception:
            audio_data = None

    elif language == 'ur':
        tts_api_url = os.environ.get("TTS_API_URL")
        api_key = os.environ.get("TTS_API_KEY")

        if not tts_api_url or not api_key:
            return None

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        voice_id = os.environ.get("TTS_URDU_VOICE_ID")

        if not voice_id:
             return None

        payload = {
            "text": text,
            "language_code": language,
            "voice_id": voice_id,
            "audio_config": {
                 "audio_encoding": "MP3"
            }
        }

        try:
            response = requests.post(tts_api_url, json=payload, headers=headers)
            response.raise_for_status()

            audio_data = response.content

        except requests.exceptions.RequestException:
            audio_data = None
        except Exception:
            audio_data = None

    else:
        audio_data = None

    return audio_data
