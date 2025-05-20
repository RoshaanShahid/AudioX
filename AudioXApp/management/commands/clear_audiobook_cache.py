from django.core.management.base import BaseCommand
from django.core.cache import cache
# No need to import fetch_audiobooks_data here as we are only dealing with the cache

class Command(BaseCommand):
    help = 'Clears the specific audiobook data cache (librivox_archive_audiobooks_data_v6).'

    def add_arguments(self, parser):
        # Optional: Add an argument to clear the entire cache
        parser.add_argument(
            '--all',
            action='store_true',
            help='Clear the entire Django cache instead of just the specific audiobook cache key.',
        )

    def handle(self, *args, **options):
        cache_key = 'librivox_archive_audiobooks_data_v6'

        if options['all']:
            self.stdout.write(self.style.NOTICE('Attempting to clear the entire cache...'))
            try:
                cache.clear()
                self.stdout.write(self.style.SUCCESS('Successfully cleared the entire cache.'))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'An error occurred while clearing the entire cache: {e}'))
        else:
            self.stdout.write(self.style.NOTICE(f"Attempting to delete cache key '{cache_key}'..."))
            # The cache.delete() method returns True if the key was deleted, False if the key didn't exist.
            # Some cache backends might not explicitly return True/False or always return None.
            # So, we proceed assuming the delete operation was issued.
            try:
                was_found_and_deleted = cache.delete(cache_key) # For backends that support it
                if was_found_and_deleted is True: # Explicitly check for True if backend supports it
                     self.stdout.write(self.style.SUCCESS(f"Successfully deleted cache key '{cache_key}'."))
                elif was_found_and_deleted is False: # Explicitly check for False
                     self.stdout.write(self.style.WARNING(f"Cache key '{cache_key}' was not found."))
                else: # For backends that return None or other values
                    self.stdout.write(self.style.SUCCESS(f"Delete command issued for cache key '{cache_key}'. "
                                                         "Its existence or successful deletion depends on the cache backend's behavior."))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"An error occurred while trying to delete cache key '{cache_key}': {e}"))

        self.stdout.write(self.style.NOTICE('Cache clearing process finished.'))