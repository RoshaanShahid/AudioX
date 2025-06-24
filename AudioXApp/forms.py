# AudioXApp/forms.py

from django import forms
import os
from .models import Admin, Audiobook  # <--- UPDATED: Audiobook model is now imported

LANGUAGE_CHOICES = [
    ('', 'Select Language...'),
    ('English', 'English'),
    ('Urdu', 'Urdu (اردو)'),
]

NARRATOR_GENDER_CHOICES = [
    ('', '---------'),
    ('female', 'Female'),
    ('male', 'Male'),
]

# --- Document Upload Form ---

class DocumentUploadForm(forms.Form):
    document_file = forms.FileField(
        label='Upload Document (PDF, DOC, DOCX)',
        widget=forms.ClearableFileInput(attrs={
            'accept': '.pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        }),
        help_text="Supports PDF, DOC, DOCX. Max 10MB."
    )
    language = forms.ChoiceField(
        label='Select Audio Language',
        choices=LANGUAGE_CHOICES,
        widget=forms.Select()
    )
    narrator_gender = forms.ChoiceField(
        label='Select Narrator Gender',
        choices=NARRATOR_GENDER_CHOICES,
        widget=forms.Select(),
        required=False
    )

    def clean_document_file(self):
        file = self.cleaned_data.get('document_file')
        if not file:
            raise forms.ValidationError("No file was uploaded. Please select a file.")

        if file.size > 10 * 1024 * 1024:
            raise forms.ValidationError("File size cannot exceed 10MB. Please upload a smaller file.")

        ext = os.path.splitext(file.name)[1].lower()
        allowed_extensions = ['.pdf', '.doc', '.docx']
        
        expected_content_types = {
            '.pdf': ['application/pdf'],
            '.doc': ['application/msword'],
            '.docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        }

        if ext not in allowed_extensions:
            raise forms.ValidationError(
                f"Unsupported file extension: '{ext}'. Please upload a valid PDF, DOC, or DOCX file."
            )

        valid_content_type_for_ext = False
        if ext in expected_content_types:
            for ct in expected_content_types[ext]:
                if file.content_type == ct:
                    valid_content_type_for_ext = True
                    break
        
        if not valid_content_type_for_ext and file.content_type == 'application/octet-stream' and ext in allowed_extensions:
            pass
        elif not valid_content_type_for_ext:
            raise forms.ValidationError(
                f"Unsupported file content type: '{file.content_type}' for a '{ext}' file. "
                "Please upload a valid PDF, DOC, or DOCX file."
            )
        return file

    def clean(self):
        cleaned_data = super().clean()
        language = cleaned_data.get("language")
        narrator_gender = cleaned_data.get("narrator_gender")

        if language in ['English', 'Urdu'] and not narrator_gender:
            self.add_error('narrator_gender', "Please select a narrator gender for the chosen language.")
        
        return cleaned_data

# --- Admin Management Form ---

class AdminManagementForm(forms.ModelForm):
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
            'username': 'Admin username (cannot be changed after creation).',
            'email': 'Admin email (cannot be changed after creation).'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['username'].widget.attrs['readonly'] = True
            self.fields['email'].widget.attrs['readonly'] = True
            if self.instance.roles:
                self.initial['roles'] = self.instance.get_roles_list()
        else:
            self.fields['password'] = forms.CharField(widget=forms.PasswordInput, required=True)
            self.fields['confirm_password'] = forms.CharField(widget=forms.PasswordInput, required=True, label="Confirm Password")
            new_order = ['username', 'email', 'password', 'confirm_password', 'roles', 'is_active']
            self.order_fields(new_order)

    def clean_roles(self):
        roles = self.cleaned_data.get('roles')
        if not roles:
            raise forms.ValidationError("At least one role must be selected.")
        return roles

    def clean(self):
        cleaned_data = super().clean()
        if not (self.instance and self.instance.pk):
            password = cleaned_data.get("password")
            confirm_password = cleaned_data.get("confirm_password")
            if password and confirm_password and password != confirm_password:
                self.add_error('confirm_password', "Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        admin = super().save(commit=False)
        selected_roles = self.cleaned_data.get('roles')
        if selected_roles:
            admin.roles = ",".join(selected_roles)
        
        if not (self.instance and self.instance.pk) and 'password' in self.cleaned_data:
            admin.set_password(self.cleaned_data['password'])

        if commit:
            admin.save()
        return admin
    
# --- Audiobook Form ---

class AudiobookForm(forms.ModelForm):
    """
    Form for creating and updating Audiobook instances.
    """
    class Meta:
        model = Audiobook
        fields = [
            'title', 'author', 'description', 'cover_image', 'language', 'genre', 'status'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'author': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 4}),
            'cover_image': forms.ClearableFileInput(attrs={'class': 'form-input'}),
            'language': forms.Select(attrs={'class': 'form-select'}),
            'genre': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
        help_texts = {
            'cover_image': 'Upload a cover image for the audiobook.',
            'status': 'Set the initial status. "Published" will make it live immediately.',
        }