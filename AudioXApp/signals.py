# AudioXApp/signals.py

from django.dispatch import receiver
from django.urls import reverse
from django.conf import settings

# For allauth signals
from allauth.account.signals import user_logged_in
from allauth.socialaccount.signals import pre_social_login, social_account_added, social_account_updated

# It's better to use a middleware to handle the actual redirect
# after login, as signals (especially user_logged_in) might not be the
# most reliable place to issue a redirect directly due to how the request-response
# cycle is handled.
# However, we can use the signal to set a flag in the session.

def needs_profile_completion(user):
    """
    Checks if the user needs to complete their profile.
    Returns True if full_name is missing or phone_number is incomplete.
    """
    if not user.full_name or not user.full_name.strip():
        return True
    if not user.phone_number or not (user.phone_number.startswith('+92') and len(user.phone_number) == 13):
        return True
    return False

@receiver(user_logged_in)
def handle_user_logged_in(sender, request, user, **kwargs):
    """
    Signal receiver for when a user logs in (either normally or via social).
    Sets a session flag if the profile needs completion.
    """
    # The actual redirect will be handled by a middleware to ensure it happens
    # at the right point in the request-response cycle.
    if needs_profile_completion(user):
        # Store the intended destination to redirect after profile completion
        # Get the 'next' parameter from the login URL if it exists
        next_url = request.GET.get('next')
        if not next_url:
            # If no 'next' param, try to get it from where allauth might store it
            # For social logins, allauth might store the original destination
            # This part can be tricky and might need adjustment based on allauth's exact behavior
            # For now, we'll try to get it from a common session key or default to home
            next_url = request.session.get('socialaccount_login_redirect_url') or \
                       request.session.get('account_login_redirect_url') # Check allauth's session keys

        if next_url:
            request.session['next_url_after_profile_completion'] = next_url
        else:
            # Default to home if no specific next URL is found
            request.session['next_url_after_profile_completion'] = reverse('AudioXApp:home')
        
        request.session['profile_incomplete'] = True
        # The middleware will check request.session['profile_incomplete']
        # and request.session['next_url_after_profile_completion']
    else:
        # Ensure flags are cleared if profile is complete
        if 'profile_incomplete' in request.session:
            del request.session['profile_incomplete']
        if 'next_url_after_profile_completion' in request.session:
            del request.session['next_url_after_profile_completion']


# You might also want to check on social_account_added if you allow
# connecting social accounts to an existing, already logged-in user.
@receiver(social_account_added)
def handle_social_account_added(request, sociallogin, **kwargs):
    """
    Called when a social account is connected to an existing user.
    """
    user = sociallogin.user
    # If the user was already logged in and just added a social account,
    # we might still want to check if their profile needs completion.
    # The user_logged_in signal might not fire in this specific scenario
    # if they were already authenticated.
    if needs_profile_completion(user):
        # Similar logic as user_logged_in to set session flags
        next_url = request.GET.get('next')
        if next_url:
            request.session['next_url_after_profile_completion'] = next_url
        else:
            request.session['next_url_after_profile_completion'] = reverse('AudioXApp:home')
        request.session['profile_incomplete'] = True
    else:
        if 'profile_incomplete' in request.session:
            del request.session['profile_incomplete']
        if 'next_url_after_profile_completion' in request.session:
            del request.session['next_url_after_profile_completion']

# Note: The actual redirection will be handled by a middleware.
# This signal handler just sets session flags.
