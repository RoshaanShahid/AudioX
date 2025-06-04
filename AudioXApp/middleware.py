# AudioXApp/middleware.py

from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch, get_script_prefix
from django.conf import settings
from django.utils.functional import SimpleLazyObject # For reverse_lazy objects
from django.contrib.auth import logout
from django.contrib import messages
import logging
from django.utils.http import urlencode # For encoding next parameter

logger = logging.getLogger(__name__)

class ProfileCompletionMiddleware:
    """
    Middleware to redirect users to profile completion page if their profile is incomplete.
    Reads exempt URLs from settings.PROFILE_COMPLETION_EXEMPT_URLS.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.always_exempt_prefixes = []
        if hasattr(settings, 'STATIC_URL') and settings.STATIC_URL:
            self.always_exempt_prefixes.append(settings.STATIC_URL)
        if hasattr(settings, 'MEDIA_URL') and settings.MEDIA_URL:
            self.always_exempt_prefixes.append(settings.MEDIA_URL)
        
        admin_url_setting = getattr(settings, 'ADMIN_URL_PATH', 'admin/')
        # Ensure leading and trailing slashes for prefix matching
        self.always_exempt_prefixes.append(f'/{admin_url_setting.strip("/")}/')
        # self.always_exempt_prefixes.append('/admin/') # Default Django admin if used separately

        self.always_exempt_prefixes = [prefix for prefix in self.always_exempt_prefixes if prefix and prefix != '/']


    def _resolve_lazy_url(self, lazy_url_obj):
        """Helper to resolve reverse_lazy objects to string paths."""
        try:
            # For reverse_lazy, calling it or str() should give the path
            # Ensure it starts with a slash for consistent comparison
            path = str(lazy_url_obj)
            if not path.startswith('/'):
                path = '/' + path
            return path
        except Exception as e:
            logger.error(f"Error resolving lazy URL '{lazy_url_obj}': {e}")
            return None

    def __call__(self, request):
        print(f"\n--- [ProfileCompletionMiddleware START] ---")
        current_request_path = request.path
        print(f"Request Path (raw): '{current_request_path}'")

        if not request.user.is_authenticated:
            print("User not authenticated. Skipping middleware.")
            print(f"--- [ProfileCompletionMiddleware END] ---\n")
            return self.get_response(request)

        # Normalize current_request_path to ensure it has a trailing slash if not root
        # This helps match Django's typical URL patterns
        if len(current_request_path) > 1 and not current_request_path.endswith('/'):
            normalized_request_path = current_request_path + '/'
        else:
            normalized_request_path = current_request_path
        print(f"Request Path (normalized for check): '{normalized_request_path}'")


        # 1. Check for always exempt path prefixes (static, media, admin)
        for prefix in self.always_exempt_prefixes:
            if normalized_request_path.startswith(prefix):
                print(f"Path '{normalized_request_path}' starts with always_exempt_prefix '{prefix}'. Exempt.")
                print(f"--- [ProfileCompletionMiddleware END] ---\n")
                return self.get_response(request)

        # 2. Check against PROFILE_COMPLETION_EXEMPT_URLS from settings
        exempt_paths_from_settings = []
        if hasattr(settings, 'PROFILE_COMPLETION_EXEMPT_URLS'):
            print(f"Raw settings.PROFILE_COMPLETION_EXEMPT_URLS: {settings.PROFILE_COMPLETION_EXEMPT_URLS}")
            for i, lazy_url_obj in enumerate(settings.PROFILE_COMPLETION_EXEMPT_URLS):
                resolved_path = self._resolve_lazy_url(lazy_url_obj)
                if resolved_path:
                    # Normalize resolved path as well
                    if len(resolved_path) > 1 and not resolved_path.endswith('/'):
                        normalized_resolved_path = resolved_path + '/'
                    else:
                        normalized_resolved_path = resolved_path
                    print(f"Exempt URL Setting [{i}]: Raw='{lazy_url_obj}', Resolved='{resolved_path}', Normalized Resolved='{normalized_resolved_path}'")
                    exempt_paths_from_settings.append(normalized_resolved_path)
        
        print(f"Final list of normalized resolved exempt paths from settings: {exempt_paths_from_settings}")

        if normalized_request_path in exempt_paths_from_settings:
            print(f"Path '{normalized_request_path}' IS IN normalized resolved exempt_paths_from_settings. Exempt.")
            print(f"--- [ProfileCompletionMiddleware END] ---\n")
            return self.get_response(request)
        else:
            print(f"Path '{normalized_request_path}' IS NOT in normalized resolved exempt_paths_from_settings.")

        # 3. Perform the profile completion check and redirect if needed
        profile_incomplete_session = request.session.get('profile_incomplete', False)
        print(f"Session 'profile_incomplete': {profile_incomplete_session}")
        
        # You might also have a direct check on the user model, e.g.:
        # needs_completion_model_check = False
        # if hasattr(request.user, 'has_completed_profile_attr') and not request.user.has_completed_profile_attr:
        # needs_completion_model_check = True
        # print(f"User model profile completion check: {needs_completion_model_check}")
        
        # Determine if redirect is needed (using your session flag logic)
        needs_redirect = profile_incomplete_session

        if needs_redirect:
            print(f"Profile is considered incomplete for user: {request.user.username}")
            try:
                complete_profile_url_path = reverse('AudioXApp:complete_profile')
                # Normalize this path too for comparison
                if len(complete_profile_url_path) > 1 and not complete_profile_url_path.endswith('/'):
                    normalized_complete_profile_url = complete_profile_url_path + '/'
                else:
                    normalized_complete_profile_url = complete_profile_url_path
            except NoReverseMatch:
                logger.error("ProfileCompletionMiddleware: Could not reverse 'AudioXApp:complete_profile'. Check URL name.")
                print(f"--- [ProfileCompletionMiddleware END - Error reversing complete_profile] ---\n")
                return self.get_response(request)

            if normalized_request_path == normalized_complete_profile_url: # Already on the completion page
                print(f"Already on 'complete_profile' page ('{normalized_request_path}'). Exempt from redirect.")
                print(f"--- [ProfileCompletionMiddleware END] ---\n")
                return self.get_response(request)
            
            next_param_value = request.GET.get('next', request.get_full_path())
            query_params = urlencode({'next': next_param_value})
            
            # Use get_script_prefix() for correct URL construction if Django isn't at domain root
            redirect_url_target = f"{get_script_prefix().rstrip('/')}{complete_profile_url_path}?{query_params}"
            
            print(f"Redirecting from '{current_request_path}' to '{redirect_url_target}' because profile incomplete.")
            messages.info(request, "Please complete your profile to continue.")
            print(f"--- [ProfileCompletionMiddleware END - Redirecting] ---\n")
            return redirect(redirect_url_target)

        print("Profile complete or path was exempt. Proceeding with request.")
        print(f"--- [ProfileCompletionMiddleware END] ---\n")
        return self.get_response(request)


class CheckUserBannedMiddleware:
    """
    Middleware to check if an authenticated user has been banned from the platform.
    If banned, logs them out and redirects them with a message.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_url_names = [
            'AudioXApp:login',
            'AudioXApp:logout',
            'AudioXApp:adminlogin', 
            'AudioXApp:admin_logout', 
        ]
        self.always_exempt_prefixes = []
        if hasattr(settings, 'STATIC_URL') and settings.STATIC_URL:
            self.always_exempt_prefixes.append(settings.STATIC_URL)
        if hasattr(settings, 'MEDIA_URL') and settings.MEDIA_URL:
            self.always_exempt_prefixes.append(settings.MEDIA_URL)
        
        admin_url_setting = getattr(settings, 'ADMIN_URL_PATH', 'admin/')
        self.always_exempt_prefixes.append(f'/{admin_url_setting.strip("/")}/')
        self.always_exempt_prefixes = [prefix for prefix in self.always_exempt_prefixes if prefix and prefix != '/']


    def _resolve_lazy_url(self, lazy_url_obj): # Helper can be reused or defined globally
        try:
            path = str(lazy_url_obj)
            if not path.startswith('/'):
                path = '/' + path
            return path
        except Exception as e:
            logger.error(f"Error resolving lazy URL '{lazy_url_obj}': {e}")
            return None

    def __call__(self, request):
        if request.user.is_authenticated:
            if hasattr(request.user, 'is_banned_by_admin') and \
               (request.user.is_banned_by_admin or not request.user.is_active):

                current_request_path = request.path
                normalized_request_path = current_request_path + '/' if len(current_request_path) > 1 and not current_request_path.endswith('/') else current_request_path
                
                is_exempt_path = False
                for prefix in self.always_exempt_prefixes:
                    if normalized_request_path.startswith(prefix):
                        is_exempt_path = True
                        break
                
                if not is_exempt_path:
                    current_exempt_paths = []
                    for name in self.exempt_url_names:
                        try:
                            resolved_path = reverse(name) # Use reverse directly here for immediate resolution
                            normalized_resolved_path = resolved_path + '/' if len(resolved_path) > 1 and not resolved_path.endswith('/') else resolved_path
                            current_exempt_paths.append(normalized_resolved_path)
                        except NoReverseMatch:
                            logger.warning(f"CheckUserBannedMiddleware: NoReverseMatch for exempt URL name '{name}'")
                    
                    if normalized_request_path in current_exempt_paths:
                        is_exempt_path = True

                if not is_exempt_path:
                    ban_reason = getattr(request.user, 'platform_ban_reason', "Your account has been disabled by an administrator.")
                    if not ban_reason and getattr(request.user, 'is_banned_by_admin', False):
                        ban_reason = "Your account has been blocked by an administrator."
                    
                    logger.info(f"Banned user {request.user.username} attempting to access {request.path}. Logging out and redirecting.")
                    logout(request)
                    messages.error(request, ban_reason)
                    
                    try:
                        login_url_path = reverse('AudioXApp:login')
                    except NoReverseMatch:
                        logger.error("CheckUserBannedMiddleware: Could not reverse 'AudioXApp:login'. Redirecting to '/login/'.")
                        login_url_path = '/login/' 
                    return redirect(login_url_path)
        
        return self.get_response(request)
