from django.shortcuts import render, redirect
from django.contrib import messages
from .models import User, Admin, CoinTransaction  # Import CoinTransaction
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash, authenticate
from django.contrib.auth.decorators import login_required
from django.templatetags.static import static
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
import json
from django.urls import reverse
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.db.models import F, Q  # Import Q for complex queries
from django.core.files.storage import default_storage  # For deleting file.
from django.db import transaction  # Import transaction


def home(request):
    return render(request, 'Homepage.html')

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
        print(f"   - Email: {email}")
        print(f"   - OTP: {otp}")

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
    return render(request, 'myprofile.html')

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
        form = PasswordChangeForm(request.user, request.POST)
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
        roles_list = request.POST.getlist('roles')  # Use getlist for multiple select

        if password != confirm_password:
            return JsonResponse({'status': 'error', 'message': 'Passwords do not match.'}, status=400)

        if not roles_list:
            return JsonResponse({'status': 'error', 'message': 'Please select at least one role.'}, status=400)
        if Admin.objects.filter(email=email).exists():
            return JsonResponse({'status':'error', 'message': 'An admin with this email already exists.'}, status=400)
        if Admin.objects.filter(username=username).exists():
            return JsonResponse({'status':'error', 'message': 'An admin with this username already exists.'}, status=400)

        try:
            roles_string = ','.join(roles_list)  # Join roles into a comma-separated string
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
        login_identifier = request.POST.get('username')  # Use a generic identifier
        password = request.POST.get('password')

        admin = None
        # Check if the identifier is an email
        if '@' in login_identifier:
            try:
                admin = Admin.objects.get(email=login_identifier)
            except Admin.DoesNotExist:
                pass  # Try username next

        # If not found by email, try username
        if not admin:
            try:
                admin = Admin.objects.get(username=login_identifier)
            except Admin.DoesNotExist:
                pass

        # Now check password if admin is found
        if admin:
            if admin.check_password(password):
                request.session['admin_id'] = admin.adminid  # Store admin's ID
                return JsonResponse({'status': 'success', 'redirect_url': reverse('admindashboard')})
            else:
                return JsonResponse({'status': 'error', 'message': 'Incorrect email/username or password.'}, status=401)
        else:
            return JsonResponse({'status': 'error', 'message': 'Incorrect email/username or password.'}, status=401)

    return render(request, 'adminlogin.html')

def admindashboard(request):
    return render(request, 'admindashboard.html')

@login_required
def buycoins(request):
    purchase_history = CoinTransaction.objects.filter(
        user=request.user, transaction_type='purchase'
    ).order_by('-transaction_date')

    return render(request, 'buycoins.html', {'purchase_history': purchase_history})


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
        payment_successful = True  # In a real application, integrate with a payment gateway here.
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
    data = json.loads(request.body) #Receives data from the request body
    sender = request.user
    recipient_identifier = data.get('recipient') #Gets recipient from the json data
    amount_str = data.get('amount') #Gets amount from the json data

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
            # Deduct coin
            sender.coins = F('coins') - amount
            sender.save()
            sender.refresh_from_db() # Refresh to get updated value
            # Add coins
            recipient.coins = F('coins') + amount
            recipient.save()

            # Create a record in transaction table for gifting
            CoinTransaction.objects.create(user=sender, transaction_type='gift_sent', amount=amount, recipient=recipient, status='completed')
            CoinTransaction.objects.create(user=recipient, transaction_type='gift_received', amount=amount, sender=sender, status='completed')



        return JsonResponse({'status': 'success', 'message': f'Successfully gifted {amount} coins to {recipient.username}!', 'new_balance': sender.coins})

    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Recipient user not found.'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'An error occurred: {str(e)}'}, status=500)

@login_required
def mywallet(request):
    # Fetch gift history for the *current user*, regardless of sender/recipient
    gift_history = CoinTransaction.objects.filter(
        user=request.user
    ).select_related('sender', 'recipient', 'user').order_by('-transaction_date')  # Optimized query

    print("Current User:", request.user)
    print("Gift History:", gift_history)

    context = {
        'user': request.user,
        'gift_history': gift_history,
    }
    return render(request, 'mywallet.html', context)