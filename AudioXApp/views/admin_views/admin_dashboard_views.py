# AudioXApp/views/admin_views/admin_dashboard_views.py

from django.shortcuts import render
from django.conf import settings
from . import dashboard_utils # The new data engine we just created
from ..decorators import admin_role_required

# --- Admin Dashboard View ---

@admin_role_required()
def admindashboard(request):
    """
    Renders the comprehensive admin dashboard.
    This view now acts as a simple bridge, calling the main context-building
    function from dashboard_utils and passing the data to the template.
    """
    
    # 1. Get all dashboard data from our powerful data engine in one call
    context = dashboard_utils.get_dashboard_context()

    # 2. Add request-specific context
    context['admin_user'] = getattr(request, 'admin_user', None)
    context['active_page'] = 'dashboard'
    context['TIME_ZONE'] = settings.TIME_ZONE
    
    # Get the active tab from the URL query parameter (e.g., ?tab=financials)
    context['active_tab'] = request.GET.get('tab', 'overview')

    # 3. Render the template with the combined context
    return render(request, 'admin/admin_dashboard.html', context)