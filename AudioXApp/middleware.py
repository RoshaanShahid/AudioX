# AudioXApp/middleware.py

from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch, get_script_prefix
from django.conf import settings
from django.utils.functional import SimpleLazyObject
from django.contrib.auth import logout
from django.contrib import messages
import logging
from django.utils.http import urlencode

logger = logging.getLogger(__name__)

# --- Profile Completion Middleware ---

class ProfileCompletionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.always_exempt_prefixes = []
        if hasattr(settings, 'STATIC_URL') and settings.STATIC_URL:
            self.always_exempt_prefixes.append(settings.STATIC_URL)
        if hasattr(settings, 'MEDIA_URL') and settings.MEDIA_URL:
            self.always_exempt_prefixes.append(settings.MEDIA_URL)
        
        admin_url_setting = getattr(settings, 'ADMIN_URL_PATH', 'admin/')
        self.always_exempt_prefixes.append(f'/{admin_url_setting.strip("/")}/')
        self.always_exempt_prefixes = [prefix for prefix in self.always_exempt_prefixes if prefix and prefix != '/']

    def _resolve_lazy_url(self, lazy_url_obj):
        try:
            path = str(lazy_url_obj)
            if not path.startswith('/'):
                path = '/' + path
            return path
        except Exception as e:
            logger.error(f"Error resolving lazy URL '{lazy_url_obj}': {e}")
            return None

    def __call__(self, request):
        current_request_path = request.path
        if not request.user.is_authenticated:
            return self.get_response(request)

        if len(current_request_path) > 1 and not current_request_path.endswith('/'):
            normalized_request_path = current_request_path + '/'
        else:
            normalized_request_path = current_request_path

        for prefix in self.always_exempt_prefixes:
            if normalized_request_path.startswith(prefix):
                return self.get_response(request)

        exempt_paths_from_settings = []
        if hasattr(settings, 'PROFILE_COMPLETION_EXEMPT_URLS'):
            for i, lazy_url_obj in enumerate(settings.PROFILE_COMPLETION_EXEMPT_URLS):
                resolved_path = self._resolve_lazy_url(lazy_url_obj)
                if resolved_path:
                    if len(resolved_path) > 1 and not resolved_path.endswith('/'):
                        normalized_resolved_path = resolved_path + '/'
                    else:
                        normalized_resolved_path = resolved_path
                    exempt_paths_from_settings.append(normalized_resolved_path)
        
        if normalized_request_path in exempt_paths_from_settings:
            return self.get_response(request)

        profile_incomplete_session = request.session.get('profile_incomplete', False)
        needs_redirect = profile_incomplete_session

        if needs_redirect:
            try:
                complete_profile_url_path = reverse('AudioXApp:complete_profile')
                if len(complete_profile_url_path) > 1 and not complete_profile_url_path.endswith('/'):
                    normalized_complete_profile_url = complete_profile_url_path + '/'
                else:
                    normalized_complete_profile_url = complete_profile_url_path
            except NoReverseMatch:
                logger.error("ProfileCompletionMiddleware: Could not reverse 'AudioXApp:complete_profile'. Check URL name.")
                return self.get_response(request)

            if normalized_request_path == normalized_complete_profile_url:
                return self.get_response(request)
            
            next_param_value = request.GET.get('next', request.get_full_path())
            query_params = urlencode({'next': next_param_value})
            redirect_url_target = f"{get_script_prefix().rstrip('/')}{complete_profile_url_path}?{query_params}"
            
            messages.info(request, "Please complete your profile to continue.")
            return redirect(redirect_url_target)

        return self.get_response(request)

# --- User Ban Check Middleware ---

class CheckUserBannedMiddleware:
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

    def _resolve_lazy_url(self, lazy_url_obj):
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
            if hasattr(request.user, 'is_banned_by_admin') and (request.user.is_banned_by_admin or not request.user.is_active):
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
                            resolved_path = reverse(name)
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