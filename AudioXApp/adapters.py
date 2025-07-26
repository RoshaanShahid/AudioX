# AudioXApp/adapters.py

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_field
from allauth.socialaccount.models import SocialAccount
from allauth.exceptions import ImmediateHttpResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from django.http import HttpRequest
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse

# --- Custom Account Adapter ---

class CustomAccountAdapter(DefaultAccountAdapter):
    def is_safe_url(self, url: str) -> bool:
        require_https_flag = False
        if hasattr(self, 'request') and isinstance(self.request, HttpRequest):
            require_https_flag = self.request.is_secure()

        return url_has_allowed_host_and_scheme(
            url,
            allowed_hosts=settings.ALLOWED_HOSTS,
            require_https=require_https_flag
        )

# --- Custom Social Account Adapter ---

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request: HttpRequest, sociallogin, data: dict):
        user = super().populate_user(request, sociallogin, data)

        full_name = data.get('name')
        first_name = data.get('given_name')
        last_name = data.get('family_name')
        current_full_name = getattr(user, 'full_name', None)

        if full_name:
            if current_full_name != full_name:
                user_field(user, 'full_name', full_name)
        elif first_name and last_name:
            composed_full_name = f"{first_name} {last_name}"
            if current_full_name != composed_full_name:
                user_field(user, 'full_name', composed_full_name)
        elif first_name:
             if current_full_name != first_name:
                user_field(user, 'full_name', first_name)

        return user

    def save_user(self, request: HttpRequest, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)

        if not sociallogin.is_existing:
            user.requires_extra_details_post_social_signup = True
            user.phone_number = None 
            user.save(update_fields=['requires_extra_details_post_social_signup', 'phone_number'])
        
        return user

    def pre_social_login(self, request: HttpRequest, sociallogin):
        """
        Custom logic to handle Google OAuth login attempts.
        If user doesn't exist, redirect to signup with error message.
        """
        super().pre_social_login(request, sociallogin)
        
        # Check if this is a login attempt (not signup)
        # This is determined by checking the 'process' parameter or the current URL path
        is_login_process = (
            request.GET.get('process') == 'login' or 
            '/login/' in request.path or
            request.session.get('socialaccount_process') == 'login'
        )
        
        # Check if user already exists in our system
        user_exists = False
        if sociallogin.account.pk:
            # Social account already exists
            user_exists = True
        else:
            # Check if user exists by email
            email = sociallogin.account.extra_data.get('email')
            if email:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    User.objects.get(email=email)
                    user_exists = True
                except User.DoesNotExist:
                    user_exists = False
        
        # If this is a login attempt and user doesn't exist, redirect with error
        if is_login_process and not user_exists:
            messages.error(
                request, 
                "No account found with this Google account. Please sign up first using this Google account, then try logging in."
            )
            # Redirect to signup page
            raise ImmediateHttpResponse(
                redirect(reverse('AudioXApp:signup'))
            )

    def is_safe_url(self, url: str) -> bool:
        require_https_flag = False
        current_request = getattr(self, 'request', None) or HttpRequest()
        if current_request and current_request.is_secure():
            require_https_flag = True
            
        return url_has_allowed_host_and_scheme(
            url,
            allowed_hosts=settings.ALLOWED_HOSTS,
            require_https=require_https_flag
        )