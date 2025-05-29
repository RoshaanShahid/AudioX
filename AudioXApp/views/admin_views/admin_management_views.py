# AudioXApp/views/admin_views/admin_management_views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
# Assuming decorators.py is in AudioXApp/views/
from ..decorators import admin_role_required
# Assuming models.py is in AudioXApp/
from ...models import Admin
# Import the new form
from ...forms import AdminManagementForm

@admin_role_required('full_access', 'manage_admins') # Updated roles
def manage_admins_list_view(request):
    """
    Displays a list of all admin accounts.
    Allows admins with 'full_access' or 'manage_admins' to view other admins.
    """
    try:
        # Exclude the current admin from the list if they shouldn't manage themselves,
        # or handle this in the template. For now, fetching all.
        admin_list = Admin.objects.all().order_by('username')
    except Exception as e:
        messages.error(request, f"An error occurred while fetching the admin list: {e}")
        admin_list = []

    context = {
        'active_page': 'manage_admins', # This should match the active_page check in admin_base.html
        'header_title': 'Manage Administrators',
        'admin_user': request.admin_user, # Passed from middleware/decorator
        'admin_list': admin_list,
    }
    return render(request, 'admin/manage_admins/admin_list.html', context)

@admin_role_required('full_access', 'manage_admins')
def edit_admin_view(request, admin_id):
    """
    View to edit an existing admin's roles and active status.
    Admins cannot edit their own roles or status through this form to prevent lockouts,
    though 'full_access' admins can edit anyone else.
    """
    admin_to_edit = get_object_or_404(Admin, adminid=admin_id)
    current_admin_user = request.admin_user # Admin performing the action

    # Basic check: Prevent admin from editing themselves directly via this form if not full_access
    # Full_access admins might still need to edit themselves, but deactivating self should be harder.
    # For simplicity, we'll allow 'full_access' to edit anyone.
    # A more granular check could be:
    # if admin_to_edit.adminid == current_admin_user.adminid and not current_admin_user.has_role('full_access'):
    #     messages.error(request, "You cannot edit your own account details here.")
    #     return redirect(reverse('AudioXApp:admin_manage_admins'))

    if request.method == 'POST':
        form = AdminManagementForm(request.POST, instance=admin_to_edit)
        if form.is_valid():
            # Prevent deactivating the last 'full_access' admin or self-deactivation by non-full_access admin
            if not form.cleaned_data.get('is_active') and admin_to_edit.adminid == current_admin_user.adminid:
                 messages.error(request, "You cannot deactivate your own account.")
                 # Re-render form, potentially with an error on 'is_active' field
                 context = {
                    'active_page': 'manage_admins',
                    'header_title': f'Edit Admin: {admin_to_edit.username}',
                    'admin_user': current_admin_user,
                    'form': form,
                    'admin_to_edit': admin_to_edit,
                 }
                 return render(request, 'admin/manage_admins/edit_admin_form.html', context)

            # Check if trying to deactivate the only admin with 'full_access'
            if not form.cleaned_data.get('is_active') and 'full_access' in admin_to_edit.get_roles_list():
                active_full_access_admins = Admin.objects.filter(is_active=True).exclude(adminid=admin_to_edit.adminid)
                only_one_left = True
                for admin_obj in active_full_access_admins:
                    if 'full_access' in admin_obj.get_roles_list():
                        only_one_left = False
                        break
                if only_one_left and Admin.objects.filter(is_active=True, adminid=admin_to_edit.adminid, roles__contains='full_access').count() == 1: # Check if this is the one
                     # Check if there are other active full_access admins
                    other_active_full_access_admins = 0
                    all_active_admins = Admin.objects.filter(is_active=True).exclude(adminid=admin_to_edit.adminid)
                    for ad in all_active_admins:
                        if 'full_access' in ad.get_roles_list():
                            other_active_full_access_admins +=1
                            break
                    if other_active_full_access_admins == 0 : # No other active full_access admin
                        messages.error(request, "Cannot deactivate the last active admin with 'full_access' role.")
                        context = {
                            'active_page': 'manage_admins',
                            'header_title': f'Edit Admin: {admin_to_edit.username}',
                            'admin_user': current_admin_user,
                            'form': form,
                            'admin_to_edit': admin_to_edit,
                        }
                        return render(request, 'admin/manage_admins/edit_admin_form.html', context)


            # Prevent removing 'full_access' from the only admin with 'full_access'
            current_roles = admin_to_edit.get_roles_list()
            new_roles = form.cleaned_data.get('roles')
            if 'full_access' in current_roles and 'full_access' not in new_roles:
                # Check if this is the only admin with 'full_access'
                other_full_access_admins = 0
                all_other_admins = Admin.objects.exclude(adminid=admin_to_edit.adminid)
                for ad in all_other_admins:
                    if 'full_access' in ad.get_roles_list() and ad.is_active:
                        other_full_access_admins +=1
                        break
                if other_full_access_admins == 0 and admin_to_edit.is_active: # No other active full_access admin
                    messages.error(request, "Cannot remove 'full_access' role from the last active admin with this role.")
                    context = {
                        'active_page': 'manage_admins',
                        'header_title': f'Edit Admin: {admin_to_edit.username}',
                        'admin_user': current_admin_user,
                        'form': form,
                        'admin_to_edit': admin_to_edit,
                    }
                    return render(request, 'admin/manage_admins/edit_admin_form.html', context)

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
        'admin_to_edit': admin_to_edit, # Pass the admin being edited to the template
    }
    return render(request, 'admin/manage_admins/edit_admin_form.html', context)
