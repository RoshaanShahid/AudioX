# AudioXApp/adapters.py

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_field # Helper to set user fields

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        """
        Populates user fields from social account data.
        This method is called after the user has successfully authenticated
        via a social provider, and a new local user is about to be created.
        """
        user = super().populate_user(request, sociallogin, data)

        # --- Populate full_name ---
        # `data` is a dictionary containing the raw data from the social provider.
        # For Google, common keys are:
        # 'name' (full name)
        # 'given_name' (first name)
        # 'family_name' (last name)
        # 'email'
        # 'picture'

        full_name = data.get('name')
        first_name = data.get('given_name')
        last_name = data.get('family_name')

        if full_name:
            user_field(user, 'full_name', full_name)
        elif first_name and last_name:
            user_field(user, 'full_name', f"{first_name} {last_name}")
        elif first_name: # Fallback if only first name is available
            user_field(user, 'full_name', first_name)
        # If no name information is available from Google,
        # the 'full_name' field might remain as its default or whatever
        # User.objects.create_user sets it to.
        # Your User model requires full_name, so this is important.
        # If it's still empty after this, the "Complete Profile" step will be crucial.

        # --- Populate username (allauth usually handles this well) ---
        # allauth will attempt to generate a unique username if not directly provided
        # or if there's a conflict. Your User model requires a unique username.
        # You generally don't need to manually set it here unless you have very specific logic.
        # Example (if needed, but usually not):
        # if not user.username:
        #     username = data.get('email', '').split('@')[0]
        #     # Add logic for uniqueness if necessary
        #     user_field(user, 'username', username)

        # Note: phone_number and bio are not provided by Google,
        # so they will take their default values from your User model.
        # The "Complete Your Profile" step will handle these.

        return user

    def pre_social_login(self, request, sociallogin):
        """
        An opportunity to intervene before a social login proceeds.
        For example, you could check if the social account's email is banned.
        """
        # user = sociallogin.user
        # email = sociallogin.account.extra_data.get('email')
        # if email and email.endswith('@banneddomain.com'):
        #     from allauth.exceptions import ImmediateHttpResponse
        #     from django.shortcuts import redirect # Or render a message
        #     from django.contrib import messages
        #     messages.error(request, "Accounts from this domain are not allowed.")
        #     raise ImmediateHttpResponse(redirect('AudioXApp:login')) # Or your desired URL
        pass # No specific pre-login action for now

    # You can override other methods from DefaultSocialAccountAdapter if needed.
    # For example, `save_user` if you need to do something special right after the user is saved.
