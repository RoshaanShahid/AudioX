# Generated by Django 5.1.5 on 2025-02-13 11:20

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('AudioXApp', '0009_remove_coinpurchase_coin_pack_and_more'),
    ]

    operations = [
        migrations.AlterModelTable(
            name='admin',
            table='ADMINS',
        ),
        migrations.AlterModelTable(
            name='cointransaction',
            table='COIN_TRANSACTIONS',
        ),
        migrations.AlterModelTable(
            name='user',
            table='USERS',
        ),
    ]
