# AudioXApp/views/summary_views.py

from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpRequest
from django.conf import settings
from AudioXApp.models import Audiobook # Assuming your Audiobook model is in AudioXApp.models
import logging
# Import specific exceptions if you plan to catch them explicitly
# from requests.exceptions import ConnectionError, Timeout # Example, if langchain uses requests

# Corrected import based on your `dir()` output
try:
    from langchain_deepseek import ChatDeepSeek # Changed from DeepSeekLLM to ChatDeepSeek
    LANGCHAIN_DEEPSEEK_AVAILABLE = True
    # Assign the imported class to a consistent variable name for use in the view
    ChatDeepSeekModel = ChatDeepSeek
except ImportError:
    LANGCHAIN_DEEPSEEK_AVAILABLE = False
    ChatDeepSeekModel = None # To avoid NameError if not available
    logging.warning(
        "langchain-deepseek library is installed, but the ChatDeepSeek class could not be imported directly. "
        "AI summary feature will be disabled. Please check the library version and documentation for correct import path."
    )
except Exception as e:
    # Catch any other unexpected errors during import
    LANGCHAIN_DEEPSEEK_AVAILABLE = False
    ChatDeepSeekModel = None
    logging.error(f"An unexpected error occurred while trying to import ChatDeepSeek: {e}", exc_info=True)


logger = logging.getLogger(__name__)

def get_ai_summary(request: HttpRequest, audiobook_id: int):
    """
    Generates an AI summary for the given audiobook ID using DeepSeek.
    The summary language is determined by the audiobook's language:
    - English book -> English summary
    - Urdu, Sindhi, Punjabi book -> Urdu summary
    - Other languages -> English summary (default)
    """
    if not LANGCHAIN_DEEPSEEK_AVAILABLE or ChatDeepSeekModel is None:
        logger.error("Attempted to use AI summary feature, but ChatDeepSeek model is not available (import failed or library missing).")
        return JsonResponse({'error': 'AI summarization module not available. Please check server configuration or library installation.'}, status=500)

    # The API key is now expected to be picked up by ChatDeepSeekModel from the environment.
    # We still check if it's in settings to ensure it's loaded from .env for clarity and potential direct use elsewhere.
    if not settings.DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY not configured in settings for AI summary. The library might not find it.")
        return JsonResponse({'error': 'AI summarization service API key not configured in application settings.'}, status=500)

    try:
        # Fetch the audiobook object by its primary key (audiobook_id)
        audiobook = get_object_or_404(Audiobook, pk=audiobook_id)
    except Audiobook.DoesNotExist:
        logger.warning(f"Audiobook with ID {audiobook_id} not found for summary generation.")
        return JsonResponse({'error': 'Audiobook not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching audiobook with ID {audiobook_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'An error occurred while retrieving audiobook details.'}, status=500)

    book_title = audiobook.title
    # Normalize book language: convert to lowercase and handle None or empty strings
    book_language_input = str(audiobook.language).lower().strip() if audiobook.language else 'unknown'

    # Determine the target language for the summary based on your requirements
    target_summary_language_name = "English" # Default
    target_summary_language_code = "en"      # Default

    # Language mapping logic
    if book_language_input in ['ur', 'urdu', 'urd']:
        target_summary_language_name = "Urdu"
        target_summary_language_code = "ur"
    elif book_language_input in ['sd', 'sindhi', 'snd']:
        target_summary_language_name = "Urdu" # Sindhi books get Urdu summary
        target_summary_language_code = "ur"
    elif book_language_input in ['pa', 'punjabi', 'panjabi', 'pnb']:
        target_summary_language_name = "Urdu" # Punjabi books get Urdu summary
        target_summary_language_code = "ur"
    elif book_language_input in ['en', 'english', 'eng']:
        target_summary_language_name = "English"
        target_summary_language_code = "en"
    else:
        # For other languages not explicitly handled, default to English summary
        logger.info(
            f"Audiobook '{book_title}' (ID: {audiobook_id}) has language '{book_language_input}', "
            f"which is not explicitly mapped for summary. Defaulting to English summary."
        )
        target_summary_language_name = "English"
        target_summary_language_code = "en"

    # Construct the prompt for the DeepSeek API
    prompt = (
        f"Please provide a concise summary for the book titled \"{book_title}\". "
        f"The original language of the book is {book_language_input if book_language_input != 'unknown' else 'not specified'}. "
        f"Write the summary in {target_summary_language_name}."
    )

    logger.info(f"Requesting AI summary for audiobook '{book_title}' (ID: {audiobook_id}). Target language: {target_summary_language_name}. Prompt: \"{prompt[:100]}...\"")

    try:
        # Initialize the DeepSeek client using the correctly imported ChatDeepSeekModel.
        # The API key is expected to be picked up from the environment variable DEEPSEEK_API_KEY.
        llm = ChatDeepSeekModel(
            model="deepseek-chat", # Or another suitable model from DeepSeek for summarization
            # deepseek_api_key=settings.DEEPSEEK_API_KEY, # <-- THIS LINE WAS REMOVED
            # You might still need other parameters like temperature, max_tokens if desired
            # temperature=0.7,
            # max_tokens=500, # Adjust as needed for summary length
        )

        # Make the API call
        summary_text = llm.invoke(prompt)

        logger.info(f"Successfully generated summary for audiobook '{book_title}' (ID: {audiobook_id}). Length: {len(summary_text)} chars.")

        # Return the generated summary
        return JsonResponse({
            'title': book_title,
            'summary': summary_text,
            'language_of_summary': target_summary_language_name, # e.g., "English" or "Urdu"
            'original_book_language': book_language_input
        })

    except Exception as e:
        # This will catch errors from the API call (e.g., network issues, API key errors, rate limits)
        # or any other unexpected errors during the llm.invoke() or processing.
        logger.error(f"Error calling DeepSeek API or processing summary for audiobook '{book_title}' (ID: {audiobook_id}): {e}", exc_info=True)
        
        error_message = f'Failed to generate summary. An external service error occurred.'
        # More specific error checks based on the actual exception 'e' can be added here
        # For example, if using 'requests' under the hood and it raises specific exceptions:
        # if isinstance(e, ConnectionError):
        #     error_message = 'Failed to connect to the summarization service. Please check network connectivity.'
        # elif isinstance(e, Timeout):
        #     error_message = 'The request to the summarization service timed out.'
        # else
        if "authenticate" in str(e).lower() or "api key" in str(e).lower() or "permission denied" in str(e).lower():
            error_message = 'Failed to generate summary due to an API key or authentication issue with the summarization service.'
        elif "rate limit" in str(e).lower():
            error_message = 'Failed to generate summary. The summarization service rate limit may have been exceeded.'
        
        return JsonResponse({'error': error_message}, status=500)

# Example of how you might add this to your urls.py in AudioXApp:
# from django.urls import path
# from .views import summary_views # Assuming this file is summary_views.py
#
# urlpatterns = [
#     # ... other url patterns ...
#     path('audiobook/<int:audiobook_id>/get-ai-summary/', summary_views.get_ai_summary, name='get_ai_summary'),
# ]
