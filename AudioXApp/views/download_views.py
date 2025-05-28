# AudioXApp/views/download_views.py

import logging 
import os

from django.shortcuts import get_object_or_404
from django.http import FileResponse, Http404
from django.utils import timezone
from django.conf import settings # For potential settings like download expiry

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

# Initialize the logger for this module
logger = logging.getLogger(__name__) # <--- AND ADDED THIS LINE

# Import your models
from ..models import (
    User, # Assuming this is your settings.AUTH_USER_MODEL
    Audiobook,
    Chapter,
    AudiobookPurchase,
    Subscription,
    UserDownloadedAudiobook
)

# Import your serializers (you'll need to create these)
# from ..serializers import (
#     AudiobookSimpleSerializer, # For listing audiobooks
#     ChapterDownloadInfoSerializer, # For chapter details and download links
#     UserDownloadedAudiobookSerializer # For download status responses
# )

# --- Helper Functions ---

def user_can_download_audiobook(user, audiobook):
    """
    Checks if a user is eligible to download a specific audiobook.
    This is a crucial piece of logic you'll need to tailor to your platform's rules.
    """
    if not user or not user.is_authenticated:
        return False

    # Rule 1: User has purchased the audiobook
    if AudiobookPurchase.objects.filter(user=user, audiobook=audiobook, status='COMPLETED').exists():
        return True

    # Rule 2: User has an active premium subscription AND the audiobook is eligible for premium download
    # (You might need a field on Audiobook like `is_downloadable_for_premium`)
    try:
        if user.subscription_type == 'PR':
            user_subscription = getattr(user, 'subscription', None) # OneToOneField
            if user_subscription and user_subscription.is_active():
                # Add more conditions if needed, e.g.,
                # if audiobook.is_downloadable_for_premium:
                # For now, assume all audiobooks are downloadable by premium users if not purchased
                return True
    except Subscription.DoesNotExist:
        pass # User has 'PR' type but no subscription object, or subscription is not active
    except AttributeError: # If user object doesn't have 'subscription' or 'subscription_type' for some reason
        logger.warning(f"User {user.pk} missing subscription attributes while checking download rights.")
        pass


    # Rule 3: Audiobook is free and generally downloadable (if you have such a category)
    # if not audiobook.is_paid and audiobook.is_generally_downloadable:
    #     return True

    return False


# --- API Views ---

class DownloadableAudiobooksListView(APIView):
    """
    Lists all audiobooks that the authenticated user is eligible to download.
    GET /api/v1/audiobooks/downloadable/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        downloadable_audiobooks = []

        # Fetch all audiobooks or a relevant subset
        # For performance, you might want to filter further (e.g., only published audiobooks)
        all_audiobooks = Audiobook.objects.filter(status='PUBLISHED').prefetch_related(
            'audiobook_purchases', # For checking purchase status in user_can_download_audiobook
            # 'chapters' # If needed for serializer
        )

        for audiobook in all_audiobooks:
            if user_can_download_audiobook(user, audiobook):
                downloadable_audiobooks.append(audiobook)
        
        # You'll need an AudiobookSimpleSerializer or similar
        # For now, returning basic info. Replace with your serializer.
        # from ..serializers import AudiobookSimpleSerializer
        # serializer = AudiobookSimpleSerializer(downloadable_audiobooks, many=True, context={'request': request})
        # return Response(serializer.data)
        
        # Placeholder response until serializer is implemented
        data = [{
            "audiobook_id": ab.audiobook_id,
            "title": ab.title,
            "author": ab.author,
            "cover_image_url": request.build_absolute_uri(ab.cover_image.url) if ab.cover_image and hasattr(ab.cover_image, 'url') else None,
            "is_paid": ab.is_paid,
            "price": ab.price
        } for ab in downloadable_audiobooks]
        return Response(data, status=status.HTTP_200_OK)


class AudiobookDownloadInfoView(APIView):
    """
    Provides download information (chapter links) for a specific audiobook
    if the user is authorized.
    It also creates/updates a UserDownloadedAudiobook record to mark intent.
    GET /api/v1/audiobooks/<int:audiobook_id>/download-info/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, audiobook_id):
        user = request.user
        audiobook = get_object_or_404(Audiobook, pk=audiobook_id, status='PUBLISHED')

        if not user_can_download_audiobook(user, audiobook):
            return Response(
                {"detail": "You are not authorized to download this audiobook."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Create or update UserDownloadedAudiobook record to grant access to chapter files
        # This record indicates the user has initiated the download process for this book.
        download_record, created = UserDownloadedAudiobook.objects.update_or_create(
            user=user,
            audiobook=audiobook,
            defaults={
                'is_active': False, # Will be set to True upon client confirmation
                'last_verified_at': timezone.now(),
                # 'expiry_date': calculate_expiry_date_for_download(user, audiobook) # Implement this if downloads expire
            }
        )
        if created:
            download_record.download_date = timezone.now() # Set on creation
            # If expiry is needed, calculate it here
            # download_record.expiry_date = calculate_expiry_date_for_download(user, audiobook, settings)
            download_record.save()


        chapters = Chapter.objects.filter(audiobook=audiobook).order_by('chapter_order')
        
        # You'll need a ChapterDownloadInfoSerializer.
        # For now, returning basic info. Replace with your serializer.
        # from ..serializers import ChapterDownloadInfoSerializer
        # chapter_serializer = ChapterDownloadInfoSerializer(chapters, many=True, context={'request': request, 'audiobook_id': audiobook.audiobook_id})
        # data = {
        #     "audiobook_id": audiobook.audiobook_id,
        #     "title": audiobook.title,
        #     "chapters": chapter_serializer.data,
        #     "download_record_id": download_record.download_id
        # }
        # return Response(data)

        # Placeholder response until serializer is implemented
        chapter_data = []
        for chapter in chapters:
            # Constructing a relative path for the API URL is generally better
            # The client can then prepend its base API URL as needed.
            # Using reverse would be even better if you name your URL patterns.
            chapter_download_path = f'/api/v1/chapters/{chapter.chapter_id}/serve-file/'
            chapter_data.append({
                "chapter_id": chapter.chapter_id,
                "chapter_name": chapter.chapter_name,
                "chapter_order": chapter.chapter_order,
                "download_url": request.build_absolute_uri(chapter_download_path)
            })

        response_data = {
            "audiobook_id": audiobook.audiobook_id,
            "title": audiobook.title,
            "author": audiobook.author,
            "cover_image_url": request.build_absolute_uri(audiobook.cover_image.url) if audiobook.cover_image and hasattr(audiobook.cover_image, 'url') else None,
            "download_record_id": download_record.download_id, # UUID
            "chapters": chapter_data,
            "message": "Authorized. Use the chapter download URLs to fetch audio files."
        }
        return Response(response_data, status=status.HTTP_200_OK)


class ServeChapterAudioFileView(APIView):
    """
    Serves the audio file for a specific chapter.
    Requires the user to be authenticated and have an active download intent
    for the parent audiobook.
    GET /api/v1/chapters/<int:chapter_id>/serve-file/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, chapter_id):
        user = request.user
        chapter = get_object_or_404(Chapter.objects.select_related('audiobook'), pk=chapter_id)
        audiobook = chapter.audiobook

        # Verify that the user has an active (or pending client download) UserDownloadedAudiobook record
        # for this chapter's parent audiobook. This confirms they went through the download-info step.
        has_download_permission_record = UserDownloadedAudiobook.objects.filter(
            user=user,
            audiobook=audiobook
        ).exists()

        if not has_download_permission_record:
            # As a stricter alternative, always require the record from AudiobookDownloadInfoView.
            # If the record is missing, it means the proper flow wasn't followed.
            logger.warning(
                f"ServeChapterAudioFileView: User {user.username} attempted to download chapter {chapter_id} "
                f"for audiobook {audiobook.audiobook_id} without a prior download record."
            )
            return Response(
                {"detail": "Download permission not established. Please request download info for the audiobook first."},
                status=status.HTTP_403_FORBIDDEN
            )

        if not chapter.audio_file or not chapter.audio_file.name:
            logger.error(f"Audio file not found for chapter {chapter_id} (Audiobook: {audiobook.title}) in database record.")
            raise Http404("Audio file not found for this chapter.")

        try:
            # IMPORTANT: For production, use X-Sendfile/X-Accel-Redirect or pre-signed cloud URLs
            # Django serving files directly is not efficient for large files or high traffic.
            
            # Check if file exists on storage
            if not chapter.audio_file.storage.exists(chapter.audio_file.name):
                logger.error(f"Audio file for chapter {chapter_id} (Path: {chapter.audio_file.name}) not found on storage.")
                raise Http404("Audio file not found on server storage.")

            # Serve the file
            response = FileResponse(chapter.audio_file.open('rb'), as_attachment=True, filename=os.path.basename(chapter.audio_file.name))
            
            # Optionally, update last_verified_at on the download record here.
            # However, this might be better done periodically by the client or on app launch.
            # download_record = UserDownloadedAudiobook.objects.get(user=user, audiobook=audiobook)
            # download_record.last_verified_at = timezone.now()
            # download_record.save(update_fields=['last_verified_at'])

            return response
        except FileNotFoundError: # This might be redundant if storage.exists is used, but good as a fallback.
            logger.error(f"FileNotFoundError for chapter {chapter_id} (Path: {chapter.audio_file.name}) for user {user.username}.")
            raise Http404("Audio file physically not found on server.")
        except Exception as e:
            logger.error(f"Error serving chapter file {chapter_id} (Audiobook: {audiobook.title}) for user {user.username}: {e}", exc_info=True)
            return Response({"detail": "An error occurred while trying to serve the file."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConfirmAudiobookDownloadedView(APIView):
    """
    Client confirms that all intended parts of an audiobook have been successfully downloaded.
    Updates the UserDownloadedAudiobook record.
    POST /api/v1/audiobooks/<int:audiobook_id>/confirm-downloaded/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, audiobook_id):
        user = request.user
        audiobook = get_object_or_404(Audiobook, pk=audiobook_id)

        try:
            download_record = UserDownloadedAudiobook.objects.get(user=user, audiobook=audiobook)
        except UserDownloadedAudiobook.DoesNotExist:
            # This path implies the client is confirming a download for which no prior intent was recorded
            # or the record was somehow deleted. Re-check general rights.
            if not user_can_download_audiobook(user, audiobook):
                return Response(
                    {"detail": "No download record found, and you are not authorized to download this audiobook."},
                    status=status.HTTP_403_FORBIDDEN
                )
            # If authorized, create the record now.
            logger.info(f"ConfirmAudiobookDownloadedView: Creating new download record for user {user.username}, audiobook {audiobook_id} as none existed.")
            download_record = UserDownloadedAudiobook.objects.create(
                user=user,
                audiobook=audiobook,
                download_date=timezone.now(), # Set download date on creation
                is_active=True, # Activating directly as it's a confirmation
                last_verified_at=timezone.now(),
                # expiry_date=calculate_expiry_date_for_download(user, audiobook, settings) # If applicable
            )
        else:
            # Record exists, update it
            download_record.is_active = True
            download_record.last_verified_at = timezone.now()
            if not download_record.download_date: # Set download_date if it wasn't set (e.g., if created with defaults)
                 download_record.download_date = timezone.now()
            download_record.save(update_fields=['is_active', 'last_verified_at', 'download_date'])

        # from ..serializers import UserDownloadedAudiobookSerializer
        # serializer = UserDownloadedAudiobookSerializer(download_record)
        # return Response(serializer.data, status=status.HTTP_200_OK)

        # Placeholder response
        return Response({
            "message": "Audiobook download confirmed and activated.",
            "download_record_id": download_record.download_id, # UUID
            "audiobook_id": audiobook.audiobook_id,
            "is_active": download_record.is_active,
            "download_date": download_record.download_date.isoformat() if download_record.download_date else None,
            "last_verified_at": download_record.last_verified_at.isoformat() if download_record.last_verified_at else None,
        }, status=status.HTTP_200_OK)

# --- Helper function for expiry (example, to be defined properly or removed if not used) ---
# def calculate_expiry_date_for_download(user, audiobook, app_settings):
#     """
#     Example logic to calculate download expiry.
#     E.g., if subscription-based, might expire when subscription ends or after a fixed period.
#     """
#     # try:
#     #     if user.subscription_type == 'PR':
#     #         user_subscription = getattr(user, 'subscription', None)
#     #         if user_subscription and user_subscription.is_active() and user_subscription.end_date:
#     #             # Example: expiry tied to subscription end, or X days, whichever is sooner/later based on policy
#     #             fixed_period_expiry = timezone.now() + timedelta(days=getattr(app_settings, "DOWNLOAD_PREMIUM_EXPIRY_DAYS", 30))
#     #             return min(user_subscription.end_date, fixed_period_expiry) if user_subscription.end_date else fixed_period_expiry
#     # except Subscription.DoesNotExist:
#     #     pass
#     # except AttributeError:
#     #     pass # Should be logged if critical attributes are missing
#     #
#     # # For purchased items or general fallback
#     # default_expiry_days = getattr(app_settings, "DOWNLOAD_DEFAULT_EXPIRY_DAYS", None) # e.g., 365 or None for no expiry
#     # if default_expiry_days:
#     #     return timezone.now() + timedelta(days=default_expiry_days)
#     return None # No expiry by default