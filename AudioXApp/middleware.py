# AudioXApp/middleware.py

from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.conf import settings # Keep settings import

class ProfileCompletionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.
        self.exempt_url_names = ['AudioXApp:complete_profile', 'AudioXApp:logout', 'account_logout']
        self.admin_path_prefix = '/admin/' # Default Django admin path prefix

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Called just before Django calls the view.
        We'll do our redirect logic here.
        """
        if not request.user.is_authenticated:
            return None

        # Construct exempt URLs dynamically
        current_exempt_urls = []
        for name in self.exempt_url_names:
            try:
                current_exempt_urls.append(reverse(name))
            except NoReverseMatch:
                # This can happen if some allauth URLs are not used or named differently
                # You might want to log this for debugging if it's unexpected
                pass
        
        # Add admin path prefix
        # This assumes your admin is mounted at /admin/ as per your AudioXCore/urls.py
        current_exempt_urls.append(self.admin_path_prefix)


        # Also exempt static and media files
        if request.path.startswith(settings.STATIC_URL) or \
           (hasattr(settings, 'MEDIA_URL') and settings.MEDIA_URL and request.path.startswith(settings.MEDIA_URL)):
            return None

        for exempt_url_pattern in current_exempt_urls:
            if request.path.startswith(exempt_url_pattern):
                return None

        if request.session.get('profile_incomplete', False):
            next_url_after_completion = request.session.get('next_url_after_profile_completion')
            complete_profile_url = reverse('AudioXApp:complete_profile')
            
            # Prevent redirect loop if already on complete_profile page
            # This check is now implicitly handled by exempt_urls if complete_profile is in exempt_url_names
            # but an explicit check doesn't hurt if exempt_urls logic changes.
            if request.path == complete_profile_url:
                return None

            redirect_url_target = complete_profile_url
            if next_url_after_completion and next_url_after_completion != complete_profile_url:
                redirect_url_target = f"{complete_profile_url}?next={next_url_after_completion}"
            
            return redirect(redirect_url_target)

        return None
