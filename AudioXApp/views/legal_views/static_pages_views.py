# AudioXApp/views/legal_views/static_pages_views.py

from django.shortcuts import render
from ..utils import _get_full_context # CORRECTED IMPORT PATH

def ourteam_view(request):
    """
    Renders the Our Team page.
    Templates will be expected at 'company/ourteam.html'.
    """
    context = _get_full_context(request)
    context['page_title'] = "Our Team"
    return render(request, 'company/ourteam.html', context)

def paymentpolicy_view(request):
    """
    Renders the Payment Policy page.
    Templates will be expected at 'legal/paymentpolicy.html'.
    """
    context = _get_full_context(request)
    context['page_title'] = "Payment Policy"
    return render(request, 'legal/paymentpolicy.html', context)

def privacypolicy_view(request):
    """
    Renders the Privacy Policy page.
    Templates will be expected at 'legal/privacypolicy.html'.
    """
    context = _get_full_context(request)
    context['page_title'] = "Privacy Policy"
    return render(request, 'legal/privacypolicy.html', context)

def piracypolicy_view(request):
    """
    Renders the Piracy Policy page.
    Templates will be expected at 'legal/piracypolicy.html'.
    """
    context = _get_full_context(request)
    context['page_title'] = "Piracy Policy"
    return render(request, 'legal/piracypolicy.html', context)

def termsandconditions_view(request):
    """
    Renders the Terms and Conditions page.
    Templates will be expected at 'legal/termsandconditions.html'.
    """
    context = _get_full_context(request)
    context['page_title'] = "Terms & Conditions"
    return render(request, 'legal/termsandconditions.html', context)

def aboutus_view(request):
    """
    Renders the About Us page.
    Templates will be expected at 'company/aboutus.html'.
    """
    context = _get_full_context(request)
    context['page_title'] = "About Us"
    return render(request, 'company/aboutus.html', context)