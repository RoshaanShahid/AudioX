import random
import requests
import feedparser
import mimetypes
import json
from urllib.parse import urlparse, unquote, quote as url_quote
from datetime import datetime, timedelta
import re 
from bs4 import BeautifulSoup

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
from django.utils import timezone
from decimal import Decimal

from ..models import Audiobook, Chapter, Review, User, AudiobookPurchase, CreatorEarning 
from .utils import _get_full_context

import logging
logger = logging.getLogger(__name__)

# Removed Google Cloud Text-to-Speech (TTS) Setup block

def clean_html(raw_html):
    """Remove HTML tags from a string."""
    if not raw_html:
        return None
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator="\n")
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

def fetch_audiobooks_data():
    cache_key = 'librivox_audiobooks_data_v1_basic' # Reverted to a simpler cache key
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.info("fetch_audiobooks_data: Returning cached LibriVox data.")
        return cached_data

    logger.info("fetch_audiobooks_data: No cached data found. Fetching from LibriVox RSS feeds.")
    rss_feeds = [
        "https://librivox.org/rss/47",
        "https://librivox.org/rss/52",
    ]
    librivox_audiobooks = []
    processed_any_feed_successfully = False
    session = requests.Session()
    user_agent_host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "YourDefaultDomain.com"
    app_name = getattr(settings, "APP_NAME", "AudioXApp") 
    headers = {'User-Agent': f'{app_name}/1.0 LibriVox RSS Fetcher (+http://{user_agent_host})'}

    for rss_url in rss_feeds:
        logger.info(f"fetch_audiobooks_data: Attempting to fetch and process RSS feed: {rss_url}")
        try:
            response = session.get(rss_url, timeout=20, headers=headers)
            response.raise_for_status() 
            feed = feedparser.parse(response.content)

            if feed.bozo:
                bozo_exc_info = f" Bozo Exception: {feed.bozo_exception}" if hasattr(feed, 'bozo_exception') else ""
                logger.warning(f"fetch_audiobooks_data: Feedparser reported an issue (bozo) with RSS feed {rss_url}.{bozo_exc_info}")

            if not feed.entries:
                logger.info(f"fetch_audiobooks_data: No entries found in RSS feed: {rss_url}")
                continue 

            current_feed_chapters_data = []
            for entry_index, entry in enumerate(feed.entries):
                audio_url = None
                if entry.enclosures:
                    for enc in entry.enclosures:
                        if 'audio' in enc.get('type', '').lower():
                            audio_url = enc.href
                            break 
                if not audio_url and entry.links:
                    for link_obj in entry.links:
                        if 'audio' in link_obj.get('type', '').lower() or \
                           any(link_obj.href.lower().endswith(ext) for ext in ['.mp3', '.ogg', '.m4a', '.wav']):
                            audio_url = link_obj.href
                            break
                
                if not audio_url:
                    logger.warning(f"fetch_audiobooks_data: No audio URL found for entry '{entry.get('title', 'N/A')}' in feed {rss_url}.")
                    continue

                chapter_title = entry.get('title', f'Untitled Chapter {entry_index + 1}').replace('"', '').strip()
                duration_str = entry.get('itunes_duration', entry.get('duration', '--:--'))
                
                current_feed_chapters_data.append({
                    "chapter_title": chapter_title,
                    "audio_url": audio_url,
                    "duration": duration_str,
                    # Removed text_content_for_tts and librivox_chapter_id
                })

            if not current_feed_chapters_data:
                logger.info(f"fetch_audiobooks_data: No valid chapters for feed: {rss_url}.")
                continue

            feed_title_raw = feed.feed.get('title', 'Unknown Title')
            title = feed_title_raw.replace('LibriVox', '').strip()
            description = feed.feed.get('summary', feed.feed.get('itunes_summary', 'No description available.'))
            if description and ("<" in description and ">" in description):
                description = clean_html(description)

            cover_image_original_url = None
            if hasattr(feed.feed, 'image') and hasattr(feed.feed.image, 'href'):
                cover_image_original_url = feed.feed.image.href
            elif 'itunes' in feed.feed and 'image' in feed.feed.itunes and hasattr(feed.feed.itunes.image, 'href'):
                cover_image_original_url = feed.feed.itunes.image.href
            
            author = feed.feed.get('author', feed.feed.get('itunes_author', 'Unknown Author'))
            slug = slugify(title) if title != 'Unknown Title' else f'unknown-librivox-book-{random.randint(1000,9999)}'
            if not slug:
                slug = f'unknown-librivox-book-{random.randint(1000,9999)}'
            
            cover_image_proxy_url = None
            if cover_image_original_url:
                try:
                    quoted_image_url = url_quote(cover_image_original_url, safe='')
                    cover_image_proxy_url = reverse('AudioXApp:fetch_cover_image') + f'?url={quoted_image_url}'
                except Exception as url_err:
                    logger.error(f"fetch_audiobooks_data: Error creating proxy URL for cover: {url_err}")
            
            librivox_audiobooks.append({
                "title": title, "description": description,
                "cover_image": cover_image_proxy_url or 'https://placehold.co/300x320/eeeeee/999999?text=Cover+Not+Found',
                "chapters": current_feed_chapters_data, 
                "slug": slug, "is_creator_book": False, "author": author,
                "language": feed.feed.get('language', 'en'),
                "genre": feed.feed.get('category', feed.feed.get('itunes_category', 'General Fiction')),
                "total_views": 0, "average_rating": None, "is_paid": False, "price": Decimal("0.00")
            })
            processed_any_feed_successfully = True
            logger.info(f"fetch_audiobooks_data: Processed audiobook '{title}' from feed {rss_url}")
        except Exception as e:
            logger.error(f"fetch_audiobooks_data: General error processing RSS feed {rss_url}: {e}", exc_info=True)
        
    if processed_any_feed_successfully and librivox_audiobooks:
        logger.info(f"fetch_audiobooks_data: Caching {len(librivox_audiobooks)} LibriVox audiobooks.")
        cache.set(cache_key, librivox_audiobooks, 3600) 
        return librivox_audiobooks
    else:
        logger.warning("fetch_audiobooks_data: No LibriVox audiobooks processed. Returning None.")
        return None

def home(request):
    librivox_audiobooks_data = fetch_audiobooks_data()
    context = _get_full_context(request)
    context["librivox_audiobooks"] = librivox_audiobooks_data if librivox_audiobooks_data else []
    
    creator_books_list = []
    try:
        first_chapter_prefetch = Prefetch(
            'chapters',
            queryset=Chapter.objects.order_by('chapter_order')[:1], 
            to_attr='first_chapter_list_for_home' 
        )
        creator_books_qs = Audiobook.objects.filter(status='PUBLISHED').select_related('creator').prefetch_related(
            first_chapter_prefetch,
            Prefetch('reviews', queryset=Review.objects.select_related('user').order_by('-created_at'))
        ).order_by('-publish_date')[:12]

        for book in creator_books_qs:
            first_chapter_audio_url = None
            first_chapter_title = None
            if hasattr(book, 'first_chapter_list_for_home') and book.first_chapter_list_for_home:
                first_chapter = book.first_chapter_list_for_home[0]
                first_chapter_title = first_chapter.chapter_name
                if first_chapter.audio_file:
                    first_chapter_audio_url = first_chapter.audio_file.url
            
            creator_books_list.append({
                'title': book.title, 'slug': book.slug, 
                'cover_image': book.cover_image, 
                'author': book.author, 
                'creator_name': book.creator.creator_name if book.creator else "Unknown Creator", 
                'first_chapter_audio_url': first_chapter_audio_url,
                'first_chapter_title': first_chapter_title, 
                'is_creator_book': True, 
                'average_rating': book.average_rating, 
                'total_views': book.total_views,
                'is_paid': book.is_paid, 
                'price': book.price,
            })
        context["creator_audiobooks"] = creator_books_list
    except Exception as db_err:
        logger.error(f"Error fetching creator audiobooks for homepage: {db_err}", exc_info=True)
        if not context.get("librivox_audiobooks"): 
            context["error_message"] = "Failed to load any audiobooks. Please try again later."
            
    context['is_creator_book'] = False 
    context['creator_js_context'] = json.dumps({})
    return render(request, "home.html", context)


@login_required
def audiobook_detail(request, audiobook_slug):
    audiobook_data = None
    is_creator_book = False 
    context = _get_full_context(request)
    template_name = 'audiobook_detail.html' 
    chapters_to_display = []
    reviews = [] 
    user_review = None 
    user_review_data = {"has_reviewed": False, "rating": 0, "comment": "", "user_id": None} 
    user_has_purchased = False 
    can_preview_chapters = False
    audiobook_lock_message = None 

    logger.info(f"Audiobook Detail: Attempting to load audiobook with slug: '{audiobook_slug}'")

    try: 
        audiobook_obj = get_object_or_404(
            Audiobook.objects.prefetch_related(
                Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order')),
                Prefetch('reviews', queryset=Review.objects.select_related('user').order_by('-created_at'))
            ).select_related('creator__user'), 
            slug=audiobook_slug
        )
        is_creator_book = True
        template_name = 'audiobook_creator_details.html' 
        audiobook_data = audiobook_obj 

        reviews = audiobook_obj.reviews.all()
        if request.user.is_authenticated:
            user_id_attr = getattr(request.user, 'user_id', request.user.pk)
            user_review_data["user_id"] = user_id_attr
            try:
                user_review = Review.objects.get(audiobook=audiobook_obj, user=request.user)
                user_review_data["has_reviewed"] = True
                user_review_data["rating"] = user_review.rating
                user_review_data["comment"] = user_review.comment or ""
            except Review.DoesNotExist:
                user_review = None

        if audiobook_obj.is_paid:
            if request.user.is_authenticated: 
                user_has_purchased = AudiobookPurchase.objects.filter(user=request.user, audiobook=audiobook_obj, status='COMPLETED').exists()
                
                if not user_has_purchased: 
                    preview_eligible_chapter_exists = audiobook_obj.chapters.filter(is_preview_eligible=True).exists()
                    if request.user.subscription_type == 'PR' and preview_eligible_chapter_exists:
                        can_preview_chapters = True
                        audiobook_lock_message = f"This is a premium audiobook. Purchase for full access (PKR {audiobook_obj.price:.2f}). Premium members can preview eligible chapters."
                    elif preview_eligible_chapter_exists : 
                        can_preview_chapters = True
                        audiobook_lock_message = f"This is a premium audiobook. Purchase for full access (PKR {audiobook_obj.price:.2f}). You can preview eligible chapters."
                    else: 
                        can_preview_chapters = False
                        audiobook_lock_message = f"This is a premium audiobook. Purchase for full access (PKR {audiobook_obj.price:.2f})."
            else: 
                user_has_purchased = False
                can_preview_chapters = audiobook_obj.chapters.filter(is_preview_eligible=True).exists()
                audiobook_lock_message = f"This is a premium audiobook. Login and purchase for full access (PKR {audiobook_obj.price:.2f})."
                if can_preview_chapters:
                    audiobook_lock_message += " You can preview eligible chapters."


        all_db_chapters = audiobook_obj.chapters.all() 
        for chapter_order_index, chapter_obj in enumerate(all_db_chapters): 
            is_accessible = False
            if not audiobook_obj.is_paid or user_has_purchased:
                is_accessible = True
            elif can_preview_chapters and chapter_obj.is_preview_eligible: 
                is_accessible = True
            
            chapters_to_display.append({
                # Removed db_chapter_id, text_content_for_tts, is_creator_chapter
                'audio_url': chapter_obj.audio_file.url if chapter_obj.audio_file else None,
                'chapter_title': chapter_obj.chapter_name,
                'duration': chapter_obj.duration_display,
                'chapter_index': chapter_order_index, 
                'is_accessible': is_accessible, 
                'is_preview_eligible': chapter_obj.is_preview_eligible 
            })

    except Http404: 
        is_creator_book = False 
        template_name = 'audiobook_detail.html'
        librivox_audiobooks_data = fetch_audiobooks_data()
        found_librivox_book = False
        if librivox_audiobooks_data:
            for book_dict_item in librivox_audiobooks_data: 
                if book_dict_item.get('slug') == audiobook_slug:
                    audiobook_data = book_dict_item
                    found_librivox_book = True
                    if 'chapters' in book_dict_item and isinstance(book_dict_item['chapters'], list):
                        for chapter_idx, chapter_info_item in enumerate(book_dict_item['chapters']): 
                            chapters_to_display.append({
                                # Removed db_chapter_id, librivox_chapter_id, text_content_for_tts, is_creator_chapter
                                'audio_url': chapter_info_item.get('audio_url'), 
                                'chapter_title': chapter_info_item.get('chapter_title', 'Untitled Chapter'),
                                'duration': chapter_info_item.get('duration', '--:--'), 
                                'chapter_index': chapter_idx,
                                'is_accessible': True, 
                                'is_preview_eligible': False 
                            })
                    break
        if not found_librivox_book:
            raise Http404("Audiobook not found.")

    context['audiobook'] = audiobook_data 
    context['is_creator_book'] = is_creator_book
    context['chapters_to_display'] = chapters_to_display 
    context['reviews'] = reviews 
    context['user_review'] = user_review 
    context['user_review_data_json'] = json.dumps(user_review_data) 
    context['user_has_purchased'] = user_has_purchased 
    context['can_preview_chapters'] = can_preview_chapters
    context['audiobook_lock_message'] = audiobook_lock_message 
    context['STRIPE_PUBLISHABLE_KEY'] = settings.STRIPE_PUBLISHABLE_KEY if hasattr(settings, 'STRIPE_PUBLISHABLE_KEY') else None
    
    if is_creator_book:
        context['creator_js_context'] = json.dumps({
            'user_review_data': user_review_data,
            'stripe_publishable_key': context.get('STRIPE_PUBLISHABLE_KEY'),
            'audiobook_slug': audiobook_slug,
        })
    else: 
        context['creator_js_context'] = json.dumps({})


    return render(request, template_name, context)


@login_required
@csrf_exempt 
def stream_audio(request):
    original_audio_url_param = request.GET.get("url") 
    # selected_voice_id = request.GET.get("voice", "default") # Voice parameter removed
    
    if not original_audio_url_param:
        logger.error("Stream Audio: 'url' parameter missing.")
        return JsonResponse({"error": "Audio source URL missing"}, status=400)

    # logger.info(f"Stream Audio: Original URL='{original_audio_url_param}', Voice='{selected_voice_id}'") # Modified log
    logger.info(f"Stream Audio: Original URL='{original_audio_url_param}'")


    # --- TTS Logic Block Removed ---
    # The entire 'if selected_voice_id != "default" and google_tts_available:' block is removed.
    # We will now always stream the original audio.

    logger.info(f"Streaming original audio for URL: {original_audio_url_param}")
    try:
        target_audio_url = unquote(original_audio_url_param)
    except Exception as e:
        logger.error(f"Stream Audio: Error decoding 'url' parameter '{original_audio_url_param}': {e}", exc_info=True)
        return JsonResponse({"error": "Invalid audio URL format in 'url' parameter"}, status=400)

    parsed_url = urlparse(target_audio_url)
    is_local_media_path = target_audio_url.startswith(settings.MEDIA_URL) and not parsed_url.scheme and not parsed_url.netloc

    if is_local_media_path:
        try:
            target_audio_url = request.build_absolute_uri(target_audio_url)
            parsed_url = urlparse(target_audio_url) 
            if not parsed_url.scheme or not parsed_url.netloc:
                logger.error(f"Stream Audio: Failed to build absolute URL for local path '{original_audio_url_param}'. Result: '{target_audio_url}'")
                return HttpResponse("Error processing local audio URL.", status=500)
        except Exception as build_err:
            logger.error(f"Stream Audio: Error building absolute URI for '{original_audio_url_param}': {build_err}", exc_info=True)
            return HttpResponse("Error processing local audio URL", status=500)
    elif not parsed_url.scheme or not parsed_url.netloc:
        logger.error(f"Stream Audio: Invalid URL structure for '{target_audio_url}'. Not full URL or known local path.")
        return HttpResponse("Invalid audio URL provided.", status=400)

    try:
        range_header = request.headers.get('Range', None)
        proxy_headers = {'User-Agent': f'{getattr(settings, "APP_NAME", "AudioXApp")}/1.0 Audio Proxy'}
        if range_header:
            proxy_headers['Range'] = range_header
        
        original_audio_response = requests.get(target_audio_url, stream=True, headers=proxy_headers, timeout=(10,30))
        original_audio_response.raise_for_status()
        
        content_type = original_audio_response.headers.get('Content-Type', 'audio/mpeg')
        if not content_type.lower().startswith('audio/'):
            guessed_type, _ = mimetypes.guess_type(target_audio_url)
            content_type = guessed_type if guessed_type and guessed_type.startswith('audio/') else 'audio/mpeg'
            logger.warning(f"Stream Audio: Original content type was not audio. Guessed/Fell back to '{content_type}'.")

        def audio_chunk_generator():
            try:
                for chunk in original_audio_response.iter_content(chunk_size=8192):
                    if chunk: yield chunk
            finally:
                if 'original_audio_response' in locals() and original_audio_response: 
                    original_audio_response.close()

        streaming_http_response = StreamingHttpResponse(audio_chunk_generator(), content_type=content_type)
        if 'Content-Length' in original_audio_response.headers: 
            streaming_http_response['Content-Length'] = original_audio_response.headers['Content-Length']
        if 'Content-Range' in original_audio_response.headers: 
            streaming_http_response['Content-Range'] = original_audio_response.headers['Content-Range']
        streaming_http_response['Accept-Ranges'] = original_audio_response.headers.get('Accept-Ranges', 'bytes')
        streaming_http_response.status_code = original_audio_response.status_code 
        return streaming_http_response

    except requests.exceptions.Timeout as e:
        logger.error(f"Stream Audio: Timeout fetching original audio '{target_audio_url}': {e}", exc_info=True)
        return HttpResponse(f"Audio stream timed out from source.", status=408)
    except requests.exceptions.HTTPError as e:
        logger.error(f"Stream Audio: HTTPError {e.response.status_code} fetching original audio '{target_audio_url}': {e.response.text}", exc_info=True)
        return HttpResponse(f"Error fetching audio from source: Status {e.response.status_code}.", status=e.response.status_code)
    except Exception as e:
        logger.error(f"Stream Audio: Unexpected error streaming original audio '{target_audio_url}': {e}", exc_info=True)
        return HttpResponse("Internal server error during audio streaming.", status=500)


@login_required
@require_POST 
@csrf_protect 
def add_review(request, audiobook_slug):
    try:
        audiobook = get_object_or_404(Audiobook, slug=audiobook_slug) 
        
        if not audiobook.creator: 
            return JsonResponse({'status': 'error', 'message': 'Reviews are not supported for this type of audiobook.'}, status=400)

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
        
        audiobook.refresh_from_db(fields=['average_rating']) 

        new_average_rating_val = audiobook.average_rating 
        
        review_data = {
            'review_id': review.pk, 
            'rating': review.rating, 
            'comment': review.comment or "",
            'user_id': getattr(review.user, 'user_id', review.user.pk), 
            'user_name': review.user.full_name or review.user.username,
            'user_profile_pic': review.user.profile_pic.url if review.user.profile_pic else None,
            'created_at': review.created_at.isoformat(),
            'timesince': timesince(review.created_at) + " ago",
        }
        return JsonResponse({
            'status': 'success', 
            'message': message, 
            'created': created,
            'new_average_rating': new_average_rating_val, 
            'review_data': review_data
        })
    except Audiobook.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid request format.'}, status=400)
    except Exception as e:
        logger.error(f"Error in add_review for slug '{audiobook_slug}': {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred. Please try again.'}, status=500)


@csrf_exempt 
def fetch_cover_image(request):
    image_url = request.GET.get("url")
    if not image_url:
        logger.warning("fetch_cover_image: No image URL provided.")
        return JsonResponse({"error": "No image URL provided"}, status=400)

    logger.info(f"fetch_cover_image: Processing URL: {image_url}")
    parsed_url = urlparse(image_url)
    if not parsed_url.scheme or not parsed_url.netloc:
        if image_url.startswith(settings.MEDIA_URL):
            try:
                image_url = request.build_absolute_uri(image_url)
                logger.info(f"fetch_cover_image: Resolved local media URL to: {image_url}")
                parsed_url = urlparse(image_url)
                if not parsed_url.scheme or not parsed_url.netloc:
                    logger.warning(f"fetch_cover_image: Invalid image URL after attempting to build absolute URI: {image_url}")
                    return HttpResponse("Invalid image URL provided", status=400)
            except Exception as build_err:
                logger.error(f"fetch_cover_image: Error building absolute URI for '{image_url}': {build_err}", exc_info=True)
                return HttpResponse("Error processing local image URL", status=500)
        else: 
            logger.warning(f"fetch_cover_image: Invalid image URL provided (not full and not local media path): {image_url}")
            return HttpResponse("Invalid image URL provided", status=400)
    
    target_image_url = image_url

    try:
        headers = {'User-Agent': f'{getattr(settings, "APP_NAME", "AudioXApp")}/1.0 Image Proxy'}
        response = requests.get(target_image_url, stream=True, timeout=15, headers=headers)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', 'image/jpeg')
        if not content_type.lower().startswith('image/'):
            original_content_type = content_type
            guessed_type, _ = mimetypes.guess_type(target_image_url)
            content_type = guessed_type if guessed_type and guessed_type.startswith('image/') else 'image/jpeg'
            logger.warning(f"fetch_cover_image: Original content type '{original_content_type}' was not image. Guessed/Fell back to '{content_type}'. URL: {target_image_url}")

        streaming_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192), content_type=content_type
        )
        if 'Content-Length' in response.headers:
            streaming_response['Content-Length'] = response.headers['Content-Length']
        return streaming_response
    except requests.exceptions.Timeout:
        logger.error(f"fetch_cover_image: Timeout fetching image from {target_image_url}", exc_info=True)
        return HttpResponse("Image fetch timed out", status=408)
    except requests.exceptions.HTTPError as e:
        logger.error(f"fetch_cover_image: HTTPError {e.response.status_code} fetching image from {target_image_url}", exc_info=True)
        return HttpResponse(f"Error fetching image: {e.response.status_code}", status=e.response.status_code)
    except requests.exceptions.RequestException as e:
        logger.error(f"fetch_cover_image: RequestException fetching image from {target_image_url}: {e}", exc_info=True)
        return HttpResponse("Failed to fetch image", status=502)
    except Exception as e:
        logger.error(f"fetch_cover_image: Unexpected error for {target_image_url}: {e}", exc_info=True)
        return HttpResponse("Internal server error fetching image", status=500)


def ourteam(request):
    context = _get_full_context(request)
    context["is_creator_book"] = False 
    context['creator_js_context'] = json.dumps({})
    return render(request, 'company/ourteam.html', context)

def paymentpolicy(request):
    context = _get_full_context(request)
    context["is_creator_book"] = False
    context['creator_js_context'] = json.dumps({})
    return render(request, 'legal/paymentpolicy.html', context)

def privacypolicy(request):
    context = _get_full_context(request)
    context["is_creator_book"] = False
    context['creator_js_context'] = json.dumps({})
    return render(request, 'legal/privacypolicy.html', context)

def piracypolicy(request): 
    context = _get_full_context(request)
    context["is_creator_book"] = False
    context['creator_js_context'] = json.dumps({})
    return render(request, 'legal/piracypolicy.html', context)

def termsandconditions(request):
    context = _get_full_context(request)
    context["is_creator_book"] = False
    context['creator_js_context'] = json.dumps({})
    return render(request, 'legal/termsandconditions.html', context)

def aboutus(request):
    context = _get_full_context(request)
    context["is_creator_book"] = False
    context['creator_js_context'] = json.dumps({})
    return render(request, 'company/aboutus.html', context)

def contactus(request):
    context = _get_full_context(request)
    context["is_creator_book"] = False
    context['creator_js_context'] = json.dumps({})
    return render(request, 'company/contactus.html', context)
