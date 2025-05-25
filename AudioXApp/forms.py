# AudioXApp/forms.py
from django import forms

LANGUAGE_CHOICES = [
    ('en', 'English'),
    ('ur', 'Urdu'),
]

# Simplified base choices. Display names will be handled by JavaScript in the template.
NARRATOR_GENDER_CHOICES = [
    ('', '---------'), # Add a default empty choice
    ('male', 'Male'),
    ('female', 'Female'),
]

class DocumentUploadForm(forms.Form):
    document_file = forms.FileField(
        label='Upload Document (PDF or Image)',
        widget=forms.ClearableFileInput(attrs={
            'accept': '.pdf,.jpg,.jpeg,.png,.tiff,.bmp',
        }),
        help_text="Supports PDF, JPG, PNG, TIFF, BMP. Max 15MB."
    )
    language = forms.ChoiceField(
        label='Select Audio Language',
        choices=LANGUAGE_CHOICES,
        widget=forms.Select(attrs={
        })
    )
    narrator_gender = forms.ChoiceField(
        label='Select Narrator Gender',
        choices=NARRATOR_GENDER_CHOICES, # Uses the simplified choices
        widget=forms.Select(attrs={
        }),
        required=False # JS will handle visibility and make it required if lang is en or ur
    )

    def clean_document_file(self):
        """
        Custom validation for the uploaded document file.
        Checks file size and content type.
        """
        file = self.cleaned_data.get('document_file')
        if not file:
            raise forms.ValidationError("No file was uploaded. Please select a file.")

        if file.size > 15 * 1024 * 1024: # 15MB
            raise forms.ValidationError("File size cannot exceed 15MB. Please upload a smaller file.")

        main_type = file.content_type.split('/')[0] if '/' in file.content_type else None
        sub_type = file.content_type.split('/')[-1] if '/' in file.content_type else None

        allowed_pdf_type = 'application/pdf'
        allowed_image_main_type = 'image'
        allowed_image_sub_types = ['jpeg', 'png', 'tiff', 'bmp', 'gif']

        if file.content_type == allowed_pdf_type:
            pass
        elif main_type == allowed_image_main_type and sub_type in allowed_image_sub_types:
            pass
        else:
            raise forms.ValidationError(
                f"Unsupported file type: '{file.content_type}'. "
                "Please upload a valid PDF document or an image file (JPG, PNG, TIFF, BMP, GIF)."
            )
        return file

    def clean(self):
        cleaned_data = super().clean()
        language = cleaned_data.get("language")
        narrator_gender = cleaned_data.get("narrator_gender")

        # Narrator gender is required if English or Urdu is selected
        if language in ['en', 'ur'] and not narrator_gender:
            self.add_error('narrator_gender', "Please select a narrator gender for the chosen language.")
        
        return cleaned_data

