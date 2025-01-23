from django.shortcuts import render, redirect
from django.contrib import messages
from .models import User
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.templatetags.static import static
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.forms import PasswordChangeForm
from django.views.decorators.http import require_POST
import json


def home(request):
    return render(request, 'homepage.html')

def signup(request):
    if request.method == 'POST':
        # Get data from your existing form
        full_name = request.POST.get('full-name') 
        username = request.POST.get('username')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm-password')

        # Basic validation (add more as needed)
        if not full_name or not username or not email or not password or not confirm_password:
            messages.error(request, "Please fill in all required fields.")
            return render(request, 'signup.html')

        if password != confirm_password:
            messages.error(request, "Passwords don't match.")
            return render(request, 'signup.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists.")
            return render(request, 'signup.html')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, 'signup.html')

        # Create the user
        try:
            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
                username=username,
                phone_number=phone_number,
            )
            messages.success(request, 'Account created successfully!')
            return redirect('login')

        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, 'signup.html')

def send_otp(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        otp = request.POST.get('otp')

        print(f"AudioX - send_otp view triggered")
        print(f"   - Email: {email}")
        print(f"   - OTP: {otp}")

        try:
            send_mail(
                'Your OTP for AudioX Signup',
                f'Your OTP is: {otp}',
                settings.EMAIL_HOST_USER,
                [email],
                fail_silently=False,
            )
            print(f"   - Email sent successfully to {email}")
            return JsonResponse({'status': 'success'})
        except Exception as e:
            print(f"   - Error sending email to {email}:")
            print(f"     - Error Type: {type(e).__name__}")
            print(f"     - Error Message: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

def login(request):
    if request.method == 'POST':
        login_identifier = request.POST.get('loginIdentifier')
        password = request.POST.get('password')

        user = None

        # Try to find the user by email first
        if '@' in login_identifier:
            try:
                user = User.objects.get(email=login_identifier)
            except User.DoesNotExist:
                pass

        # If user not found by email, try username
        if not user:
            try:
                user = User.objects.get(username=login_identifier)
            except User.DoesNotExist:
                pass

        # If a user is found, check the password
        if user:
            if user.check_password(password):
                auth_login(request, user)
                messages.success(request, "")
                return redirect('home')
            else:
                messages.error(request, "Incorrect password")
        else:
            messages.error(request, "Incorrect email or username")

        return render(request, 'login.html')

    return render(request, 'login.html')

@login_required
def myprofile(request):
    return render(request, 'myprofile.html')

@login_required
@require_POST
def update_profile(request):
    user = request.user
    print("User:", user)

    # Check the content type to determine if it's a file upload or JSON
    if request.content_type.startswith('multipart'):
        print("Profile picture update request (Multipart)")

        if 'profile_pic' in request.FILES:
            user.profile_pic = request.FILES['profile_pic']
            print("Profile picture file:", request.FILES['profile_pic'])

            try:
                user.save()
                print("Profile picture updated successfully")
                return JsonResponse({'status': 'success', 'message': 'Profile picture updated successfully'})
            except Exception as e:
                print("Error saving profile picture:", e)
                return JsonResponse({'status': 'error', 'message': f'Error saving profile picture: {e}'})

    elif request.content_type == 'application/json':
        print("Field update request (JSON)")
        try:
            data = json.loads(request.body)
            print("Parsed Data:", data)

            # ... (your existing field update logic: username, full_name, email, bio) ...

            try:
                user.save()
                print("Profile updated successfully")
                return JsonResponse({'status': 'success', 'message': 'Profile updated successfully'})
            except Exception as e:
                print("Error saving profile:", e)
                return JsonResponse({'status': 'error', 'message': f'Error saving profile: {e}'})

        except json.JSONDecodeError as e:
            print("JSON Decode Error:", e)
            return JsonResponse({'status': 'error', 'message': f'Invalid JSON data: {e}'})

    # If neither condition is met
    print("Invalid request")
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

@login_required
def change_password(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            auth_logout(request)
            return JsonResponse({'status': 'success', 'message': 'Password updated successfully! Please log in again.'})
        else:
            errors = {field: error[0] for field, error in form.errors.items()}
            return JsonResponse({'status': 'error', 'message': 'Please correct the errors below.', 'errors': errors})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request'})
    
def ourteam(request):
    return render(request, 'ourteam.html')

def paymentpolicy(request):
    return render(request, 'paymentpolicy.html')

def privacypolicy(request):
    return render(request, 'privacypolicy.html')

def piracypolicy(request):
    return render(request, 'piracypolicy.html')

def termsandconditions(request):
    return render(request, 'termsandconditions.html')

def aboutus(request):
    return render(request, 'aboutus.html')

def contactus(request):
    return render(request, 'contactus.html')

def logout_view(request):
    auth_logout(request)
    return redirect('home')