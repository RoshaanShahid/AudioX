# AudioXApp/views/summary_views.py

from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpRequest
from django.conf import settings
from AudioXApp.models import Audiobook
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

# --- AI Summary View ---

def get_ai_summary(request: HttpRequest, audiobook_id: int):
    gemini_api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if not gemini_api_key:
        logger.error("GEMINI_API_KEY not configured in settings for AI summary.")
        return JsonResponse({'status': 'error', 'message': 'AI summarization service API key not configured.'}, status=500)

    try:
        audiobook = get_object_or_404(Audiobook, pk=audiobook_id)
    except Audiobook.DoesNotExist:
        logger.warning(f"Audiobook with ID {audiobook_id} not found for summary generation.")
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching audiobook with ID {audiobook_id}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An error occurred while retrieving audiobook details.'}, status=500)

    book_title = audiobook.title
    text_to_summarize = audiobook.description or audiobook.title
    
    if not text_to_summarize or len(text_to_summarize.split()) < 20:
        logger.warning(f"Text for summary for audiobook '{book_title}' (ID: {audiobook_id}) is too short. Using combined title, author, and description.")
        text_to_summarize = f"Audiobook Title: {audiobook.title}. Author: {audiobook.author or 'Unknown Author'}. Description: {audiobook.description or 'No description available.'}"
        if len(text_to_summarize.split()) < 10:
            return JsonResponse({'status': 'error', 'message': 'Not enough content to generate a summary for this audiobook.'}, status=400)

    book_language_input = str(audiobook.language).lower().strip() if audiobook.language else 'unknown'
    target_summary_language_name = "English"
    
    if book_language_input in ['ur', 'urdu', 'urd']:
        target_summary_language_name = "Urdu"
    elif book_language_input in ['sd', 'sindhi', 'snd']:
        target_summary_language_name = "Urdu"
    elif book_language_input in ['pa', 'punjabi', 'panjabi', 'pnb']:
        target_summary_language_name = "Urdu"
    elif book_language_input in ['en', 'english', 'eng']:
        target_summary_language_name = "English"
    else:
        logger.info(f"Audiobook '{book_title}' (ID: {audiobook_id}) has language '{book_language_input}', which is not explicitly mapped for summary. Defaulting to English summary.")
        target_summary_language_name = "English"

    prompt = (
        f"Provide a concise summary (around 100-150 words) for the audiobook titled \"{book_title}\" "
        f"by {audiobook.author or 'Unknown Author'}. "
        f"The original language of the book is {book_language_input if book_language_input != 'unknown' else 'not specified'}. "
        f"Please write the summary in {target_summary_language_name}. "
        f"Base the summary on the following text:\n\n'{text_to_summarize}'"
    )

    logger.info(f"Requesting AI summary for audiobook '{book_title}' (ID: {audiobook_id}). Target language: {target_summary_language_name}. Prompt snippet: \"{prompt[:150]}...\"")

    try:
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel(model_name='gemini-1.5-flash')
        response = model.generate_content(prompt)
        summary_text = response.text.strip()

        logger.info(f"Successfully generated summary for audiobook '{book_title}' (ID: {audiobook_id}). Length: {len(summary_text)} chars.")

        return JsonResponse({
            'status': 'success',
            'title': book_title,
            'summary': summary_text,
            'language_of_summary': target_summary_language_name,
            'original_book_language': book_language_input
        })
    except Exception as e:
        logger.error(f"Error calling Google Gemini API or processing summary for audiobook '{book_title}' (ID: {audiobook_id}): {e}", exc_info=True)
        error_message = 'Failed to generate summary. An external service error occurred.'
        return JsonResponse({'status': 'error', 'message': error_message}, status=500)