# Generated by Django 5.1.5 on 2025-02-13 10:54

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AudioXApp', '0007_alter_coinpurchase_coin_pack_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='coinpurchase',
            name='purchase_time',
            field=models.TimeField(default=datetime.time(15, 54, 14, 367812)),
        ),
    ]
