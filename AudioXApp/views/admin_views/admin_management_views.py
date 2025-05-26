# AudioXApp/views/admin_views/admin_management_views.py

from django.shortcuts import render
from django.contrib import messages
# Assuming decorators.py is in AudioXApp/views/
from ..decorators import admin_role_required
# Assuming models.py is in AudioXApp/
from ...models import Admin

@admin_role_required('full_access')
def manage_admins_list_view(request):
    """
    Displays a list of all admin accounts.
    Allows admins with 'full_access' to view other admins.
    Future enhancements: add/edit/delete functionality.
    """
    try:
        admin_list = Admin.objects.all().order_by('username')
    except Exception as e:
        messages.error(request, f"An error occurred while fetching the admin list: {e}")
        admin_list = []

    context = {
        'active_page': 'manage_admins',
        'header_title': 'Manage Administrators',
        'admin_user': request.admin_user,
        'admin_list': admin_list,
    }
    return render(request, 'admin/manage_admins/admin_list.html', context)