from django.core.management.base import BaseCommand
from AudioXApp.models import Audiobook, Chapter
from django.db import transaction
import logging
from collections import defaultdict # Import defaultdict

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Populates the external_chapter_identifier for existing external audiobook chapters.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting population of external_chapter_identifier..."))
        
        # Filter for external audiobooks that have chapters and whose chapters might be missing the identifier
        # We filter for chapters where external_chapter_identifier IS NULL AND audiobook is NOT a creator book
        chapters_to_update = Chapter.objects.filter(
            external_chapter_identifier__isnull=True,
            audiobook__is_creator_book=False
        ).select_related('audiobook').order_by('audiobook__slug', 'chapter_order')

        updated_count = 0
        processed_audiobooks = set()

        # Group chapters by audiobook to reduce database hits for slug
        chapters_by_audiobook = defaultdict(list)
        for chapter in chapters_to_update:
            chapters_by_audiobook[chapter.audiobook].append(chapter)

        self.stdout.write(f"Found {len(chapters_to_update)} chapters to update across {len(chapters_by_audiobook)} external audiobooks.")

        for audiobook, chapters_list in chapters_by_audiobook.items():
            try:
                with transaction.atomic():
                    self.stdout.write(f"Processing audiobook: '{audiobook.title}' (Slug: {audiobook.slug})")
                    for chapter in chapters_list:
                        # Construct the external identifier using the current slug and chapter order
                        external_identifier = f"ext-{audiobook.slug}-{chapter.chapter_order}"
                        
                        # Before assigning, quickly check if this identifier is already taken by another chapter
                        # (This is a safety check, usually unique_together on external_chapter_identifier prevents this)
                        if Chapter.objects.filter(external_chapter_identifier=external_identifier).exclude(pk=chapter.pk).exists():
                            logger.warning(f"Skipping chapter PK {chapter.pk} ('{chapter.chapter_name}'). Generated ID '{external_identifier}' already exists for another chapter. This should not happen if external_chapter_identifier is unique.")
                            self.stdout.write(self.style.WARNING(f"  - WARNING: Skipping '{chapter.chapter_name}' due to conflicting ID: {external_identifier}"))
                            continue
                            
                        chapter.external_chapter_identifier = external_identifier
                        chapter.save(update_fields=['external_chapter_identifier']) # Only update this field
                        updated_count += 1
                        self.stdout.write(f"  - Updated chapter '{chapter.chapter_name}' (PK: {chapter.pk}) with external_id: '{external_identifier}'")
                    processed_audiobooks.add(audiobook.slug)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error updating chapters for audiobook '{audiobook.slug}': {e}"))
                logger.error(f"Error in populate_external_chapter_ids for audiobook {audiobook.slug}: {e}", exc_info=True)

        self.stdout.write(self.style.SUCCESS(f"Finished population. Successfully updated {updated_count} chapters across {len(processed_audiobooks)} external audiobooks."))
        self.stdout.write(self.style.WARNING("NOTE: Existing ListeningHistory records will continue to point to Chapter PKs. "
                                             "However, the frontend_id property on Chapter will now correctly resolve "
                                             "to the external_chapter_identifier, fixing the mismatch in JavaScript."))