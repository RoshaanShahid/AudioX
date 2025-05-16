# content_views.py

import random
import requests
import feedparser
import mimetypes
import json
from urllib.parse import urlparse # quote was unused
from decimal import Decimal
from datetime import datetime 

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse, Http404
from django.contrib import messages
from django.core.cache import cache
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Avg 
from django.conf import settings
from django.core.exceptions import SuspiciousOperation 
from django.utils.timesince import timesince 
from django.db import transaction # Added for atomic transaction in add_review
import logging # Ensure logging is imported

# Custom logger for this view module
# THIS IS THE CRUCIAL LINE FOR THE NameError. ENSURE IT'S PRESENT AND UNCOMMENTED.
logger = logging.getLogger(__name__) 

from ..models import Audiobook, Chapter, Review, User, AudiobookPurchase, CreatorEarning # Assuming models are in parent directory
from .utils import _get_full_context # Assuming utils.py is in the same directory (views/)

def fetch_audiobooks_data():
    """
    Fetches audiobook data from LibriVox RSS feeds and Archive.org by genre and language.
    Caches the results.
    IMPORTANT: This function is intended to be called by a background task or management command
    to periodically update the cache, not directly by views handling user requests if it's slow.
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
                    # Ensure AudioXApp:fetch_cover_image is a valid reversible URL name
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
        except requests.exceptions.Timeout as e:
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
    archive_timeout = 30

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
        except requests.exceptions.Timeout as e:
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
            return combined_data
        else:
            return None


@require_GET
def api_audiobooks(request):
    """API endpoint to get cached audiobook data."""
    cache_key = 'librivox_archive_audiobooks_data_v5'
    data = cache.get(cache_key)
    
    if data is not None:
        return JsonResponse(data, safe=False)
    else:
        return JsonResponse({"message": "Audiobook data is currently being updated or is not available. Please try again shortly."}, status=202)

def home(request):
    """Renders the English home page with audiobooks."""
    context = _get_full_context(request)
    cache_key = 'librivox_archive_audiobooks_data_v5' # For external books
    
    audiobook_data = cache.get(cache_key)

    context["librivox_audiobooks"] = []
    context["archive_genre_audiobooks"] = {} # For external English genre books
    context["creator_audiobooks"] = [] # This will hold English creator books
    context["error_message"] = None

    # --- Populate external (LibriVox, Archive.org) audiobooks ---
    if audiobook_data is not None:
        print(f"CACHE HIT for English homepage (external): Using cached data (key: {cache_key}).")
        context["librivox_audiobooks"] = audiobook_data.get("librivox_audiobooks", [])
        context["archive_genre_audiobooks"] = audiobook_data.get("archive_genre_audiobooks", {})
    else:
        print(f"CACHE MISS for English homepage (external): No data in cache (key: {cache_key}).")
        context["error_message"] = (
            "External audiobook listings are currently being updated. "
            "Please check back shortly. In the meantime, enjoy content from our creators!"
        )

    # --- Populate Creator Audiobooks for English Language ---
    try:
        first_chapter_prefetch = Prefetch(
            'chapters',
            queryset=Chapter.objects.order_by('chapter_order'),
            to_attr='first_chapter_list'
        )
        
        # Fetch English audiobooks by creators
        creator_books_qs = Audiobook.objects.filter(
            status='PUBLISHED', 
            language__iexact='English' # Ensure filtering by English language
        ).select_related('creator').prefetch_related(
            first_chapter_prefetch,
            Prefetch('reviews', queryset=Review.objects.select_related('user').order_by('-created_at'))
        ).order_by('-publish_date')[:12] # Limit for homepage display

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
                'source': 'creator', 
                'title': book.title, 
                'slug': book.slug,
                'cover_image': book.cover_image.url if book.cover_image else None,
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
                # Add language and genre for potential use in template/JS, though this view is English-specific
                'language': book.language,
                'genre': book.genre 
            })
        context["creator_audiobooks"] = creator_books_list
        
        if not creator_books_list and not context["librivox_audiobooks"] and not context["archive_genre_audiobooks"]:
             if not context["error_message"]: # Avoid overwriting cache miss message
                context["error_message"] = "No English audiobooks are currently available."


    except Exception as db_err:
        print(f"Error fetching creator audiobooks for English homepage: {db_err}")
        logger.error(f"Error fetching creator audiobooks for English homepage: {db_err}", exc_info=True)
        if not context["librivox_audiobooks"] and not context["archive_genre_audiobooks"] and not context["creator_audiobooks"]:
            context["error_message"] = "Failed to load any audiobooks at this time. Please try again later."
            if not messages.get_messages(request) and not audiobook_data:
                messages.error(request, "We encountered an issue loading audiobook data.")

    return render(request, "audiobooks/English/English_Home.html", context)


def _render_genre_or_language_page(request, page_type, display_name, template_name, cache_key_segment, query_term):
    """
    Helper function to render genre-specific or language-specific pages.
    Fetches both external (cached) and creator-uploaded audiobooks.
    """
    context = _get_full_context(request)
    cache_key = 'librivox_archive_audiobooks_data_v5' # For external books
    
    external_audiobook_data = cache.get(cache_key)
    
    context["display_name"] = display_name
    context["audiobooks_list"] = [] # For external books
    context["creator_audiobooks"] = [] # For creator books
    context["error_message"] = None

    # --- Populate external (Archive.org) audiobooks for the specific genre/language ---
    if external_audiobook_data:
        print(f"CACHE HIT for _render_genre_or_language_page (external): Using cached data (key: {cache_key}).")
        source_dict = external_audiobook_data.get(cache_key_segment, {})
        context["audiobooks_list"] = source_dict.get(query_term, [])
    else:
        print(f"CACHE MISS for _render_genre_or_language_page (external): No data in cache (key: {cache_key}).")
        context["error_message"] = (
            f"External listings for {display_name} are currently being updated. "
            "Please check back shortly. In the meantime, enjoy content from our creators!"
        )

    # --- Populate Creator Audiobooks for the specific genre/language ---
    try:
        first_chapter_prefetch = Prefetch(
            'chapters',
            queryset=Chapter.objects.order_by('chapter_order'),
            to_attr='first_chapter_list'
        )

        creator_books_query = Audiobook.objects.filter(status='PUBLISHED')

        if page_type == "genre": # English Genre pages
            creator_books_query = creator_books_query.filter(
                language__iexact='English', 
                genre__iexact=query_term # query_term is the specific genre name
            )
        elif page_type == "language": # Urdu, Punjabi, Sindhi pages
            creator_books_query = creator_books_query.filter(
                language__iexact=query_term # query_term is the language name
            )
        
        creator_books_qs = creator_books_query.select_related('creator').prefetch_related(
            first_chapter_prefetch,
            Prefetch('reviews', queryset=Review.objects.select_related('user').order_by('-created_at'))
        ).order_by('-publish_date')

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
                'source': 'creator', 
                'title': book.title, 
                'slug': book.slug,
                'cover_image': book.cover_image.url if book.cover_image else None,
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
                'language': book.language, # Include for consistency
                'genre': book.genre 
            })
        context["creator_audiobooks"] = creator_books_list

        if not creator_books_list and not context["audiobooks_list"]:
            if not context["error_message"]:
                 context["error_message"] = f"No audiobooks found for {display_name} at the moment."


    except Exception as db_err:
        print(f"Error fetching creator audiobooks for {page_type} '{display_name}': {db_err}")
        logger.error(f"Error fetching creator audiobooks for {page_type} '{display_name}': {db_err}", exc_info=True)
        if not context["audiobooks_list"] and not context["creator_audiobooks"]: # If both external and creator lists are empty
            context["error_message"] = f"Failed to load audiobooks for {display_name}. Please try again later."
            # Avoid duplicate messages if cache miss already set one
            if not messages.get_messages(request) and not external_audiobook_data : 
                messages.error(request, f"We encountered an issue loading data for {display_name}.")
                
    return render(request, template_name, context)


@login_required
def audiobook_detail(request, audiobook_slug):
    """Renders the detail page for an audiobook."""
    audiobook_data = None
    is_creator_book = False
    context = _get_full_context(request)
    template_name = 'audiobook_detail.html' # Default for external
    
    reviews_list = [] # To store all reviews for display
    user_review_object = None # Stores the review object if the current user has reviewed
    current_user_has_reviewed = False # NEW: Direct boolean flag

    # This dictionary is primarily for JS consumption via JSON, e.g., pre-filling an edit form
    user_review_data_for_json = {
        "has_reviewed": False, 
        "rating": 0, 
        "comment": "", 
        "user_id": None
    }
    if request.user.is_authenticated and hasattr(request.user, 'user_id'):
        # Set user_id for the JSON if user is authenticated and has user_id attribute
        user_review_data_for_json["user_id"] = request.user.user_id

    user_has_purchased = False
    can_preview_chapters = False
    chapters_to_display = []
    audiobook_lock_message = None

    try:
        # Try to fetch as a creator-uploaded audiobook first
        audiobook_obj = get_object_or_404(
            Audiobook.objects.prefetch_related(
                Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order')),
                Prefetch('reviews', queryset=Review.objects.select_related('user').order_by('-created_at'))
            ).select_related('creator'),
            slug=audiobook_slug
        )
        is_creator_book = True
        template_name = 'audiobook_creator_details.html' # Specific template for creator books
        audiobook_data = audiobook_obj # This is an Audiobook model instance

        reviews_list = audiobook_obj.reviews.all() # Get all reviews for this book

        # Check if the current logged-in user has reviewed this specific audiobook
        # This check is only relevant for creator books where we manage reviews
        if request.user.is_authenticated: # Should always be true due to @login_required
            try:
                user_review_object = Review.objects.get(audiobook=audiobook_obj, user=request.user)
                current_user_has_reviewed = True # Set the direct boolean flag
                
                # Populate the dictionary for JSON (e.g., for pre-filling an edit form via JS)
                user_review_data_for_json["has_reviewed"] = True
                user_review_data_for_json["rating"] = user_review_object.rating
                user_review_data_for_json["comment"] = user_review_object.comment or ""
                # user_id is already set above if user is authenticated
            except Review.DoesNotExist:
                # current_user_has_reviewed remains False, user_review_object remains None
                # user_review_data_for_json["has_reviewed"] remains False (its default)
                logger.debug(f"User {request.user.username} has not reviewed audiobook {audiobook_slug}.")
            except TypeError: # Should not happen with @login_required but defensive
                logger.warning(f"TypeError while checking review for user {request.user.username} on {audiobook_slug}.")
                # Ensure flags remain false
                current_user_has_reviewed = False
                user_review_object = None
                user_review_data_for_json["has_reviewed"] = False


        # Logic for paid content and previews for creator books
        if audiobook_obj.is_paid:
            if request.user.is_authenticated and hasattr(request.user, 'has_purchased_audiobook'):
                user_has_purchased = request.user.has_purchased_audiobook(audiobook_obj)
            
            if not user_has_purchased:
                # Check for premium subscription preview access
                is_premium_subscriber = (request.user.is_authenticated and 
                                         hasattr(request.user, 'subscription_type') and 
                                         request.user.subscription_type == 'PR')

                if audiobook_obj.preview_chapters > 0 : # Check if any chapters are set for preview
                    can_preview_chapters = True 
                    preview_chapter_count = audiobook_obj.preview_chapters
                    plural_s = "s" if preview_chapter_count > 1 else ""
                    if is_premium_subscriber:
                         audiobook_lock_message = (
                            f"This is a premium audiobook. Purchase for full access (PKR {audiobook_obj.price:.2f}). "
                            f"As a premium member, you can preview the first {preview_chapter_count} chapter{plural_s}."
                        )
                    else:
                        audiobook_lock_message = (
                            f"This is a premium audiobook. Purchase for full access (PKR {audiobook_obj.price:.2f}). "
                            f"You can preview the first {preview_chapter_count} chapter{plural_s}."
                        )
                else: # No chapters are set for preview
                    can_preview_chapters = False
                    audiobook_lock_message = f"This is a premium audiobook. Purchase for full access (PKR {audiobook_obj.price:.2f}). No preview chapters available."
        
        all_db_chapters = audiobook_obj.chapters.all().order_by('chapter_order')
        preview_limit = audiobook_obj.preview_chapters if audiobook_obj.is_paid and not user_has_purchased and can_preview_chapters else 0

        for i, chapter_obj in enumerate(all_db_chapters):
            is_accessible = False
            if not audiobook_obj.is_paid or user_has_purchased:
                is_accessible = True
            elif can_preview_chapters and i < preview_limit: # Preview allowed chapters
                is_accessible = True
            
            chapters_to_display.append({
                'object': chapter_obj, 
                'is_accessible': is_accessible,
                'audio_url': chapter_obj.audio_file.url if chapter_obj.audio_file else None,
                'chapter_title': chapter_obj.chapter_name,
                'is_preview_eligible': i < preview_limit if audiobook_obj.is_paid and not user_has_purchased else False,
                'duration': getattr(chapter_obj, 'duration', None), 
                'chapter_index': i 
            })

    except Http404:
        logger.info(f"Creator audiobook with slug '{audiobook_slug}' not found. Checking external sources from cache.")
        cache_key = 'librivox_archive_audiobooks_data_v5'
        external_audiobook_data_cache = cache.get(cache_key)
        found_external_book = None

        if external_audiobook_data_cache:
            for source_key in ["librivox_audiobooks", "archive_genre_audiobooks", "archive_language_audiobooks"]:
                if source_key == "librivox_audiobooks":
                    item_list = external_audiobook_data_cache.get(source_key, [])
                    for book_dict in item_list:
                        if book_dict.get('slug') == audiobook_slug:
                            found_external_book = book_dict
                            break
                else: # For archive_genre_audiobooks and archive_language_audiobooks (which are dicts of lists)
                    for _, book_list in external_audiobook_data_cache.get(source_key, {}).items():
                        for book_dict in book_list:
                            if book_dict.get('slug') == audiobook_slug:
                                found_external_book = book_dict
                                break
                        if found_external_book: break
                if found_external_book: break
        
        if found_external_book:
            audiobook_data = found_external_book 
            is_creator_book = False # It's an external book
            template_name = 'audiobook_detail.html' 
            
            # For external books, reviews from our DB are not applicable, and user cannot have reviewed it in our system
            reviews_list = [] 
            user_review_object = None
            current_user_has_reviewed = False # Explicitly false
            user_review_data_for_json["has_reviewed"] = False # Reset for external books

            if 'chapters' in audiobook_data:
                for i, ch_info in enumerate(audiobook_data.get('chapters', [])):
                    chapters_to_display.append({
                        'object': None, 
                        'chapter_title': ch_info.get('chapter_title'),
                        'audio_url': ch_info.get('audio_url'), 
                        'is_accessible': True, 
                        'is_preview_eligible': False, 
                        'duration': ch_info.get('duration'), 
                        'chapter_index': i
                    })
        else:
            messages.error(request, "Audiobook not found or is not available.")
            logger.warning(f"Audiobook with slug '{audiobook_slug}' not found in DB or cache.")
            raise Http404("Audiobook not found or is not available.")
    
    context['audiobook'] = audiobook_data
    context['is_creator_book'] = is_creator_book
    context['reviews'] = reviews_list # Pass the list of all reviews
    context['user_review_object'] = user_review_object # The current user's review object (or None)
    context['current_user_has_reviewed'] = current_user_has_reviewed # NEW: Direct boolean flag
    context['user_review_data_json'] = json.dumps(user_review_data_for_json) # For JS (e.g. edit form)
    context['user_has_purchased'] = user_has_purchased
    context['chapters_to_display'] = chapters_to_display
    context['audiobook_lock_message'] = audiobook_lock_message

    if hasattr(settings, 'STRIPE_PUBLISHABLE_KEY'):
        context['STRIPE_PUBLISHABLE_KEY'] = settings.STRIPE_PUBLISHABLE_KEY
    
    if not is_creator_book and isinstance(audiobook_data, dict):
        audiobook_data.setdefault('author', 'Unknown Author')
        audiobook_data.setdefault('source', 'External Source')
        if isinstance(audiobook_data.get('cover_image'), dict): 
            audiobook_data['cover_image'] = audiobook_data['cover_image'].get('url')

    return render(request, template_name, context)

# --- Genre Views (no changes to their calls to the helper, just ensure helper is updated) ---
def genre_fiction(request):
    return _render_genre_or_language_page(request, "genre", "Fiction", 'audiobooks/English/genrefiction.html', "archive_genre_audiobooks", "Fiction")

def genre_mystery(request):
    return _render_genre_or_language_page(request, "genre", "Mystery", 'audiobooks/English/genremystery.html', "archive_genre_audiobooks", "Mystery")

def genre_thriller(request):
    return _render_genre_or_language_page(request, "genre", "Thriller", 'audiobooks/English/genrethriller.html', "archive_genre_audiobooks", "Thriller")

def genre_scifi(request):
    return _render_genre_or_language_page(request, "genre", "Science Fiction", 'audiobooks/English/genrescifi.html', "archive_genre_audiobooks", "Science Fiction")

def genre_fantasy(request):
    return _render_genre_or_language_page(request, "genre", "Fantasy", 'audiobooks/English/genrefantasy.html', "archive_genre_audiobooks", "Fantasy")

def genre_romance(request):
    return _render_genre_or_language_page(request, "genre", "Romance", 'audiobooks/English/genreromance.html', "archive_genre_audiobooks", "Romance")

def genre_biography(request):
    return _render_genre_or_language_page(request, "genre", "Biography", 'audiobooks/English/genrebiography.html', "archive_genre_audiobooks", "Biography")

def genre_history(request):
    return _render_genre_or_language_page(request, "genre", "History", 'audiobooks/English/genrehistory.html', "archive_genre_audiobooks", "History")

def genre_selfhelp(request):
    return _render_genre_or_language_page(request, "genre", "Self-Help", 'audiobooks/English/genreselfhelp.html', "archive_genre_audiobooks", "Self-Help")

def genre_business(request):
    return _render_genre_or_language_page(request, "genre", "Business", 'audiobooks/English/genrebusiness.html', "archive_genre_audiobooks", "Business")

# --- Language Views (no changes to their calls to the helper) ---
def urdu_page(request):
    return _render_genre_or_language_page(request, "language", "Urdu", 'audiobooks/Urdu/Urdu_Home.html', "archive_language_audiobooks", "Urdu")

def punjabi_page(request):
    return _render_genre_or_language_page(request, "language", "Punjabi", 'audiobooks/Punjabi/Punjabi_Home.html', "archive_language_audiobooks", "Punjabi")

def sindhi_page(request):
    return _render_genre_or_language_page(request, "language", "Sindhi", 'audiobooks/Sindhi/Sindhi_Home.html', "archive_language_audiobooks", "Sindhi")


@login_required # Consider if login is truly required for streaming public domain audio
@csrf_exempt # Typically okay for a GET request that proxies content
def stream_audio(request):
    """Streams audio content from a given URL, handling local and external files."""
    # --- ADD THIS LINE FOR DEBUGGING ---
    print(f"--- stream_audio VIEW HIT --- Request: {request.method} {request.get_full_path()}") 
    
    audio_url_param = request.GET.get("url")
    if not audio_url_param: # Handles empty string or None
        print(f"stream_audio: No audio URL provided in query parameter. Path: {request.get_full_path()}")
        return JsonResponse({"error": "No audio URL provided"}, status=400)

    target_audio_url = audio_url_param # Django's request.GET already URL-decodes query params
    parsed_url = urlparse(target_audio_url)
    
    # Check if it's a local media URL (relative path starting with MEDIA_URL)
    # This logic might need adjustment based on how you store/serve creator-uploaded audio
    is_local_media = target_audio_url.startswith(settings.MEDIA_URL) and not parsed_url.scheme and not parsed_url.netloc

    if is_local_media:
        try:
            # If it's a relative media URL, build the full absolute URI
            if not target_audio_url.startswith(('http://', 'https://')):
                target_audio_url = request.build_absolute_uri(target_audio_url)
            print(f"Streaming local audio URL: {audio_url_param} -> {target_audio_url}")
        except Exception as build_err:
            print(f"Error building absolute URL for local audio {audio_url_param}: {build_err}")
            return HttpResponse("Error processing local audio URL", status=500)
    elif not all([parsed_url.scheme, parsed_url.netloc]): 
        # If it's not local and not a full external URL (e.g., missing scheme like 'http')
        print(f"Invalid audio URL provided (not local media, not a full external URL): {audio_url_param}")
        return HttpResponse(f"Invalid audio URL provided: {audio_url_param}", status=400)
    else:
        # It's an external URL
        print(f"Streaming external audio URL: {target_audio_url}") # target_audio_url is already decoded here

    try:
        range_header = request.headers.get('Range', None)
        # Use a generic user-agent or one specific to your app
        user_agent_host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "audiox.com" # Fallback
        proxy_headers = {'User-Agent': f'AudioXApp Audio Proxy/1.0 (+http://{user_agent_host})'}
        
        if range_header:
            proxy_headers['Range'] = range_header
            print(f"Streaming with Range header: {range_header} for URL: {target_audio_url}")

        audio_stream_timeout = 45 # seconds
        # Make the request to the actual audio source
        response = requests.get(target_audio_url, stream=True, headers=proxy_headers, timeout=audio_stream_timeout)
        response.raise_for_status() # Will raise an HTTPError for bad responses (4XX or 5XX)

        # Determine content type
        content_type = response.headers.get('Content-Type', 'audio/mpeg')
        if not content_type.lower().startswith('audio/'):
            guessed_type, _ = mimetypes.guess_type(target_audio_url)
            if guessed_type and guessed_type.startswith('audio/'):
                content_type = guessed_type
            else:
                content_type = 'audio/mpeg' # Default if unsure
            print(f"Determined audio content type: {content_type} for URL {target_audio_url}")

        # Stream the content
        def generate_audio_chunks():
            try:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk: 
                        yield chunk
            except Exception as e_gen:
                print(f"Error during audio streaming generation for {target_audio_url}: {e_gen}")
            finally:
                response.close() # Ensure the response is closed

        streaming_response = StreamingHttpResponse(generate_audio_chunks(), content_type=content_type)
        
        # Pass through relevant headers for seeking and content length
        if 'Content-Range' in response.headers:
            streaming_response['Content-Range'] = response.headers['Content-Range']
        if 'Content-Length' in response.headers:
            streaming_response['Content-Length'] = response.headers['Content-Length']
        streaming_response['Accept-Ranges'] = 'bytes' # Important for seeking
        streaming_response.status_code = response.status_code # Usually 200 or 206 for ranged requests
        
        print(f"Successfully streaming {content_type} from {target_audio_url} with status {streaming_response.status_code}")
        return streaming_response

    except requests.exceptions.Timeout:
        print(f"Audio stream request TIMED OUT for {target_audio_url}")
        return HttpResponse("Audio stream timed out from external source", status=408) # Request Timeout
    except requests.exceptions.HTTPError as e_http:
        print(f"HTTP error {e_http.response.status_code} fetching audio from {target_audio_url}: {e_http.response.text[:200]}")
        # Return a more specific error to the client if possible
        return HttpResponse(f"Error fetching audio from external source: Status {e_http.response.status_code}", status=e_http.response.status_code)
    except requests.exceptions.RequestException as e_req:
        print(f"Request error fetching audio from {target_audio_url}: {e_req}")
        return HttpResponse("Error processing audio stream (could not connect to external source)", status=502) # Bad Gateway
    except SuspiciousOperation as e_susp: 
        print(f"Suspicious audio stream request for {target_audio_url}: {e_susp}")
        return JsonResponse({"error": str(e_susp)}, status=400)
    except Exception as e_stream:
        print(f"Unexpected error during audio streaming for {target_audio_url}: {e_stream}")
        # Log the full traceback here for better debugging in production
        import traceback
        traceback.print_exc()
        return HttpResponse("Internal server error during audio streaming", status=500)


@csrf_exempt 
def fetch_cover_image(request):
    """Proxies external and local cover images."""
    image_url = request.GET.get("url")
    if not image_url:
        return JsonResponse({"error": "No image URL provided"}, status=400)

    target_image_url = image_url
    parsed_url = urlparse(image_url)
    is_local_media = image_url.startswith(settings.MEDIA_URL) and not parsed_url.scheme and not parsed_url.netloc

    if is_local_media:
        try:
            if not target_image_url.startswith(('http://', 'https://')):
                target_image_url = request.build_absolute_uri(target_image_url)
            print(f"Processing local image URL: {image_url} -> {target_image_url}")
        except Exception as build_err:
            print(f"Error building absolute URL for local image {image_url}: {build_err}")
            return HttpResponse("Error processing local image URL", status=500)
    elif not all([parsed_url.scheme, parsed_url.netloc]):
        print(f"Invalid image URL provided (not local media, not a full external URL): {image_url}")
        return HttpResponse("Invalid image URL provided", status=400)
    else:
        print(f"Processing external image URL: {image_url}")

    try:
        proxy_headers = {'User-Agent': f'AudioXApp Image Proxy/1.0 (+http://{settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "YourDomain.com"})'}
        image_fetch_timeout = 30 
        
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
            response.iter_content(chunk_size=8192), content_type=content_type
        )
        if 'Content-Length' in response.headers:
            streaming_response['Content-Length'] = response.headers['Content-Length']
        streaming_response.status_code = response.status_code
        return streaming_response

    except requests.exceptions.Timeout:
        print(f"Image fetch TIMED OUT for {target_image_url}")
        return HttpResponse("Image fetch timed out", status=408)
    except requests.exceptions.HTTPError as e_http:
        print(f"HTTP error {e_http.response.status_code} fetching image from {target_image_url}")
        return HttpResponse(f"Error fetching image: {e_http.response.status_code}", status=e_http.response.status_code)
    except requests.exceptions.RequestException as e_req:
        print(f"Request error fetching image from {target_image_url}: {e_req}")
        return HttpResponse("Failed to fetch image", status=502) 
    except SuspiciousOperation as e_susp:
        print(f"Suspicious image request for {target_image_url}: {e_susp}")
        return JsonResponse({"error": str(e_susp)}, status=400)
    except Exception as e_img:
        print(f"Unexpected error during image fetch for {target_image_url}: {e_img}")
        return HttpResponse("Internal server error", status=500)


@login_required
@require_POST
@csrf_protect 
def add_review(request, audiobook_slug):
    """
    Handles adding or updating a review for an audiobook.
    Expects a JSON payload with 'rating' and 'comment'.
    """
    logger.info(f"add_review attempt for slug: {audiobook_slug} by user: {request.user.username}")
    try:
        # Fetch the audiobook. Allow reviews for any published audiobook.
        audiobook = get_object_or_404(
            Audiobook, 
            slug=audiobook_slug,
            status='PUBLISHED' # Ensure reviews are only for published audiobooks
        )
        logger.debug(f"Audiobook found: {audiobook.title} (ID: {audiobook.audiobook_id})")

        # Check if the user is allowed to review this audiobook.
        # Example: User must have purchased a paid audiobook to review it.
        can_review = False
        if not audiobook.is_paid:
            can_review = True
            logger.debug(f"Audiobook '{audiobook.title}' is free. Allowing review by {request.user.username}.")
        elif request.user.is_authenticated and hasattr(request.user, 'has_purchased_audiobook'):
            if request.user.has_purchased_audiobook(audiobook):
                can_review = True
                logger.debug(f"User {request.user.username} has purchased '{audiobook.title}'. Allowing review.")
            else:
                logger.warning(f"User {request.user.username} has NOT purchased paid audiobook '{audiobook.title}'. Denying review.")
        
        if not can_review:
            return JsonResponse({
                'status': 'error', 
                'message': 'You must purchase this audiobook or it must be free to leave a review.'
            }, status=403) # Forbidden

        try:
            data = json.loads(request.body)
            rating_str = data.get('rating') 
            comment = data.get('comment', '').strip() # Default to empty string if not provided
            logger.debug(f"Review submission data from user {request.user.username}: rating='{rating_str}', comment length={len(comment)}")
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON payload for review from user {request.user.username} for slug {audiobook_slug}.")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON format in request body.'}, status=400)

        try:
            rating = int(rating_str) 
            if not 1 <= rating <= 5:
                # This validation should ideally also be in a Django Form if you were using one.
                raise ValueError("Rating must be between 1 and 5.")
        except (ValueError, TypeError) as e_rating: 
            logger.warning(f"Invalid rating value '{rating_str}' from user {request.user.username} for slug {audiobook_slug}: {e_rating}")
            return JsonResponse({'status': 'error', 'message': 'Invalid rating value. Please provide a whole number between 1 and 5.'}, status=400)

        # Use atomic transaction to ensure data integrity during create/update.
        with transaction.atomic():
            review, created = Review.objects.update_or_create(
                audiobook=audiobook,
                user=request.user, 
                defaults={'rating': rating, 'comment': comment}
            )
            logger.info(f"Review {'created' if created else 'updated'} (ID: {review.review_id}) for audiobook ID {audiobook.audiobook_id} by user {request.user.username}.")
        
        # The audiobook.average_rating property will calculate the new average on next access.
        # No explicit refresh of audiobook instance is strictly needed for this property if it's well-defined.
        new_average_rating = audiobook.average_rating 

        message = "Review updated successfully!" if not created else "Review added successfully!"
        
        user_profile_pic_url = None
        if hasattr(review.user, 'profile_pic') and review.user.profile_pic:
            try:
                user_profile_pic_url = review.user.profile_pic.url
            except ValueError: 
                logger.warning(f"Could not get profile_pic URL for user {review.user.username} during review response.")
                pass # Silently ignore if URL cannot be generated

        review_data = {
            'review_id': review.review_id,
            'rating': review.rating,
            'comment': review.comment or "", # Ensure comment is a string
            'user_id': review.user.user_id, 
            'user_name': getattr(review.user, 'full_name', review.user.username) or review.user.username,
            'user_profile_pic': user_profile_pic_url,
            'created_at': review.created_at.isoformat(), 
            'timesince': timesince(review.created_at) + " ago", 
        }
        
        logger.info(f"Successfully processed review for '{audiobook.title}'. Average rating now: {new_average_rating}")
        return JsonResponse({
            'status': 'success',
            'message': message,
            'created': created,
            'new_average_rating': str(new_average_rating) if new_average_rating is not None else "0.0", 
            'review_data': review_data
        })

    except Audiobook.DoesNotExist:
        logger.warning(f"add_review: Audiobook with slug '{audiobook_slug}' not found or not published.")
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found or not available for review.'}, status=404)
    except Exception as e_review:
        # This will catch any other unhandled exceptions and log them.
        logger.error(f"Unexpected error in add_review for slug {audiobook_slug}, user {request.user.username}: {type(e_review).__name__} - {str(e_review)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected server error occurred. Please try again.'}, status=500)

# Static Pages
def ourteam(request): return render(request, 'company/ourteam.html', _get_full_context(request))
def paymentpolicy(request): return render(request, 'legal/paymentpolicy.html', _get_full_context(request))
def privacypolicy(request): return render(request, 'legal/privacypolicy.html', _get_full_context(request))
def piracypolicy(request): return render(request, 'legal/piracypolicy.html', _get_full_context(request))
def termsandconditions(request): return render(request, 'legal/termsandconditions.html', _get_full_context(request))
def aboutus(request): return render(request, 'company/aboutus.html', _get_full_context(request))
def contactus(request): return render(request, 'company/contactus.html', _get_full_context(request))