import random
import requests
import feedparser
import mimetypes
import json
from urllib.parse import urlparse
from datetime import datetime, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse, Http404
from django.contrib import messages
from django.core.cache import cache
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, F
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.timesince import timesince
from django.utils import timezone
from decimal import Decimal

from ..models import Audiobook, Chapter, Review, User, AudiobookPurchase, CreatorEarning
from .utils import _get_full_context


def fetch_audiobooks_data():
    cache_key = 'librivox_audiobooks_data_v2'
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    rss_feeds = [
        "https://librivox.org/rss/47",
        "https://librivox.org/rss/52",
    ]
    librivox_audiobooks = []
    fetch_successful = False
    session = requests.Session()
    user_agent_host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "YourDomain.com"
    headers = {'User-Agent': f'AudioXApp/1.0 (+http://{user_agent_host})'}

    for rss_url in rss_feeds:
        try:
            response = session.get(rss_url, timeout=20, headers=headers)
            response.raise_for_status()
            feed = feedparser.parse(response.content)

            if feed.bozo:
                pass # Error handled by general exception or lack of entries

            if not feed.entries:
                continue

            chapters_data = []
            for entry in feed.entries:
                audio_url = None
                if entry.enclosures:
                    for enc in entry.enclosures:
                        if 'audio' in enc.get('type', '').lower():
                            audio_url = enc.href
                            break
                if not audio_url and entry.links:
                    for link in entry.links:
                        if 'audio' in link.get('type', '').lower() or \
                           any(link.href.lower().endswith(ext) for ext in ['.mp3', '.ogg', '.m4a', '.wav']):
                            audio_url = link.href
                            break
                if not audio_url:
                    continue

                chapter_title = entry.title.replace('"', '').strip() if entry.title else 'Untitled Chapter'
                chapters_data.append({"chapter_title": chapter_title, "audio_url": audio_url})

            if not chapters_data:
                continue

            title = feed.feed.get('title', 'Unknown Title').replace('LibriVox', '').strip()
            description = feed.feed.get('summary', feed.feed.get('itunes_summary', 'No description available.'))
            cover_image_original_url = None
            if hasattr(feed.feed, 'image') and hasattr(feed.feed.image, 'href'):
                cover_image_original_url = feed.feed.image.href
            elif 'itunes' in feed.feed and 'image' in feed.feed.itunes and hasattr(feed.feed.itunes.image, 'href'):
                cover_image_original_url = feed.feed.itunes.image.href

            slug = slugify(title) if title != 'Unknown Title' else f'unknown-book-{random.randint(1000,9999)}'
            cover_image_proxy_url = None
            if cover_image_original_url:
                try:
                    quoted_image_url = requests.utils.quote(cover_image_original_url, safe='')
                    cover_image_proxy_url = reverse('AudioXApp:fetch_cover_image') + f'?url={quoted_image_url}'
                except Exception as url_err:
                    pass # Error creating proxy URL

            first_chapter_original_audio_url = chapters_data[0]["audio_url"] if chapters_data else None
            first_chapter_title = chapters_data[0]["chapter_title"] if chapters_data else None

            librivox_audiobooks.append({
                "title": title,
                "description": description,
                "cover_image": cover_image_proxy_url,
                "chapters": chapters_data,
                "first_chapter_audio_url": first_chapter_original_audio_url,
                "first_chapter_title": first_chapter_title,
                "slug": slug,
                "is_creator_book": False,
                "total_views": 0,
                "average_rating": None,
                "is_paid": False,
                "price": Decimal("0.00")
            })
            fetch_successful = True
        except requests.exceptions.RequestException as e:
            pass # Error fetching feed
        except Exception as e:
            pass # Error processing feed

    if fetch_successful:
        cache.set(cache_key, librivox_audiobooks, 3600)
        return librivox_audiobooks
    else:
        return None


def home(request):
    librivox_audiobooks_data = fetch_audiobooks_data()
    context = _get_full_context(request)

    context["librivox_audiobooks"] = []
    context["creator_audiobooks"] = []
    context["error_message"] = None

    if librivox_audiobooks_data is not None:
        context["librivox_audiobooks"] = librivox_audiobooks_data
    else:
        pass # No specific error message here

    try:
        first_chapter_prefetch = Prefetch(
            'chapters',
            queryset=Chapter.objects.order_by('chapter_order'),
            to_attr='first_chapter_list'
        )

        creator_books_qs = Audiobook.objects.filter(status='PUBLISHED').select_related('creator').prefetch_related(
            first_chapter_prefetch,
            Prefetch('reviews', queryset=Review.objects.select_related('user').order_by('-created_at'))
        ).order_by('-publish_date')[:12]

        creator_books_list = []
        for book in creator_books_qs:
            first_chapter_audio_url = None
            first_chapter_title = None
            if hasattr(book, 'first_chapter_list') and book.first_chapter_list:
                first_chapter = book.first_chapter_list[0]
                first_chapter_title = first_chapter.chapter_name
                if first_chapter.audio_file:
                    first_chapter_audio_url = first_chapter.audio_file.url

            creator_books_list.append({
                'title': book.title,
                'slug': book.slug,
                'cover_image': book.cover_image,
                'author': book.author,
                'creator': book.creator,
                'first_chapter_audio_url': first_chapter_audio_url,
                'first_chapter_title': first_chapter_title,
                'is_creator_book': True,
                'average_rating': book.average_rating,
                'total_views': book.total_views,
                'is_paid': book.is_paid,
                'price': book.price,
                'status': book.status,
            })
        context["creator_audiobooks"] = creator_books_list

    except Exception as db_err:
        if not context["librivox_audiobooks"]:
            context["error_message"] = "Failed to load any audiobooks. Please try again later."
            messages.error(request, context["error_message"])

    return render(request, "home.html", context)


@login_required
def audiobook_detail(request, audiobook_slug):
    audiobook_data = None
    is_creator_book = False
    context = _get_full_context(request)
    template_name = 'audiobook_detail.html'
    reviews = []
    user_review = None
    user_review_data = {"has_reviewed": False, "rating": 0, "comment": "", "user_id": None}
    user_has_purchased = False
    can_preview_chapters = False
    chapters_to_display = []
    audiobook_lock_message = None

    try:
        audiobook_obj = get_object_or_404(
            Audiobook.objects.prefetch_related(
                Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order')),
                Prefetch('reviews', queryset=Review.objects.select_related('user').order_by('-created_at'))
            ).select_related('creator'),
            slug=audiobook_slug
        )

        is_creator_book = True
        template_name = 'audiobook_creator_details.html'
        audiobook_data = audiobook_obj

        if is_creator_book and audiobook_obj.status != 'PUBLISHED':
            pass # View count handled by AJAX
        elif is_creator_book:
            pass # View count handled by AJAX

        reviews = audiobook_obj.reviews.all()
        user_review_data["user_id"] = request.user.user_id
        try:
            user_review = Review.objects.get(audiobook=audiobook_obj, user=request.user)
            user_review_data["has_reviewed"] = True
            user_review_data["rating"] = user_review.rating
            user_review_data["comment"] = user_review.comment or ""
        except Review.DoesNotExist:
            user_review = None

        if audiobook_obj.is_paid:
            user_has_purchased = request.user.has_purchased_audiobook(audiobook_obj)
            if not user_has_purchased:
                if request.user.subscription_type == 'PR':
                    can_preview_chapters = True
                    audiobook_lock_message = f"This is a premium audiobook. Purchase for full access (PKR {audiobook_obj.price:.2f}). Premium members can preview the first chapter."
                else:
                    can_preview_chapters = False
                    audiobook_lock_message = f"This is a premium audiobook. Purchase for full access (PKR {audiobook_obj.price:.2f})."

        all_chapters = audiobook_obj.chapters.all()
        for chapter in all_chapters:
            is_accessible = False
            if not audiobook_obj.is_paid or user_has_purchased:
                is_accessible = True
            elif can_preview_chapters and chapter.is_preview_eligible:
                is_accessible = True

            chapters_to_display.append({
                'object': chapter,
                'is_accessible': is_accessible,
                'audio_url': chapter.audio_file.url if chapter.audio_file else None,
                'chapter_title': chapter.chapter_name,
                'is_preview_eligible': chapter.is_preview_eligible
            })

    except Http404:
        librivox_audiobooks_data = fetch_audiobooks_data()
        if librivox_audiobooks_data:
            for book_dict in librivox_audiobooks_data:
                if book_dict.get('slug') == audiobook_slug:
                    audiobook_data = book_dict
                    is_creator_book = False
                    template_name = 'audiobook_detail.html'
                    if 'chapters' in book_dict:
                        for chapter_info in book_dict['chapters']:
                            chapters_to_display.append({
                                'object': None,
                                'chapter_title': chapter_info.get('chapter_title'),
                                'audio_url': chapter_info.get('audio_url'),
                                'is_accessible': True,
                                'is_preview_eligible': False
                            })
                    break
        else:
            messages.error(request, "Failed to load external audiobook data or audiobook not found. Please try again later.")

    if not audiobook_data:
        raise Http404("Audiobook not found or is not available.")

    context['audiobook'] = audiobook_data
    context['is_creator_book'] = is_creator_book
    context['reviews'] = reviews
    context['user_review'] = user_review
    context['user_review_data_json'] = json.dumps(user_review_data)
    context['user_has_purchased'] = user_has_purchased
    context['chapters_to_display'] = chapters_to_display
    context['audiobook_lock_message'] = audiobook_lock_message
    context['STRIPE_PUBLISHABLE_KEY'] = settings.STRIPE_PUBLISHABLE_KEY

    return render(request, template_name, context)


@login_required
@require_POST
@csrf_protect
def add_review(request, audiobook_slug):
    try:
        audiobook = get_object_or_404(Audiobook, slug=audiobook_slug)
        if not hasattr(audiobook, 'creator') or not audiobook.creator:
            return JsonResponse({'status': 'error', 'message': 'Reviews are only supported for creator-uploaded audiobooks.'}, status=400)

        data = json.loads(request.body)
        rating = data.get('rating')
        comment = data.get('comment', '').strip()

        try:
            rating = int(rating)
            if not 1 <= rating <= 5:
                raise ValueError("Rating must be between 1 and 5.")
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid rating value. Please provide a number between 1 and 5.'}, status=400)

        review, created = Review.objects.update_or_create(
            audiobook=audiobook,
            user=request.user,
            defaults={'rating': rating, 'comment': comment}
        )
        message = "Review updated successfully!" if not created else "Review added successfully!"
        new_average_rating = audiobook.average_rating
        review_data = {
            'review_id': review.review_id,
            'rating': review.rating,
            'comment': review.comment or "",
            'user_id': review.user.user_id,
            'user_name': review.user.full_name or review.user.username,
            'user_profile_pic': review.user.profile_pic.url if review.user.profile_pic else None,
            'created_at': review.created_at.isoformat(),
            'timesince': timesince(review.created_at) + " ago",
        }
        return JsonResponse({
            'status': 'success', 'message': message, 'created': created,
            'new_average_rating': new_average_rating, 'review_data': review_data
        })
    except Audiobook.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid request format.'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred. Please try again.'}, status=500)


@csrf_exempt
def fetch_cover_image(request):
    image_url = request.GET.get("url")
    if not image_url:
        return JsonResponse({"error": "No image URL provided"}, status=400)

    parsed_url = urlparse(image_url)
    target_image_url = image_url

    if image_url.startswith(settings.MEDIA_URL) and not all([parsed_url.scheme, parsed_url.netloc]):
        try:
            target_image_url = request.build_absolute_uri(image_url)
        except Exception as build_err:
            return HttpResponse("Error processing local image URL", status=500)
    elif not all([parsed_url.scheme, parsed_url.netloc]):
        return HttpResponse("Invalid image URL provided", status=400)
    else:
        pass # External URL

    try:
        headers = {'User-Agent': 'AudioXApp Image Proxy/1.0'}
        response = requests.get(target_image_url, stream=True, timeout=15, headers=headers)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', 'image/jpeg')
        if not content_type.lower().startswith('image/'):
            guessed_type, _ = mimetypes.guess_type(target_image_url)
            if guessed_type and guessed_type.startswith('image/'):
                content_type = guessed_type
            else:
                content_type = 'image/jpeg'

        streaming_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type=content_type
        )
        if 'Content-Length' in response.headers:
            streaming_response['Content-Length'] = response.headers['Content-Length']
        return streaming_response
    except requests.exceptions.Timeout:
        return HttpResponse("Image fetch timed out", status=408)
    except requests.exceptions.HTTPError as e:
        return HttpResponse(f"Error fetching image: {e.response.status_code}", status=e.response.status_code)
    except requests.exceptions.RequestException as e:
        return HttpResponse("Failed to fetch image", status=502)
    except Exception as e:
        return HttpResponse("Internal server error", status=500)


@login_required
@csrf_exempt
def stream_audio(request):
    audio_url_param = request.GET.get("url")
    if not audio_url_param:
        return JsonResponse({"error": "No audio URL provided"}, status=400)

    target_audio_url = audio_url_param
    parsed_url = urlparse(target_audio_url)
    is_local_media = not parsed_url.scheme and not parsed_url.netloc and target_audio_url.startswith(settings.MEDIA_URL)

    if is_local_media:
        try:
            target_audio_url = request.build_absolute_uri(target_audio_url)
        except Exception as build_err:
            return HttpResponse("Error processing local audio URL", status=500)
    elif not all([parsed_url.scheme, parsed_url.netloc]):
        return HttpResponse("Invalid audio URL provided", status=400)
    else:
        pass # External URL

    try:
        range_header = request.headers.get('Range', None)
        headers = {'User-Agent': 'AudioXApp Audio Proxy/1.0'}
        if range_header:
            headers['Range'] = range_header

        response = requests.get(target_audio_url, stream=True, headers=headers, timeout=30)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', 'audio/mpeg')
        if not content_type.lower().startswith('audio/'):
            guessed_type, _ = mimetypes.guess_type(target_audio_url)
            if guessed_type and guessed_type.startswith('audio/'):
                content_type = guessed_type
            else:
                content_type = 'audio/mpeg'

        def generate():
            try:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            except Exception as e:
                pass # Error during generation
            finally:
                response.close()

        streaming_response = StreamingHttpResponse(generate(), content_type=content_type)
        if 'Content-Range' in response.headers:
            streaming_response['Content-Range'] = response.headers['Content-Range']
        if 'Content-Length' in response.headers:
            streaming_response['Content-Length'] = response.headers['Content-Length']
        streaming_response['Accept-Ranges'] = 'bytes'
        streaming_response.status_code = response.status_code
        return streaming_response

    except requests.exceptions.Timeout:
        return HttpResponse("Audio stream timed out", status=408)
    except requests.exceptions.HTTPError as e:
        return HttpResponse(f"Error fetching audio: {e.response.status_code}", status=e.response.status_code)
    except requests.exceptions.RequestException as e:
        return HttpResponse("Error processing audio stream", status=502)
    except Exception as e:
        return HttpResponse("Internal server error during audio streaming", status=500)


def ourteam(request):
    context = _get_full_context(request)
    return render(request, 'company/ourteam.html', context)

def paymentpolicy(request):
    context = _get_full_context(request)
    return render(request, 'legal/paymentpolicy.html', context)

def privacypolicy(request):
    context = _get_full_context(request)
    return render(request, 'legal/privacypolicy.html', context)

def piracypolicy(request):
    context = _get_full_context(request)
    return render(request, 'legal/piracypolicy.html', context)

def termsandconditions(request):
    context = _get_full_context(request)
    return render(request, 'legal/termsandconditions.html', context)

def aboutus(request):
    context = _get_full_context(request)
    return render(request, 'company/aboutus.html', context)

def contactus(request):
    context = _get_full_context(request)
    return render(request, 'company/contactus.html', context)
