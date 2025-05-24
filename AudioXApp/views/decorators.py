# AudioXApp/views/decorators.py

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required # Added for creator_required
from ..models import Admin, Creator # Added Creator model import
import logging # Added for creator_required

logger = logging.getLogger(__name__) # Added for creator_required

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
                logger.error(f"Error in admin_role_required decorator: {type(e).__name__} - {e}", exc_info=True)
                messages.error(request, "A server error occurred while trying to load the page. Please try again or contact support.")
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
            admin_user_obj = Admin.objects.get(pk=admin_id, is_active=True) # Renamed to avoid conflict
            request.admin_user = admin_user_obj
            return view_func(request, *args, **kwargs)

        except Admin.DoesNotExist:
            # Admin user not found or is inactive
            request.session.flush()
            messages.error(request, "Invalid admin session. Please log in again.")
            return redirect(reverse('AudioXApp:adminlogin'))
        except Exception as e:
            logger.error(f"Error in admin_login_required decorator: {type(e).__name__} - {e}", exc_info=True)
            messages.error(request, "An error occurred verifying your admin session.")
            return redirect(reverse('AudioXApp:adminlogin'))

    return _wrapped_view


# --- ADDED creator_required decorator ---
def creator_required(view_func):
    @login_required # Ensure the user is logged in first
    @wraps(view_func) # Preserve metadata of the original view function
    def _wrapped_view(request, *args, **kwargs):
        try:
            # Attempt to fetch the creator profile associated with the logged-in user
            # Assuming Creator model has a OneToOneField to User named 'user'
            # and user_id is the primary key for User model.
            creator = Creator.objects.select_related('user').get(user=request.user)
            
            if creator.is_banned:
                messages.error(request, "Your creator account is banned and you cannot access this page.")
                return redirect('AudioXApp:home') # Or a more specific "banned" page
            
            if creator.verification_status != 'approved':
                messages.warning(request, "Your creator profile is not yet approved. Access denied.")
                # Redirect to a page that explains their status, or home
                return redirect('AudioXApp:creator_welcome') # Or 'AudioXApp:home'
            
            # If all checks pass, attach the creator object to the request and call the original view
            request.creator = creator
            return view_func(request, *args, **kwargs)

        except Creator.DoesNotExist:
            messages.warning(request, "You do not have an active creator profile. Please apply or wait for approval.")
            return redirect('AudioXApp:creator_welcome') # Redirect to apply or welcome page
        except Exception as e:
            user_identifier = request.user.username if hasattr(request.user, 'username') else "Unknown User"
            logger.error(f"Error in creator_required decorator for user {user_identifier}: {type(e).__name__} - {e}", exc_info=True)
            messages.error(request, "An error occurred while verifying your creator status. Please try again later.")
            return redirect('AudioXApp:home')
    return _wrapped_view
