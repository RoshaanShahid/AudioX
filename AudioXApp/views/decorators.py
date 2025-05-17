# AudioXApp/decorators.py

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from ..models import Admin

def admin_role_required(*roles):
    """
    Decorator for views that require admin login and specific roles.
    If no roles are specified, it only checks for an active admin session.
    Populates request.admin_user if successful.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Check for admin session flags
            is_admin_flag = request.session.get('is_admin')
            admin_id = request.session.get('admin_id')

            if not is_admin_flag or not admin_id:
                messages.warning(request, "Admin login required.")
                return redirect(reverse('AudioXApp:adminlogin'))

            try:
                # Fetch the active admin user
                admin = Admin.objects.get(adminid=admin_id, is_active=True)
                request.admin_user = admin # Attach admin object to request

                # Check roles if specified
                if roles:
                    admin_roles_list = admin.get_roles_list()
                    # Grant access if admin has 'full_access' or any of the required roles
                    if 'full_access' not in admin_roles_list and not any(role in admin_roles_list for role in roles):
                        messages.error(request, "You do not have permission to access this specific page.")
                        return redirect(reverse('AudioXApp:admindashboard'))

                # If admin is logged in, active, and has required roles (or none required), proceed
                return view_func(request, *args, **kwargs)

            except Admin.DoesNotExist:
                # Admin user not found or is inactive
                messages.error(request, "Admin session invalid. Please log in again.")
                request.session.flush() # Clear potentially invalid session
                return redirect(reverse('AudioXApp:adminlogin'))
            except Exception as e:
                # Catch any other unexpected errors during admin check or view execution
                messages.error(request, "A server error occurred while trying to load the page. Please try again or contact support.")
                # Optionally flush session on unexpected errors, depending on desired security level
                # request.session.flush()
                return redirect(reverse('AudioXApp:adminlogin'))

        return _wrapped_view
    return decorator


def admin_login_required(view_func):
    """
    Decorator for views that strictly require an admin to be logged in and active.
    It populates request.admin_user.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Check for admin session flags
        is_admin_flag = request.session.get('is_admin')
        admin_id = request.session.get('admin_id')

        if not is_admin_flag or not admin_id:
            messages.warning(request, "Please log in as an administrator to access this page.")
            return redirect(reverse('AudioXApp:adminlogin'))

        try:
            # Fetch the active admin user and attach to request
            admin_user = Admin.objects.get(pk=admin_id, is_active=True)
            request.admin_user = admin_user
            return view_func(request, *args, **kwargs)

        except Admin.DoesNotExist:
            # Admin user not found or is inactive
            request.session.flush()
            messages.error(request, "Invalid admin session. Please log in again.")
            return redirect(reverse('AudioXApp:adminlogin'))
        except Exception:
            # Catch any other unexpected errors
            messages.error(request, "An error occurred verifying your admin session.")
            # Optionally flush session
            # request.session.flush()
            return redirect(reverse('AudioXApp:adminlogin'))

    return _wrapped_view
