import random
import requests
import feedparser
import mimetypes
import json
from urllib.parse import urlparse
from decimal import Decimal
from datetime import datetime # For review timestamps

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse, Http404
from django.contrib import messages
from django.core.cache import cache
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Avg # Avg for potential use in rating, Prefetch is used
from django.conf import settings
from django.core.exceptions import SuspiciousOperation # Used in stream_audio, fetch_cover_image
from django.utils.timesince import timesince # Used in add_review

# Assuming 'views' is a subfolder in your app, '..' is correct for models.
# e.g., your_app/views/contentview.py and your_app/models.py
from ..models import Audiobook, Chapter, Review, User, AudiobookPurchase, CreatorEarning
# Assuming utils.py is in the same directory as contentview.py (e.g., your_app/views/utils.py)
from .utils import _get_full_context


def fetch_audiobooks_data():
    """
    Fetches audiobook data from LibriVox RSS feeds and Archive.org by genre and language.
    Caches the results.
    """
    cache_key = 'librivox_archive_audiobooks_data_v5' 
    cached_data = cache.get(cache_key)
    if cached_data:
        print(f"CACHE HIT: Using cached data for audiobooks (key: {cache_key}).")
        return cached_data

    print(f"CACHE MISS: Fetching fresh data for audiobooks (key: {cache_key})...")
    librivox_audiobooks = []
    archive_genre_audiobooks = {}
    archive_language_audiobooks = {} 
    fetch_successful = False 

    # --- Fetch from LibriVox RSS Feeds ---
    rss_feeds = [
        "https://librivox.org/rss/47", "https://librivox.org/rss/52",
        "https://librivox.org/rss/53", "https://librivox.org/rss/54",
        "https://librivox.org/rss/59", "https://librivox.org/rss/60",
        "https://librivox.org/rss/61", "https://librivox.org/rss/62"
    ]
    session = requests.Session()
    user_agent_host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "YourDomain.com"
    headers = {'User-Agent': f'AudioXApp/1.0 (+http://{user_agent_host})'}
    # Increased timeout for RSS feeds
    rss_timeout = 45 # seconds

    for rss_url in rss_feeds:
        try:
            print(f"Fetching LibriVox RSS feed: {rss_url} with timeout {rss_timeout}s")
            response = session.get(rss_url, timeout=rss_timeout, headers=headers)
            response.raise_for_status()
            feed = feedparser.parse(response.content)

            if feed.bozo:
                print(f"Bozo feed detected for {rss_url}: {feed.bozo_exception}")

            if not feed.entries:
                print(f"No entries found in RSS feed: {rss_url}")
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
                    # print(f"No audio URL found for entry in {rss_url}: {entry.title}")
                    continue

                chapter_title = entry.title.replace('"', '').strip() if entry.title else 'Untitled Chapter'
                chapters_data.append({"chapter_title": chapter_title, "audio_url": audio_url})

            if not chapters_data:
                print(f"No chapters with audio found for audiobook in {rss_url}")
                continue

            title = feed.feed.get('title', 'Unknown Title').replace('LibriVox', '').strip()
            description = feed.feed.get('summary', feed.feed.get('itunes_summary', 'No description available.'))

            cover_image_original_url = None
            if hasattr(feed.feed, 'image') and hasattr(feed.feed.image, 'href'):
                cover_image_original_url = feed.feed.image.href
            elif hasattr(feed.feed, 'image') and hasattr(feed.feed.image, 'url'):
                cover_image_original_url = feed.feed.image.url
            elif 'itunes' in feed.feed and hasattr(feed.feed.itunes, 'image') and hasattr(feed.feed.itunes.image, 'href'):
                cover_image_original_url = feed.feed.itunes.image.href
            elif 'image' in feed.feed and isinstance(feed.feed.image, str):
                cover_image_original_url = feed.feed.image
            
            if not cover_image_original_url:
                for entry_img in feed.entries: 
                    if hasattr(entry_img, 'links'):
                        for link in entry_img.links:
                            if 'image' in link.get('type', '').lower() or any(link.href.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                                cover_image_original_url = link.href
                                break
                        if cover_image_original_url: break
                    if hasattr(entry_img, 'enclosures'):
                        for enc in entry_img.enclosures:
                            if 'image' in enc.get('type', '').lower() or any(enc.href.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                                cover_image_original_url = enc.href
                                break
                        if cover_image_original_url: break
                    if cover_image_original_url: break


            slug = slugify(title) if title and title != 'Unknown Title' else f'unknown-librivox-book-{random.randint(1000,9999)}'
            
            cover_image_proxy_url = None
            if cover_image_original_url:
                try:
                    quoted_image_url = requests.utils.quote(cover_image_original_url, safe='')
                    cover_image_proxy_url = reverse('AudioXApp:fetch_cover_image') + f'?url={quoted_image_url}'
                except Exception as url_err:
                    print(f"Error creating proxy URL for {cover_image_original_url}: {url_err}")

            first_chapter_original_audio_url = chapters_data[0]["audio_url"] if chapters_data else None
            first_chapter_title = chapters_data[0]["chapter_title"] if chapters_data else None

            librivox_audiobooks.append({
                "source": "librivox", "title": title, "description": description,
                "cover_image": cover_image_proxy_url, "chapters": chapters_data,
                "first_chapter_audio_url": first_chapter_original_audio_url,
                "first_chapter_title": first_chapter_title, "slug": slug,
                "is_creator_book": False, "total_views": 0, "average_rating": None,
                "is_paid": False, "price": Decimal("0.00")
            })
            fetch_successful = True
        except requests.exceptions.Timeout as e: # More specific timeout handling
            print(f"TIMEOUT error fetching RSS feed {rss_url}: {e}")
        except requests.exceptions.RequestException as e:
            print(f"RequestException error fetching RSS feed {rss_url}: {e}")
        except Exception as e:
            print(f"Generic error processing RSS feed {rss_url}: {e}")

    # --- Fetch from Archive.org by Genre and Language ---
    base_url = "https://archive.org/advancedsearch.php"
    search_terms = [
        "Fiction", "Mystery", "Thriller", "Science Fiction",
        "Fantasy", "Romance", "Biography", "History",
        "Self-Help", "Business",
        "Urdu", "Punjabi", "Sindhi" 
    ]
    archive_timeout = 30 # Timeout for Archive.org API calls

    for term in search_terms:
        params = {
            "q": f'subject:"{term}" AND collection:librivoxaudio AND mediatype:audio',
            "fl[]": ["identifier", "title", "creator", "description", "subject"],
            "rows": 10, "output": "json"
        }
        try:
            print(f"Fetching Archive.org term: '{term}' with timeout {archive_timeout}s")
            response = session.get(base_url, params=params, timeout=archive_timeout, headers=headers)
            response.raise_for_status()
            data = response.json()
            docs = data.get('response', {}).get('docs', [])
            audiobooks_for_term = []

            for doc in docs:
                identifier = doc.get('identifier')
                title = doc.get('title', 'Unknown Title')
                creator = doc.get('creator', 'Unknown Author')
                description = doc.get('description', 'No description available.')
                subjects = doc.get('subject', [])

                if not identifier: continue

                meta_url = f"https://archive.org/metadata/{identifier}"
                # Using the same archive_timeout for metadata call
                meta_resp = session.get(meta_url, timeout=archive_timeout, headers=headers) 
                meta_resp.raise_for_status()
                meta_data = meta_resp.json()
                files = meta_data.get("files", [])
                chapters = []

                for f_item in files: 
                    if f_item.get("format") in ["VBR MP3", "MP3"] and "name" in f_item:
                        chapter_title = f_item.get("title", f_item.get("name", 'Untitled Chapter')).replace('"', '').strip()
                        chapters.append({
                            "chapter_title": chapter_title,
                            "audio_url": f"https://archive.org/download/{identifier}/{requests.utils.quote(f_item['name'])}"
                        })
                if not chapters: continue

                slug = slugify(title) if title and title != 'Unknown Title' else f'unknown-archive-{term.lower().replace(" ", "-")}-book-{random.randint(1000,9999)}'


                book_data = {
                    "source": "archive", "title": title, "description": description,
                    "author": creator, "cover_image": f"https://archive.org/services/img/{identifier}",
                    "chapters": chapters,
                    "first_chapter_audio_url": chapters[0]["audio_url"] if chapters else None,
                    "first_chapter_title": chapters[0]["chapter_title"] if chapters else None,
                    "slug": slug, "is_creator_book": False, "total_views": 0,
                    "average_rating": None, "is_paid": False, "price": Decimal("0.00"),
                    "subjects": subjects
                }
                audiobooks_for_term.append(book_data)

            if audiobooks_for_term:
                if term in ["Urdu", "Punjabi", "Sindhi"]:
                    archive_language_audiobooks[term] = audiobooks_for_term
                else:
                    archive_genre_audiobooks[term] = audiobooks_for_term
                fetch_successful = True
        except requests.exceptions.Timeout as e: # More specific timeout handling
            print(f"TIMEOUT error fetching term '{term}' from Archive.org: {e}")
        except requests.exceptions.RequestException as e:
            print(f"RequestException error fetching term '{term}' from Archive.org: {e}")
        except Exception as e:
            print(f"Generic error processing term '{term}' data from Archive.org: {e}")

    combined_data = {
        "librivox_audiobooks": librivox_audiobooks,
        "archive_genre_audiobooks": archive_genre_audiobooks,
        "archive_language_audiobooks": archive_language_audiobooks
    }

    if fetch_successful:
        print(f"CACHE SET: Storing fetched data in cache (key: {cache_key}, duration: 3600s).")
        cache.set(cache_key, combined_data, 3600) # Cache for 1 hour
        return combined_data
    else:
        print(f"FETCH UNSUCCESSFUL: No new data to cache. Returning potentially partial or None.")
        if librivox_audiobooks or archive_genre_audiobooks or archive_language_audiobooks:
            return combined_data # Return whatever was fetched
        else:
            return None # Indicate complete failure to fetch anything


@require_GET
def api_audiobooks(request):
    """API endpoint to get cached audiobook data."""
    data = fetch_audiobooks_data()
    if data is not None:
        return JsonResponse(data, safe=False)
    else:
        return JsonResponse({"error": "Failed to fetch audiobook data."}, status=500)


def home(request):
    """Renders the home page with audiobooks."""
    audiobook_data = fetch_audiobooks_data()
    context = _get_full_context(request) 

    context["librivox_audiobooks"] = []
    context["archive_genre_audiobooks"] = {}
    context["archive_language_audiobooks"] = {} 
    context["creator_audiobooks"] = []
    context["error_message"] = None

    if audiobook_data is not None:
        context["librivox_audiobooks"] = audiobook_data.get("librivox_audiobooks", [])
        context["archive_genre_audiobooks"] = audiobook_data.get("archive_genre_audiobooks", {})
        context["archive_language_audiobooks"] = audiobook_data.get("archive_language_audiobooks", {})
    else:
        # This error message will be set if fetch_audiobooks_data returns None (complete failure)
        if not context.get("librivox_audiobooks") and \
           not context.get("archive_genre_audiobooks") and \
           not context.get("archive_language_audiobooks"): # Check all potential sources
            context["error_message"] = "Failed to load external audiobook data at this time. Please try again later."
            messages.error(request, context["error_message"])

    # --- Fetch Creator Audiobooks ---
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
                'source': 'creator', 'title': book.title, 'slug': book.slug,
                'cover_image': book.cover_image.url if book.cover_image else None,
                'author': book.author, 'creator': book.creator,
                'first_chapter_audio_url': first_chapter_audio_url,
                'first_chapter_title': first_chapter_title,
                'is_creator_book': True, 'average_rating': book.average_rating,
                'total_views': book.total_views, 'is_paid': book.is_paid,
                'price': book.price, 'status': book.status,
            })
        context["creator_audiobooks"] = creator_books_list
    except Exception as db_err:
        print(f"Error fetching creator audiobooks: {db_err}")
        # Only set global error if external also failed
        if not context["librivox_audiobooks"] and \
           not context["archive_genre_audiobooks"] and \
           not context.get("archive_language_audiobooks"): 
            context["error_message"] = "Failed to load any audiobooks. Please try again later."
            # Avoid double messaging if external data error already set
            if not messages.get_messages(request):
                 messages.error(request, context["error_message"])


    return render(request, "home.html", context)


@login_required
def audiobook_detail(request, audiobook_slug):
    """Renders the detail page for an audiobook."""
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

        reviews = audiobook_obj.reviews.all()
        if request.user.is_authenticated and hasattr(request.user, 'user_id'): 
            user_review_data["user_id"] = request.user.user_id
        try:
            if request.user.is_authenticated: 
                user_review = Review.objects.get(audiobook=audiobook_obj, user=request.user)
                user_review_data["has_reviewed"] = True
                user_review_data["rating"] = user_review.rating
                user_review_data["comment"] = user_review.comment or ""
        except Review.DoesNotExist:
            user_review = None
        except TypeError: 
             user_review = None


        if audiobook_obj.is_paid:
            if request.user.is_authenticated and hasattr(request.user, 'has_purchased_audiobook'):
                user_has_purchased = request.user.has_purchased_audiobook(audiobook_obj)
            if not user_has_purchased:
                if request.user.is_authenticated and hasattr(request.user, 'subscription_type') and request.user.subscription_type == 'PR':
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
            elif can_preview_chapters and hasattr(chapter, 'is_preview_eligible') and chapter.is_preview_eligible:
                is_accessible = True
            
            chapters_to_display.append({
                'object': chapter, 'is_accessible': is_accessible,
                'audio_url': chapter.audio_file.url if chapter.audio_file else None,
                'chapter_title': chapter.chapter_name,
                'is_preview_eligible': hasattr(chapter, 'is_preview_eligible') and chapter.is_preview_eligible,
                'duration': getattr(chapter, 'duration', None),
            })

    except Http404:
        print(f"Creator audiobook with slug '{audiobook_slug}' not found. Checking external sources.")
        external_audiobook_data = fetch_audiobooks_data() # Fetch external data (will use cache if available)

        if external_audiobook_data:
            # Check LibriVox RSS audiobooks
            for book_dict in external_audiobook_data.get("librivox_audiobooks", []):
                if book_dict.get('slug') == audiobook_slug:
                    audiobook_data = book_dict
                    break
            # Check Archive.org genre audiobooks
            if not audiobook_data:
                for genre, book_list in external_audiobook_data.get("archive_genre_audiobooks", {}).items():
                    for book_dict in book_list:
                        if book_dict.get('slug') == audiobook_slug:
                            audiobook_data = book_dict
                            break
                    if audiobook_data: break
            # Check Archive.org language audiobooks
            if not audiobook_data:
                for language, book_list in external_audiobook_data.get("archive_language_audiobooks", {}).items():
                    for book_dict in book_list:
                        if book_dict.get('slug') == audiobook_slug:
                            audiobook_data = book_dict
                            break
                    if audiobook_data: break
        
        if audiobook_data: 
            is_creator_book = False
            template_name = 'audiobook_detail.html'
            if 'chapters' in audiobook_data: # Ensure chapters exist before trying to process
                chapters_to_display = [{
                    'object': None, 'chapter_title': ch_info.get('chapter_title'),
                    'audio_url': ch_info.get('audio_url'), 'is_accessible': True, # External are free
                    'is_preview_eligible': False, 'duration': None, # N/A for external
                } for ch_info in audiobook_data.get('chapters', [])] # Default to empty list
        else: 
            messages.error(request, "Audiobook not found or is not available.")
            raise Http404("Audiobook not found or is not available.")

    context['audiobook'] = audiobook_data
    context['is_creator_book'] = is_creator_book
    context['reviews'] = reviews
    context['user_review'] = user_review
    context['user_review_data_json'] = json.dumps(user_review_data)
    context['user_has_purchased'] = user_has_purchased
    context['chapters_to_display'] = chapters_to_display
    context['audiobook_lock_message'] = audiobook_lock_message
    if hasattr(settings, 'STRIPE_PUBLISHABLE_KEY'):
        context['STRIPE_PUBLISHABLE_KEY'] = settings.STRIPE_PUBLISHABLE_KEY
    
    if not is_creator_book and audiobook_data: 
        context['audiobook']['source'] = audiobook_data.get('source', 'unknown')
        context['audiobook']['author'] = audiobook_data.get('author', 'Unknown Author')

    return render(request, template_name, context)

# 🔹 Individual Genre Views
def _render_genre_or_language_page(request, page_type, term_name, template_name, data_key_plural, data_key_singular):
    """Helper function to render genre or language specific pages."""
    audiobook_data = fetch_audiobooks_data()
    context = {} 
    
    term_audiobooks = []
    if audiobook_data and data_key_plural in audiobook_data:
        term_audiobooks = audiobook_data[data_key_plural].get(term_name, [])
    
    if not term_audiobooks:
        messages.info(request, f"No audiobooks found for {page_type} '{term_name}'.")

    context[f"{page_type}_name"] = term_name # e.g. genre_name or language_name
    context["audiobooks"] = term_audiobooks
    return render(request, template_name, context)

def genre_fiction(request):
    return _render_genre_or_language_page(request, "genre", "Fiction", 'genrefiction.html', "archive_genre_audiobooks", "Fiction")

def genre_mystery(request):
    return _render_genre_or_language_page(request, "genre", "Mystery", 'genremystery.html', "archive_genre_audiobooks", "Mystery")

def genre_thriller(request):
    return _render_genre_or_language_page(request, "genre", "Thriller", 'genrethriller.html', "archive_genre_audiobooks", "Thriller")

def genre_scifi(request):
    return _render_genre_or_language_page(request, "genre", "Science Fiction", 'genrescifi.html', "archive_genre_audiobooks", "Science Fiction")

def genre_fantasy(request):
    return _render_genre_or_language_page(request, "genre", "Fantasy", 'genrefantasy.html', "archive_genre_audiobooks", "Fantasy")

def genre_romance(request):
    return _render_genre_or_language_page(request, "genre", "Romance", 'genre_romance.html', "archive_genre_audiobooks", "Romance")

def genre_biography(request):
    return _render_genre_or_language_page(request, "genre", "Biography", 'genrebiography.html', "archive_genre_audiobooks", "Biography")

def genre_history(request):
    return _render_genre_or_language_page(request, "genre", "History", 'genrehistory.html', "archive_genre_audiobooks", "History")

def genre_selfhelp(request):
    return _render_genre_or_language_page(request, "genre", "Self-Help", 'genreselfhelp.html', "archive_genre_audiobooks", "Self-Help")

def genre_business(request):
    return _render_genre_or_language_page(request, "genre", "Business", 'genrebusiness.html', "archive_genre_audiobooks", "Business")


# 🔹 Language Views
def urdu_page(request):
    return _render_genre_or_language_page(request, "language", "Urdu", 'urdu.html', "archive_language_audiobooks", "Urdu")

def punjabi_page(request):
    return _render_genre_or_language_page(request, "language", "Punjabi", 'punjabi.html', "archive_language_audiobooks", "Punjabi")

def sindhi_page(request):
    return _render_genre_or_language_page(request, "language", "Sindhi", 'sindhi.html', "archive_language_audiobooks", "Sindhi")


# 🔹 Streaming audio
@login_required 
@csrf_exempt 
def stream_audio(request):
    """Streams audio content from a given URL, handling local and external files."""
    audio_url_param = request.GET.get("url")
    if not audio_url_param:
        return JsonResponse({"error": "No audio URL provided"}, status=400)

    target_audio_url = audio_url_param
    parsed_url = urlparse(target_audio_url)
    is_local_media = not parsed_url.scheme and not parsed_url.netloc and target_audio_url.startswith(settings.MEDIA_URL)

    if is_local_media:
        try:
            target_audio_url = request.build_absolute_uri(target_audio_url)
            print(f"Streaming local audio URL: {audio_url_param} -> {target_audio_url}")
        except Exception as build_err:
            print(f"Error building absolute URL for local audio {audio_url_param}: {build_err}")
            return HttpResponse("Error processing local audio URL", status=500)
    elif not all([parsed_url.scheme, parsed_url.netloc]):
        print(f"Invalid audio URL provided (not local, not full URL): {audio_url_param}")
        return HttpResponse("Invalid audio URL provided", status=400)
    else: 
        print(f"Streaming external audio URL: {audio_url_param}")

    try:
        range_header = request.headers.get('Range', None)
        # Set a general User-Agent for proxied requests
        proxy_headers = {'User-Agent': 'AudioXApp Audio Proxy/1.0 (+http://YourDomain.com)'} # Replace YourDomain
        if range_header:
            proxy_headers['Range'] = range_header
            print(f"Streaming with Range header: {range_header}")

        # Increased timeout for audio streaming request
        audio_stream_timeout = 45 # seconds
        response = requests.get(target_audio_url, stream=True, headers=proxy_headers, timeout=audio_stream_timeout)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', 'audio/mpeg')
        if not content_type.lower().startswith('audio/'):
            guessed_type, _ = mimetypes.guess_type(target_audio_url)
            if guessed_type and guessed_type.startswith('audio/'):
                content_type = guessed_type
            else:
                content_type = 'audio/mpeg' 
            print(f"Determined audio content type: {content_type} for URL {target_audio_url}")


        def generate():
            try:
                for chunk in response.iter_content(chunk_size=8192): # 8KB chunks
                    if chunk: yield chunk
            except Exception as e_gen: # More specific exception name
                print(f"Error during audio streaming generation for {target_audio_url}: {e_gen}")
            finally:
                response.close() # Ensure connection is closed

        streaming_response = StreamingHttpResponse(generate(), content_type=content_type)
        if 'Content-Range' in response.headers:
            streaming_response['Content-Range'] = response.headers['Content-Range']
        if 'Content-Length' in response.headers:
            streaming_response['Content-Length'] = response.headers['Content-Length']
        streaming_response['Accept-Ranges'] = 'bytes'
        streaming_response.status_code = response.status_code
        return streaming_response

    except requests.exceptions.Timeout:
        print(f"Audio stream request TIMED OUT for {target_audio_url}")
        return HttpResponse("Audio stream timed out", status=408) # Request Timeout
    except requests.exceptions.HTTPError as e_http: # More specific exception name
        print(f"HTTP error {e_http.response.status_code} fetching audio from {target_audio_url}")
        return HttpResponse(f"Error fetching audio: {e_http.response.status_code}", status=e_http.response.status_code)
    except requests.exceptions.RequestException as e_req: # More specific exception name
        print(f"Request error fetching audio from {target_audio_url}: {e_req}")
        return HttpResponse("Error processing audio stream", status=502) 
    except SuspiciousOperation as e_susp: # More specific exception name
        print(f"Suspicious audio stream request for {target_audio_url}: {e_susp}")
        return JsonResponse({"error": str(e_susp)}, status=400)
    except Exception as e_stream: # More specific exception name for unexpected errors
        print(f"Unexpected error during audio streaming for {target_audio_url}: {e_stream}")
        return HttpResponse("Internal server error during audio streaming", status=500)


# 🔹 Image proxy
@csrf_exempt 
def fetch_cover_image(request):
    """Proxies external and local cover images."""
    image_url = request.GET.get("url")
    if not image_url:
        return JsonResponse({"error": "No image URL provided"}, status=400)

    target_image_url = image_url
    parsed_url = urlparse(image_url)
    is_local_media = image_url.startswith(settings.MEDIA_URL) and not all([parsed_url.scheme, parsed_url.netloc])

    if is_local_media:
        try:
            target_image_url = request.build_absolute_uri(image_url) 
            print(f"Processing local image URL: {image_url} -> {target_image_url}")
        except Exception as build_err:
            print(f"Error building absolute URL for local image {image_url}: {build_err}")
            return HttpResponse("Error processing local image URL", status=500)
    elif not all([parsed_url.scheme, parsed_url.netloc]):
        print(f"Invalid image URL provided (not local, not full URL): {image_url}")
        return HttpResponse("Invalid image URL provided", status=400)
    else: 
        print(f"Processing external image URL: {image_url}")

    try:
        # Set a general User-Agent for proxied requests
        proxy_headers = {'User-Agent': 'AudioXApp Image Proxy/1.0 (+http://YourDomain.com)'} # Replace YourDomain
        
        # Increased timeout for image fetching
        image_fetch_timeout = 30 # seconds
        response = requests.get(target_image_url, stream=True, timeout=image_fetch_timeout, headers=proxy_headers)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', 'image/jpeg')
        if not content_type.lower().startswith('image/'):
            guessed_type, _ = mimetypes.guess_type(target_image_url)
            if guessed_type and guessed_type.startswith('image/'):
                content_type = guessed_type
            else:
                content_type = 'image/jpeg' 
            print(f"Determined image content type: {content_type} for URL {target_image_url}")


        streaming_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192), content_type=content_type # 8KB chunks
        )
        if 'Content-Length' in response.headers:
            streaming_response['Content-Length'] = response.headers['Content-Length']
        streaming_response.status_code = response.status_code
        return streaming_response

    except requests.exceptions.Timeout:
        print(f"Image fetch TIMED OUT for {target_image_url}")
        return HttpResponse("Image fetch timed out", status=408) # Request Timeout
    except requests.exceptions.HTTPError as e_http: # More specific exception name
        print(f"HTTP error {e_http.response.status_code} fetching image from {target_image_url}")
        return HttpResponse(f"Error fetching image: {e_http.response.status_code}", status=e_http.response.status_code)
    except requests.exceptions.RequestException as e_req: # More specific exception name
        print(f"Request error fetching image from {target_image_url}: {e_req}")
        return HttpResponse("Failed to fetch image", status=502) 
    except SuspiciousOperation as e_susp: # More specific exception name
        print(f"Suspicious image request for {target_image_url}: {e_susp}")
        return JsonResponse({"error": str(e_susp)}, status=400)
    except Exception as e_img: # More specific exception name for unexpected errors
        print(f"Unexpected error during image fetch for {target_image_url}: {e_img}")
        return HttpResponse("Internal server error", status=500)


@login_required
@require_POST
@csrf_protect
def add_review(request, audiobook_slug):
    """Handles adding or updating a review for a creator-uploaded audiobook."""
    try:
        audiobook = get_object_or_404(Audiobook, slug=audiobook_slug)
        if not hasattr(audiobook, 'creator') or not audiobook.creator: # Check if it's a creator book
            return JsonResponse({'status': 'error', 'message': 'Reviews are only supported for creator-uploaded audiobooks.'}, status=400)

        try:
            data = json.loads(request.body)
            rating = data.get('rating')
            comment = data.get('comment', '').strip()
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON format in request body.'}, status=400)

        try:
            rating = int(rating)
            if not 1 <= rating <= 5:
                raise ValueError("Rating must be between 1 and 5.")
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid rating value. Please provide a number between 1 and 5.'}, status=400)

        review, created = Review.objects.update_or_create(
            audiobook=audiobook, user=request.user,
            defaults={'rating': rating, 'comment': comment}
        )
        
        audiobook.refresh_from_db() 
        new_average_rating = audiobook.average_rating 

        message = "Review updated successfully!" if not created else "Review added successfully!"
        review_data = {
            'review_id': review.review_id, 
            'rating': review.rating,
            'comment': review.comment or "",
            'user_id': getattr(review.user, 'user_id', getattr(review.user, 'id', None)), 
            'user_name': getattr(review.user, 'full_name', review.user.username), # Prefer full_name
            'user_profile_pic': getattr(getattr(review.user, 'profile_pic', None), 'url', None), # Safely access URL
            'created_at': review.created_at.isoformat(), 
            'timesince': timesince(review.created_at) + " ago", 
        }
        return JsonResponse({
            'status': 'success', 'message': message, 'created': created,
            'new_average_rating': new_average_rating, 'review_data': review_data
        })
    except Audiobook.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except Exception as e_review: # More specific exception name
        print(f"Error in add_review for {audiobook_slug}: {e_review}")
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred. Please try again.'}, status=500)


# 🔹 Static Pages
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
