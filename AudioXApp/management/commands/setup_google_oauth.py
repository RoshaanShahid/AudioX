from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Set up Google OAuth configuration for django-allauth'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update existing configurations',
        )

    def handle(self, *args, **options):
        force = options['force']
        
        # Step 1: Set up Django Sites
        self.stdout.write("Setting up Django Sites...")
        
        try:
            site = Site.objects.get(pk=settings.SITE_ID)
            if site.domain == 'example.com' or force:
                site.domain = '127.0.0.1:8000'  # For development
                site.name = 'AudioX Development'
                site.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Updated site: {site.domain}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Site already configured: {site.domain}')
                )
        except Site.DoesNotExist:
            site = Site.objects.create(
                pk=settings.SITE_ID,
                domain='127.0.0.1:8000',
                name='AudioX Development'
            )
            self.stdout.write(
                self.style.SUCCESS(f'Created site: {site.domain}')
            )

        # Step 2: Set up Google OAuth App
        self.stdout.write("Setting up Google OAuth app...")
        
        google_client_id = os.getenv('GOOGLE_CLIENT_ID')
        google_client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        
        if not google_client_id or not google_client_secret:
            self.stdout.write(
                self.style.ERROR(
                    'GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env file'
                )
            )
            return

        try:
            google_app = SocialApp.objects.get(provider='google')
            if force:
                google_app.client_id = google_client_id
                google_app.secret = google_client_secret
                google_app.name = 'Google OAuth'
                google_app.save()
                google_app.sites.add(site)
                self.stdout.write(
                    self.style.SUCCESS('Updated Google OAuth app')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('Google OAuth app already exists')
                )
        except SocialApp.DoesNotExist:
            google_app = SocialApp.objects.create(
                provider='google',
                name='Google OAuth',
                client_id=google_client_id,
                secret=google_client_secret,
            )
            google_app.sites.add(site)
            self.stdout.write(
                self.style.SUCCESS('Created Google OAuth app')
            )

        # Step 3: Display setup instructions
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS("Google OAuth Setup Complete!"))
        self.stdout.write("="*50)
        
        self.stdout.write("\nIn your Google Cloud Console, make sure to configure:")
        self.stdout.write(f"• Authorized JavaScript origins: http://127.0.0.1:8000")
        self.stdout.write(f"• Authorized redirect URIs:")
        self.stdout.write(f"  - http://127.0.0.1:8000/accounts/google/login/callback/")
        self.stdout.write(f"  - http://localhost:8000/accounts/google/login/callback/")
        
        if settings.DEBUG:
            self.stdout.write("\nFor production, update the site domain and add:")
            self.stdout.write("• https://yourdomain.com")
            self.stdout.write("• https://yourdomain.com/accounts/google/login/callback/")
        
        self.stdout.write("\nGoogle OAuth is now ready to use!") 