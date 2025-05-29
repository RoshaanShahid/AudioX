# AudioXApp/forms.py
from django import forms
import os # For file extension checking
from .models import Admin # Import the Admin model

# Values for LANGUAGE_CHOICES should match the keys in EDGE_TTS_VOICES_BY_LANGUAGE
# in creator_tts_views.py (e.g., 'English', 'Urdu')
# --- MERGED LANGUAGE_CHOICES (using HEAD version) ---
LANGUAGE_CHOICES = [
    ('', 'Select Language...'), # Added a more descriptive default
    ('English', 'English'),   # Changed 'en' to 'English' for consistency with typical TTS voice map keys
    ('Urdu', 'Urdu (اردو)'),     # Changed 'ur' to 'Urdu', kept descriptive text
    # Add other languages here if they are supported by your TTS (e.g., 'Punjabi', 'Sindhi')
    # Ensure these keys match those in your TTS voice mapping.
    # Example:
    # ('Punjabi', 'Punjabi (پنجابی)'),
    # ('Sindhi', 'Sindhi (سنڌي)'),
]
# --- END MERGED LANGUAGE_CHOICES ---

NARRATOR_GENDER_CHOICES = [
    ('', '---------'), # User's preferred empty choice
    ('female', 'Female'), # Changed order to female first, often a default
    ('male', 'Male'),
]

class DocumentUploadForm(forms.Form): # Using your existing form name
    document_file = forms.FileField(
        label='Upload Document (PDF, DOC, DOCX)', # Updated label
        widget=forms.ClearableFileInput(attrs={
            # Updated accept types to reflect typical document formats for text extraction
            'accept': '.pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        }),
        help_text="Supports PDF, DOC, DOCX. Max 10MB." # Updated help text and size
    )
    language = forms.ChoiceField(
        label='Select Audio Language',
        choices=LANGUAGE_CHOICES, # Using updated choices
        widget=forms.Select()
    )
    narrator_gender = forms.ChoiceField(
        label='Select Narrator Gender',
        choices=NARRATOR_GENDER_CHOICES,
        widget=forms.Select(),
        required=False # JavaScript will handle conditional requirement based on language selected in the template
    )

    def clean_document_file(self):
        file = self.cleaned_data.get('document_file')
        if not file:
            # This should ideally be caught by required=True on the field itself,
            # but an explicit check here is also fine.
            raise forms.ValidationError("No file was uploaded. Please select a file.")

        # Check file size (10MB for documents)
        if file.size > 10 * 1024 * 1024:
            raise forms.ValidationError("File size cannot exceed 10MB. Please upload a smaller file.")

        # Validate file type based on extension and content type for PDF/DOC/DOCX
        ext = os.path.splitext(file.name)[1].lower()
        allowed_extensions = ['.pdf', '.doc', '.docx']
        
        # Standard content types for these extensions
        # Note: Content types can sometimes vary slightly based on OS/browser, so extension check is a good backup.
        expected_content_types = {
            '.pdf': ['application/pdf'],
            '.doc': ['application/msword'],
            '.docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        }

        if ext not in allowed_extensions:
            raise forms.ValidationError(
                f"Unsupported file extension: '{ext}'. Please upload a valid PDF, DOC, or DOCX file."
            )

        # Check if the content type matches one of the expected types for the given extension
        valid_content_type_for_ext = False
        if ext in expected_content_types:
            for ct in expected_content_types[ext]:
                if file.content_type == ct:
                    valid_content_type_for_ext = True
                    break
        
        # Allow some flexibility if content type is 'application/octet-stream' but extension is correct
        # as this can happen with some uploads. The view's text extraction will be the final judge.
        if not valid_content_type_for_ext and file.content_type == 'application/octet-stream' and ext in allowed_extensions:
            pass # Allow, but log a warning perhaps in the view if processing fails
        elif not valid_content_type_for_ext:
                raise forms.ValidationError(
                    f"Unsupported file content type: '{file.content_type}' for a '{ext}' file. "
                    "Please upload a valid PDF, DOC, or DOCX file."
                )
                
        return file

    def clean(self):
        cleaned_data = super().clean()
        language = cleaned_data.get("language") # This will now be 'English', 'Urdu', etc.
        narrator_gender = cleaned_data.get("narrator_gender")

        # Narrator gender is required if specific languages (e.g., English, Urdu) are selected
        # This list should match languages for which you offer distinct gendered voices in your TTS setup.
        if language in ['English', 'Urdu'] and not narrator_gender: # Using full language names
            self.add_error('narrator_gender', "Please select a narrator gender for the chosen language.")
        
        return cleaned_data

# --- Admin Management Form ---
class AdminManagementForm(forms.ModelForm):
    """
    Form for managing Admin users, including their roles and active status.
    """
    roles = forms.MultipleChoiceField(
        choices=Admin.RoleChoices.choices,
        widget=forms.CheckboxSelectMultiple,
        required=True,
        help_text="Select one or more roles for the admin."
    )

    class Meta:
        model = Admin
        fields = ['username', 'email', 'roles', 'is_active']
        help_texts = {
            'is_active': 'Unselect this to deactivate the admin account. They will not be able to log in.',
            'username': 'Admin username (cannot be changed after creation for simplicity here, but can be displayed as readonly).',
            'email': 'Admin email (cannot be changed after creation for simplicity here, but can be displayed as readonly).'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make username and email readonly if instance exists (editing)
        if self.instance and self.instance.pk:
            self.fields['username'].widget.attrs['readonly'] = True
            self.fields['email'].widget.attrs['readonly'] = True
            # Populate initial roles from the comma-separated string in the model
            if self.instance.roles:
                self.initial['roles'] = self.instance.get_roles_list()
        else: # For new admin creation (if this form is used for that)
            self.fields['password'] = forms.CharField(widget=forms.PasswordInput, required=True)
            self.fields['confirm_password'] = forms.CharField(widget=forms.PasswordInput, required=True, label="Confirm Password")
            # Reorder fields to put password fields after email for new admin
            new_order = ['username', 'email', 'password', 'confirm_password', 'roles', 'is_active']
            self.order_fields(new_order)


    def clean_roles(self):
        roles = self.cleaned_data.get('roles')
        if not roles:
            raise forms.ValidationError("At least one role must be selected.")
        # Ensure 'full_access' is not mixed with other roles if it's meant to be exclusive (optional logic)
        # For now, we allow mixing.
        return roles

    def clean(self):
        cleaned_data = super().clean()
        # If creating a new admin, check password confirmation
        if not (self.instance and self.instance.pk): # Only for new admins
            password = cleaned_data.get("password")
            confirm_password = cleaned_data.get("confirm_password")
            if password and confirm_password and password != confirm_password:
                self.add_error('confirm_password', "Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        admin = super().save(commit=False)
        # Convert list of roles from form back to comma-separated string for the model
        selected_roles = self.cleaned_data.get('roles')
        if selected_roles:
            admin.roles = ",".join(selected_roles)
        
        # Handle password for new admin
        if not (self.instance and self.instance.pk) and 'password' in self.cleaned_data:
            admin.set_password(self.cleaned_data['password'])

        if commit:
            admin.save()
        return admin

