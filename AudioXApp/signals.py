# AudioXApp/signals.py

from django.dispatch import receiver
from django.urls import reverse
from django.conf import settings
from allauth.account.signals import user_logged_in
from allauth.socialaccount.signals import social_account_added
from .models import User

# --- Profile Completion Signal Handlers ---

def needs_profile_completion(user):
    if not hasattr(user, 'full_name') or not user.full_name or not user.full_name.strip():
        return True
    if not hasattr(user, 'phone_number') or not user.phone_number:
        return True
    return False

@receiver(user_logged_in)
def handle_user_logged_in(sender, request, user, **kwargs):
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