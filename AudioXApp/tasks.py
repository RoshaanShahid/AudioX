# AudioXApp/tasks.py

from celery import shared_task
from django.db import transaction
import logging

from .models import Chapter, Audiobook
from .services import moderation_service 

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_chapter_for_moderation(self, chapter_id):
    """
    Celery task to process a single chapter for content moderation.
    """
    try:
        with transaction.atomic():
            chapter = Chapter.objects.select_for_update().get(chapter_id=chapter_id)
            logger.info(f"Starting moderation for Chapter ID: {chapter.chapter_id} ('{chapter.chapter_name}')")

            if not chapter.audio_file or not hasattr(chapter.audio_file, 'path') or not chapter.audio_file.path:
                logger.warning(f"Chapter ID {chapter.chapter_id} has no valid audio file path. Marking for review.")
                chapter.moderation_status = Chapter.ModerationStatusChoices.NEEDS_REVIEW
                chapter.moderation_notes = "Processing failed: Could not find a valid audio file path for the chapter."
                chapter.save(update_fields=['moderation_status', 'moderation_notes'])
                return

            transcription_result = moderation_service.transcribe_audio(
                audio_file_path=chapter.audio_file.path,
                language_name=chapter.audiobook.language
            )
            
            if not transcription_result['success']:
                logger.error(f"Transcription failed for Chapter ID: {chapter.chapter_id}. Reason: {transcription_result['error']}")
                chapter.moderation_status = Chapter.ModerationStatusChoices.NEEDS_REVIEW
                chapter.moderation_notes = f"Audio transcription failed: {transcription_result['error']}. Please review manually."
                chapter.save(update_fields=['moderation_status', 'moderation_notes'])
                return

            transcript = transcription_result['transcript']
            chapter.transcript = transcript
            
            if not transcript:
                logger.warning(f"Transcription returned empty for Chapter ID: {chapter.chapter_id}.")
                chapter.moderation_status = Chapter.ModerationStatusChoices.NEEDS_REVIEW
                chapter.moderation_notes = "Audio was transcribed as empty. Please review manually."
                chapter.save(update_fields=['transcript', 'moderation_status', 'moderation_notes'])
                return

            analysis_result = moderation_service.analyze_text(transcript, chapter.audiobook.language)

            if analysis_result['is_inappropriate']:
                chapter.moderation_status = Chapter.ModerationStatusChoices.NEEDS_REVIEW
                chapter.moderation_notes = analysis_result.get('details', 'Flagged by automated content analysis.')
                logger.info(f"Chapter ID {chapter.chapter_id} flagged for manual review. Reason: {chapter.moderation_notes}")
            else:
                chapter.moderation_status = Chapter.ModerationStatusChoices.APPROVED
                chapter.moderation_notes = 'Automatically approved by content analysis.'
                logger.info(f"Chapter ID {chapter.chapter_id} automatically approved.")

            chapter.save()

    except Chapter.DoesNotExist:
        logger.error(f"Chapter with ID {chapter_id} not found for moderation.")
        return 
    except Exception as exc:
        logger.error(f"An unexpected error occurred during moderation of chapter {chapter_id}: {exc}", exc_info=True)
        try:
            with transaction.atomic():
                chapter = Chapter.objects.select_for_update().get(chapter_id=chapter_id)
                chapter.moderation_status = Chapter.ModerationStatusChoices.NEEDS_REVIEW
                chapter.moderation_notes = f"Processing failed with an unexpected error. Needs manual review."
                chapter.save(update_fields=['moderation_status', 'moderation_notes'])
        except Chapter.DoesNotExist:
            pass 
        self.retry(exc=exc)

    finally:
        try:
            chapter = Chapter.objects.get(chapter_id=chapter_id)
            check_and_update_audiobook_status.delay(chapter.audiobook.audiobook_id)
        except Chapter.DoesNotExist:
            pass


@shared_task
def check_and_update_audiobook_status(audiobook_id):
    """
    Checks the status of all chapters for an audiobook. If all have been processed,
    it updates the parent audiobook's moderation and public status accordingly.
    """
    try:
        with transaction.atomic():
            audiobook = Audiobook.objects.select_for_update().get(pk=audiobook_id)
            chapters = audiobook.chapters.all()
            total_chapters_count = chapters.count()

            if total_chapters_count == 0:
                logger.warning(f"Audiobook ID {audiobook_id} has no chapters. Flagging for review.")
                # CORRECTED: Use string literal 'UNDER_REVIEW'
                if audiobook.status != 'UNDER_REVIEW':
                    audiobook.moderation_status = Audiobook.ModerationStatusChoices.NEEDS_REVIEW
                    audiobook.status = 'UNDER_REVIEW'
                    audiobook.moderation_notes = "Cannot publish: Audiobook has no chapters."
                    audiobook.save(update_fields=['moderation_status', 'status', 'moderation_notes'])
                return

            chapter_statuses = set(chapters.values_list('moderation_status', flat=True))

            if Chapter.ModerationStatusChoices.PENDING_REVIEW in chapter_statuses:
                logger.info(f"Audiobook ID {audiobook_id} is still awaiting moderation for some chapters. Check will run again later.")
                return

            is_any_rejected = Chapter.ModerationStatusChoices.REJECTED in chapter_statuses
            is_any_needs_review = Chapter.ModerationStatusChoices.NEEDS_REVIEW in chapter_statuses

            if is_any_rejected or is_any_needs_review:
                # CORRECTED: Use string literal 'UNDER_REVIEW'
                if audiobook.status != 'UNDER_REVIEW':
                    audiobook.moderation_status = Audiobook.ModerationStatusChoices.NEEDS_REVIEW
                    audiobook.status = 'UNDER_REVIEW'
                    audiobook.moderation_notes = "One or more chapters require manual review or have been rejected."
                    audiobook.save(update_fields=['moderation_status', 'status', 'moderation_notes'])
                    logger.warning(f"Audiobook ID {audiobook_id} has been flagged and is now UNDER REVIEW.")
            
            elif all(status == Chapter.ModerationStatusChoices.APPROVED for status in chapter_statuses):
                if audiobook.moderation_status != Audiobook.ModerationStatusChoices.APPROVED:
                    audiobook.moderation_status = Audiobook.ModerationStatusChoices.APPROVED
                    audiobook.moderation_notes = "All chapters have been automatically approved."
                    audiobook.save() 
                    logger.info(f"Audiobook ID {audiobook_id} ('{audiobook.title}') has been fully approved and is now Published.")
            
            else:
                 # CORRECTED: Use string literal 'UNDER_REVIEW'
                 if audiobook.status != 'UNDER_REVIEW':
                    audiobook.moderation_status = Audiobook.ModerationStatusChoices.NEEDS_REVIEW
                    audiobook.status = 'UNDER_REVIEW'
                    audiobook.moderation_notes = f"Chapters have an unhandled combination of statuses: {chapter_statuses}. Please review."
                    audiobook.save(update_fields=['moderation_status', 'status', 'moderation_notes'])
                    logger.error(f"Audiobook ID {audiobook_id} has an unhandled chapter status mix: {chapter_statuses}")

    except Audiobook.DoesNotExist:
        logger.error(f"Audiobook with ID {audiobook_id} not found for status check.")