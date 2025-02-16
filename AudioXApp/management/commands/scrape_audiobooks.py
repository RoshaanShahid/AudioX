import os
import requests
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from AudioXApp.models import Audiobook , Chapter

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

class Command(BaseCommand):
    help = 'Download selected audiobooks and save them to the database'

    def handle(self, *args, **kwargs):
        media_root = os.path.join(os.getcwd(), 'media', 'audiobooks')
        os.makedirs(media_root, exist_ok=True)

        for book in AUDIOBOOKS:
            response = requests.get(book['url'])
            if response.status_code == 200:
                file_name = f"{book['title'].replace(' ', '_')}.mp3"
                file_path = os.path.join(media_root, file_name)
                with open(file_path, 'wb') as f:
                    f.write(response.content)

                with open(file_path, 'rb') as f:
                    audiobook = Audiobook(
                        title=book['title'],
                        author=book['author'],
                        file_url=f'audiobooks/{file_name}'
                    )
                    audiobook.save()
                    self.stdout.write(self.style.SUCCESS(f"Saved: {book['title']}"))
            else:
                self.stdout.write(self.style.ERROR(f"Failed to download: {book['title']}"))
