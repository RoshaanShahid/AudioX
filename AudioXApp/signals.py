# AudioXApp/signals.py

from django.dispatch import receiver
from django.urls import reverse
from django.conf import settings

# For allauth signals
from allauth.account.signals import user_logged_in
from allauth.socialaccount.signals import social_account_added

# Import User model
from .models import User

# --- Profile Completion Logic ---

def needs_profile_completion(user):
    """
    Checks if the user needs to complete their profile.
    Returns True if full_name or phone_number is missing/empty.
    """
    if not hasattr(user, 'full_name') or not user.full_name or not user.full_name.strip():
        return True
    if not hasattr(user, 'phone_number') or not user.phone_number:
        return True
    return False

# --- Allauth Signal Handlers ---

@receiver(user_logged_in)
def handle_user_logged_in(sender, request, user, **kwargs):
    """
    Signal receiver for user login.
    Sets a session flag if the profile needs completion and stores the next URL.
    """
    if needs_profile_completion(user):
        next_url = request.GET.get('next')
        if not next_url:
            next_url = request.session.get('socialaccount_login_redirect_url') or \
                       request.session.get('account_login_redirect_url')

        request.session['next_url_after_profile_completion'] = next_url or reverse('AudioXApp:home')
        request.session['profile_incomplete'] = True
    else:
        if 'profile_incomplete' in request.session:
            del request.session['profile_incomplete']
        if 'next_url_after_profile_completion' in request.session:
            del request.session['next_url_after_profile_completion']


@receiver(social_account_added)
def handle_social_account_added(request, sociallogin, **kwargs):
    """
    Called when a social account is connected to an existing user.
    Checks profile completion and sets session flags if needed.
    """
    user = sociallogin.user
    if needs_profile_completion(user):
        next_url = request.GET.get('next')
        request.session['next_url_after_profile_completion'] = next_url or reverse('AudioXApp:home')
        request.session['profile_incomplete'] = True
    else:
        if 'profile_incomplete' in request.session:
            del request.session['profile_incomplete']
        if 'next_url_after_profile_completion' in request.session:
            del request.session['next_url_after_profile_completion']

