# AudioXApp/services/moderation_service.py

import logging
import os
import re 
from django.conf import settings
from django.core.cache import cache
from google.cloud import speech
from google.api_core import exceptions as google_exceptions
from google.cloud import language_v1

# NEW: Import the fuzzy matching library
from thefuzz import fuzz

from ..models import BannedKeyword

logger = logging.getLogger(__name__)

# --- Language & Audio Mappings (No changes here) ---
LANGUAGE_CODE_MAPPING = {
    'English': 'en-US',
    'Urdu': 'ur-PK',
    'Punjabi': 'pa-IN',
    'Sindhi': 'sd-IN', 
}

AUDIO_ENCODING_MAPPING = {
    '.mp3': speech.RecognitionConfig.AudioEncoding.MP3,
    '.wav': speech.RecognitionConfig.AudioEncoding.LINEAR16,
    '.ogg': speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
    '.m4a': speech.RecognitionConfig.AudioEncoding.MP3,
}

# --- _get_banned_keywords_for_language (No changes here) ---
def _get_banned_keywords_for_language(language_name):
    language_code = 'en'
    for key, val in LANGUAGE_CODE_MAPPING.items():
        if key.lower() == language_name.lower():
            language_code = val.split('-')[0]
            break
            
    cache_key = f'banned_keywords_{language_code}'
    
    keywords = cache.get(cache_key)
    if keywords is None:
        logger.info(f"Cache miss for banned keywords in '{language_name}' (code: {language_code}). Fetching from DB.")
        keywords = list(BannedKeyword.objects.filter(language=language_code).values_list('keyword', flat=True))
        keywords = [k.strip().lower() for k in keywords if k]
        cache.set(cache_key, keywords, 3600)
    
    return keywords

# --- transcribe_audio (No changes here) ---
def transcribe_audio(audio_file_path, language_name='English'):
    logger.info(f"Attempting transcription for '{audio_file_path}' with language '{language_name}'")
    
    if not settings.GOOGLE_APPLICATION_CREDENTIALS or not os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
        error_msg = "Google Cloud credentials file not found or not configured in settings.py. Cannot perform transcription."
        logger.error(error_msg)
        return {'success': False, 'transcript': None, 'error': error_msg}

    if not os.path.exists(audio_file_path):
        error_msg = f"Audio file not found at path: {audio_file_path}"
        logger.error(error_msg)
        return {'success': False, 'transcript': None, 'error': error_msg}
        
    try:
        client = speech.SpeechClient.from_service_account_file(settings.GOOGLE_APPLICATION_CREDENTIALS)
        with open(audio_file_path, "rb") as audio_file:
            content = audio_file.read()
        audio = speech.RecognitionAudio(content=content)
        file_ext = os.path.splitext(audio_file_path)[1].lower()
        encoding = AUDIO_ENCODING_MAPPING.get(file_ext)
        gcp_language_code = LANGUAGE_CODE_MAPPING.get(language_name, 'en-US')
        if not encoding:
            error_msg = f"Unsupported audio format: '{file_ext}'. Cannot transcribe."
            logger.error(error_msg)
            return {'success': False, 'transcript': None, 'error': error_msg}
        config = speech.RecognitionConfig(
            encoding=encoding,
            language_code=gcp_language_code,
            enable_automatic_punctuation=True,
        )
        logger.info(f"Sending audio file to Google STT API. Encoding: {encoding}, Language: {gcp_language_code}")
        response = client.recognize(config=config, audio=audio)
        transcript = "".join(result.alternatives[0].transcript for result in response.results)
        logger.info(f"Transcription successful for '{os.path.basename(audio_file_path)}'. Transcript length: {len(transcript)} chars.")
        return {'success': True, 'transcript': transcript, 'error': None}
    except Exception as e:
        error_msg = "An unexpected error occurred during the Google Speech-to-Text API call."
        logger.error(f"{error_msg} - Original error: {e}", exc_info=True)
        return {'success': False, 'transcript': None, 'error': str(e)}


def analyze_text(transcript_text, language_name):
    """
    Analyzes a transcript for banned keywords using fuzzy matching
    and for negative sentiment.
    Returns a dictionary: {'is_inappropriate': bool, 'details': str}
    """
    # --- Pass 1: Banned Keyword Check (with Fuzzy Matching) ---
    banned_keywords = _get_banned_keywords_for_language(language_name)
    
    normalized_transcript = ' ' + re.sub(r'[^\w\s]', ' ', transcript_text.lower()) + ' '
    normalized_transcript = re.sub(r'\s+', ' ', normalized_transcript)

    logger.info("--- Moderation Check (Fuzzy) ---")
    logger.info(f"Language: {language_name}")
    logger.info(f"Banned Keywords Fetched: {banned_keywords}")

    # ADDED THIS LINE FOR DEBUGGING: Let's see the exact text being checked.
    logger.info(f"Normalized Transcript for Matching: '{normalized_transcript}'")

    SIMILARITY_THRESHOLD = 80
    
    if not banned_keywords:
        logger.info("No banned keywords configured for this language. Skipping keyword check.")
    else:
        transcript_words = normalized_transcript.strip().split()

        for banned_word in banned_keywords:
            for transcript_word in transcript_words:
                similarity_score = fuzz.ratio(banned_word, transcript_word)
                
                if similarity_score >= SIMILARITY_THRESHOLD:
                    logger.warning(
                        f"BANNED KEYWORD FOUND (Fuzzy Match): Keyword '{banned_word}' is "
                        f"{similarity_score}% similar to transcript word '{transcript_word}'. Flagging for review."
                    )
                    return {
                        'is_inappropriate': True,
                        'details': f"Content flagged for potential banned keyword. Found '{transcript_word}' which is highly similar to '{banned_word}'."
                    }
            
    # --- Pass 2: Sentiment Analysis (No changes here) ---
    if not settings.GOOGLE_APPLICATION_CREDENTIALS or not os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
        logger.warning("Google Cloud credentials not configured. Skipping sentiment analysis.")
        return {'is_inappropriate': False, 'details': 'Passed keyword check; sentiment analysis skipped due to config.'}
        
    try:
        client = language_v1.LanguageServiceClient.from_service_account_file(settings.GOOGLE_APPLICATION_CREDENTIALS)
        document = language_v1.Document(content=transcript_text, type_=language_v1.Document.Type.PLAIN_TEXT)
        sentiment = client.analyze_sentiment(document=document).document_sentiment
        logger.info(f"Sentiment analysis result: Score={sentiment.score:.2f}, Magnitude={sentiment.magnitude:.2f}")

        if sentiment.score < -0.5 and sentiment.magnitude > 1.0:
            logger.warning("Content flagged for highly negative sentiment.")
            return {
                'is_inappropriate': True,
                'details': f"Content flagged for highly negative sentiment (Score: {sentiment.score:.2f})."
            }
    except Exception as e:
        logger.error(f"Error during Google Natural Language API call: {e}", exc_info=True)
        pass

    logger.info("Content passed all automated checks.")
    return {'is_inappropriate': False, 'details': 'Passed automated keyword and sentiment checks.'}