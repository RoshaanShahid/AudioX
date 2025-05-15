# AudioXApp/signals.py

from django.dispatch import receiver
from django.urls import reverse
from django.conf import settings
import logging

# For allauth signals
from allauth.account.signals import user_logged_in
from allauth.socialaccount.signals import pre_social_login, social_account_added, social_account_updated

# Import User model if used in needs_profile_completion
from .models import User 

logger = logging.getLogger(__name__)

# --- Google Cloud Speech-to-Text (STT) Setup REMOVED ---
# No longer importing google.cloud.speech or Chapter for STT purposes here.

# --- Allauth Signal Handlers (Profile Completion Logic) ---

def needs_profile_completion(user):
    """
    Checks if the user needs to complete their profile.
    Returns True if full_name is missing or phone_number is incomplete.
    Adjust logic based on your User model's actual fields and requirements.
    """
    if not hasattr(user, 'full_name') or not user.full_name or not user.full_name.strip():
        logger.debug(f"User {user.email} needs profile completion: full_name missing.")
        return True
    if not hasattr(user, 'phone_number') or not user.phone_number: 
        logger.debug(f"User {user.email} needs profile completion: phone_number missing.")
        return True
    return False

@receiver(user_logged_in)
def handle_user_logged_in(sender, request, user, **kwargs):
    """
    Signal receiver for when a user logs in (either normally or via social).
    Sets a session flag if the profile needs completion.
    """
    logger.debug(f"User {user.email} logged in. Checking profile completion status.")
    if needs_profile_completion(user):
        next_url = request.GET.get('next')
        if not next_url:
            next_url = request.session.get('socialaccount_login_redirect_url') or \
                       request.session.get('account_login_redirect_url')

        request.session['next_url_after_profile_completion'] = next_url or reverse('AudioXApp:home')
        request.session['profile_incomplete'] = True
        logger.info(f"User {user.email} profile marked as incomplete. Next URL after completion: {request.session['next_url_after_profile_completion']}")
    else:
        if 'profile_incomplete' in request.session:
            del request.session['profile_incomplete']
        if 'next_url_after_profile_completion' in request.session:
            del request.session['next_url_after_profile_completion']
        logger.debug(f"User {user.email} profile is complete.")

@receiver(social_account_added)
def handle_social_account_added(request, sociallogin, **kwargs):
    """
    Called when a social account is connected to an existing user.
    """
    user = sociallogin.user
    logger.debug(f"Social account added for user {user.email}. Checking profile completion status.")
    if needs_profile_completion(user):
        next_url = request.GET.get('next') 
        request.session['next_url_after_profile_completion'] = next_url or reverse('AudioXApp:home')
        request.session['profile_incomplete'] = True
        logger.info(f"User {user.email} (after social account added) profile marked as incomplete. Next URL: {request.session['next_url_after_profile_completion']}")
    else:
        if 'profile_incomplete' in request.session:
            del request.session['profile_incomplete']
        if 'next_url_after_profile_completion' in request.session:
            del request.session['next_url_after_profile_completion']
        logger.debug(f"User {user.email} (after social account added) profile is complete.")

# --- Speech-to-Text (STT) Signal Handler REMOVED ---
# The @receiver(post_save, sender=Chapter) and 
# transcribe_audio_on_chapter_save function have been removed.

