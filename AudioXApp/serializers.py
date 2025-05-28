# AudioXApp/serializers.py

from rest_framework import serializers
from django.urls import reverse # For generating URLs if needed, though direct construction is used in views for simplicity

from .models import (
    Audiobook,
    Chapter,
    UserDownloadedAudiobook,
    User # Assuming settings.AUTH_USER_MODEL refers to this
)

class UserSimpleSerializer(serializers.ModelSerializer):
    """
    A simple serializer for basic User information.
    """
    class Meta:
        model = User
        fields = ['user_id', 'username', 'full_name']


class AudiobookSimpleSerializer(serializers.ModelSerializer):
    """
    Serializer for listing audiobooks with essential details for download eligibility.
    Used by DownloadableAudiobooksListView.
    """
    cover_image_url = serializers.SerializerMethodField()
    # You could add more fields like average_rating, creator_name, etc.

    class Meta:
        model = Audiobook
        fields = [
            'audiobook_id',
            'title',
            'author',
            'narrator',
            'slug',
            'cover_image_url',
            'is_paid',
            'price',
            'duration', # DurationField
            'language',
            'genre',
            # 'status', # If relevant for the client to know
        ]
        read_only_fields = fields # Typically these are read-only in a listing

    def get_cover_image_url(self, obj):
        request = self.context.get('request')
        if obj.cover_image and hasattr(obj.cover_image, 'url'):
            if request:
                return request.build_absolute_uri(obj.cover_image.url)
            return obj.cover_image.url # Fallback if no request in context
        return None


class ChapterDownloadInfoSerializer(serializers.ModelSerializer):
    """
    Serializer for providing chapter details including its specific download URL.
    Used by AudiobookDownloadInfoView.
    """
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Chapter
        fields = [
            'chapter_id',
            'chapter_name',
            'chapter_order',
            'is_preview_eligible',
            # 'duration_display', # If you have a method for this on the Chapter model
            'download_url',
        ]
        read_only_fields = fields

    def get_download_url(self, obj):
        request = self.context.get('request')
        # Construct the URL to the ServeChapterAudioFileView
        # It's generally better to use reverse if your URL patterns are named,
        # but direct construction is also common if the pattern is stable.
        # Example using reverse (assuming your URL is named 'serve_chapter_audio_file'):
        # try:
        #     path = reverse('AudioXApp:serve_chapter_audio_file', kwargs={'chapter_id': obj.chapter_id})
        # except NoReverseMatch:
        #     # Fallback or log error
        #     path = f'/api/v1/chapters/{obj.chapter_id}/serve-file/' # Fallback
        
        # Direct construction as used in the view placeholder:
        path = f'/api/v1/chapters/{obj.chapter_id}/serve-file/'

        if request:
            return request.build_absolute_uri(path)
        return path # Return relative path if no request context


class AudiobookDownloadDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed audiobook information when requesting download info,
    including a list of chapters with their download info.
    """
    chapters = ChapterDownloadInfoSerializer(many=True, read_only=True)
    cover_image_url = serializers.SerializerMethodField()
    download_record_id = serializers.UUIDField(source='user_downloads.first.download_id', read_only=True, allow_null=True) # Example to get from related

    class Meta:
        model = Audiobook
        fields = [
            'audiobook_id',
            'title',
            'author',
            'narrator',
            'slug',
            'description',
            'cover_image_url',
            'is_paid',
            'price',
            'duration',
            'chapters', # Nested list of chapters
            'download_record_id', # If you want to include the ID of the UserDownloadedAudiobook record
        ]
        read_only_fields = fields

    def get_cover_image_url(self, obj):
        request = self.context.get('request')
        if obj.cover_image and hasattr(obj.cover_image, 'url'):
            if request:
                return request.build_absolute_uri(obj.cover_image.url)
            return obj.cover_image.url
        return None
    
    def to_representation(self, instance):
        """
        Custom representation to add download_record_id if available in context.
        This is an alternative to using 'source' if the relation is more complex
        or if the record is passed directly via context.
        """
        representation = super().to_representation(instance)
        download_record = self.context.get('download_record')
        if download_record:
            representation['download_record_id'] = download_record.download_id
        elif 'download_record_id' in self.context : # If passed directly
             representation['download_record_id'] = self.context.get('download_record_id')

        # If you want to get the download_record_id via a reverse relation from Audiobook to UserDownloadedAudiobook
        # (assuming a user is also in context for filtering the correct download record)
        # user = self.context.get('request').user if self.context.get('request') else None
        # if user:
        #     try:
        #         # This assumes UserDownloadedAudiobook has a ForeignKey to Audiobook named 'audiobook'
        #         # and a ForeignKey to User named 'user'.
        #         download_instance = UserDownloadedAudiobook.objects.filter(audiobook=instance, user=user).first()
        #         if download_instance:
        #             representation['download_record_id'] = download_instance.download_id
        #     except UserDownloadedAudiobook.DoesNotExist:
        #         pass # No download record for this user and audiobook
        return representation


class UserDownloadedAudiobookSerializer(serializers.ModelSerializer):
    """
    Serializer for the UserDownloadedAudiobook model.
    Used by ConfirmAudiobookDownloadedView.
    """
    user = UserSimpleSerializer(read_only=True) # Nested user info
    audiobook = AudiobookSimpleSerializer(read_only=True) # Nested audiobook info
    # Or just audiobook_id if you prefer not to nest the full simple serializer:
    # audiobook_id = serializers.PrimaryKeyRelatedField(queryset=Audiobook.objects.all(), source='audiobook')


    class Meta:
        model = UserDownloadedAudiobook
        fields = [
            'download_id',
            'user',
            'audiobook', # or 'audiobook_id'
            'download_date',
            'expiry_date',
            'is_active',
            'last_verified_at',
        ]
        read_only_fields = ['download_id', 'user', 'audiobook', 'download_date', 'last_verified_at']
        # 'expiry_date' and 'is_active' might be updatable by admin actions later,
        # but for user confirmation, these are usually set by the server.

    def to_representation(self, instance):
        """
        Ensure dates are in a consistent format (e.g., ISO 8601).
        ModelSerializer usually handles this well for DateTimeFields, but explicit formatting can be added.
        """
        representation = super().to_representation(instance)
        if instance.download_date:
            representation['download_date'] = instance.download_date.isoformat()
        if instance.expiry_date:
            representation['expiry_date'] = instance.expiry_date.isoformat()
        if instance.last_verified_at:
            representation['last_verified_at'] = instance.last_verified_at.isoformat()
        return representation

