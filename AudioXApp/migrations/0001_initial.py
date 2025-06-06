# Generated by Django 4.2.19 on 2025-05-26 10:33

import AudioXApp.models
from decimal import Decimal
from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Admin',
            fields=[
                ('adminid', models.AutoField(primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('username', models.CharField(max_length=255, unique=True)),
                ('password', models.CharField(max_length=128)),
                ('roles', models.CharField(help_text='Comma-separated list of roles', max_length=512)),
                ('is_active', models.BooleanField(default=True)),
                ('last_login', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Custom Administrator',
                'verbose_name_plural': 'Custom Administrators',
                'db_table': 'ADMINS',
            },
        ),
        migrations.CreateModel(
            name='Audiobook',
            fields=[
                ('audiobook_id', models.AutoField(primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=255)),
                ('author', models.CharField(blank=True, max_length=255, null=True)),
                ('narrator', models.CharField(blank=True, max_length=255, null=True)),
                ('language', models.CharField(blank=True, max_length=100, null=True)),
                ('duration', models.DurationField(blank=True, help_text='Total duration of the audiobook. Calculated from chapters if possible.', null=True)),
                ('description', models.TextField(help_text='Detailed description of the audiobook.', null=True)),
                ('publish_date', models.DateTimeField(default=django.utils.timezone.now, help_text='Original publication date or date added to platform.')),
                ('genre', models.CharField(blank=True, max_length=100, null=True)),
                ('slug', models.SlugField(blank=True, help_text='URL-friendly identifier, auto-generated from title.', max_length=255, unique=True)),
                ('cover_image', models.ImageField(blank=True, null=True, upload_to='audiobook_covers/')),
                ('status', models.CharField(choices=[('PUBLISHED', 'Published'), ('INACTIVE', 'Inactive'), ('REJECTED', 'Rejected by Admin'), ('PAUSED_BY_ADMIN', 'Paused by Admin')], db_index=True, default='PUBLISHED', help_text='The current status of the audiobook.', max_length=20)),
                ('source', models.CharField(choices=[('creator', 'Creator Upload'), ('librivox', 'LibriVox'), ('archive', 'Archive.org')], db_index=True, default='creator', help_text='Source of the audiobook (Creator, LibriVox, Archive.org)', max_length=10)),
                ('total_views', models.PositiveIntegerField(default=0, help_text='Total number of times the audiobook detail page has been viewed.')),
                ('is_paid', models.BooleanField(default=False, help_text='Is this audiobook paid or free?')),
                ('price', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Price in PKR if the audiobook is paid (set to 0.00 if free).', max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))])),
                ('total_sales', models.PositiveIntegerField(default=0, help_text='Number of times this audiobook has been sold (for paid books).')),
                ('total_revenue_generated', models.DecimalField(decimal_places=2, default=0.0, help_text='Total gross revenue generated by this audiobook before platform fees.', max_digits=12)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, help_text='Timestamp when the audiobook record was created.')),
                ('updated_at', models.DateTimeField(auto_now=True, help_text='Timestamp when the audiobook record was last updated.')),
                ('is_creator_book', models.BooleanField(default=True, help_text='True if uploaded by a platform creator, False if a placeholder for an external book (e.g., for reviews only).')),
            ],
            options={
                'db_table': 'AUDIOBOOKS',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='AudiobookPurchase',
            fields=[
                ('purchase_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('purchase_date', models.DateTimeField(auto_now_add=True)),
                ('amount_paid', models.DecimalField(decimal_places=2, help_text='Total amount paid by the user in PKR.', max_digits=10)),
                ('platform_fee_percentage', models.DecimalField(decimal_places=2, default=Decimal('10.00'), help_text='Platform fee percentage at the time of purchase.', max_digits=5)),
                ('platform_fee_amount', models.DecimalField(decimal_places=2, help_text='Calculated platform fee in PKR.', max_digits=10)),
                ('creator_share_amount', models.DecimalField(decimal_places=2, help_text='Amount credited to the creator in PKR.', max_digits=10)),
                ('stripe_checkout_session_id', models.CharField(blank=True, db_index=True, help_text='Stripe Checkout Session ID for reference.', max_length=255, null=True)),
                ('stripe_payment_intent_id', models.CharField(blank=True, db_index=True, help_text='Stripe Payment Intent ID for reference.', max_length=255, null=True)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed'), ('REFUNDED', 'Refunded')], default='PENDING', max_length=10)),
                ('audiobook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='audiobook_sales', to='AudioXApp.audiobook')),
            ],
            options={
                'verbose_name': 'Audiobook Purchase',
                'verbose_name_plural': 'Audiobook Purchases',
                'db_table': 'AUDIOBOOK_PURCHASES',
                'ordering': ['-purchase_date'],
            },
        ),
        migrations.CreateModel(
            name='Chapter',
            fields=[
                ('chapter_id', models.AutoField(primary_key=True, serialize=False)),
                ('chapter_name', models.CharField(max_length=255)),
                ('chapter_order', models.PositiveIntegerField(help_text='Order of the chapter within the audiobook (e.g., 1, 2, 3).')),
                ('audio_file', models.FileField(blank=True, help_text='Audio file for the chapter.', null=True, upload_to='chapters_audio/')),
                ('text_content', models.TextField(blank=True, help_text='Text content for this chapter (e.g., for TTS generation or display).', null=True)),
                ('is_tts_generated', models.BooleanField(default=False, help_text="True if this chapter's audio was generated using Text-to-Speech.")),
                ('tts_voice_id', models.CharField(blank=True, choices=[('ali_narrator', 'Ali Narrator (Male PK)'), ('aisha_narrator', 'Aisha Narrator (Female PK)')], default=None, help_text='Voice used if audio was generated by TTS.', max_length=50, null=True)),
                ('is_preview_eligible', models.BooleanField(default=False, help_text='Can this chapter be previewed by premium users if the book is paid but not purchased?')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, help_text='Timestamp when the chapter was added.')),
                ('updated_at', models.DateTimeField(auto_now=True, help_text='Timestamp when the chapter was last updated.')),
                ('audiobook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chapters', to='AudioXApp.audiobook')),
            ],
            options={
                'db_table': 'CHAPTERS',
                'ordering': ['audiobook', 'chapter_order'],
                'unique_together': {('audiobook', 'chapter_order')},
            },
        ),
        migrations.CreateModel(
            name='Ticket',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ticket_display_id', models.CharField(editable=False, help_text='User-friendly ticket ID, e.g., AXT-1001', max_length=20, unique=True)),
                ('subject', models.CharField(max_length=255, verbose_name='Subject')),
                ('description', models.TextField(verbose_name='Description')),
                ('status', models.CharField(choices=[('OPEN', 'Open'), ('PROCESSING', 'Processing'), ('AWAITING_USER', 'Awaiting User Response'), ('RESOLVED', 'Resolved'), ('CLOSED', 'Closed'), ('REOPENED', 'Reopened')], default='OPEN', max_length=20, verbose_name='Status')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last Updated At')),
                ('resolved_at', models.DateTimeField(blank=True, help_text='Timestamp when the ticket was first marked as resolved.', null=True, verbose_name='Resolved At')),
                ('closed_at', models.DateTimeField(blank=True, help_text='Timestamp when the ticket was finally closed (e.g., after a resolved period).', null=True, verbose_name='Closed At')),
                ('assigned_admin_identifier', models.CharField(blank=True, help_text='Identifier (e.g., username or ID) of the admin handling the ticket from your custom Admin system.', max_length=255, null=True, verbose_name='Assigned Admin Identifier')),
            ],
            options={
                'verbose_name': 'Support Ticket',
                'verbose_name_plural': 'Support Tickets',
                'db_table': 'SUPPORT_TICKETS',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='TicketCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('is_creator_specific', models.BooleanField(default=False, help_text='Is this category primarily for creators?')),
            ],
            options={
                'verbose_name': 'Ticket Category',
                'verbose_name_plural': 'Ticket Categories',
                'db_table': 'TICKET_CATEGORIES',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='UserLibraryItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('audiobook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='saved_by_users', to='AudioXApp.audiobook')),
            ],
            options={
                'verbose_name': 'User Library Item',
                'verbose_name_plural': 'User Library Items',
                'db_table': 'USER_LIBRARY_ITEMS',
                'ordering': ['-added_at'],
            },
        ),
        migrations.CreateModel(
            name='WithdrawalAccount',
            fields=[
                ('account_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('account_type', models.CharField(choices=[('bank', 'Bank Account'), ('jazzcash', 'JazzCash'), ('easypaisa', 'Easypaisa'), ('nayapay', 'Nayapay'), ('upaisa', 'Upaisa')], max_length=20)),
                ('account_title', models.CharField(help_text='Full name registered with the account.', max_length=100)),
                ('account_identifier', models.CharField(help_text='Account Number (JazzCash/Easypaisa/Nayapay/Upaisa) or IBAN (Bank Account).', max_length=34)),
                ('bank_name', models.CharField(blank=True, help_text="Required only if Account Type is 'Bank Account'.", max_length=100, null=True)),
                ('is_primary', models.BooleanField(default=False, help_text='Mark one account as primary for withdrawals.')),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(blank=True, help_text='Timestamp when this account was last used for a withdrawal.', null=True)),
            ],
            options={
                'db_table': 'WITHDRAWAL_ACCOUNTS',
                'ordering': ['creator', '-added_at'],
            },
        ),
        migrations.CreateModel(
            name='User',
            fields=[
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('user_id', models.BigAutoField(primary_key=True, serialize=False)),
                ('full_name', models.CharField(max_length=255)),
                ('username', models.CharField(max_length=255, unique=True)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('phone_number', models.CharField(default='', max_length=20)),
                ('bio', models.TextField(default='')),
                ('profile_pic', models.ImageField(blank=True, null=True, upload_to='profile_pics/')),
                ('subscription_type', models.CharField(choices=[('FR', 'Free'), ('PR', 'Premium')], default='FR', max_length=2)),
                ('coins', models.IntegerField(default=0)),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.')),
                ('is_staff', models.BooleanField(default=False)),
                ('is_superuser', models.BooleanField(default=False)),
                ('date_joined', models.DateTimeField(auto_now_add=True)),
                ('is_2fa_enabled', models.BooleanField(default=False, verbose_name='2FA Enabled')),
                ('is_banned_by_admin', models.BooleanField(default=False, help_text='Set to true if the user is banned from the entire platform by an admin.')),
                ('platform_ban_reason', models.TextField(blank=True, help_text='Reason provided by admin if the user is banned from the platform.', null=True)),
                ('platform_banned_at', models.DateTimeField(blank=True, help_text='Timestamp when the user was banned from the platform.', null=True)),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.group', verbose_name='groups')),
                ('library_audiobooks', models.ManyToManyField(blank=True, related_name='saved_in_libraries', through='AudioXApp.UserLibraryItem', to='AudioXApp.audiobook')),
                ('platform_banned_by', models.ForeignKey(blank=True, help_text='Admin who banned this user from the platform.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='platform_banned_users', to='AudioXApp.admin')),
                ('purchased_audiobooks', models.ManyToManyField(related_name='purchased_by_users', through='AudioXApp.AudiobookPurchase', to='AudioXApp.audiobook')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.permission', verbose_name='user permissions')),
            ],
            options={
                'db_table': 'USERS',
            },
        ),
        migrations.CreateModel(
            name='Creator',
            fields=[
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='creator_profile', serialize=False, to=settings.AUTH_USER_MODEL)),
                ('cid', models.CharField(blank=True, db_index=True, help_text='Unique Creator ID, generated upon approval.', max_length=100, null=True, unique=True)),
                ('creator_name', models.CharField(help_text='Public display name for the creator', max_length=100)),
                ('creator_unique_name', models.CharField(help_text='Unique handle (@yourname) for URLs and mentions', max_length=50, unique=True, validators=[django.core.validators.RegexValidator(code='invalid_creator_unique_name', message='Unique name can only contain letters, numbers, and underscores.', regex='^[a-zA-Z0-9_]+$')])),
                ('creator_profile_pic', models.ImageField(blank=True, help_text='Optional: Specific profile picture for the creator page.', null=True, upload_to=AudioXApp.models.creator_profile_pic_path)),
                ('total_earning', models.DecimalField(decimal_places=2, default=0.0, help_text='Total gross earnings from sales before platform fees.', max_digits=12)),
                ('available_balance', models.DecimalField(decimal_places=2, default=0.0, help_text='Net earnings available for withdrawal after platform fees.', max_digits=12)),
                ('cnic_front', models.ImageField(help_text='Front side of CNIC', null=True, upload_to=AudioXApp.models.creator_cnic_path)),
                ('cnic_back', models.ImageField(help_text='Back side of CNIC', null=True, upload_to=AudioXApp.models.creator_cnic_path)),
                ('verification_status', models.CharField(choices=[('pending', 'Pending Verification'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=10)),
                ('terms_accepted_at', models.DateTimeField(blank=True, help_text='Timestamp when creator terms were accepted during the last application', null=True)),
                ('is_banned', models.BooleanField(db_index=True, default=False, help_text='Is this creator currently banned?')),
                ('ban_reason', models.TextField(blank=True, help_text='Reason provided by admin if creator is banned.', null=True)),
                ('banned_at', models.DateTimeField(blank=True, help_text='Timestamp when the creator was banned.', null=True)),
                ('rejection_reason', models.TextField(blank=True, help_text='Reason provided by admin if the LATEST application is rejected', null=True)),
                ('last_application_date', models.DateTimeField(blank=True, help_text='Timestamp of the most recent application submission', null=True)),
                ('application_attempts_current_month', models.PositiveIntegerField(default=0, help_text='Number of applications submitted in the current cycle (resets monthly based on last_application_date)')),
                ('approved_at', models.DateTimeField(blank=True, help_text='Timestamp when the application was approved.', null=True)),
                ('attempts_at_approval', models.PositiveIntegerField(blank=True, help_text='Number of attempts made when this application was approved.', null=True)),
                ('welcome_popup_shown', models.BooleanField(default=False, help_text="Has the 'Welcome Creator' popup been shown?")),
                ('rejection_popup_shown', models.BooleanField(default=False, help_text="Has the 'Application Rejected' popup been shown?")),
                ('admin_notes', models.TextField(blank=True, help_text='Internal notes for admins regarding this creator.', null=True)),
                ('last_name_change_date', models.DateTimeField(blank=True, help_text='Timestamp of the last display name change.', null=True)),
                ('last_unique_name_change_date', models.DateTimeField(blank=True, help_text='Timestamp of the last unique name (@handle) change.', null=True)),
                ('last_withdrawal_request_date', models.DateTimeField(blank=True, help_text='Timestamp of the last non-cancelled withdrawal request.', null=True)),
                ('profile_pic_updated_at', models.DateTimeField(blank=True, help_text='Timestamp of the last profile picture update.', null=True)),
                ('approved_by', models.ForeignKey(blank=True, help_text='Admin who approved this application.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_creators', to='AudioXApp.admin')),
                ('banned_by', models.ForeignKey(blank=True, help_text='Admin who banned this creator.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='banned_creators', to='AudioXApp.admin')),
            ],
            options={
                'db_table': 'CREATORS',
            },
        ),
        migrations.AddField(
            model_name='userlibraryitem',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='library_items', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='TicketMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('message', models.TextField(verbose_name='Message')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('is_admin_reply', models.BooleanField(default=False, help_text='True if this message is from an admin/support agent.', verbose_name='Is Admin Reply')),
                ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='AudioXApp.ticket', verbose_name='Ticket')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ticket_messages', to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
            options={
                'verbose_name': 'Support Ticket Message',
                'verbose_name_plural': 'Support Ticket Messages',
                'db_table': 'SUPPORT_TICKET_MESSAGES',
                'ordering': ['created_at'],
            },
        ),
        migrations.AddField(
            model_name='ticket',
            name='category',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tickets', to='AudioXApp.ticketcategory', verbose_name='Category'),
        ),
        migrations.AddField(
            model_name='ticket',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='support_tickets', to=settings.AUTH_USER_MODEL, verbose_name='User'),
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plan', models.CharField(choices=[('monthly', 'Monthly Premium'), ('annual', 'Annual Premium')], max_length=20)),
                ('start_date', models.DateTimeField()),
                ('end_date', models.DateTimeField(blank=True, help_text="End of the current billing cycle. For 'canceled' status, this is when access ends.", null=True)),
                ('status', models.CharField(choices=[('active', 'Active'), ('canceled', 'Canceled'), ('expired', 'Expired'), ('pending', 'Pending Payment'), ('failed', 'Payment Failed'), ('past_due', 'Past Due')], db_index=True, default='active', max_length=10)),
                ('stripe_subscription_id', models.CharField(blank=True, db_index=True, max_length=255, null=True)),
                ('stripe_customer_id', models.CharField(blank=True, db_index=True, max_length=255, null=True)),
                ('stripe_payment_method_brand', models.CharField(blank=True, help_text='e.g., visa, mastercard', max_length=50, null=True)),
                ('stripe_payment_method_last4', models.CharField(blank=True, help_text='Last 4 digits of the card', max_length=4, null=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='subscription', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'SUBSCRIPTIONS',
            },
        ),
        migrations.CreateModel(
            name='CoinTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_type', models.CharField(choices=[('purchase', 'Purchase'), ('reward', 'Reward'), ('spent', 'Spent'), ('refund', 'Refund'), ('gift_sent', 'Gift Sent'), ('gift_received', 'Gift Received'), ('withdrawal', 'Withdrawal'), ('withdrawal_fee', 'Withdrawal Fee')], max_length=15)),
                ('amount', models.IntegerField()),
                ('transaction_date', models.DateTimeField(auto_now_add=True)),
                ('status', models.CharField(choices=[('completed', 'Completed'), ('pending', 'Pending'), ('failed', 'Failed'), ('processing', 'Processing'), ('rejected', 'Rejected')], default='pending', max_length=10)),
                ('pack_name', models.CharField(blank=True, max_length=255, null=True)),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('recipient', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gifts_received', to=settings.AUTH_USER_MODEL)),
                ('sender', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gifts_sent', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coin_transactions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'COIN_TRANSACTIONS',
                'ordering': ['-transaction_date'],
            },
        ),
        migrations.AddField(
            model_name='audiobookpurchase',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='audiobook_purchases', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='WithdrawalRequest',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('old_request_id', models.CharField(blank=True, help_text='Legacy request ID, if applicable.', max_length=255, null=True)),
                ('amount', models.DecimalField(decimal_places=2, help_text='Amount requested for withdrawal in PKR', max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('status', models.CharField(choices=[('PENDING', 'Pending Approval'), ('PROCESSING', 'Processing Payment'), ('COMPLETED', 'Payment Completed'), ('REJECTED', 'Rejected by Admin'), ('FAILED', 'Payment Failed')], db_index=True, default='PENDING', max_length=25)),
                ('request_date', models.DateTimeField(auto_now_add=True)),
                ('processed_date', models.DateTimeField(blank=True, help_text='Timestamp when request was Approved or Rejected by admin', null=True)),
                ('admin_notes', models.TextField(blank=True, help_text='Reason for rejection, or other admin notes. Visible to creator.', null=True)),
                ('payment_slip', models.ImageField(blank=True, help_text='Payment slip uploaded by admin upon approval.', null=True, upload_to=AudioXApp.models.withdrawal_payment_slip_path)),
                ('payment_reference', models.CharField(blank=True, help_text='Payment transaction reference, if any.', max_length=255, null=True)),
                ('processed_by', models.ForeignKey(blank=True, help_text='Admin who last updated the status (approved/rejected/marked processing)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='processed_withdrawals', to='AudioXApp.admin')),
                ('withdrawal_account', models.ForeignKey(help_text='The account selected for this withdrawal request.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='withdrawal_requests', to='AudioXApp.withdrawalaccount')),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='withdrawal_requests', to='AudioXApp.creator')),
            ],
            options={
                'verbose_name': 'Withdrawal Request',
                'verbose_name_plural': 'Withdrawal Requests',
                'db_table': 'WITHDRAWAL_REQUESTS',
                'ordering': ['-request_date'],
            },
        ),
        migrations.AddField(
            model_name='withdrawalaccount',
            name='creator',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='withdrawal_accounts', to='AudioXApp.creator'),
        ),
        migrations.AlterUniqueTogether(
            name='userlibraryitem',
            unique_together={('user', 'audiobook')},
        ),
        migrations.AddField(
            model_name='ticket',
            name='creator_profile',
            field=models.ForeignKey(blank=True, help_text='Associated creator profile, if the user is a creator and the issue is creator-specific.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='creator_support_tickets', to='AudioXApp.creator', verbose_name='Creator Profile'),
        ),
        migrations.CreateModel(
            name='Review',
            fields=[
                ('review_id', models.AutoField(primary_key=True, serialize=False)),
                ('rating', models.PositiveIntegerField(help_text='Rating from 1 to 5 stars.', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('comment', models.TextField(blank=True, help_text="User's review comment (optional).", null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('audiobook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='AudioXApp.audiobook')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Audiobook Review',
                'verbose_name_plural': 'Audiobook Reviews',
                'db_table': 'REVIEWS',
                'ordering': ['-created_at'],
                'unique_together': {('audiobook', 'user')},
            },
        ),
        migrations.CreateModel(
            name='ListeningHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('progress_seconds', models.PositiveIntegerField(default=0, help_text='Timestamp in seconds where the user left off within the audiobook or current chapter.')),
                ('last_listened_at', models.DateTimeField(auto_now=True)),
                ('audiobook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='listening_sessions', to='AudioXApp.audiobook')),
                ('current_chapter', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='listening_markers', to='AudioXApp.chapter')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='listening_history', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Listening History',
                'verbose_name_plural': 'Listening Histories',
                'db_table': 'LISTENING_HISTORY',
                'ordering': ['-last_listened_at'],
                'unique_together': {('user', 'audiobook')},
            },
        ),
        migrations.CreateModel(
            name='CreatorEarning',
            fields=[
                ('earning_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('earning_type', models.CharField(choices=[('sale', 'Sale Earning'), ('view', 'View Earning'), ('bonus', 'Bonus'), ('adjustment', 'Adjustment')], db_index=True, default='sale', max_length=10)),
                ('amount_earned', models.DecimalField(decimal_places=2, help_text='Net amount earned by the creator for this transaction.', max_digits=10)),
                ('transaction_date', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('view_count_for_earning', models.PositiveIntegerField(blank=True, help_text="Number of views this earning entry represents, if type is 'view'.", null=True)),
                ('earning_per_view_at_transaction', models.DecimalField(blank=True, decimal_places=4, help_text="Earning rate per view at the time of this transaction, if type is 'view'.", max_digits=6, null=True)),
                ('notes', models.TextField(blank=True, help_text='Any notes related to this earning, e.g., reason for adjustment or bonus.', null=True)),
                ('audiobook_title_at_transaction', models.CharField(blank=True, help_text='Title of the audiobook at the time of the transaction (denormalized).', max_length=255, null=True)),
                ('audiobook', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='earning_entries', to='AudioXApp.audiobook')),
                ('purchase', models.OneToOneField(blank=True, help_text='Link to the specific purchase if this earning is from a sale.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='earning_record', to='AudioXApp.audiobookpurchase')),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='earnings_log', to='AudioXApp.creator')),
            ],
            options={
                'verbose_name': 'Creator Earning',
                'verbose_name_plural': 'Creator Earnings',
                'db_table': 'CREATOR_EARNINGS',
                'ordering': ['-transaction_date'],
            },
        ),
        migrations.CreateModel(
            name='CreatorApplicationLog',
            fields=[
                ('log_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('application_date', models.DateTimeField(default=django.utils.timezone.now, help_text='Timestamp when this specific application was submitted')),
                ('attempt_number_monthly', models.PositiveIntegerField(help_text='Which attempt this was in the submission month (at the time of submission)')),
                ('creator_name_submitted', models.CharField(max_length=100)),
                ('creator_unique_name_submitted', models.CharField(max_length=50)),
                ('cnic_front_submitted', models.ImageField(blank=True, help_text='CNIC Front submitted for this attempt', null=True, upload_to=AudioXApp.models.creator_cnic_path)),
                ('cnic_back_submitted', models.ImageField(blank=True, help_text='CNIC Back submitted for this attempt', null=True, upload_to=AudioXApp.models.creator_cnic_path)),
                ('terms_accepted_at_submission', models.DateTimeField(help_text='Timestamp when terms were accepted for this submission')),
                ('status', models.CharField(choices=[('submitted', 'Submitted'), ('approved', 'Approved'), ('rejected', 'Rejected')], db_index=True, default='submitted', max_length=10)),
                ('processed_at', models.DateTimeField(blank=True, help_text='Timestamp when the application was approved or rejected', null=True)),
                ('rejection_reason', models.TextField(blank=True, help_text='Reason provided if this specific application was rejected', null=True)),
                ('processed_by', models.ForeignKey(blank=True, help_text='Admin who approved or rejected this specific application.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='processed_creator_applications', to='AudioXApp.admin')),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='application_logs', to='AudioXApp.creator')),
            ],
            options={
                'verbose_name': 'Creator Application Log',
                'verbose_name_plural': 'Creator Application Logs',
                'db_table': 'CREATOR_APPLICATION_LOGS',
                'ordering': ['creator', '-application_date'],
            },
        ),
        migrations.CreateModel(
            name='AudiobookViewLog',
            fields=[
                ('view_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('viewed_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('audiobook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='view_logs', to='AudioXApp.audiobook')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audiobook_views', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Audiobook View Log',
                'verbose_name_plural': 'Audiobook View Logs',
                'db_table': 'AUDIOBOOK_VIEW_LOGS',
                'ordering': ['-viewed_at'],
                'indexes': [models.Index(fields=['audiobook', 'viewed_at'], name='AUDIOBOOK_V_audiobo_0ca16b_idx'), models.Index(fields=['user', 'audiobook', 'viewed_at'], name='AUDIOBOOK_V_user_id_182167_idx')],
            },
        ),
        migrations.AddConstraint(
            model_name='audiobookpurchase',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'COMPLETED')), fields=('user', 'audiobook'), name='unique_completed_purchase_per_user_audiobook'),
        ),
        migrations.AddField(
            model_name='audiobook',
            name='creator',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audiobooks', to='AudioXApp.creator'),
        ),
        migrations.AddConstraint(
            model_name='withdrawalaccount',
            constraint=models.UniqueConstraint(condition=models.Q(('is_primary', True)), fields=('creator',), name='unique_primary_withdrawal_account_per_creator'),
        ),
    ]
