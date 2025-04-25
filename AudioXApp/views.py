from django.shortcuts import render, redirect
from django.contrib import messages
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
import ffmpeg  # You might not need this if you aren't doing processing
from bs4 import BeautifulSoup
# from pydub import AudioSegment  # You probably don't need this for simple streaming
from django.contrib.auth.forms import PasswordChangeForm
from io import BytesIO
import audible  # Likely not needed for LibriVox
import feedparser
import json
import requests
from django.urls import reverse
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.db.models import F
from django.core.files.storage import default_storage
from django.utils import timezone
# from AudioXApp.models import Audiobook  # If you use it
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt  # Import this
from django.core.exceptions import SuspiciousOperation
from django.utils.text import slugify  # Import slugify HERE, at the top level
import random  # Import the random module




def signup(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        username = request.POST.get('username')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm-password')
        email_verified = request.POST.get('emailVerified')
        entered_otp = request.POST.get('otp')

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

        if not entered_otp:
            return JsonResponse({'status': 'error', 'message': "OTP is required."})

        try:
            user_otp = request.session.get('otp')
            if not user_otp or entered_otp != user_otp:
                return JsonResponse({'status': 'error', 'message': "Incorrect OTP."})

        except KeyError:
            return JsonResponse({'status': 'error', 'message': "OTP session expired or not set."})

        del request.session['otp']

        try:
            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
                username=username,
                phone_number=phone_number,
                coins=0
            )
            return JsonResponse({'status': 'success', 'message': 'Account created successfully!'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"An error occurred: {e}"})

    return render(request, 'signup.html')


def send_otp(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        otp = request.POST.get('otp')

        print(f"AudioX - send_otp view triggered")
        print(f"   - Email: {email}")
        print(f"   - OTP: {otp}")

        request.session['otp'] = otp

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
            print(f"       - Error Type: {type(e).__name__}")
            print(f"       - Error Message: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})


def login(request):
    if request.method == 'POST':
        login_identifier = request.POST.get('loginIdentifier')
        password = request.POST.get('password')
        user = None

        if '@' in login_identifier:
            try:
                user = User.objects.get(email=login_identifier)
            except User.DoesNotExist:
                pass
        if not user:
            try:
                user = User.objects.get(username=login_identifier)
            except User.DoesNotExist:
                pass
        if user:
            if user.check_password(password):
                auth_login(request, user)
                return JsonResponse({'status': 'success'})
            else:
                return JsonResponse({'status': 'error', 'message': "Incorrect password"}, status=401)
        else:
            return JsonResponse({'status': 'error', 'message': "Incorrect email or username"}, status=401)
    return render(request, 'login.html')


@login_required
def myprofile(request):
    context = {
        'subscription_type': request.user.subscription_type or 'FR',
    }
    return render(request, 'myprofile.html', context)


@login_required
@require_POST
def update_profile(request):
    user = request.user
    print("User:", user)

    if request.content_type.startswith('multipart'):
        print("Profile picture update request (Multipart)")

        if 'profile_pic' in request.FILES:
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
                return JsonResponse({'status': 'error', 'message': f'Error saving profile picture: {e}'}, status=500)

        if 'remove_profile_pic' in request.POST:
            if user.profile_pic:
                default_storage.delete(user.profile_pic.path)
                user.profile_pic = None
                user.save()
                return JsonResponse({'status': 'success', 'message': 'Profile picture removed successfully'})
            else:
                return JsonResponse({'status': 'error', 'message': 'No profile picture to remove'}, status=400)


    elif request.content_type == 'application/json':
        print("Field update request (JSON)")
        try:
            data = json.loads(request.body)
            print("Parsed Data:", data)

            if 'username' in data:
                username = data['username']
                if User.objects.exclude(pk=user.pk).filter(username=username).exists():
                    return JsonResponse({'status': 'error', 'message': 'Username already exists'}, status=400)
                user.username = username

            if 'name' in data:
                user.full_name = data['name']

            if 'email' in data:
                email = data['email']
                if User.objects.exclude(pk=user.pk).filter(email=email).exists():
                    return JsonResponse({'status': 'error', 'message': 'Email already exists'}, status=400)
                user.email = email

            if 'bio' in data:
                user.bio = data['bio']

            try:
                user.save()
                print("Profile updated successfully")
                return JsonResponse({'status': 'success', 'message': 'Profile updated successfully'})
            except Exception as e:
                print("Error saving profile:", e)
                return JsonResponse({'status': 'error', 'message': f'Error saving profile: {e}'}, status=500)

        except json.JSONDecodeError as e:
            print("JSON Decode Error:", e)
            return JsonResponse({'status': 'error', 'message': f'Invalid JSON data: {e}'}, status=400)
    print("Invalid request")
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)


@login_required
def change_password(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)  # Assuming you have a PasswordChangeForm
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            auth_logout(request)
            return JsonResponse({'status': 'success', 'message': 'Password updated successfully! Please log in again.'})
        else:
            errors = {field: error[0] for field, error in form.errors.items()}
            return JsonResponse({'status': 'error', 'message': 'Please correct the errors below.', 'errors': errors}, status=400)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)


def ourteam(request):
    context = {
        'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'
    }
    return render(request, 'ourteam.html', context)


def paymentpolicy(request):
    context = {
        'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'
    }
    return render(request, 'paymentpolicy.html', context)


def privacypolicy(request):
    context = {
        'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'
    }
    return render(request, 'privacypolicy.html', context)


def piracypolicy(request):
    context = {
        'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'
    }
    return render(request, 'piracypolicy.html', context)


def termsandconditions(request):
    context = {
        'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'
    }
    return render(request, 'termsandconditions.html', context)


def aboutus(request):
    context = {
        'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'
    }
    return render(request, 'aboutus.html', context)


def contactus(request):
    context = {
        'subscription_type': request.user.subscription_type or 'FR' if request.user.is_authenticated else 'FR'
    }
    return render(request, 'contactus.html', context)


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

        if password != confirm_password:
            return JsonResponse({'status': 'error', 'message': 'Passwords do not match.'}, status=400)

        if not roles_list:
            return JsonResponse({'status': 'error', 'message': 'Please select at least one role.'}, status=400)
        if Admin.objects.filter(email=email).exists():
            return JsonResponse({'status': 'error', 'message': 'An admin with this email already exists.'}, status=400)
        if Admin.objects.filter(username=username).exists():
            return JsonResponse({'status': 'error', 'message': 'An admin with this username already exists.'}, status=400)

        try:
            roles_string = ','.join(roles_list)
            admin = Admin(email=email, username=username, roles=roles_string)
            admin.set_password(password)
            admin.save()
            return JsonResponse({'status': 'success', 'message': 'Admin account created successfully!', 'redirect_url': reverse('adminlogin')})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'An error occurred: {e}'}, status=500)

    else:
        return render(request, 'adminsignup.html')


def adminlogin(request):
    if request.method == 'POST':
        login_identifier = request.POST.get('username')
        password = request.POST.get('password')

        admin = None
        if '@' in login_identifier:
            try:
                admin = Admin.objects.get(email=login_identifier)
            except Admin.DoesNotExist:
                pass

        if not admin:
            try:
                admin = Admin.objects.get(username=login_identifier)
            except Admin.DoesNotExist:
                pass

        if admin:
            if admin.check_password(password):
                request.session['admin_id'] = admin.adminid
                return JsonResponse({'status': 'success', 'redirect_url': reverse('admindashboard')})
            else:
                return JsonResponse({'status': 'error', 'message': 'Incorrect email/username or password.'}, status=401)
        else:
            return JsonResponse({'status': 'error', 'message': 'Incorrect email/username or password.'}, status=401)

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
            # Audiobook.objects.get_or_create(
            #     title=title,
            #     author=author,
            #     url=link
            # )

        return JsonResponse({"message": "Audiobooks scraped successfully!"})

    return JsonResponse({"error": "Failed to fetch data"}, status=400)


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
        try:
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                print(f"Warning: No entries found for feed: {rss_url}")  # Log a warning
                continue  # Skip to the next feed

            chapters = []
            for entry in feed.entries:
                audio_url = entry.enclosures[0].href if entry.enclosures else None
                chapters.append({
                    "chapter_title": entry.title,
                    "audio_url": audio_url if audio_url else None  # Keep the original LibriVox URL
                })

            title = feed.feed.get('title', 'Unknown')
            cover_image = feed.feed.image.href if hasattr(feed.feed, 'image') and hasattr(feed.feed.image, 'href') else None

            audiobooks.append({
                "title": title,
                "cover_image": f"/fetch_cover_image?url={cover_image}" if cover_image else None,
                "chapters": chapters,
                "first_chapter_audio_url": chapters[0]["audio_url"] if chapters else None
            })
            
            # Log the title and chapter count
            print(f"Fetched {title} with {len(chapters)} chapters.")
            
        except Exception as e:
            print(f"Error parsing feed {rss_url}: {e}")  # Log any errors

    # Log the total number of books after all feeds are processed
    print(f"Total Audiobooks Fetched: {len(audiobooks)}")

    return JsonResponse({"audiobooks": audiobooks})



def home(request):
    audiobooks_response = fetch_audiobooks(request)

    if audiobooks_response.status_code != 200:
        context = {
            "audiobooks": [],
            "subscription_type": "FR",
            "error_message": "Failed to load audiobooks. Please try again later.",
        }
        if request.user.is_authenticated:
            context["subscription_type"] = request.user.subscription_type or "FR"
        return render(request, "home.html", context)

    try:
        audiobooks_data = json.loads(audiobooks_response.content.decode('utf-8'))
    except json.JSONDecodeError:
        context = {
            "audiobooks": [],
            "subscription_type": "FR",
            "error_message": "Failed to load audiobook data. Please try again.",
        }
        if request.user.is_authenticated:
            context["subscription_type"] = request.user.subscription_type or "FR"
        return render(request, "home.html", context)

    # Log the audiobooks data for debugging
    print(f"Audiobooks Data: {audiobooks_data}")

    # Add slugs to the audiobook data
    for book in audiobooks_data["audiobooks"]:
        book['slug'] = slugify(book['title'])  # Create URL-safe slug

    context = {
        "audiobooks": audiobooks_data["audiobooks"],
        "subscription_type": "FR",
    }

    if request.user.is_authenticated:
        context["subscription_type"] = request.user.subscription_type or "FR"

    return render(request, "home.html", context)



def audiobook_detail(request, audiobook_slug):
    """Displays details for a single audiobook."""
    audiobooks_response = fetch_audiobooks(request)  # Fetch all books

    if audiobooks_response.status_code != 200:
        # Handle error (e.g., show an error message)
        return render(request, 'error_page.html', {'message': 'Failed to load audiobooks.'})

    audiobooks_data = json.loads(audiobooks_response.content.decode('utf-8'))
    audiobook = None
    for book in audiobooks_data["audiobooks"]:
        if slugify(book['title']) == audiobook_slug:
            audiobook = book
            break

    if not audiobook:
        # Handle case where audiobook is not found (404)
        return HttpResponse("Audiobook not found", status=404)
        # Or, for a better user experience, use:
        # return render(request, '404.html'), 404  # Create a 404.html template

    context = {
        'audiobook': audiobook,
        'subscription_type': request.user.subscription_type if request.user.is_authenticated else 'FR',
    }
    return render(request, 'audiobook_detail.html', context)

# ... (rest of your views: stream_audio, etc.) ...

@csrf_exempt  # CSRF exemption is generally NOT recommended for production.  Consider proper CSRF handling.
def stream_audio(request):
    audio_url = request.GET.get("url")
    if not audio_url:
        return JsonResponse({"error": "No audio URL provided"}, status=400)

    try:
        # --- Initial request to get headers ---
        initial_response = requests.get(audio_url, stream=True)
        initial_response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        # Get the content type.  Default to audio/mpeg if not provided.
        content_type = initial_response.headers.get('Content-Type', 'audio/mpeg')

        # Check if content type is supported, or use a reasonable default
        if not content_type.startswith('audio/'):
            content_type = 'audio/mpeg'  # A reasonable default for audio

        # --- Calculate skip bytes ---
        #  We *can't* reliably seek within a *streamed* response from requests.
        #  We *must* read and discard the bytes we want to skip.  This is very
        #  important. Seeking only works on local files or servers that VERY
        #  specifically support range requests in a way that requests.get can use.

        # Determine a reasonable bitrate.  This is an *estimate*.  LibriVox uses
        # variable bitrate, so this won't be perfectly accurate, but it'll be
        # close enough for a 15-second skip.  Use a default if we can't get it.
        bitrate_str = initial_response.headers.get('icy-br')  # LibriVox often sends this
        if bitrate_str:
            try:
                bitrate = int(bitrate_str) * 1000  # Convert kbps to bps
            except ValueError:
                bitrate = 128000  # Default to 128kbps
        else:
            bitrate = 128000  # A reasonable default (128 kbps)

        bytes_per_second = bitrate / 8
        skip_bytes = int(bytes_per_second * 15)  # Calculate bytes to skip

        # --- Close the initial connection ---
        initial_response.close()

        # --- New request with Range header (if supported by the server) ---
        headers = {'Range': f'bytes={skip_bytes}-'}
        response = requests.get(audio_url, stream=True, headers=headers)
        response.raise_for_status()  # Check for errors again

        def generate():
            # --- Read and discard initial bytes if Range header wasn't fully honored ---
            bytes_read = 0
            if 'Content-Range' not in response.headers:
                # Server might not support Range, or might have sent from start.
                # Read and discard the bytes.
                for chunk in response.iter_content(chunk_size=8192):
                    bytes_read += len(chunk)
                    if bytes_read >= skip_bytes:
                        # Yield the remaining part of the chunk after skipping.
                        yield chunk[skip_bytes - (bytes_read - len(chunk)):]
                        break  # Stop discarding

            # --- Stream the remaining content ---
            for chunk in response.iter_content(chunk_size=8192):
                yield chunk

        return StreamingHttpResponse(generate(), content_type=content_type)

    except requests.RequestException as e:
        print(f"Error streaming audio: {e}")  # Log the error
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


@login_required
def buycoins(request):  # Corrected function name here
    purchase_history = CoinTransaction.objects.filter(
        user=request.user, transaction_type='purchase'
    ).order_by('-transaction_date')
    context = {
        'purchase_history': purchase_history,
        'subscription_type': request.user.subscription_type or 'FR',  # Add this. Very important
    }

    return render(request, 'buycoins.html', context)


@login_required
@require_POST
def buy_coins(request):
    try:
        data = json.loads(request.body)
        coins = int(data.get('coins'))
        price = float(data.get('price'))

        if not coins or not price:
            return JsonResponse({'status': 'error', 'message': 'Coins and price are required.'}, status=400)

        if coins <= 0 or price <= 0:
            return JsonResponse({'status': 'error', 'message': 'Coins and price must be positive values.'}, status=400)

        user = request.user
        payment_successful = True
        if coins == 100:
            pack_name = "Bronze Pack"
        elif coins == 250:
            pack_name = "Emerald Pack"
        elif coins == 500:
            pack_name = "Gold Pack"
        elif coins == 750:
            pack_name = "Ruby Pack"
        elif coins == 1000:
            pack_name = "Sapphire Pack"
        elif coins == 2000:
            pack_name = "Diamond Pack"
        else:
            pack_name = f"{coins} Coins"

        if payment_successful:
            transaction = CoinTransaction.objects.create(
                user=user,
                transaction_type='purchase',
                amount=coins,
                status='completed',
                pack_name=pack_name,
                price=price
            )

            user.coins = F('coins') + coins
            user.save()
            user.refresh_from_db()

            return JsonResponse({
                'status': 'success',
                'message': f'Successfully purchased {coins} coins!',
                'new_coin_balance': user.coins
            })
        else:
            transaction = CoinTransaction.objects.create(
                user=user,
                transaction_type='purchase',
                amount=coins,
                status='failed',
                pack_name=pack_name,
                price=price
            )
            return JsonResponse({'status': 'error', 'message': 'Invalid request data.'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500)


@login_required
@require_POST  # Important: Only allow POST requests
def gift_coins(request):
    data = json.loads(request.body)  # Receives data from the request body
    sender = request.user
    recipient_identifier = data.get('recipient')  # Gets recipient from the json data
    amount_str = data.get('amount')  # Gets amount from the json data

    try:
        amount = int(amount_str)
        if amount <= 0:
            return JsonResponse({'status': 'error', 'message': 'Gift amount must be positive.'}, status=400)
        if sender.coins < amount:
            return JsonResponse({'status': 'error', 'message': 'Insufficient coins.'}, status=400)

    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Invalid gift amount.'}, status=400)

    try:
        # Try to find the recipient by username or email
        if '@' in recipient_identifier:
            recipient = User.objects.get(email=recipient_identifier)
        else:
            recipient = User.objects.get(username=recipient_identifier)

        if recipient == sender:
            return JsonResponse({'status': 'error', 'message': 'You cannot gift coins to yourself.'}, status=400)

        # Perform the transaction atomically
        with transaction.atomic():
            # Deduct coins from sender
            sender.coins = F('coins') - amount
            sender.save()
            sender.refresh_from_db()  # Refresh to get updated value

            # Add coins to recipient
            recipient.coins = F('coins') + amount
            recipient.save()
            recipient.refresh_from_db()  # also good practice to refresh here

            # Create transaction records
            sent_transaction = CoinTransaction.objects.create(
                user=sender,
                transaction_type='gift_sent',
                amount=amount,
                recipient=recipient,
                status='completed',
                pack_name=None,  # gift doesn't have a pack name
                price=None,  # gift sent doesnt have price
            )
            received_transaction = CoinTransaction.objects.create(
                user=recipient,
                transaction_type='gift_received',
                amount=amount,
                sender=sender,
                status='completed',
                pack_name=None,  # gift doesn't have a pack name
                price=None,  # gift received doesnt have price
            )

        return JsonResponse({
            'status': 'success',
            'message': f'Successfully gifted {amount} coins to {recipient.username}!',  # Improved message
            'new_balance': sender.coins,
            # No need to return the full transaction here.
        })


    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Recipient user not found.'}, status=400)
    except IntegrityError as e:  # Catch database constraint errors
        return JsonResponse({'status': 'error', 'message': f'Database error: {str(e)}'}, status=500)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'An error occurred: {str(e)}'}, status=500)


@login_required
def mywallet(request):
    # Fetch gift history for the *current user*,  but only coin-related transactions
    gift_history = CoinTransaction.objects.filter(
        user=request.user
    ).exclude(
        # Exclude subscription purchases
        transaction_type='purchase',
        pack_name__in=['Monthly Premium Subscription', 'Annual Premium Subscription']
    ).select_related('sender', 'recipient', 'user').order_by('-transaction_date')  # Optimized query

    print("Current User:", request.user)
    print("Gift History:", gift_history)

    context = {
        'user': request.user,
        'gift_history': gift_history,
        'subscription_type': request.user.subscription_type or 'FR',  # Important
    }
    return render(request, 'mywallet.html', context)


@login_required
def subscribe(request):
    context = {
        'subscription_type': request.user.subscription_type or 'FR'  # Always include
    }
    return render(request, 'subscription.html', context)


@login_required
@require_POST
def subscribe_now(request):
    user = request.user
    plan = request.POST.get('plan')

    if plan not in ('monthly', 'annual'):
        messages.error(request, 'Invalid plan selected.')
        return redirect('subscribe')

    if hasattr(user, 'subscription') and user.subscription.is_active():
        messages.error(request, "You already have an active subscription.")
        return redirect('managesubscription')

    payment_successful = True  # Simulate payment

    if payment_successful:
        now = timezone.now()
        if plan == 'monthly':
            end_date = now + timezone.timedelta(days=30)
            price = Decimal('3000')  # Use Decimal for monetary values
        elif plan == 'annual':
            end_date = now + timezone.timedelta(days=365)
            price = Decimal('30000')  # Use Decimal for monetary values
        else:  # Should never happen, but good practice
            messages.error(request, 'Invalid plan selected.')
            return redirect('subscribe')

        try:
            # Try to update existing subscription, if it exists
            subscription = request.user.subscription
            subscription.plan = plan
            subscription.start_date = now
            subscription.end_date = end_date
            subscription.status = 'active'
            subscription.stripe_subscription_id = "sub_FAKE_STRIPE_ID"  # Replace with real ID later
            subscription.stripe_customer_id = "cus_FAKE_STRIPE_ID"  # Replace with real ID later
            subscription.save()

        except Subscription.DoesNotExist:
            # Create a new subscription
            subscription = Subscription.objects.create(
                user=user,
                plan=plan,
                start_date=now,
                end_date=end_date,
                status='active',
                stripe_subscription_id="sub_FAKE",
                stripe_customer_id="cus_FAKE"
            )
        # Create a CoinTransaction for the subscription purchase.
        CoinTransaction.objects.create(
            user=user,
            transaction_type='purchase',
            amount=0,  # Or however you want to represent subscription in coins.
            status='completed',
            pack_name=f"{subscription.get_plan_display()} Subscription",  # Use get_plan_display
            price=price  # Use Decimal for monetary values
        )

        user.subscription_type = 'PR'  # Set user to premium
        user.save()

        messages.success(request, f"You have successfully subscribed to the {plan} plan!")
        return redirect(reverse('subscribe') + '?success=true')  # Redirect with success param
    else:
        messages.error(request, 'Payment failed. Please try again.')
        return redirect('subscribe')


@login_required
def managesubscription(request):
    """Displays subscription details and allows cancellation."""
    try:
        subscription = request.user.subscription
    except Subscription.DoesNotExist:
        subscription = None

    if subscription:
        subscription.update_status()

    # Fetch payment history related to subscriptions
    payment_history = CoinTransaction.objects.filter(
        user=request.user,
        transaction_type='purchase',
        # Correct pack names, matching what's created in subscribe_now
        pack_name__in=['Monthly Premium Subscription', 'Annual Premium Subscription']
    ).order_by('-transaction_date')

    context = {
        'subscription': subscription,
        'subscription_type': request.user.subscription_type or 'FR',
        'payment_history': payment_history,  # Pass the payment history
    }
    return render(request, 'managesubscription.html', context)


@login_required
@require_POST
def cancel_subscription(request):
    """Handles subscription cancellation."""
    try:
        subscription = request.user.subscription
        subscription.status = 'canceled'
        subscription.end_date = timezone.now()
        subscription.save()

        request.user.subscription_type = 'FR'
        request.user.save()

        messages.success(request, "Your subscription has been canceled.")
        return redirect('managesubscription')  # Redirect to the *new* URL

    except Subscription.DoesNotExist:
        messages.error(request, "You do not have an active subscription to cancel.")
        return redirect('managesubscription')
    except Exception as e:
        messages.error(request, f"An error occurred: {e}")
        return redirect('managesubscription')

def forgot_password_view(request):
    return render(request, 'forgotpassword.html')

def handle_forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')

        try:
            user = User.objects.get(email=email)  # Check if the email exists
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email address.')
            return render(request, 'forgotpassword.html') # Re-render with error

        # Generate OTP
        otp = str(random.randint(100000, 999999))  # 6-digit OTP
        request.session['reset_otp'] = otp  # Store OTP in session
        request.session['reset_email'] = email  # Store email for later

        # Send OTP via email
        try:
            send_mail(
                'Password Reset OTP',
                f'Your OTP for password reset is: {otp}',
                settings.EMAIL_HOST_USER,  # Or settings.DEFAULT_FROM_EMAIL
                [email],
                fail_silently=False,
            )
            messages.success(request, 'An OTP has been sent to your email address.')
            # Redirect to a new OTP verification page.  *CRUCIAL*
            return redirect('verify_otp') # Redirect to new route


        except Exception as e:
            messages.error(request, f'Error sending email: {e}')
            return render(request, 'forgotpassword.html')

    # Should not normally reach here with a POST request; good practice
    return render(request, 'forgotpassword.html')

def verify_otp_view(request):
    if request.method == 'POST':
        entered_otp = request.POST.get('otp')
        stored_otp = request.session.get('reset_otp')

        if entered_otp == stored_otp:
            # OTP is correct, proceed to password reset
            del request.session['reset_otp']  # Clear OTP from session
            # Render the password reset form.  *NEW TEMPLATE*
            return render(request, 'reset_password.html')
        else:
            messages.error(request, 'Incorrect OTP.')
            return render(request, 'verify_otp.html') # Re-render OTP form.

    # GET request: show OTP entry form
    return render(request, 'verify_otp.html')

def reset_password_view(request):
  if request.method == 'POST':
    email = request.session.get('reset_email') # Get email from when OTP sent
    new_password = request.POST.get('password')
    confirm_password = request.POST.get('confirm_password')

    if not email:
        messages.error(request, 'Password reset session expired.  Please start again.')
        return redirect('forgot_password')

    if new_password != confirm_password:
        messages.error(request, 'Passwords do not match.')
        return render(request, 'reset_password.html')

    try:
        user = User.objects.get(email=email)
        user.set_password(new_password)
        user.save()
        del request.session['reset_email']  # Clean up the session
        messages.success(request, 'Password reset successfully.  You can now log in.')
        return redirect('login')

    except User.DoesNotExist:
        # This *should* not happen, but is good for extra safety.
        messages.error(request, 'User not found.  Please start the password reset process again.')
        return redirect('forgot_password')
  else:
    return render(request, "reset_password.html")