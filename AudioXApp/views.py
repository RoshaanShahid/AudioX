from django.shortcuts import render, redirect
from django.contrib import messages
# Ensure User model is imported correctly
from .models import User, Admin, CoinTransaction, Subscription, Audiobook
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash, authenticate
from django.contrib.auth.decorators import login_required
from django.templatetags.static import static
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.db.utils import IntegrityError
from decimal import Decimal
# Removed unused ffmpeg import
# import ffmpeg
# Removed unused BeautifulSoup import
# from bs4 import BeautifulSoup
from django.contrib.auth.forms import PasswordChangeForm
from io import BytesIO
# Removed unused audible import
# import audible
import feedparser
import json
import requests
from django.urls import reverse
# Removed unused check_password import (authenticate handles this)
# from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.db.models import F
from django.core.files.storage import default_storage
from django.utils import timezone
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import SuspiciousOperation
from django.utils.text import slugify
import random
from django.core.validators import validate_email
# --- Import Django Cache ---
from django.core.cache import cache
# Import password hashing utilities if needed for Admin model
from django.contrib.auth.hashers import make_password, check_password
# Import QueryDict for internal POST simulation
from django.http import QueryDict


# --- Signup and Send OTP ---
# ... (signup function remains the same) ...
def signup(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        username = request.POST.get('username')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm-password')
        entered_otp = request.POST.get('otp')

        if not all([full_name, username, email, password, confirm_password, entered_otp]):
            return JsonResponse({'status': 'error', 'message': "Please fill in all required fields, including the OTP."}, status=400)

        if password != confirm_password:
            return JsonResponse({'status': 'error', 'message': "Passwords don't match."}, status=400)

        try:
            validate_email(email)
        except ValidationError:
             return JsonResponse({'status': 'error', 'message': 'Invalid email address format.'}, status=400)

        if User.objects.filter(email=email).exists():
            return JsonResponse({'status': 'error', 'message': "Email already exists."}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({'status': 'error', 'message': "Username already exists."}, status=400)

        stored_otp = request.session.get('otp')
        stored_email_for_otp = request.session.get('otp_email')

        if not stored_otp or not stored_email_for_otp:
             return JsonResponse({'status': 'error', 'message': "OTP session expired or not found. Please request a new OTP."}, status=400)

        if email != stored_email_for_otp:
             return JsonResponse({'status': 'error', 'message': "OTP verification failed (email mismatch). Please request a new OTP."}, status=400)

        if entered_otp != stored_otp:
            return JsonResponse({'status': 'error', 'message': "Incorrect OTP entered."}, status=400)

        try:
            del request.session['otp']
            del request.session['otp_email']
        except KeyError:
            pass

        try:
            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
                username=username,
                phone_number=phone_number if phone_number else None,
                coins=0
            )
            # Automatically set subscription type to Free on signup
            user.subscription_type = 'FR'
            user.save(update_fields=['subscription_type'])
            return JsonResponse({'status': 'success', 'message': 'Account created successfully! You can now log in.'})

        except IntegrityError:
             return JsonResponse({'status': 'error', 'message': 'Username or Email already exists (database constraint).'}, status=400)
        except Exception as e:
             print(f"Error creating user {email}: {e}")
             return JsonResponse({'status': 'error', 'message': f"An unexpected error occurred during account creation. Please try again."}, status=500)

    return render(request, 'signup.html')


# --- Send OTP (Used for Signup & Login 2FA) ---
def send_otp(request, purpose='signup'): # Added purpose parameter
    if request.method == 'POST':
        # Get email from POST data for signup, but allow passing it directly for login
        email = request.POST.get('email') # For login, email is set on request.POST before calling

        if not email:
            return JsonResponse({'status': 'error', 'message': 'Email address is required.'}, status=400)
        try:
            validate_email(email)
        except ValidationError:
             return JsonResponse({'status': 'error', 'message': 'Invalid email address format.'}, status=400)

        # Modify check based on purpose
        if purpose == 'signup':
            if User.objects.filter(email=email).exists():
                return JsonResponse({'status': 'error', 'message': 'This email address is already registered.'}, status=400)
            session_otp_key = 'otp'
            session_email_key = 'otp_email'
            subject = 'Your OTP for AudioX Signup'
            message_body = 'Your One-Time Password (OTP) for AudioX signup is: {otp}\n\nThis OTP is valid for 5 minutes.'

        elif purpose == 'login':
            # For login, the email MUST exist
            try:
                user = User.objects.get(email=email)
                # Check if 2FA is actually enabled for this user before sending
                if not user.is_2fa_enabled:
                    # This case should ideally be caught before calling send_otp for login
                    print(f"Warning: send_otp called for login purpose but 2FA is disabled for {email}")
                    return JsonResponse({'status': 'error', 'message': '2FA is not enabled for this account.'}, status=400)
            except User.DoesNotExist:
                 # Don't reveal email non-existence for login OTP request
                 # Silently pretend to send or just return success
                 print(f"Login OTP requested for non-existent email: {email}")
                 # Return success but don't actually send/store OTP
                 return JsonResponse({'status': 'success', 'message': 'If an account with that email exists and requires 2FA, an OTP has been sent.'})

            session_otp_key = 'login_otp' # Use different session key for login OTP
            session_email_key = 'login_email_pending_2fa' # Use different session key to track user needing OTP verification
            subject = 'Your AudioX Login Verification Code'
            message_body = 'Your One-Time Password (OTP) for AudioX login is: {otp}\n\nThis OTP is valid for 5 minutes.'
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid OTP purpose specified.'}, status=400)


        otp = str(random.randint(100000, 999999))

        request.session[session_otp_key] = otp
        request.session.set_expiry(300) # 5 minutes expiry
        request.session[session_email_key] = email # Store email associated with this OTP attempt

        print(f"AudioX - send_otp view triggered for purpose: {purpose}")
        print(f"  - Email: {email}")
        print(f"  - Generated OTP: {otp} (Storing in session key: {session_otp_key})")

        try:
            send_mail(
                subject,
                message_body.format(otp=otp), # Format message body with OTP
                settings.EMAIL_HOST_USER,
                [email],
                fail_silently=False,
            )
            print(f"  - Email sent successfully to {email} for purpose: {purpose}")
            success_message = 'OTP successfully sent to your email.' if purpose == 'signup' else 'A verification code has been sent to your email.'
            return JsonResponse({'status': 'success', 'message': success_message})

        except Exception as e:
            print(f"  - Error sending email to {email} for purpose {purpose}:")
            print(f"      - Error Type: {type(e).__name__}")
            print(f"      - Error Message: {e}")
            # Generic error message for security
            return JsonResponse({'status': 'error', 'message': 'Failed to send OTP email. Please try again later or contact support.'}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method. Only POST requests are allowed.'}, status=405)


# --- fetch_audiobooks_data (Helper function for fetching/caching) ---
# ... (fetch_audiobooks_data function remains the same) ...
def fetch_audiobooks_data():
    cache_key = 'librivox_audiobooks_data'
    cached_data = cache.get(cache_key)
    if cached_data:
        print("Serving audiobooks from cache.")
        return cached_data

    print("Fetching fresh audiobooks from LibriVox.")
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
    fetch_successful = False

    for rss_url in rss_feeds:
        try:
            response = requests.get(rss_url, timeout=10) # 10 second timeout
            response.raise_for_status()

            feed = feedparser.parse(response.content)
            if not feed.entries:
                print(f"Warning: No entries found for feed: {rss_url}")
                continue

            chapters = []
            for entry in feed.entries:
                audio_url = entry.enclosures[0].href if entry.enclosures else None
                chapters.append({
                    "chapter_title": entry.title,
                    "audio_url": audio_url if audio_url else None
                })

            title = feed.feed.get('title', 'Unknown Title')
            cover_image = feed.feed.image.href if hasattr(feed.feed, 'image') and hasattr(feed.feed.image, 'href') else None
            slug = slugify(title) if title != 'Unknown Title' else f'unknown-book-{random.randint(1000,9999)}'
            cover_image_url = f"/fetch_cover_image/?url={requests.utils.quote(cover_image)}" if cover_image else None


            audiobooks.append({
                "title": title,
                "cover_image": cover_image_url,
                "chapters": chapters,
                "first_chapter_audio_url": chapters[0]["audio_url"] if chapters else None,
                "slug": slug
            })
            fetch_successful = True

        except requests.exceptions.RequestException as e:
             print(f"Error fetching feed {rss_url}: {e}")
        except Exception as e:
             print(f"Error processing feed {rss_url}: {e}")

    if fetch_successful:
        cache.set(cache_key, audiobooks, 3600) # Cache for 1 hour
        return audiobooks
    else:
        return None


# --- Home View (Using the cached data) ---
# ... (home view remains the same) ...
def home(request):
    audiobooks_data = fetch_audiobooks_data()
    context = { "audiobooks": [], "subscription_type": "FR", "error_message": None, }
    if audiobooks_data is None:
        context["error_message"] = "Failed to load audiobooks. Please try again later."
    else:
        context["audiobooks"] = audiobooks_data
    if request.user.is_authenticated:
        context["subscription_type"] = request.user.subscription_type or "FR"
    return render(request, "home.html", context)

# --- Audiobook Detail View (Also uses cached data) ---
# ... (audiobook_detail view remains the same) ...
def audiobook_detail(request, audiobook_slug):
    audiobooks_data = fetch_audiobooks_data()
    audiobook = None
    if audiobooks_data is None:
        return render(request, 'error_page.html', {'message': 'Failed to load audiobook data.'})
    for book in audiobooks_data:
        if book.get('slug') == audiobook_slug:
            audiobook = book
            break
    if not audiobook:
        return HttpResponse("Audiobook not found", status=404)
    context = { 'audiobook': audiobook, 'subscription_type': request.user.subscription_type if request.user.is_authenticated else 'FR', }
    return render(request, 'audiobook_detail.html', context)

# --- fetch_cover_image ---
# ... (fetch_cover_image view remains the same) ...
@csrf_exempt # Consider proper CSRF handling if needed
def fetch_cover_image(request):
    image_url = request.GET.get("url")
    if not image_url:
        return JsonResponse({"error": "No image URL provided"}, status=400)
    try:
        response = requests.get(image_url, stream=True, timeout=10)
        response.raise_for_status()
        return HttpResponse(response.content, content_type=response.headers.get('Content-Type', 'image/jpeg'))
    except requests.exceptions.Timeout:
         print(f"Timeout fetching image: {image_url}")
         return HttpResponse("Image fetch timed out", status=408)
    except requests.exceptions.RequestException as e:
         print(f"Error fetching image {image_url}: {e}")
         return HttpResponse("Failed to fetch image", status=502)

# --- ADDED scrape_audiobooks function ---
# ... (scrape_audiobooks view remains the same) ...
def scrape_audiobooks(request):
    print("scrape_audiobooks view called (placeholder).")
    return JsonResponse({"status": "info", "message": "Scraping endpoint reached (placeholder implementation)."})


# --- Other views (login, myprofile, etc.) ---

# --- Login View (UPDATED for 2FA Check) ---
def login(request):
    if request.method == 'POST':
        login_identifier = request.POST.get('loginIdentifier')
        password = request.POST.get('password')
        user = None

        # Try authenticating with email first, then username
        user = authenticate(request, username=login_identifier, password=password)

        if user:
            # --- 2FA Check ---
            if user.is_2fa_enabled:
                print(f"2FA enabled for {user.email}. Sending OTP.")
                # Prepare data for send_otp (it expects POST-like data)
                # We need to modify the request object temporarily for the internal call
                # Store original POST data
                original_post = request.POST
                # Create mutable QueryDict for internal call
                post_data = QueryDict(mutable=True)
                post_data['email'] = user.email
                request.POST = post_data

                try:
                    otp_response = send_otp(request, purpose='login') # Call send_otp for login
                finally:
                    # IMPORTANT: Restore original POST data after the call
                    request.POST = original_post

                # Check if OTP sending was successful
                if otp_response.status_code == 200:
                    try:
                        otp_data = json.loads(otp_response.content)
                        if otp_data.get('status') == 'success':
                            # Store identifier in session to know who is verifying OTP
                            request.session['2fa_user_email'] = user.email # Store email
                            request.session['2fa_user_id'] = user.pk # Store pk just in case
                            request.session.set_expiry(300) # Keep session alive for OTP entry (5 mins)
                            print(f"OTP sent for 2FA login attempt for {user.email}. Storing email in session.")
                            # Signal frontend that OTP is required
                            # Pass back the email so frontend can display "OTP sent to user@example.com"
                            return JsonResponse({'status': '2fa_required', 'email': user.email})
                        else:
                            # Handle case where send_otp internally failed but returned 200 OK
                            print(f"send_otp failed internally: {otp_data.get('message')}")
                            return JsonResponse({'status': 'error', 'message': otp_data.get('message', 'Failed to send OTP.')}, status=500)
                    except json.JSONDecodeError:
                        print(f"Error decoding send_otp response for {user.email}")
                        return JsonResponse({'status': 'error', 'message': 'Error processing OTP request.'}, status=500)
                else:
                    # Handle HTTP error from send_otp
                    print(f"send_otp returned HTTP error {otp_response.status_code} for {user.email}")
                    # Try to get error message from response if possible
                    error_message = 'Failed to initiate 2FA verification.'
                    try:
                        error_data = json.loads(otp_response.content)
                        if error_data.get('message'):
                            error_message = error_data['message']
                    except json.JSONDecodeError:
                        pass # Keep default error message
                    return JsonResponse({'status': 'error', 'message': error_message}, status=500)

            else:
                # 2FA is disabled, log in directly
                auth_login(request, user)
                # Clear any potential leftover 2FA session keys
                request.session.pop('2fa_user_email', None)
                request.session.pop('2fa_user_id', None)
                request.session.pop('login_otp', None)
                request.session.pop('login_email_pending_2fa', None)
                print(f"User {user.email} logged in successfully (2FA disabled).")
                return JsonResponse({'status': 'success'}) # Redirect handled by frontend
        else:
            # Authentication failed (user not found or wrong password)
             print(f"Login failed for identifier: {login_identifier}")
             return JsonResponse({'status': 'error', 'message': "Incorrect email/username or password."}, status=401)

    # For GET request
    return render(request, 'login.html')


# --- ADDED VIEW for Login OTP Verification ---
@require_POST # Ensure this view only accepts POST requests
def verify_login_otp(request):
    """
    Verifies the OTP submitted during the 2FA login process.
    """
    if not request.headers.get('x-requested-with') == 'XMLHttpRequest':
        # Only allow AJAX requests
        return JsonResponse({'status': 'error', 'message': 'Invalid request type.'}, status=400)

    try:
        data = json.loads(request.body)
        entered_otp = data.get('otp')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)

    if not entered_otp:
        return JsonResponse({'status': 'error', 'message': 'OTP is required.'}, status=400)

    # Retrieve expected OTP and user email from session
    stored_otp = request.session.get('login_otp')
    user_email = request.session.get('login_email_pending_2fa') # Use the correct session key
    user_id = request.session.get('2fa_user_id') # Get user ID as well (set during login check)

    print(f"Verifying login OTP. Email in session: {user_email}, Entered OTP: {entered_otp}, Stored OTP: {stored_otp}") # Debugging

    if not stored_otp or not user_email or not user_id:
        # Session data missing or expired
        return JsonResponse({'status': 'error', 'message': 'Verification session expired or invalid. Please try logging in again.'}, status=400)

    if entered_otp == stored_otp:
        # OTP is correct
        try:
            # Retrieve the user who is trying to log in
            user = User.objects.get(pk=user_id, email=user_email) # Verify both ID and email match

            # Log the user in
            auth_login(request, user)
            print(f"User {user.email} successfully verified OTP and logged in.")

            # Clean up all related session keys immediately after successful login
            request.session.pop('login_otp', None)
            request.session.pop('login_email_pending_2fa', None)
            request.session.pop('2fa_user_email', None) # Clear this too, just in case
            request.session.pop('2fa_user_id', None)

            return JsonResponse({'status': 'success', 'message': 'Verification successful!'})

        except User.DoesNotExist:
            print(f"Error during OTP verification: User not found for email {user_email} / id {user_id}")
            # Should not happen if session data was set correctly, but handle defensively
            return JsonResponse({'status': 'error', 'message': 'User verification failed. Please try again.'}, status=400)
        except Exception as e:
             print(f"Error during final login after OTP verification: {e}")
             return JsonResponse({'status': 'error', 'message': 'An error occurred during login. Please try again.'}, status=500)

    else:
        # Incorrect OTP
        print(f"Incorrect OTP entered for {user_email}. Expected: {stored_otp}, Got: {entered_otp}")
        return JsonResponse({'status': 'error', 'message': 'Invalid verification code.'}, status=400)
# --- End Added View ---


@login_required
def myprofile(request):
    # Pass the 2FA status to the template context
    context = {
        'subscription_type': request.user.subscription_type or 'FR',
        'is_2fa_enabled': request.user.is_2fa_enabled, # Pass 2FA status
    }
    return render(request, 'myprofile.html', context)

@login_required
@require_POST # Ensure only POST requests
def update_profile(request):
    user = request.user
    print(f"update_profile called for user: {user.email}")

    # Handle profile picture updates (multipart form data)
    if request.content_type.startswith('multipart'):
        print("Profile picture update request (Multipart)")
        # --- Profile Picture Upload ---
        if 'profile_pic' in request.FILES:
            # Delete old picture if it exists
            if user.profile_pic:
                try:
                    # Check if file exists before attempting delete
                    if default_storage.exists(user.profile_pic.name):
                        default_storage.delete(user.profile_pic.name)
                        print(f"Deleted old profile picture: {user.profile_pic.name}")
                    else:
                         print(f"Old profile picture file not found, skipping delete: {user.profile_pic.name}")
                except Exception as e:
                    # Log error but continue, maybe file system issue
                    print(f"Error deleting old profile picture {user.profile_pic.name}: {e}")

            # Assign new picture
            user.profile_pic = request.FILES['profile_pic']
            print(f"New profile picture file received: {user.profile_pic.name}")

            try:
                user.save(update_fields=['profile_pic']) # Save only the updated field
                print("Profile picture updated successfully in DB")
                # Return URL for frontend update (include cache buster)
                pic_url = user.profile_pic.url + f'?t={timezone.now().timestamp()}'
                return JsonResponse({'status': 'success', 'message': 'Profile picture updated successfully', 'profile_pic_url': pic_url})
            except Exception as e:
                print(f"Error saving profile picture to DB: {e}")
                return JsonResponse({'status': 'error', 'message': f'Error saving profile picture: {e}'}, status=500)
        # --- Profile Picture Removal ---
        # Check for a specific field indicating removal, e.g., 'remove_profile_pic'
        # This part seems to be handled by the JSON block below in the original code.
        # If you intend to handle removal via multipart, adjust accordingly.
        else:
             return JsonResponse({'status': 'error', 'message': 'No profile picture file found in request.'}, status=400)


    # Handle field updates (JSON data)
    elif request.content_type == 'application/json':
        print("Field update request (JSON)")
        try:
            data = json.loads(request.body)
            print("Parsed Data:", data)
            fields_to_update = [] # Keep track of fields actually changed

            # --- Username Update ---
            if 'username' in data:
                username = data['username'].strip()
                if not username:
                     return JsonResponse({'status': 'error', 'message': 'Username cannot be empty.'}, status=400)
                if user.username != username:
                    if User.objects.exclude(pk=user.pk).filter(username=username).exists():
                        return JsonResponse({'status': 'error', 'message': 'Username already exists'}, status=400)
                    user.username = username
                    fields_to_update.append('username')

            # --- Full Name Update ---
            if 'full_name' in data: # Changed from 'name' to match model field
                full_name = data['full_name'].strip()
                # Allow empty full name? Adjust validation if needed.
                if user.full_name != full_name:
                    user.full_name = full_name
                    fields_to_update.append('full_name')

            # --- Email Update ---
            if 'email' in data:
                email = data['email'].strip()
                if not email:
                     return JsonResponse({'status': 'error', 'message': 'Email cannot be empty.'}, status=400)
                try:
                    validate_email(email) # Validate format
                except ValidationError:
                    return JsonResponse({'status': 'error', 'message': 'Invalid email address format.'}, status=400)

                if user.email != email:
                    if User.objects.exclude(pk=user.pk).filter(email=email).exists():
                        return JsonResponse({'status': 'error', 'message': 'Email already exists'}, status=400)
                    user.email = email
                    fields_to_update.append('email')

            # --- Bio Update ---
            if 'bio' in data:
                bio = data['bio'].strip()
                if user.bio != bio:
                    user.bio = bio
                    fields_to_update.append('bio')

            # --- Profile Picture Removal (via JSON flag) ---
            if data.get('remove_profile_pic') is True:
                if user.profile_pic:
                    try:
                        if default_storage.exists(user.profile_pic.name):
                            default_storage.delete(user.profile_pic.name)
                            print(f"Deleted profile picture via JSON flag: {user.profile_pic.name}")
                        else:
                            print(f"Profile picture file not found for removal: {user.profile_pic.name}")
                        user.profile_pic = None
                        fields_to_update.append('profile_pic')
                    except Exception as e:
                         print(f"Error deleting profile picture {user.profile_pic.name} via JSON flag: {e}")
                         # Decide if this should be a hard error or just logged
                         return JsonResponse({'status': 'error', 'message': f'Error removing profile picture: {e}'}, status=500)
                else:
                     print("Request to remove profile pic via JSON, but none exists.")
                     # No error needed, just ignore if no picture exists

            # --- 2FA Status Update ---
            if 'is_2fa_enabled' in data:
                new_2fa_status = data.get('is_2fa_enabled')
                if isinstance(new_2fa_status, bool): # Ensure it's a boolean
                    if user.is_2fa_enabled != new_2fa_status:
                        user.is_2fa_enabled = new_2fa_status
                        fields_to_update.append('is_2fa_enabled')
                        print(f"2FA status updated to: {user.is_2fa_enabled}")
                else:
                    print(f"Invalid data type for is_2fa_enabled: {type(new_2fa_status)}")
                    return JsonResponse({'status': 'error', 'message': 'Invalid value for 2FA status.'}, status=400)
            # --- End 2FA Update ---

            # Save only if fields were actually changed
            if fields_to_update:
                try:
                    user.save(update_fields=fields_to_update)
                    print(f"Profile fields updated successfully: {fields_to_update}")
                    # Construct appropriate success message based on what was updated
                    if 'is_2fa_enabled' in fields_to_update and len(fields_to_update) == 1:
                         message = f"Two-Factor Authentication {'enabled' if user.is_2fa_enabled else 'disabled'}."
                    elif 'profile_pic' in fields_to_update and data.get('remove_profile_pic') is True and len(fields_to_update) == 1:
                         message = "Profile picture removed successfully."
                    else:
                         message = "Profile updated successfully."
                    return JsonResponse({'status': 'success', 'message': message})
                except Exception as e:
                    print(f"Error saving profile fields {fields_to_update}: {e}")
                    return JsonResponse({'status': 'error', 'message': f'Error saving profile: {e}'}, status=500)
            else:
                # No actual changes detected
                print("No fields needed updating.")
                return JsonResponse({'status': 'success', 'message': 'No changes detected.'})


        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {e}")
            return JsonResponse({'status': 'error', 'message': f'Invalid JSON data: {e}'}, status=400)
        except Exception as e: # Catch unexpected errors
            print(f"Unexpected error processing JSON update: {e}")
            return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred.'}, status=500)

    else:
        # Invalid content type
        print(f"Invalid request content type: {request.content_type}")
        return JsonResponse({'status': 'error', 'message': 'Invalid request format.'}, status=415) # Unsupported Media Type


@login_required
def change_password(request):
    # This view remains largely the same, but ensure it only handles password changes
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user) # Important to keep user logged in
            # Don't log out here, password change shouldn't force logout immediately
            # auth_logout(request)
            return JsonResponse({'status': 'success', 'message': 'Password updated successfully!'}) # Removed login again message
        else:
            errors = {field: error[0] for field, error in form.errors.items()}
            # Customize error message for old password if needed
            if 'old_password' in errors and 'Invalid password' in errors['old_password']:
                 errors['old_password'] = 'Incorrect current password.'
            return JsonResponse({'status': 'error', 'message': 'Please correct the errors below.', 'errors': errors}, status=400)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method or type.'}, status=400)


# --- Static pages ---
# ... (static page views remain the same) ...
def ourteam(request): context = {'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'}; return render(request, 'ourteam.html', context)
def paymentpolicy(request): context = {'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'}; return render(request, 'paymentpolicy.html', context)
def privacypolicy(request): context = {'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'}; return render(request, 'privacypolicy.html', context)
def piracypolicy(request): context = {'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'}; return render(request, 'piracypolicy.html', context)
def termsandconditions(request): context = {'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'}; return render(request, 'termsandconditions.html', context)
def aboutus(request): context = {'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'}; return render(request, 'aboutus.html', context)
def contactus(request): context = {'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'}; return render(request, 'contactus.html', context)

# --- Logout ---
# ... (logout_view remains the same) ...
def logout_view(request): auth_logout(request); return redirect('AudioXApp:home')

# --- Admin views ---
# ... (admin views remain the same) ...
def adminsignup(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        username = request.POST.get('username')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        roles_list = request.POST.getlist('roles')
        if password != confirm_password: return JsonResponse({'status': 'error', 'message': 'Passwords do not match.'}, status=400)
        if not roles_list: return JsonResponse({'status': 'error', 'message': 'Please select at least one role.'}, status=400)
        if Admin.objects.filter(email=email).exists(): return JsonResponse({'status': 'error', 'message': 'An admin with this email already exists.'}, status=400)
        if Admin.objects.filter(username=username).exists(): return JsonResponse({'status': 'error', 'message': 'An admin with this username already exists.'}, status=400)
        try:
            roles_string = ','.join(roles_list)
            admin = Admin(email=email, username=username, roles=roles_string)
            admin.set_password(password) # Use set_password
            admin.save()
            return JsonResponse({'status': 'success', 'message': 'Admin account created successfully!', 'redirect_url': reverse('adminlogin')}) # Ensure 'adminlogin' URL name exists
        except Exception as e: return JsonResponse({'status': 'error', 'message': f'An error occurred: {e}'}, status=500)
    else: return render(request, 'adminsignup.html')

def adminlogin(request):
    if request.method == 'POST':
        login_identifier = request.POST.get('username') # Assuming input name is 'username'
        password = request.POST.get('password')
        admin = None
        if '@' in login_identifier:
            try: admin = Admin.objects.get(email=login_identifier)
            except Admin.DoesNotExist: pass
        if not admin:
            try: admin = Admin.objects.get(username=login_identifier)
            except Admin.DoesNotExist: pass
        if admin:
            # Use check_password method defined in Admin model
            if admin.check_password(password):
                # Use Django's session framework for admin login if desired
                # Or set a specific admin session key
                request.session['admin_id'] = admin.adminid
                request.session['is_admin'] = True # Example flag
                request.session.save() # Ensure session is saved
                return JsonResponse({'status': 'success', 'redirect_url': reverse('admindashboard')}) # Ensure 'admindashboard' URL name exists
            else: return JsonResponse({'status': 'error', 'message': 'Incorrect email/username or password.'}, status=401)
        else: return JsonResponse({'status': 'error', 'message': 'Admin account not found.'}, status=404) # More specific error
    return render(request, 'adminlogin.html')

def admindashboard(request):
    # Add check for admin session
    if not request.session.get('is_admin'):
        # Redirect to admin login if not logged in as admin
        return redirect('adminlogin') # Ensure 'adminlogin' URL name exists
    return render(request, 'admindashboard.html')


# --- Audio Streaming ---
# ... (stream_audio view remains the same) ...
@csrf_exempt
def stream_audio(request):
    audio_url = request.GET.get("url")
    if not audio_url: return JsonResponse({"error": "No audio URL provided"}, status=400)
    try:
        headers = {'Range': 'bytes=0-'}
        response = requests.get(audio_url, stream=True, headers=headers, timeout=15)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', 'audio/mpeg')
        if not content_type.startswith('audio/'): content_type = 'audio/mpeg'
        def generate():
            try:
                for chunk in response.iter_content(chunk_size=8192): yield chunk
            except Exception as e: print(f"Error during audio generation: {e}")
            finally: response.close()
        return StreamingHttpResponse(generate(), content_type=content_type)
    except requests.exceptions.Timeout: print(f"Timeout streaming audio: {audio_url}"); return HttpResponse("Audio stream timed out", status=408)
    except requests.exceptions.RequestException as e: print(f"Error streaming audio {audio_url}: {e}"); return HttpResponse("Error processing audio stream", status=502)


# --- Wallet/Coins/Subscription Views ---
# ... (buycoins, buy_coins, gift_coins, mywallet, subscribe, subscribe_now, managesubscription, cancel_subscription views remain the same) ...
@login_required
def buycoins(request): purchase_history = CoinTransaction.objects.filter(user=request.user, transaction_type='purchase').order_by('-transaction_date'); context = { 'purchase_history': purchase_history, 'subscription_type': request.user.subscription_type or 'FR', }; return render(request, 'buycoins.html', context)
@login_required
@require_POST
def buy_coins(request):
    try:
        data = json.loads(request.body); coins = int(data.get('coins')); price = float(data.get('price'))
        if not coins or not price: return JsonResponse({'status': 'error', 'message': 'Coins and price are required.'}, status=400)
        if coins <= 0 or price <= 0: return JsonResponse({'status': 'error', 'message': 'Coins and price must be positive values.'}, status=400)
        user = request.user; payment_successful = True # Simulate payment
        if coins == 100: pack_name = "Bronze Pack"
        elif coins == 250: pack_name = "Emerald Pack"
        elif coins == 500: pack_name = "Gold Pack"
        elif coins == 750: pack_name = "Ruby Pack"
        elif coins == 1000: pack_name = "Sapphire Pack"
        elif coins == 2000: pack_name = "Diamond Pack"
        else: pack_name = f"{coins} Coins"
        if payment_successful:
            transaction_rec = CoinTransaction.objects.create(user=user, transaction_type='purchase', amount=coins, status='completed', pack_name=pack_name, price=price)
            user.coins = F('coins') + coins; user.save(); user.refresh_from_db()
            return JsonResponse({'status': 'success', 'message': f'Successfully purchased {coins} coins!', 'new_coin_balance': user.coins})
        else:
            CoinTransaction.objects.create(user=user, transaction_type='purchase', amount=coins, status='failed', pack_name=pack_name, price=price)
            return JsonResponse({'status': 'error', 'message': 'Payment failed.'}, status=400)
    except json.JSONDecodeError: return JsonResponse({'status': 'error', 'message': 'Invalid request data.'}, status=400)
    except (ValueError, TypeError): return JsonResponse({'status': 'error', 'message': 'Invalid coin or price value.'}, status=400)
    except Exception as e: print(f"Error buying coins for {request.user}: {e}"); return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500)

@login_required
@require_POST
def gift_coins(request):
    try:
        data = json.loads(request.body); sender = request.user; recipient_identifier = data.get('recipient'); amount_str = data.get('amount')
        if not recipient_identifier or not amount_str: return JsonResponse({'status': 'error', 'message': 'Recipient and amount are required.'}, status=400)
        try:
            amount = int(amount_str)
            if amount <= 0: return JsonResponse({'status': 'error', 'message': 'Gift amount must be positive.'}, status=400)
            # Check balance before transaction starts
            if sender.coins < amount: return JsonResponse({'status': 'error', 'message': 'Insufficient coins.'}, status=400)
        except (ValueError, TypeError): return JsonResponse({'status': 'error', 'message': 'Invalid gift amount.'}, status=400)
        try:
            if '@' in recipient_identifier: recipient = User.objects.get(email=recipient_identifier)
            else: recipient = User.objects.get(username=recipient_identifier)
            if recipient == sender: return JsonResponse({'status': 'error', 'message': 'You cannot gift coins to yourself.'}, status=400)
            with transaction.atomic():
                sender_locked = User.objects.select_for_update().get(pk=sender.pk)
                if sender_locked.coins < amount: raise ValidationError('Insufficient coins.') # Re-check inside transaction
                sender_locked.coins -= amount; sender_locked.save()
                recipient_locked = User.objects.select_for_update().get(pk=recipient.pk)
                recipient_locked.coins += amount; recipient_locked.save()
                CoinTransaction.objects.create(user=sender_locked, transaction_type='gift_sent', amount=amount, recipient=recipient_locked, status='completed')
                CoinTransaction.objects.create(user=recipient_locked, transaction_type='gift_received', amount=amount, sender=sender_locked, status='completed')
            sender.refresh_from_db()
            return JsonResponse({'status': 'success', 'message': f'Successfully gifted {amount} coins to {recipient.username}!', 'new_balance': sender.coins,})
        except User.DoesNotExist: return JsonResponse({'status': 'error', 'message': 'Recipient user not found.'}, status=404)
        except ValidationError as e: return JsonResponse({'status': 'error', 'message': e.message}, status=400)
        except IntegrityError as e: print(f"Integrity error gifting coins from {sender} to {recipient_identifier}: {e}"); return JsonResponse({'status': 'error', 'message': 'Database error during transaction.'}, status=500)
        except Exception as e: print(f"Error gifting coins from {sender} to {recipient_identifier}: {e}"); return JsonResponse({'status': 'error', 'message': f'An error occurred: {str(e)}'}, status=500)
    except json.JSONDecodeError: return JsonResponse({'status': 'error', 'message': 'Invalid request data.'}, status=400)

@login_required
def mywallet(request): gift_history = CoinTransaction.objects.filter(user=request.user).exclude(transaction_type='purchase', pack_name__in=['Monthly Premium Subscription', 'Annual Premium Subscription']).select_related('sender', 'recipient').order_by('-transaction_date'); context = { 'user': request.user, 'gift_history': gift_history, 'subscription_type': request.user.subscription_type or 'FR', }; return render(request, 'mywallet.html', context)
@login_required
def subscribe(request): context = { 'subscription_type': request.user.subscription_type or 'FR' }; return render(request, 'subscription.html', context)
@login_required
@require_POST
def subscribe_now(request):
    user = request.user; plan = request.POST.get('plan')
    if plan not in ('monthly', 'annual'): messages.error(request, 'Invalid plan selected.'); return redirect('AudioXApp:subscribe')
    if Subscription.objects.filter(user=user, status='active').exists(): messages.info(request, "You already have an active subscription."); return redirect('AudioXApp:managesubscription')
    payment_successful = True # Simulate payment
    if payment_successful:
        now = timezone.now()
        if plan == 'monthly': end_date = now + timezone.timedelta(days=30); price = Decimal('3000.00'); pack_name = "Monthly Premium Subscription"
        elif plan == 'annual': end_date = now + timezone.timedelta(days=365); price = Decimal('30000.00'); pack_name = "Annual Premium Subscription"
        else: messages.error(request, 'Invalid plan selected.'); return redirect('AudioXApp:subscribe')
        with transaction.atomic():
            subscription, created = Subscription.objects.update_or_create(user=user, defaults={'plan': plan, 'start_date': now, 'end_date': end_date, 'status': 'active', 'stripe_subscription_id': f"sub_FAKE_{random.randint(1000,9999)}", 'stripe_customer_id': f"cus_FAKE_{random.randint(1000,9999)}"})
            CoinTransaction.objects.create(user=user, transaction_type='purchase', amount=0, status='completed', pack_name=pack_name, price=price)
            user.subscription_type = 'PR'; user.save(update_fields=['subscription_type'])
        messages.success(request, f"You have successfully subscribed to the {subscription.get_plan_display()} plan!")
        return redirect('AudioXApp:managesubscription')
    else: messages.error(request, 'Payment failed. Please try again.'); return redirect('AudioXApp:subscribe')

@login_required
def managesubscription(request):
    subscription = Subscription.objects.filter(user=request.user).first()
    if subscription and subscription.status == 'active':
        if subscription.end_date and subscription.end_date < timezone.now():
            subscription.status = 'expired'; subscription.save()
            request.user.subscription_type = 'FR'; request.user.save(update_fields=['subscription_type'])
    payment_history = CoinTransaction.objects.filter(user=request.user, transaction_type='purchase', pack_name__in=['Monthly Premium Subscription', 'Annual Premium Subscription']).order_by('-transaction_date')
    context = { 'subscription': subscription, 'subscription_type': request.user.subscription_type or 'FR', 'payment_history': payment_history, }
    return render(request, 'managesubscription.html', context)

@login_required
@require_POST
def cancel_subscription(request):
    try:
        subscription = Subscription.objects.get(user=request.user, status='active')
        subscription.status = 'canceled'; subscription.save(update_fields=['status'])
        request.user.subscription_type = 'FR'; request.user.save(update_fields=['subscription_type'])
        messages.success(request, "Your subscription has been canceled.")
    except Subscription.DoesNotExist: messages.warning(request, "You do not have an active subscription to cancel.")
    except Exception as e: print(f"Error canceling subscription for {request.user}: {e}"); messages.error(request, f"An error occurred while canceling your subscription.")
    return redirect('AudioXApp:managesubscription')


# --- Password Reset Views ---
def forgot_password_view(request): return render(request, 'forgotpassword.html')

def handle_forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        if not email:
            messages.error(request, 'Please enter an email address.')
            return render(request, 'forgotpassword.html')
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Security: Don't reveal if email exists. Send message regardless.
            messages.success(request, 'If an account with that email exists, an OTP has been sent.')
            return redirect('AudioXApp:verify_otp') # Redirect to OTP page

        otp = str(random.randint(100000, 999999))
        request.session['reset_otp'] = otp
        request.session['reset_email'] = email
        request.session.set_expiry(300) # OTP expires in 5 minutes

        try:
            send_mail(
                'Password Reset OTP for AudioX',
                f'Your OTP for password reset is: {otp}. It is valid for 5 minutes.',
                settings.EMAIL_HOST_USER,
                [email],
                fail_silently=False,
            )
            messages.success(request, 'If an account with that email exists, an OTP has been sent.')
            return redirect('AudioXApp:verify_otp')
        except Exception as e:
            print(f"Error sending password reset OTP to {email}: {e}")
            messages.error(request, 'There was an error sending the OTP email. Please try again later.')
            return render(request, 'forgotpassword.html') # Show error on the same page

    # For GET request
    return render(request, 'forgotpassword.html')

def verify_otp_view(request):
    if 'reset_email' not in request.session:
        messages.warning(request, 'Password reset session expired or invalid. Please request a new OTP.')
        return redirect('AudioXApp:forgot_password')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp')
        stored_otp = request.session.get('reset_otp')

        if not entered_otp:
            messages.error(request, 'Please enter the OTP.')
            return render(request, 'verify_otp.html')

        if stored_otp is None:
            messages.error(request, 'OTP has expired. Please request a new one.')
            return redirect('AudioXApp:forgot_password')

        if entered_otp == stored_otp:
            request.session['reset_otp_verified'] = True
            # Clear OTP itself now, keep email and verified flag
            if 'reset_otp' in request.session: del request.session['reset_otp']
            return redirect('AudioXApp:reset_password')
        else:
            messages.error(request, 'Incorrect OTP entered.')
            return render(request, 'verify_otp.html')

    # For GET request: show OTP entry form
    return render(request, 'verify_otp.html')

def reset_password_view(request):
    if not request.session.get('reset_otp_verified') or 'reset_email' not in request.session:
        messages.error(request, 'Invalid password reset request. Please start again.')
        return redirect('AudioXApp:forgot_password')

    if request.method == 'POST':
        email = request.session.get('reset_email') # Should exist due to check above
        new_password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if not new_password or not confirm_password:
            messages.error(request, 'Please enter and confirm your new password.')
            return render(request, 'reset_password.html')

        if new_password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'reset_password.html')

        # Add password strength validation if needed here

        try:
            user = User.objects.get(email=email)
            user.set_password(new_password)
            user.save()

            # Clean up session variables after successful reset
            if 'reset_email' in request.session: del request.session['reset_email']
            if 'reset_otp_verified' in request.session: del request.session['reset_otp_verified']
            if 'reset_otp' in request.session: del request.session['reset_otp'] # Just in case

            messages.success(request, 'Your password has been reset successfully. You can now log in.')
            return redirect('AudioXApp:login')

        except User.DoesNotExist:
            # This *should* not happen if email was validated before, but good safety check
            messages.error(request, 'User not found. Please start the password reset process again.')
            # Clean up session
            if 'reset_email' in request.session:
                del request.session['reset_email']
            if 'reset_otp_verified' in request.session:
                del request.session['reset_otp_verified']
            # *** CORRECTED INDENTATION FOR THIS BLOCK ***
            return redirect('AudioXApp:forgot_password') # Corrected indentation

        except Exception as e:
            print(f"Error resetting password for {email}: {e}")
            messages.error(request, 'An unexpected error occurred while resetting your password.')
            return render(request, 'reset_password.html') # Show error on reset page

    # For GET request: show the password reset form
    return render(request, "reset_password.html")
