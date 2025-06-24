# AudioXApp/views/summary_views.py

from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpRequest
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from AudioXApp.models import Audiobook
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)

# --- AI Summary View ---

@login_required
@require_http_methods(["GET"])
def get_ai_summary(request: HttpRequest, audiobook_id: int):
    """Generate AI summary - restricted to premium users only"""
    
    # Check if user has premium subscription
    if not hasattr(request.user, 'subscription_type') or request.user.subscription_type != 'PR':
        logger.warning(f"Non-premium user {request.user.username} attempted to access AI summary for audiobook {audiobook_id}")
        return JsonResponse({
            'status': 'error', 
            'message': 'AI summaries are available for Premium subscribers only. Upgrade to Premium to access this feature.',
            'premium_required': True,
            'subscription_url': '/subscribe/'
        }, status=403)
    
    # Check if Gemini API key is configured
    gemini_api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if not gemini_api_key:
        logger.error("GEMINI_API_KEY not configured in settings for AI summary.")
        return JsonResponse({
            'status': 'error', 
            'message': 'AI summarization service is currently unavailable. Please try again later.'
        }, status=500)

    try:
        audiobook = get_object_or_404(Audiobook, pk=audiobook_id)
    except Audiobook.DoesNotExist:
        logger.warning(f"Audiobook with ID {audiobook_id} not found for summary generation.")
        return JsonResponse({
            'status': 'error', 
            'message': 'Audiobook not found.'
        }, status=404)
    except Exception as e:
        logger.error(f"Error fetching audiobook with ID {audiobook_id}: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error', 
            'message': 'An error occurred while retrieving audiobook details.'
        }, status=500)

    book_title = audiobook.title
    text_to_summarize = audiobook.description or audiobook.title
    
    # Validate content length
    if not text_to_summarize or len(text_to_summarize.split()) < 20:
        logger.warning(f"Text for summary for audiobook '{book_title}' (ID: {audiobook_id}) is too short. Using combined title, author, and description.")
        text_to_summarize = f"Audiobook Title: {audiobook.title}. Author: {audiobook.author or 'Unknown Author'}. Description: {audiobook.description or 'No description available.'}"
        
        if len(text_to_summarize.split()) < 10:
            return JsonResponse({
                'status': 'error', 
                'message': 'Not enough content available to generate a meaningful summary for this audiobook.'
            }, status=400)

    # Determine target language for summary
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

    # Create prompt for AI summary generation
    prompt = (
        f"Provide a concise and informative summary (around 100-150 words) for the audiobook titled \"{book_title}\" "
        f"by {audiobook.author or 'Unknown Author'}. "
        f"The original language of the book is {book_language_input if book_language_input != 'unknown' else 'not specified'}. "
        f"Please write the summary in {target_summary_language_name}. "
        f"Focus on the main themes, key points, and overall content of the audiobook. "
        f"Base the summary on the following text:\n\n'{text_to_summarize}'"
    )

    logger.info(f"Premium user {request.user.username} requesting AI summary for audiobook '{book_title}' (ID: {audiobook_id}). Target language: {target_summary_language_name}")

    try:
        # Configure and call Gemini API
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel(model_name='gemini-1.5-flash')
        response = model.generate_content(prompt)
        summary_text = response.text.strip()

        logger.info(f"Successfully generated summary for audiobook '{book_title}' (ID: {audiobook_id}) for premium user {request.user.username}. Length: {len(summary_text)} chars.")

        return JsonResponse({
            'status': 'success',
            'title': book_title,
            'summary': summary_text,
            'language_of_summary': target_summary_language_name,
            'original_book_language': book_language_input,
            'user_is_premium': True
        })
        
    except Exception as e:
        logger.error(f"Error calling Google Gemini API or processing summary for audiobook '{book_title}' (ID: {audiobook_id}): {e}", exc_info=True)
        error_message = 'Failed to generate summary due to an external service error. Please try again in a few moments.'
        return JsonResponse({
            'status': 'error', 
            'message': error_message
        }, status=500)
