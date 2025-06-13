# AudioXApp/management/commands/populate_static_audiobooks.py

import os
import requests
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.utils.text import slugify
from ...models import Audiobook, Chapter

# --- Predefined List of Audiobooks to Download ---
AUDIOBOOKS = [
    {
        "title": "Selected Ghazals of Ghalib",
        "author": "Mirza Ghalib",
        "url": "https://archive.org/download/ghazals_ghalib_0809_librivox/ghazalsofghalib_01_ghalib.mp3"
    },
    {
        "title": "Crime and Punishment",
        "author": "Fyodor Dostoyevsky",
        "url": "https://archive.org/download/crime_and_punishment_librivox/crime_and_punishment_01_dostoevsky.mp3"
    },
    {
        "title": "Beyond Good and Evil",
        "author": "Friedrich Nietzsche",
        "url": "https://archive.org/download/beyond_good_and_evil_librivox/beyond_good_and_evil_01_nietzsche.mp3"
    },
    {
        "title": "The Apology of Socrates",
        "author": "Plato",
        "url": "https://archive.org/download/apology_1103_librivox/apology_01_plato.mp3"
    },
    {
        "title": "War and Peace, Volume 1",
        "author": "Leo Tolstoy",
        "url": "https://archive.org/download/war_and_peace_vol1_1001_librivox/war_and_peace_01_tolstoy.mp3"
    }
]

# --- Management Command ---
class Command(BaseCommand):
    """
    Downloads a predefined list of audiobooks from archive.org, creates Audiobook
    and Chapter entries in the database, and saves the audio files locally.
    
    Usage:
        python manage.py populate_static_audiobooks
    """
    help = 'Download selected audiobooks and save them to the database'

    def handle(self, *args, **kwargs):
        """The main logic of the command."""
        self.stdout.write(self.style.NOTICE('Starting to download and save static audiobooks...'))

        for book_data in AUDIOBOOKS:
            try:
                # Check if the audiobook already exists to avoid duplicates
                audiobook, created = Audiobook.objects.get_or_create(
                    title=book_data['title'],
                    defaults={
                        'author': book_data['author'],
                        'is_creator_book': False,
                        'source': 'archive',
                        'status': 'PUBLISHED',
                        'is_paid': False,
                        'description': f"A public domain recording of {book_data['title']} by {book_data['author']}."
                    }
                )

                if created:
                    self.stdout.write(f"Downloading '{book_data['title']}'...")
                    response = requests.get(book_data['url'], stream=True)
                    response.raise_for_status()  # Will raise an HTTPError for bad responses (4xx or 5xx)

                    # Create a single chapter for this audiobook
                    chapter, chapter_created = Chapter.objects.get_or_create(
                        audiobook=audiobook,
                        chapter_order=1,
                        defaults={'chapter_name': book_data['title']}
                    )

                    if chapter_created:
                        # Save the downloaded audio to the chapter's audio_file field
                        file_name = f"{slugify(book_data['title'])}.mp3"
                        chapter.audio_file.save(file_name, ContentFile(response.content), save=True)
                        self.stdout.write(self.style.SUCCESS(f"Successfully saved and created chapter for: {book_data['title']}"))
                    else:
                        self.stdout.write(self.style.WARNING(f"Audiobook '{book_data['title']}' created, but chapter already existed. Skipping file download."))
                else:
                    self.stdout.write(self.style.WARNING(f"Audiobook '{book_data['title']}' already exists in the database. Skipping."))

            except requests.exceptions.RequestException as e:
                self.stderr.write(self.style.ERROR(f"Failed to download '{book_data['title']}': {e}"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"An unexpected error occurred for '{book_data['title']}': {e}"))
        
        self.stdout.write(self.style.SUCCESS('Finished processing all static audiobooks.'))