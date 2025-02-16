from django.shortcuts import render, redirect
from django.contrib import messages
from .models import User, Admin
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash, authenticate
from django.contrib.auth.decorators import login_required
from django.templatetags.static import static
from django.http import JsonResponse, HttpResponse , StreamingHttpResponse
from django.contrib.auth.forms import PasswordChangeForm
from django.views.decorators.http import require_POST
import ffmpeg
from pydub import AudioSegment
from io import BytesIO
import audible
import feedparser
import json
import requests
from django.urls import reverse
from django.contrib.auth.hashers import check_password  # Import check_password
from django.core.exceptions import ValidationError  # Import ValidationError
from django.db.models import F
from django.core.files.storage import default_storage #For deleting file.
from bs4 import BeautifulSoup
from .models import Audiobook
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import SuspiciousOperation
#from .fetch_audiobooks import fetch_audiobooks


"""def home(request):
    audiobooks = fetch_audiobooks()
    return render(request, "home.html", {"audiobooks": audiobooks})"""


def signup(request):
    if request.method == 'POST':
        # Get data from your existing form.  Use the CORRECT names.
        full_name = request.POST.get('full_name')
        username = request.POST.get('username')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone')  # Corrected name
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm-password')  # Corrected name
        email_verified = request.POST.get('emailVerified')
        entered_otp = request.POST.get('otp')  # Get the entered OTP

        # Basic validation (add more as needed)
        if not full_name or not username or not email or not password or not confirm_password:
            return JsonResponse({'status': 'error', 'message': "Please fill in all required fields."})

        if password != confirm_password:
            return JsonResponse({'status': 'error', 'message': "Passwords don't match."})

        if User.objects.filter(email=email).exists():
            return JsonResponse({'status': 'error', 'message': "Email already exists."})

        if User.objects.filter(username=username).exists():
            return JsonResponse({'status': 'error', 'message': "Username already exists."})

        if email_verified != 'true':
            return JsonResponse({'status': 'error', 'message': "Email not verified."})
        
        # --- OTP Verification ---
        if not entered_otp:
            return JsonResponse({'status': 'error', 'message': "OTP is required."})

        try:
            user_otp = request.session.get('otp')  # Get the stored OTP.  CRITICAL
            if not user_otp or entered_otp != user_otp:
                return JsonResponse({'status': 'error', 'message': "Incorrect OTP."})

        except KeyError:
            return JsonResponse({'status': 'error', 'message': "OTP session expired or not set."})

        # Clear the OTP from the session after successful verification
        del request.session['otp']


        # Create the user
        try:
            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
                username=username,
                phone_number=phone_number,
                coins = 0 # Initialize coins to 0 upon signup
            )
            # messages.success(request, 'Account created successfully!') # Don't use messages here
            return JsonResponse({'status': 'success', 'message': 'Account created successfully!'})  # Return JSON

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"An error occurred: {e}"})

    return render(request, 'signup.html')  # GET request: show the form

def send_otp(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        otp = request.POST.get('otp')  # Get the OTP from the request

        print(f"AudioX - send_otp view triggered")
        print(f"  - Email: {email}")
        print(f"  - OTP: {otp}")

        # Store the OTP in the session.  VERY IMPORTANT.
        request.session['otp'] = otp

        try:
            send_mail(
                'Your OTP for AudioX Signup',
                f'Your OTP is: {otp}',
                settings.EMAIL_HOST_USER,
                [email],
                fail_silently=False,
            )
            print(f"  - Email sent successfully to {email}")
            return JsonResponse({'status': 'success'})
        except Exception as e:
            print(f"  - Error sending email to {email}:")
            print(f"    - Error Type: {type(e).__name__}")
            print(f"    - Error Message: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})
    
def login(request):
    if request.method == 'POST':
        login_identifier = request.POST.get('loginIdentifier')  # Get the identifier
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
            if user.check_password(password):
                auth_login(request, user)
                # messages.success(request, "Login successful!") # No longer needed - AJAX handles it
                return JsonResponse({'status': 'success'})  # Return success
            else:
                return JsonResponse({'status': 'error', 'message': "Incorrect password"})  # Return JSON
        else:
            return JsonResponse({'status': 'error', 'message': "Incorrect email or username"})  # Return JSON


    return render(request, 'login.html')  # GET request: show login form

@login_required
def myprofile(request):
    return render(request, 'myprofile.html')

@login_required
@require_POST
def update_profile(request):
    user = request.user
    print("User:", user)

    if request.content_type.startswith('multipart'):
        print("Profile picture update request (Multipart)")

        if 'profile_pic' in request.FILES:
            # Delete old profile picture if it exists
            if user.profile_pic:
                default_storage.delete(user.profile_pic.path)

            user.profile_pic = request.FILES['profile_pic']
            print("Profile picture file:", request.FILES['profile_pic'])

            try:
                user.save()
                print("Profile picture updated successfully")
                return JsonResponse({'status': 'success', 'message': 'Profile picture updated successfully'})
            except Exception as e:
                print("Error saving profile picture:", e)
                return JsonResponse({'status': 'error', 'message': f'Error saving profile picture: {e}'})
        
        # Handle profile picture removal
        if 'remove_profile_pic' in request.POST:
            if user.profile_pic:
                # Delete the file from storage
                default_storage.delete(user.profile_pic.path)
                user.profile_pic = None # Set the field to None (null in the database)
                user.save()
                return JsonResponse({'status': 'success', 'message': 'Profile picture removed successfully'})
            else:
                return JsonResponse({'status': 'error', 'message': 'No profile picture to remove'})

    elif request.content_type == 'application/json':
        print("Field update request (JSON)")
        try:
            data = json.loads(request.body)
            print("Parsed Data:", data)

            # Update fields if they are in the parsed data
            if 'username' in data:
                username = data['username']
                if User.objects.exclude(pk=user.pk).filter(username=username).exists():
                    return JsonResponse({'status': 'error', 'message': 'Username already exists'})
                user.username = username

            if 'name' in data:  # Changed 'full_name' to 'name' to match your myprofile.js
                user.full_name = data['name']  # Changed 'full_name' to 'name'

            if 'email' in data:
                email = data['email']
                if User.objects.exclude(pk=user.pk).filter(email=email).exists():
                    return JsonResponse({'status': 'error', 'message': 'Email already exists'})
                user.email = email

            if 'bio' in data:
                user.bio = data['bio']

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

def adminsignup(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        username = request.POST.get('username')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        roles_list = request.POST.getlist('roles')

        # --- Validation ---
        if password != confirm_password:
            return JsonResponse({'status': 'error', 'message': 'Passwords do not match.'})

        if not roles_list:
            return JsonResponse({'status': 'error', 'message': 'Please select at least one role.'})
        if Admin.objects.filter(email=email).exists():
            return JsonResponse({'status':'error', 'message': 'An admin with this email already exists.'})
        if Admin.objects.filter(username=username).exists():
            return JsonResponse({'status':'error', 'message': 'An admin with this username already exists.'})

        # --- Create the Admin object ---
        try:
            roles_string = ','.join(roles_list)
            admin = Admin(email=email, username=username, roles=roles_string)
            admin.set_password(password)
            admin.save()
            # Return success response *with* the redirect URL
            return JsonResponse({'status': 'success', 'message': 'Admin account created successfully!', 'redirect_url': reverse('adminlogin')})


        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'An error occurred: {e}'})

    else:  # GET request
        return render(request, 'adminsignup.html')



    if request.method == 'POST':
        login_identifier = request.POST.get('username')
        password = request.POST.get('password')

        admin = None
        if '@' in login_identifier:
            admin = authenticate(request, email=login_identifier, password=password)
        else:
            admin = authenticate(request, username=login_identifier, password=password)

        if admin:
            login(request, admin)  # Use Django's login function!
            return JsonResponse({'status': 'success', 'redirect_url': reverse('admindashboard')})
        else:
            return JsonResponse({'status': 'error', 'message': 'Incorrect email/username or password.'})

    return render(request, 'adminlogin.html')

def adminlogin(request):
    if request.method == 'POST':
        email = request.POST.get('email')  # Get email from the form
        password = request.POST.get('password')

        try:
            # Find the admin by email
            admin = Admin.objects.get(email=email)

            # Check the password using check_password
            if check_password(password, admin.password):
                # Correct password.  Log the admin in.  We don't use Django's
                # built-in authentication here because it's designed for
                # the User model, not a custom Admin model.
                request.session['admin_id'] = admin.adminid  # Store admin's ID
                return JsonResponse({'status': 'success', 'redirect_url': reverse('admindashboard')})
            else:
                return JsonResponse({'status': 'error', 'message': 'Incorrect email or password.'})

        except Admin.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Incorrect email or password.'})

    return render(request, 'adminlogin.html')

def admindashboard(request):
    return render(request, 'admindashboard.html')


def scrape_audiobooks(request):
    url = "https://librivox.org/search?genre=fiction"  # Example: Fiction genre from LibriVox
    response = requests.get(url)
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        books = soup.find_all("li", class_="book-item")
        
        for book in books:
            title = book.find("h3", class_="book-title").text.strip()
            author = book.find("h4", class_="book-author").text.strip() if book.find("h4", class_="book-author") else "Unknown"
            link = book.find("a")["href"]  # Audiobook URL
            
            # Save to database if not already stored
            Audiobook.objects.get_or_create(
                title=title,
                author=author,
                url=link
            )
        
        return JsonResponse({"message": "Audiobooks scraped successfully!"})
    
    return JsonResponse({"error": "Failed to fetch data"}, status=400)







from django.http import JsonResponse, StreamingHttpResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import SuspiciousOperation
import requests
import feedparser

def fetch_audiobooks(request):  
    rss_feeds = [
        "https://librivox.org/rss/47",  # Count of Monte Cristo
        "https://librivox.org/rss/52",  # Letters of Two Brides
        "https://librivox.org/rss/53",  # Bleak House
        "https://librivox.org/rss/54",  # Penguin Island
        "https://librivox.org/rss/59",  # Crime and Punishment
        "https://librivox.org/rss/60",  # Beyond Good and Evil
        "https://librivox.org/rss/61",  # The Apology
        "https://librivox.org/rss/62"   # Mirza Ghalib
    ]
    
    audiobooks = []
    
    for rss_url in rss_feeds:
        feed = feedparser.parse(rss_url)
        if not feed.entries:
            continue  

        chapters = []
        for entry in feed.entries:  
            audio_url = entry.enclosures[0].href if entry.enclosures else None  
            chapters.append({
                "chapter_title": entry.title,
                "audio_url": f"/stream_audio?url={audio_url}" if audio_url else None  
            })
        
        title = feed.feed.get('title', 'Unknown')
        author = feed.feed.get('author', 'Unknown')
        cover_image = feed.feed.image.href if hasattr(feed.feed, 'image') else None
        
        audiobooks.append({
            "title": title,
            "author": author,
            "cover_image": f"/fetch_cover_image?url={cover_image}" if cover_image else None,
            "chapters": chapters
        })
    
    return JsonResponse({"audiobooks": audiobooks})  

def home(request):
    audiobooks = fetch_audiobooks(request)  
    return render(request, "home.html", {"audiobooks": audiobooks})

@csrf_exempt
def stream_audio(request):
    audio_url = request.GET.get("url")
    if not audio_url:
        return JsonResponse({"error": "No audio URL provided"}, status=400)

    try:
        response = requests.get(audio_url, stream=True)
        if response.status_code != 200:
            return JsonResponse({"error": "Failed to fetch audio"}, status=response.status_code)

        def generate():
            for chunk in response.iter_content(chunk_size=8192):  
                yield chunk
        
        return StreamingHttpResponse(generate(), content_type="audio/mpeg")

    except requests.RequestException:
        return JsonResponse({"error": "Error processing audio"}, status=500)

@csrf_exempt
def fetch_cover_image(request):
    image_url = request.GET.get("url")
    if not image_url:
        return JsonResponse({"error": "No image URL provided"}, status=400)
    
    try:
        response = requests.get(image_url, stream=True)
        if response.status_code == 200:
            return HttpResponse(response.content, content_type=response.headers['Content-Type'])
        else:
            return JsonResponse({"error": "Failed to fetch image"}, status=response.status_code)
    except requests.RequestException:
        raise SuspiciousOperation("Invalid image request")


"""def home(request):
    audiobooks = fetch_audiobooks(request).content.decode("utf-8")
    return render(request, 'home.html', {"audiobooks": audiobooks})"""