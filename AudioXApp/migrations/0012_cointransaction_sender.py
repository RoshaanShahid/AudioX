# Generated by Django 5.1.5 on 2025-02-13 16:42

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AudioXApp', '0011_cointransaction_recipient_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='cointransaction',
            name='sender',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gifts_sent', to=settings.AUTH_USER_MODEL),
        ),
    ]
