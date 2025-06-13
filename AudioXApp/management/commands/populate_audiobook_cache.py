# AudioXApp/management/commands/populate_audiobook_cache.py

import time
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from ...views.content_views import fetch_audiobooks_data

# --- Populate Audiobook Cache Command ---

class Command(BaseCommand):
    """
    Fetches audiobook data from LibriVox and Archive.org and populates the cache.
    
    This command is designed to be run as a scheduled task (e.g., a cron job)
    to keep the external audiobook data fresh without impacting user request times.
    
    Usage:
        python manage.py populate_audiobook_cache
    """
    help = 'Fetches audiobook data from external sources and populates the cache.'

    def handle(self, *args, **options):
        """The main logic of the command."""
        self.stdout.write(self.style.NOTICE('Starting audiobook cache population...'))
        
        start_time = time.time()

        try:
            # This function handles its own caching logic and logging
            fetched_data = fetch_audiobooks_data()

            end_time = time.time()
            duration = end_time - start_time

            if fetched_data:
                librivox_count = len(fetched_data.get("librivox_audiobooks", []))
                archive_genre_count = sum(len(books) for books in fetched_data.get("archive_genre_audiobooks", {}).values())
                archive_lang_count = sum(len(books) for books in fetched_data.get("archive_language_audiobooks", {}).values())
                
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully populated audiobook cache in {duration:.2f} seconds. '
                    f'LibriVox: {librivox_count}, Archive Genres: {archive_genre_count}, Archive Languages: {archive_lang_count} items.'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Audiobook cache population completed in {duration:.2f} seconds, but no data was fetched. Check logs for details.'
                ))

        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            self.stderr.write(self.style.ERROR(f'An error occurred during cache population after {duration:.2f} seconds: {e}'))

        self.stdout.write(self.style.NOTICE('Cache population process finished.'))