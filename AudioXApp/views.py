from django.shortcuts import render, redirect
from django.contrib import messages
from .models import User
from django.urls import reverse
from django.db.models import Q
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout

def home(request):
    return render(request, 'homepage.html')

def signup(request):
    if request.method == 'POST':
        # Get data from your existing form
        full_name = request.POST.get('full-name')  # Match the 'name' attributes in your HTML form
        username = request.POST.get('username')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm-password')

        # Basic validation (add more as needed)
        if not full_name or not username or not email or not password or not confirm_password:
            messages.error(request, "Please fill in all required fields.")
            return render(request, 'signup.html')  # Re-render the form with errors

        if password != confirm_password:
            messages.error(request, "Passwords don't match.")
            return render(request, 'signup.html')  # Re-render the form with errors

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
            return redirect('login')  # Redirect to login page

        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, 'signup.html')  # Render the form for GET requests

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
                pass  # User not found by email, try username next

        # If user not found by email, try username
        if not user:
            try:
                user = User.objects.get(username=login_identifier)
            except User.DoesNotExist:
                pass  # User not found by username either

        # If a user is found, check the password
        if user:
            if user.check_password(password):  # Use check_password
                auth_login(request, user)
                messages.success(request, "Logged in successfully!")
                return redirect('home')
            else:
                messages.error(request, "Incorrect password")  # Password doesn't match
        else:
            messages.error(request, "Incorrect email or username")  # User not found

        return render(request, 'login.html')

    return render(request, 'login.html')

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
    auth_logout(request)  # Use the imported auth_logout
    return redirect('home')  # Or any other URL name