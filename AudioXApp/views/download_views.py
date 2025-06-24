# AudioXApp/views/download_views.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from .utils import _get_full_context

# --- My Downloads Page View ---

@login_required
def my_downloads_page(request):
    """Downloads page - restricted to premium users only"""
    
    # Check if user has premium subscription
    if not hasattr(request.user, 'subscription_type') or request.user.subscription_type != 'PR':
        messages.warning(
            request, 
            "Downloads are available for Premium subscribers only. Upgrade to Premium to access offline downloads."
        )
        # Redirect to subscription page
        return redirect('AudioXApp:subscribe')
    
    context = _get_full_context(request)
    context['page_title'] = "My Offline Downloads"
    context['user_is_premium'] = True
    
    return render(request, 'user/my_downloads.html', context)
