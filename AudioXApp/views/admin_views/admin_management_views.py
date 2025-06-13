# AudioXApp/views/admin_views/admin_management_views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from ..decorators import admin_role_required
from ...models import Admin
from ...forms import AdminManagementForm

# --- Admin Management List View ---

@admin_role_required('full_access', 'manage_admins')
def manage_admins_list_view(request):
    """
    Displays a list of all admin accounts for management.
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

# --- Edit Admin View ---

@admin_role_required('full_access', 'manage_admins')
def edit_admin_view(request, admin_id):
    """
    Handles the editing of an existing admin's roles and status.
    """
    admin_to_edit = get_object_or_404(Admin, adminid=admin_id)
    current_admin_user = request.admin_user

    if request.method == 'POST':
        form = AdminManagementForm(request.POST, instance=admin_to_edit)
        if form.is_valid():
            # Prevent self-deactivation
            if not form.cleaned_data.get('is_active') and admin_to_edit.adminid == current_admin_user.adminid:
                messages.error(request, "You cannot deactivate your own account.")
            # Prevent deactivating the last full-access admin
            elif not form.cleaned_data.get('is_active') and 'full_access' in admin_to_edit.get_roles_list():
                active_full_access_admins = Admin.objects.filter(is_active=True, roles__contains='full_access').exclude(adminid=admin_to_edit.adminid)
                if not active_full_access_admins.exists():
                    messages.error(request, "Cannot deactivate the last active admin with 'full_access' role.")
                else:
                    form.save()
                    messages.success(request, f"Admin '{admin_to_edit.username}' updated successfully.")
                    return redirect(reverse('AudioXApp:admin_manage_admins'))
            # Prevent removing the last full-access role
            elif 'full_access' in admin_to_edit.get_roles_list() and 'full_access' not in form.cleaned_data.get('roles'):
                other_full_access_admins = Admin.objects.filter(is_active=True, roles__contains='full_access').exclude(adminid=admin_to_edit.adminid)
                if not other_full_access_admins.exists():
                    messages.error(request, "Cannot remove 'full_access' role from the last active admin with this role.")
                else:
                    form.save()
                    messages.success(request, f"Admin '{admin_to_edit.username}' updated successfully.")
                    return redirect(reverse('AudioXApp:admin_manage_admins'))
            else:
                form.save()
                messages.success(request, f"Admin '{admin_to_edit.username}' updated successfully.")
                return redirect(reverse('AudioXApp:admin_manage_admins'))
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AdminManagementForm(instance=admin_to_edit)

    context = {
        'active_page': 'manage_admins',
        'header_title': f'Edit Admin: {admin_to_edit.username}',
        'admin_user': current_admin_user,
        'form': form,
        'admin_to_edit': admin_to_edit,
    }
    return render(request, 'admin/manage_admins/edit_admin_form.html', context)