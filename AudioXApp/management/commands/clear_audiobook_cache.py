# AudioXApp/management/commands/clearcache.py

from django.core.management.base import BaseCommand
from django.core.cache import cache

# --- Clear Cache Management Command ---

class Command(BaseCommand):
    """
    A Django management command to clear a specific cache key or the entire cache.
    
    This command helps in manually flushing cached data, which is useful during
    development or when you need to force-fetch fresh data.
    
    Usage:
        python manage.py clearcache
        python manage.py clearcache --all
    """
    help = 'Clears the specific audiobook data cache or the entire cache.'

    def add_arguments(self, parser):
        """Adds command-line arguments to the command."""
        parser.add_argument(
            '--all',
            action='store_true',
            help='Clear the entire Django cache instead of the specific audiobook cache key.',
        )

    def handle(self, *args, **options):
        """The main logic of the command."""
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
            try:
                was_found_and_deleted = cache.delete(cache_key)
                if was_found_and_deleted:
                    self.stdout.write(self.style.SUCCESS(f"Successfully deleted cache key '{cache_key}'."))
                else:
                    self.stdout.write(self.style.WARNING(f"Cache key '{cache_key}' was not found."))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"An error occurred while trying to delete cache key '{cache_key}': {e}"))

        self.stdout.write(self.style.NOTICE('Cache clearing process finished.'))