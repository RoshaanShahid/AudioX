import traceback # Add this import at the top of your decorators.py
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from ..models import Admin # Assuming Admin model is in ..models

def admin_role_required(*roles):
    """
    Decorator for views that require admin login and specific roles.
    If no roles are specified, it only checks for admin login and active status.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # --- Start Debugging ---
            print(f"\n--- [Decorator Check: admin_role_required for: {request.path}] ---")
            print(f"Incoming Session items: {dict(request.session.items())}")
            # --- End Debugging ---

            is_admin_flag = request.session.get('is_admin')
            # --- Debugging ---
            print(f"Value of 'is_admin' from session: {is_admin_flag}")
            # --- End Debugging ---
            if not is_admin_flag:
                messages.warning(request, "Admin login required. Session may have expired or is_admin flag not set.")
                # --- Debugging ---
                print("Redirecting to login: 'is_admin' flag is False or None.")
                # --- End Debugging ---
                return redirect(reverse('AudioXApp:adminlogin'))

            admin_id = request.session.get('admin_id')
            # --- Debugging ---
            print(f"Value of 'admin_id' from session: {admin_id}")
            # --- End Debugging ---
            if not admin_id:
                messages.error(request, "Admin session invalid (missing ID). Please log in again.")
                request.session.flush() # Clear potentially corrupted session
                # --- Debugging ---
                print("Redirecting to login: 'admin_id' is False or None.")
                # --- End Debugging ---
                return redirect(reverse('AudioXApp:adminlogin'))

            try:
                # --- Debugging ---
                print(f"Attempting to fetch Admin with adminid: {admin_id}")
                # --- End Debugging ---
                admin = Admin.objects.get(adminid=admin_id) # adminid is the PK in your Admin model
                # --- Debugging ---
                print(f"Admin object fetched: {admin.username}, is_active: {admin.is_active}")
                # --- End Debugging ---

                if not admin.is_active:
                    messages.error(request, "Your admin account is inactive.")
                    request.session.flush()
                    # --- Debugging ---
                    print(f"Redirecting to login: Admin '{admin.username}' is not active.")
                    # --- End Debugging ---
                    return redirect(reverse('AudioXApp:adminlogin'))

                # Populate request.admin_user early if admin is valid so far
                request.admin_user = admin 
                
                admin_roles_list = admin.get_roles_list()
                # --- Debugging ---
                print(f"Admin roles from admin.get_roles_list(): {admin_roles_list}")
                print(f"Decorator roles required for this view: {roles}")
                # --- End Debugging ---
                
                has_permission = False

                if not roles: # If decorator is used as @admin_role_required()
                    has_permission = True # Access granted if logged in and active
                    # --- Debugging ---
                    print("Permission check: No specific roles required by decorator, access granted.")
                    # --- End Debugging ---
                elif 'full_access' in admin_roles_list:
                    has_permission = True
                    # --- Debugging ---
                    print("Permission check: Admin has 'full_access' role, access granted.")
                    # --- End Debugging ---
                elif any(role in admin_roles_list for role in roles):
                    has_permission = True
                    # --- Debugging ---
                    print(f"Permission check: Admin has one of the required roles ({roles}), access granted.")
                    # --- End Debugging ---
                else:
                    # --- Debugging ---
                    print(f"Permission check: Admin does NOT have required roles ({roles}).")
                    # --- End Debugging ---


                if has_permission:
                    # --- Debugging ---
                    print(f"Permission GRANTED for {admin.username} to access {request.path}. Proceeding to view.")
                    # --- End Debugging ---
                    return view_func(request, *args, **kwargs) # <<< Error likely happens inside this call
                else:
                    messages.error(request, "You do not have permission to access this specific page.")
                    # --- Debugging ---
                    print(f"Permission DENIED for {admin.username} for roles {roles} at {request.path}. Redirecting to dashboard.")
                    # --- End Debugging ---
                    return redirect(reverse('AudioXApp:admindashboard')) 

            except Admin.DoesNotExist:
                messages.error(request, "Admin session invalid (user not found with ID). Please log in again.")
                request.session.flush()
                # --- Debugging ---
                print(f"Redirecting to login: Admin.DoesNotExist for admin_id {admin_id}.")
                # --- End Debugging ---
                return redirect(reverse('AudioXApp:adminlogin'))
            except Exception as e: # This block catches the error from view_func
                # --- Debugging ---
                print(f"An UNEXPECTED ERROR occurred in admin_role_required decorator (likely from within the wrapped view_func '{view_func.__name__}'): {type(e).__name__} - {e}")
                print("--- Full Traceback of the error caught by decorator ---")
                traceback.print_exc() # THIS WILL PRINT THE FULL TRACEBACK
                print("--- End Traceback ---")
                # --- End Debugging ---
                messages.error(request, "A server error occurred while trying to load the page. Please try again or contact support.")
                # Flushing session on any error from the view might be too aggressive,
                # but let's keep it for now to maintain current behavior.
                if request.session.get('is_admin'): 
                    request.session.flush()
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
        # (Previous debugging prints can be kept or removed for this decorator as it's not the primary suspect for this specific error)
        print(f"\n--- [Decorator Check: admin_login_required for: {request.path}] ---")
        print(f"Incoming Session items: {dict(request.session.items())}")

        is_admin_flag = request.session.get('is_admin')
        admin_id = request.session.get('admin_id')

        print(f"Value of 'is_admin': {is_admin_flag}, 'admin_id': {admin_id}")

        if not is_admin_flag or not admin_id:
            messages.warning(request, "Please log in as an administrator to access this page.")
            print("Redirecting to login: 'is_admin' or 'admin_id' missing from session.")
            return redirect(reverse('AudioXApp:adminlogin'))

        try:
            print(f"Attempting to fetch Admin with pk (adminid): {admin_id}, requiring is_active=True")
            admin_user = Admin.objects.get(pk=admin_id, is_active=True)
            request.admin_user = admin_user
            print(f"Admin object fetched for admin_login_required: {admin_user.username}")
            print(f"Permission GRANTED for {admin_user.username} by admin_login_required. Proceeding to view.")
        except Admin.DoesNotExist:
            request.session.flush()
            messages.error(request, "Invalid admin session (user not found or inactive). Please log in again.")
            print(f"Redirecting to login: Admin.DoesNotExist or not active for admin_id {admin_id}.")
            return redirect(reverse('AudioXApp:adminlogin'))
        except Exception as e:
            print(f"An UNEXPECTED ERROR occurred in admin_login_required decorator (likely from view_func '{view_func.__name__}'): {type(e).__name__} - {e}")
            print("--- Full Traceback of the error caught by decorator ---")
            traceback.print_exc()
            print("--- End Traceback ---")
            messages.error(request, "An error occurred verifying your admin session.")
            if request.session.get('is_admin'):
                 request.session.flush()
            return redirect(reverse('AudioXApp:adminlogin'))

        return view_func(request, *args, **kwargs)
    return _wrapped_view
