# AudioXApp/views/download_views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .utils import _get_full_context # Assuming this is your common context utility

@login_required
def my_downloads_page(request):
    # Ensure this line and its indentation use standard spaces
    context = _get_full_context(request)
    context['page_title'] = "My Offline Downloads"
    # Most of the logic to list downloads will be client-side via JavaScript
    # interacting with IndexedDB. This view just serves the page.
    return render(request, 'user/my_downloads.html', context)