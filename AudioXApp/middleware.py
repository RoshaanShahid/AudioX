# AudioXApp/middleware.py

from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.conf import settings
from django.contrib.auth import logout # Import logout
from django.contrib import messages # Import messages

class ProfileCompletionMiddleware:
    """
    Middleware to redirect users to profile completion page if their profile is incomplete.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        # URL names that are exempt from the profile completion check
        self.exempt_url_names = ['AudioXApp:complete_profile', 'AudioXApp:logout', 'account_logout']
        # Default Django admin path prefix
        self.admin_path_prefix = '/admin/' # Standard Django admin, adjust if your custom admin has a different prefix
        self.django_admin_path_prefix = '/django-admin/'


    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Called just before Django calls the view.
        Handles the profile completion redirect logic.
        """
        if not request.user.is_authenticated:
            return None

        current_exempt_urls = []
        for name in self.exempt_url_names:
            try:
                current_exempt_urls.append(reverse(name))
            except NoReverseMatch:
                pass
        
        # Add path prefixes for admin areas
        current_exempt_urls.append(self.admin_path_prefix) # Your custom admin path
        current_exempt_urls.append(self.django_admin_path_prefix) # Django's built-in admin

        if request.path.startswith(settings.STATIC_URL) or \
           (hasattr(settings, 'MEDIA_URL') and settings.MEDIA_URL and request.path.startswith(settings.MEDIA_URL)):
            return None

        for exempt_url_pattern in current_exempt_urls:
            if request.path.startswith(exempt_url_pattern):
                return None

        if request.session.get('profile_incomplete', False):
            complete_profile_url = reverse('AudioXApp:complete_profile')
            if request.path == complete_profile_url:
                return None
            
            next_url_after_completion = request.session.get('next_url_after_profile_completion', request.get_full_path())
            
            redirect_url_target = f"{complete_profile_url}?next={next_url_after_completion}"
            if request.path == next_url_after_completion: # Avoid redirect loop if already on intended next
                 pass # Let them proceed if they somehow landed on next_url_after_completion before completing profile but session says incomplete

            return redirect(redirect_url_target)
        return None


class CheckUserBannedMiddleware:
    """
    Middleware to check if an authenticated user has been banned from the platform.
    If banned, logs them out and redirects them with a message.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        # URLs that should be accessible even if banned (e.g., logout, login page to see message)
        # Add any other essential public info pages if needed.
        self.exempt_url_names = [
            'AudioXApp:login',
            'AudioXApp:logout',
            'AudioXApp:adminlogin', # Assuming this is your custom admin login
            'AudioXApp:admin_logout', # Custom admin logout
            # Add other pages if needed, like a generic "account blocked" info page
        ]
        self.admin_path_prefix = '/admin/' # Your custom admin path
        self.django_admin_path_prefix = '/django-admin/' # Django's built-in admin


    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Only process for authenticated users
        if request.user.is_authenticated:
            # Check if the user is banned (using the fields we added to the User model)
            # We also check `is_active` because we set it to False upon banning.
            if hasattr(request.user, 'is_banned_by_admin') and \
               (request.user.is_banned_by_admin or not request.user.is_active):

                # Construct list of exempt URLs for this check
                current_exempt_urls = []
                for name in self.exempt_url_names:
                    try:
                        current_exempt_urls.append(reverse(name))
                    except NoReverseMatch:
                        pass
                
                # Also exempt static and media files explicitly
                is_exempt_path = False
                if request.path.startswith(settings.STATIC_URL) or \
                   (hasattr(settings, 'MEDIA_URL') and settings.MEDIA_URL and request.path.startswith(settings.MEDIA_URL)):
                    is_exempt_path = True

                if not is_exempt_path:
                    for exempt_url_pattern in current_exempt_urls:
                        if request.path.startswith(exempt_url_pattern):
                            is_exempt_path = True
                            break
                
                # If the current path is not exempt, log out and redirect
                if not is_exempt_path:
                    ban_reason = getattr(request.user, 'platform_ban_reason', "Your account has been disabled.")
                    if not ban_reason and getattr(request.user, 'is_banned_by_admin', False):
                        ban_reason = "Your account has been blocked by an administrator."
                    
                    logout(request) # Log the user out
                    messages.error(request, ban_reason) # Add the ban reason as a message
                    
                    # Redirect to the login page (or a dedicated "account blocked" page)
                    # The login page will then show the message from `messages` framework
                    # or directly if you modify it to handle query params.
                    return redirect(reverse('AudioXApp:login'))
        return None