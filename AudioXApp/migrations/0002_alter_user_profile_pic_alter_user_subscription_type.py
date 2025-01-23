# Generated by Django 5.1.5 on 2025-01-23 17:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AudioXApp', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='profile_pic',
            field=models.ImageField(blank=True, default='/static/img/default_profile.png', null=True, upload_to='profile_pics/'),
        ),
        migrations.AlterField(
            model_name='user',
            name='subscription_type',
            field=models.CharField(choices=[('FR', 'Free'), ('PR', 'Premium')], default='FR', max_length=2),
        ),
    ]
