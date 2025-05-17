# AudioXApp/adapters.py

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_field

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter for allauth social accounts to handle user population.
    """
    def populate_user(self, request, sociallogin, data):
        """
        Populates user fields from social account data when a new user is created.
        """
        user = super().populate_user(request, sociallogin, data)

        # Populate full_name from social provider data if available
        full_name = data.get('name')
        first_name = data.get('given_name')
        last_name = data.get('family_name')

        if full_name:
            user_field(user, 'full_name', full_name)
        elif first_name and last_name:
            user_field(user, 'full_name', f"{first_name} {last_name}")
        elif first_name:
            user_field(user, 'full_name', first_name)

        # allauth handles username population and uniqueness

        return user

    def pre_social_login(self, request, sociallogin):
        """
        Opportunity to intervene before a social login proceeds.
        """
        pass

