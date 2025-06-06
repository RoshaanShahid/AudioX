# Generated by Django 4.2.19 on 2025-05-27 20:34

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('AudioXApp', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserDownloadedAudiobook',
            fields=[
                ('download_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('download_date', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Download Date')),
                ('expiry_date', models.DateTimeField(blank=True, help_text='Optional: When the download access expires (e.g., for subscription-based downloads).', null=True, verbose_name='Expiry Date')),
                ('is_active', models.BooleanField(default=True, help_text='Is this download currently active and usable offline? Set to False if expired or revoked.', verbose_name='Is Active')),
                ('last_verified_at', models.DateTimeField(blank=True, help_text="Timestamp when the client app last verified the download's validity with the server.", null=True, verbose_name='Last Verified At')),
                ('audiobook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_downloads', to='AudioXApp.audiobook', verbose_name='Audiobook')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='downloaded_audiobooks', to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
            options={
                'verbose_name': 'User Downloaded Audiobook',
                'verbose_name_plural': 'User Downloaded Audiobooks',
                'db_table': 'USER_DOWNLOADED_AUDIOBOOKS',
                'ordering': ['-download_date'],
                'unique_together': {('user', 'audiobook')},
            },
        ),
    ]
