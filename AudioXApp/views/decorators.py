from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from ..models import Admin

def admin_role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            is_admin_flag = request.session.get('is_admin')
            if not is_admin_flag:
                messages.warning(request, "Admin login required. Session may have expired.")
                return redirect(reverse('AudioXApp:adminlogin'))

            admin_id = request.session.get('admin_id')
            if not admin_id:
                messages.error(request, "Admin session invalid (missing ID). Please log in again.")
                request.session.flush()
                return redirect(reverse('AudioXApp:adminlogin'))

            try:
                admin = Admin.objects.get(adminid=admin_id)

                if not admin.is_active:
                    messages.error(request, "Your admin account is inactive.")
                    request.session.flush()
                    return redirect(reverse('AudioXApp:adminlogin'))

                admin_roles_list = admin.get_roles_list()
                has_permission = False

                if not roles:
                    has_permission = True
                elif 'full_access' in admin_roles_list:
                    has_permission = True
                elif any(role in admin_roles_list for role in roles):
                    has_permission = True

                if has_permission:
                    request.admin_user = admin
                    return view_func(request, *args, **kwargs)
                else:
                    messages.error(request, "You do not have permission to access this page.")
                    return redirect(reverse('AudioXApp:admindashboard'))

            except Admin.DoesNotExist:
                messages.error(request, "Admin session invalid (user not found). Please log in again.")
                request.session.flush()
                return redirect(reverse('AudioXApp:adminlogin'))
            except Exception as e:
                # Keep basic exception handling, but remove detailed logging
                # print(f"An unexpected error occurred during permission check: {e}") # Simple print for server log
                messages.error(request, f"An server error occurred during permission check. Please try again or contact support.")
                request.session.flush()
                return redirect(reverse('AudioXApp:adminlogin'))
        return _wrapped_view
    return decorator


def admin_login_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.session.get('is_admin') or not request.session.get('admin_id'):
            messages.warning(request, "Please log in as an administrator to access this page.")
            return redirect(reverse('AudioXApp:adminlogin'))

        try:
            admin_user = Admin.objects.get(pk=request.session['admin_id'], is_active=True)
            request.admin_user = admin_user
        except Admin.DoesNotExist:
            request.session.flush()
            messages.error(request, "Invalid admin session. Please log in again.")
            return redirect(reverse('AudioXApp:adminlogin'))
        except Exception as e:
            # print(f"Error fetching admin user in decorator: {e}") # Simple print for server log
            messages.error(request, "An error occurred verifying your admin session.")
            request.session.flush()
            return redirect(reverse('AudioXApp:adminlogin'))

        return view_func(request, *args, **kwargs)
    return _wrapped_view
