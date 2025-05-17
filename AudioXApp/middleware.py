# AudioXApp/middleware.py

from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.conf import settings

class ProfileCompletionMiddleware:
    """
    Middleware to redirect users to profile completion page if their profile is incomplete.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        # URL names that are exempt from the profile completion check
        self.exempt_url_names = ['AudioXApp:complete_profile', 'AudioXApp:logout', 'account_logout']
        # Default Django admin path prefix
        self.admin_path_prefix = '/admin/'

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Called just before Django calls the view.
        Handles the profile completion redirect logic.
        """
        # If the user is not authenticated, no need to check profile completion
        if not request.user.is_authenticated:
            return None

        # Dynamically construct list of exempt URLs
        current_exempt_urls = []
        for name in self.exempt_url_names:
            try:
                current_exempt_urls.append(reverse(name))
            except NoReverseMatch:
                # Handle cases where a URL name might not be found
                pass

        # Add the Django admin path prefix to exempt URLs
        current_exempt_urls.append(self.admin_path_prefix)

        # Also exempt static and media files
        if request.path.startswith(settings.STATIC_URL) or \
           (hasattr(settings, 'MEDIA_URL') and settings.MEDIA_URL and request.path.startswith(settings.MEDIA_URL)):
            return None

        # Check if the current path starts with any of the exempt URLs
        for exempt_url_pattern in current_exempt_urls:
            if request.path.startswith(exempt_url_pattern):
                return None

        # Check if the profile_incomplete flag is set in the session
        if request.session.get('profile_incomplete', False):
            complete_profile_url = reverse('AudioXApp:complete_profile')

            # Prevent redirection if the user is already on the complete profile page
            if request.path == complete_profile_url:
                return None

            # Get the URL to redirect to after profile completion
            next_url_after_completion = request.session.get('next_url_after_profile_completion')

            # Determine the target URL for the redirect
            redirect_url_target = complete_profile_url
            if next_url_after_completion and next_url_after_completion != complete_profile_url:
                # Append the 'next' parameter to the complete profile URL
                redirect_url_target = f"{complete_profile_url}?next={next_url_after_completion}"

            # Redirect the user to the profile completion page
            return redirect(redirect_url_target)

        # If profile is complete or not authenticated/exempt, proceed as normal
        return None
