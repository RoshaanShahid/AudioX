# AudioXApp/adapters.py

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_field
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from django.http import HttpRequest # Ensure HttpRequest is imported if type hinting or specific checks are needed.

class CustomAccountAdapter(DefaultAccountAdapter):
    """
    Custom adapter for allauth account actions (login, signup, etc.).
    Inherits 'is_ajax' from DefaultAccountAdapter.
    """
    def is_safe_url(self, url: str) -> bool:
        """
        Checks if a URL is safe to redirect to for account actions.
        """
        require_https_flag = False
        # self.request should be available if allauth passes it,
        # otherwise, make a sensible default or handle its absence.
        if hasattr(self, 'request') and isinstance(self.request, HttpRequest):
            require_https_flag = self.request.is_secure()

        return url_has_allowed_host_and_scheme(
            url,
            allowed_hosts=settings.ALLOWED_HOSTS,
            require_https=require_https_flag
        )

    # is_ajax is inherited from DefaultAccountAdapter.
    # You typically do not need to redefine it.
    # Example of how it's defined in the parent class (for your reference):
    # def is_ajax(self, request: HttpRequest) -> bool:
    #     return request.headers.get("x-requested-with") == "XMLHttpRequest"

    # Add any other custom methods for your account adapter here.
    # For example, if you override 'clean_email', 'clean_username', etc.


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter for allauth social accounts to handle user population.
    """
    def populate_user(self, request: HttpRequest, sociallogin, data: dict):
        """
        Populates user fields from social account data when a new user is created.
        """
        user = super().populate_user(request, sociallogin, data)

        # Populate full_name from social provider data if available
        full_name = data.get('name')
        first_name = data.get('given_name') # Standard OIDC claim
        last_name = data.get('family_name')  # Standard OIDC claim

        if full_name:
            user_field(user, 'full_name', full_name)
        elif first_name and last_name:
            user_field(user, 'full_name', f"{first_name} {last_name}")
        elif first_name:
            user_field(user, 'full_name', first_name)
        # You might want to populate other fields like 'email' if not automatically done,
        # or ensure 'username' is populated as per your requirements if allauth's
        # default doesn't suit you. Ensure your User model has 'full_name' field.

        return user

    def pre_social_login(self, request: HttpRequest, sociallogin):
        """
        Opportunity to intervene before a social login proceeds.
        For example, to link to an existing user account.
        """
        # Example: if sociallogin.is_existing:
        #     return
        # user = sociallogin.user
        # Check if user's email is verified, etc.
        pass # Keep 'pass' if no specific pre-login action is needed

    def is_safe_url(self, url: str) -> bool:
        """
        Checks if a URL is safe to redirect to for social account actions.
        """
        require_https_flag = False
        if hasattr(self, 'request') and isinstance(self.request, HttpRequest):
            require_https_flag = self.request.is_secure()

        return url_has_allowed_host_and_scheme(
            url,
            allowed_hosts=settings.ALLOWED_HOSTS,
            require_https=require_https_flag
        )

    # 'is_ajax' is generally not directly called on SocialAccountAdapter
    # by the standard account views. It would inherit from DefaultSocialAccountAdapter
    # if it were, which in turn inherits from DefaultAccountAdapter.