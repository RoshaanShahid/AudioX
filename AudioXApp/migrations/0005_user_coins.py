# Generated by Django 5.1.5 on 2025-02-13 09:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AudioXApp', '0004_admin'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='coins',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
