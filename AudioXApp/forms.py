# AudioX/AudioXApp/forms.py
from django import forms

class PdfUploadForm(forms.Form):
    pdf_file = forms.FileField(label='Select a PDF file')
    language = forms.ChoiceField(
        label='Select Language',
        choices=[('en', 'English'), ('ur', 'Urdu')] # Use appropriate language codes for your TTS API
    )