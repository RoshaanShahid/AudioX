# AudioXApp/views/admin_views/admin_auth_views.py

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect

from ...models import Admin # Relative import from parent directory models
from ..decorators import admin_login_required # Relative import from parent directory views.decorators


# --- Admin Authentication Views ---

def admin_welcome_view(request):
    """Renders the admin welcome page or redirects to dashboard if logged in."""
    if request.session.get('is_admin') and request.session.get('admin_id'):
        return redirect('AudioXApp:admindashboard')
    return render(request, 'admin/admin_welcome.html')

def adminsignup(request):
    """Handles admin signup."""
    if request.method == 'POST':
        email = request.POST.get('email')
        username = request.POST.get('username')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        roles_list = request.POST.getlist('roles')

        errors = {}
        if not email or not username or not password or not confirm_password:
            errors['__all__'] = 'All credential fields are required.'
        if password != confirm_password:
            errors['confirm_password'] = 'Passwords do not match.'
        if not roles_list:
            errors['roles'] = 'Please select at least one role.'
        else:
            valid_roles = [choice[0] for choice in Admin.RoleChoices.choices]
            if not all(role in valid_roles for role in roles_list):
                errors['roles'] = 'Invalid role selected.'

        if email:
            if Admin.objects.filter(email__iexact=email).exists():
                errors['email_prefix'] = 'An admin with this email already exists.'
            try:
                validate_email(email)
            except ValidationError:
                errors['email_prefix'] = 'Invalid email format.'

        if username and Admin.objects.filter(username__iexact=username).exists():
            errors['username_prefix'] = 'An admin with this username already exists.'

        if errors:
            return JsonResponse({
                'status': 'error',
                'message': 'Please correct the errors below.',
                'errors': errors
            }, status=400)

        try:
            roles_string = ','.join(roles_list)
            admin = Admin.objects.create_admin(
                email=email,
                username=username,
                password=password,
                roles=roles_string
            )
            return JsonResponse({
                'status': 'success',
                'message': 'Admin account created successfully!',
                'redirect_url': reverse('AudioXApp:adminlogin')
            })
        except ValueError as ve:
            return JsonResponse({'status': 'error', 'message': str(ve), 'errors': {'__all__': str(ve)}}, status=400)
        except Exception:
            return JsonResponse({
                'status': 'error',
                'message': 'An unexpected server error occurred during registration.',
                'errors': {'__all__': 'Server error during registration.'}
            }, status=500)
    else:
        context = {'role_choices': Admin.RoleChoices.choices}
        return render(request, 'admin/admin_register.html', context)


def adminlogin(request):
    """Handles admin login."""
    if request.method == 'POST':
        login_identifier = request.POST.get('username')
        password = request.POST.get('password')
        admin = None

        if not login_identifier or not password:
            return JsonResponse({'status': 'error', 'message': 'Email/Username and password are required.'}, status=400)

        if '@' in login_identifier:
            try:
                admin_by_email = Admin.objects.filter(email__iexact=login_identifier).first()
                if admin_by_email and admin_by_email.check_password(password):
                    admin = admin_by_email
            except Admin.DoesNotExist:
                pass

        if not admin:
            try:
                admin_by_username = Admin.objects.filter(username__iexact=login_identifier).first()
                if admin_by_username and admin_by_username.check_password(password):
                    admin = admin_by_username
            except Admin.DoesNotExist:
                pass

        if admin:
            if admin.is_active:
                request.session['admin_id'] = admin.adminid
                request.session['admin_username'] = admin.username
                request.session['is_admin'] = True

                try:
                    admin_roles_list = admin.get_roles_list()
                except AttributeError:
                    admin_roles_list = []

                request.session['admin_roles'] = admin_roles_list
                request.session.set_expiry(settings.SESSION_COOKIE_AGE)

                admin.last_login = timezone.now()
                admin.save(update_fields=['last_login'])

                return JsonResponse({'status': 'success', 'redirect_url': reverse('AudioXApp:admindashboard')})
            else:
                return JsonResponse({'status': 'error', 'message': 'This admin account is inactive.'}, status=403)
        else:
            return JsonResponse({'status': 'error', 'message': 'Incorrect email/username or password.'}, status=401)

    if request.session.get('is_admin') and request.session.get('admin_id'):
        return redirect('AudioXApp:admindashboard')

    return render(request, 'admin/admin_login.html')


@admin_login_required
@require_POST
@csrf_protect
def admin_logout_view(request):
    """Logs out the current admin user."""
    try:
        keys_to_delete = ['admin_id', 'admin_username', 'is_admin', 'admin_roles']
        for key in keys_to_delete:
            request.session.pop(key, None)
        messages.success(request, "You have been logged out successfully.")
    except Exception:
        messages.error(request, "An error occurred during logout. Please try again.")
    return redirect('AudioXApp:adminlogin')
