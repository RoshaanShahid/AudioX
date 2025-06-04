# AudioXApp/adapters.py

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_field # For populating user fields
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from django.http import HttpRequest # Ensure HttpRequest is imported

# Assuming your User model is in AudioXApp.models
# from .models import User # Not strictly needed in this file if not directly querying,
                         # but good for clarity if User methods were called.

class CustomAccountAdapter(DefaultAccountAdapter):
    """
    Custom adapter for allauth account actions (login, signup, etc.).
    """
    def is_safe_url(self, url: str) -> bool:
        """
        Checks if a URL is safe to redirect to for account actions.
        """
        require_https_flag = False
        if hasattr(self, 'request') and isinstance(self.request, HttpRequest):
            require_https_flag = self.request.is_secure()

        return url_has_allowed_host_and_scheme(
            url,
            allowed_hosts=settings.ALLOWED_HOSTS,
            require_https=require_https_flag
        )

    # is_ajax is inherited from DefaultAccountAdapter.
    # You typically do not need to redefine it unless changing its behavior.


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter for allauth social accounts to handle user population
    and set flags for profile completion.
    """
    def populate_user(self, request: HttpRequest, sociallogin, data: dict):
        """
        Populates user fields from social account data when a new user is created or
        an existing user logs in via social account for the first time with this provider.
        This method is called before save_user.
        """
        user = super().populate_user(request, sociallogin, data)

        # Populate full_name from social provider data if available
        # (Google usually provides 'name', 'given_name', 'family_name')
        full_name = data.get('name')
        first_name = data.get('given_name') # Standard OIDC claim for Google
        last_name = data.get('family_name')  # Standard OIDC claim for Google

        # Your User model requires full_name.
        # Ensure it's populated, falling back if necessary.
        current_full_name = getattr(user, 'full_name', None)

        if full_name:
            if current_full_name != full_name:
                user_field(user, 'full_name', full_name)
        elif first_name and last_name:
            composed_full_name = f"{first_name} {last_name}"
            if current_full_name != composed_full_name:
                user_field(user, 'full_name', composed_full_name)
        elif first_name: # Fallback if only first_name is available
             if current_full_name != first_name:
                user_field(user, 'full_name', first_name)
        # If full_name is still not set and is mandatory, allauth's default user creation
        # or your User manager might raise an error or use a fallback (e.g., username).
        # Since your UserManager requires full_name in create_user, allauth ensures it's passed
        # using user_username, user_email or user_first_last_name.

        return user

    def save_user(self, request: HttpRequest, sociallogin, form=None):
        """
        Saves a newly signed up social login.
        This is where we'll set our custom flag for needing phone number.
        """
        # Let allauth do its default user saving/linking first.
        # This will create a new User if sociallogin.is_existing is False,
        # or link to an existing User if sociallogin.is_existing is True.
        user = super().save_user(request, sociallogin, form)

        # `sociallogin.is_existing` is True if the social account is being connected
        # to an already existing local User account.
        # It's False if a new User account is being created via this social login.
        if not sociallogin.is_existing:
            # This is a brand new user signing up via a social account (e.g., Google).
            # They will need to provide their phone number.
            # Their full_name should have been populated by the `populate_user` method.
            user.requires_extra_details_post_social_signup = True
            
            # Explicitly set phone_number to None for new social signups,
            # as this is the primary field they need to complete.
            # Bio is optional and defaults to None in the model.
            user.phone_number = None 
            
            # Save these specific changes
            user.save(update_fields=['requires_extra_details_post_social_signup', 'phone_number'])
        
        return user

    def pre_social_login(self, request: HttpRequest, sociallogin):
        """
        An opportunity to intervene before a social login proceeds.
        For example, to prevent certain social users from logging in,
        or to automatically link to an existing account if logic dictates.
        """
        # user = sociallogin.user
        # if sociallogin.account.provider == 'google':
        #     # Example: Check if the Google email domain is allowed
        #     email_domain = user.email.split('@')[-1]
        #     if email_domain not in ['alloweddomain.com']:
        #         from allauth.exceptions import ImmediateHttpResponse
        #         from django.contrib import messages
        #         messages.error(request, "Logins from this email domain are not allowed.")
        #         raise ImmediateHttpResponse(redirect(settings.ACCOUNT_LOGIN_URL)) # Or some other page

        # Call super() if you're not interrupting the flow with an ImmediateHttpResponse
        super().pre_social_login(request, sociallogin)


    def is_safe_url(self, url: str) -> bool:
        """
        Checks if a URL is safe to redirect to for social account actions.
        """
        require_https_flag = False
        # The request object should be available on the adapter instance
        # when allauth calls this method during its views.
        current_request = getattr(self, 'request', None) or HttpRequest() # Fallback to default HttpRequest if not set
        if current_request and current_request.is_secure():
            require_https_flag = True
            
        return url_has_allowed_host_and_scheme(
            url,
            allowed_hosts=settings.ALLOWED_HOSTS,
            require_https=require_https_flag
        )