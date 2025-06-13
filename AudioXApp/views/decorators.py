# AudioXApp/views/decorators.py

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from ..models import Admin, Creator
import logging

logger = logging.getLogger(__name__)

# --- Admin Role Required Decorator ---

def admin_role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            is_admin_flag = request.session.get('is_admin')
            admin_id = request.session.get('admin_id')

            if not is_admin_flag or not admin_id:
                messages.warning(request, "Admin login required.")
                return redirect(reverse('AudioXApp:adminlogin'))

            try:
                admin = Admin.objects.get(adminid=admin_id, is_active=True)
                request.admin_user = admin

                if roles:
                    admin_roles_list = admin.get_roles_list()
                    if 'full_access' not in admin_roles_list and not any(role in admin_roles_list for role in roles):
                        messages.error(request, "You do not have permission to access this specific page.")
                        return redirect(reverse('AudioXApp:admindashboard'))
                
                return view_func(request, *args, **kwargs)

            except Admin.DoesNotExist:
                messages.error(request, "Admin session invalid. Please log in again.")
                request.session.flush()
                return redirect(reverse('AudioXApp:adminlogin'))
            except Exception as e:
                logger.error(f"Error in admin_role_required decorator: {type(e).__name__} - {e}", exc_info=True)
                messages.error(request, "A server error occurred while trying to load the page. Please try again or contact support.")
                return redirect(reverse('AudioXApp:adminlogin'))
        return _wrapped_view
    return decorator

# --- Admin Login Required Decorator ---

def admin_login_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        is_admin_flag = request.session.get('is_admin')
        admin_id = request.session.get('admin_id')

        if not is_admin_flag or not admin_id:
            messages.warning(request, "Please log in as an administrator to access this page.")
            return redirect(reverse('AudioXApp:adminlogin'))

        try:
            admin_user_obj = Admin.objects.get(pk=admin_id, is_active=True)
            request.admin_user = admin_user_obj
            return view_func(request, *args, **kwargs)
        except Admin.DoesNotExist:
            request.session.flush()
            messages.error(request, "Invalid admin session. Please log in again.")
            return redirect(reverse('AudioXApp:adminlogin'))
        except Exception as e:
            logger.error(f"Error in admin_login_required decorator: {type(e).__name__} - {e}", exc_info=True)
            messages.error(request, "An error occurred verifying your admin session.")
            return redirect(reverse('AudioXApp:adminlogin'))
    return _wrapped_view

# --- Creator Required Decorator ---

def creator_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        try:
            creator = Creator.objects.select_related('user').get(user=request.user)
            
            if creator.is_banned:
                messages.error(request, "Your creator account is banned and you cannot access this page.")
                return redirect('AudioXApp:home')
            
            if creator.verification_status != 'approved':
                messages.warning(request, "Your creator profile is not yet approved. Access denied.")
                return redirect('AudioXApp:creator_welcome')
            
            request.creator = creator
            return view_func(request, *args, **kwargs)

        except Creator.DoesNotExist:
            messages.warning(request, "You do not have an active creator profile. Please apply or wait for approval.")
            return redirect('AudioXApp:creator_welcome')
        except Exception as e:
            user_identifier = request.user.username if hasattr(request.user, 'username') else "Unknown User"
            logger.error(f"Error in creator_required decorator for user {user_identifier}: {type(e).__name__} - {e}", exc_info=True)
            messages.error(request, "An error occurred while verifying your creator status. Please try again later.")
            return redirect('AudioXApp:home')
    return _wrapped_view