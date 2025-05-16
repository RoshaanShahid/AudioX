# AudioXApp/management/commands/populate_audiobook_cache.py

import time
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
# Adjust the import path according to your project structure if AudioXApp is not at the top level
# or if content_views is in a different location within AudioXApp.
# Assuming AudioXApp is an app in your project and content_views is in AudioXApp/views/
try:
    from AudioXApp.views.content_views import fetch_audiobooks_data
except ImportError:
    # This fallback might be needed if your project structure is different
    # or if running the command from a context where AudioXApp isn't directly in sys.path
    # For example, if AudioXApp is inside a 'src' directory that isn't the project root.
    # This is a common setup. If your app is directly under the project root,
    # the first import should work.
    from ...views.content_views import fetch_audiobooks_data


class Command(BaseCommand):
    help = 'Fetches audiobook data from external sources and populates the cache.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Starting audiobook cache population...'))
        
        # Record start time
        start_time = time.time()

        try:
            # Call the function that fetches and caches the data
            # This function should handle its own caching logic (cache.set)
            # and print statements for CACHE HIT/MISS/SET
            fetched_data = fetch_audiobooks_data()

            end_time = time.time()
            duration = end_time - start_time

            if fetched_data:
                # The fetch_audiobooks_data function already prints cache status.
                # We can add a summary here.
                librivox_count = len(fetched_data.get("librivox_audiobooks", []))
                archive_genre_count = sum(len(books) for books in fetched_data.get("archive_genre_audiobooks", {}).values())
                archive_lang_count = sum(len(books) for books in fetched_data.get("archive_language_audiobooks", {}).values())
                
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully populated audiobook cache in {duration:.2f} seconds. '
                    f'LibriVox: {librivox_count}, Archive Genres: {archive_genre_count}, Archive Languages: {archive_lang_count} items.'
                ))
            else:
                # This case implies fetch_audiobooks_data returned None, meaning a complete failure
                self.stdout.write(self.style.WARNING(
                    f'Audiobook cache population completed in {duration:.2f} seconds, but no data was fetched or an error occurred within fetch_audiobooks_data. Check its logs.'
                ))

        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            self.stderr.write(self.style.ERROR(f'An error occurred during cache population after {duration:.2f} seconds: {e}'))
            # You might want to raise CommandError to indicate failure more strongly
            # raise CommandError(f'Failed to populate cache: {e}')

        self.stdout.write(self.style.NOTICE('Cache population process finished.'))

