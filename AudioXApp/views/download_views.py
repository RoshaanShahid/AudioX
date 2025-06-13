# AudioXApp/views/download_views.py

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .utils import _get_full_context

# --- My Downloads Page View ---

@login_required
def my_downloads_page(request):
    context = _get_full_context(request)
    context['page_title'] = "My Offline Downloads"
    return render(request, 'user/my_downloads.html', context)