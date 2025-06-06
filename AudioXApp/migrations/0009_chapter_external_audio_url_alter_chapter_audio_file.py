# Generated by Django 4.2.19 on 2025-06-01 08:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AudioXApp', '0008_merge_20250529_1042'),
    ]

    operations = [
        migrations.AddField(
            model_name='chapter',
            name='external_audio_url',
            field=models.URLField(blank=True, help_text='Direct URL for externally sourced chapter audio (Librivox, Archive.org).', max_length=1024, null=True),
        ),
        migrations.AlterField(
            model_name='chapter',
            name='audio_file',
            field=models.FileField(blank=True, help_text='Audio file for creator-uploaded chapters.', null=True, upload_to='chapters_audio/'),
        ),
    ]
