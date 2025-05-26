# AudioXApp/views/content_views.py

import random
import requests
import feedparser
import mimetypes
import json
from urllib.parse import urlparse, quote
from django.db.models import Q
from decimal import Decimal, InvalidOperation
import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse, Http404
from django.contrib import messages
from django.core.cache import cache
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Avg, F
from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.utils.timesince import timesince
from django.db import transaction
from django.utils import timezone

import logging
logger = logging.getLogger(__name__)

from ..models import Audiobook, Chapter, Review, User, AudiobookPurchase, CreatorEarning, Creator, AudiobookViewLog
from .utils import _get_full_context

# --- External Data Fetching (Background Task Recommended) ---

def fetch_audiobooks_data():
    """
    Fetches audiobook data from LibriVox RSS feeds and Archive.org.
    Caches the results. Intended for background execution.
    """
    cache_key = 'librivox_archive_audiobooks_data_v6'
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.info(f"CACHE HIT: Using cached data for audiobooks (key: {cache_key}).")
        return cached_data

    logger.info(f"CACHE MISS: Fetching fresh data for audiobooks (key: {cache_key})...")
    librivox_audiobooks = []
    archive_genre_audiobooks = {}
    archive_language_audiobooks = {}
    fetch_successful = False

    rss_feeds = [
        "https://librivox.org/rss/47", "https://librivox.org/rss/52",
        "https://librivox.org/rss/53", "https://librivox.org/rss/54",
        "https://librivox.org/rss/59", "https://librivox.org/rss/60",
        "https://librivox.org/rss/61", "https://librivox.org/rss/62"
    ]
    session = requests.Session()
    user_agent_host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "AudioXApp.com"
    headers = {'User-Agent': f'AudioXApp/1.0 (+http://{user_agent_host})'}
    rss_timeout = 45

    for rss_url in rss_feeds:
        try:
            response = session.get(rss_url, timeout=rss_timeout, headers=headers)
            response.raise_for_status()
            feed = feedparser.parse(response.content)

            if feed.bozo:
                logger.warning(f"Bozo feed detected for {rss_url}: {feed.bozo_exception}")

            if not feed.entries:
                logger.info(f"No entries found in RSS feed: {rss_url}")
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
                logger.info(f"No chapters with audio found for audiobook in {rss_url}")
                continue

            title = feed.feed.get('title', 'Unknown Title').replace('LibriVox', '').strip()
            description = feed.feed.get('summary', feed.feed.get('itunes_summary', 'No description available.'))
            author = feed.feed.get('author', feed.feed.get('itunes_author', 'Various Authors'))

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
            
            slug = slugify(title) if title and title != 'Unknown Title' else f'librivox-book-{random.randint(1000,9999)}'

            cover_image_proxy_url = None
            if cover_image_original_url:
                try:
                    quoted_image_url = quote(cover_image_original_url, safe='')
                    cover_image_proxy_url = reverse('AudioXApp:fetch_cover_image') + f'?url={quoted_image_url}'
                except Exception as url_err:
                    logger.error(f"Error creating proxy URL for {cover_image_original_url}: {url_err}")

            first_chapter_original_audio_url = chapters_data[0]["audio_url"] if chapters_data else None
            first_chapter_title = chapters_data[0]["chapter_title"] if chapters_data else None

            librivox_audiobooks.append({
                "source": "librivox", "title": title, "description": description, "author": author,
                "cover_image": cover_image_proxy_url, "chapters": chapters_data,
                "first_chapter_audio_url": first_chapter_original_audio_url,
                "first_chapter_title": first_chapter_title, "slug": slug,
                "is_creator_book": False,
                "total_views": 0, "average_rating": None,
                "is_paid": False, "price": Decimal("0.00"),
                "language": feed.feed.get('language', 'en')
            })
            fetch_successful = True
        except requests.exceptions.Timeout as e:
            logger.error(f"TIMEOUT error fetching RSS feed {rss_url}: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"RequestException error fetching RSS feed {rss_url}: {e}")
        except Exception as e:
            logger.error(f"Generic error processing RSS feed {rss_url}: {e}", exc_info=True)

    base_url = "https://archive.org/advancedsearch.php"
    search_terms = [
        "Fiction", "Mystery", "Thriller", "Science Fiction",
        "Fantasy", "Romance", "Biography", "History",
        "Self-Help", "Business",
        "Urdu", "Punjabi", "Sindhi"
    ]
    language_specific_terms = ["Urdu", "Punjabi", "Sindhi"]
    archive_timeout = 30

    for term in search_terms:
        query_string = ""
        if term in language_specific_terms:
            query_string = f'language:"{term}" AND collection:librivoxaudio AND mediatype:audio'
        else:
            query_string = f'subject:"{term}" AND collection:librivoxaudio AND mediatype:audio'

        params = {
            "q": query_string,
            "fl[]": ["identifier", "title", "creator", "description", "subject", "language"],
            "rows": 10,
            "output": "json"
        }
        try:
            response = session.get(base_url, params=params, timeout=archive_timeout, headers=headers)
            response.raise_for_status()
            data = response.json()
            docs = data.get('response', {}).get('docs', [])
            audiobooks_for_term = []

            for doc in docs:
                identifier = doc.get('identifier')
                title = doc.get('title', 'Unknown Title')
                creator_data = doc.get('creator', 'Unknown Author')
                if isinstance(creator_data, list):
                    author = ', '.join(creator_data)
                else:
                    author = creator_data

                description_data = doc.get('description', 'No description available.')
                if isinstance(description_data, list):
                    description = ' '.join(description_data)
                else:
                    description = description_data
                
                subjects = doc.get('subject', [])
                language_from_doc = doc.get('language', 'English')
                if isinstance(language_from_doc, list):
                    language_from_doc = language_from_doc[0] if language_from_doc else 'English'

                if not identifier: continue

                meta_url = f"https://archive.org/metadata/{identifier}"
                meta_resp = session.get(meta_url, timeout=archive_timeout, headers=headers)
                meta_resp.raise_for_status()
                meta_data = meta_resp.json()
                files = meta_data.get("files", [])
                chapters = []

                for f_item in files:
                    if f_item.get("format") in ["VBR MP3", "MP3", "64Kbps MP3", "128Kbps MP3"] and "name" in f_item:
                        chapter_title_raw = f_item.get("title", f_item.get("name", 'Untitled Chapter'))
                        if not isinstance(chapter_title_raw, str):
                            chapter_title_raw = str(chapter_title_raw)
                        chapter_title = chapter_title_raw.replace('"', '').strip()
                        chapters.append({
                            "chapter_title": chapter_title,
                            "audio_url": f"https://archive.org/download/{identifier}/{quote(f_item['name'])}"
                        })
                if not chapters: continue
                
                slug = slugify(title) if title and title != 'Unknown Title' else f'archive-{term.lower().replace(" ", "-")}-{random.randint(1000,9999)}'

                book_data = {
                    "source": "archive", "title": title, "description": description,
                    "author": author, "cover_image": f"https://archive.org/services/img/{identifier}",
                    "chapters": chapters,
                    "first_chapter_audio_url": chapters[0]["audio_url"] if chapters else None,
                    "first_chapter_title": chapters[0]["chapter_title"] if chapters else None,
                    "slug": slug,
                    "is_creator_book": False,
                    "total_views": 0,
                    "average_rating": None,
                    "is_paid": False, "price": Decimal("0.00"),
                    "subjects": subjects,
                    "language": language_from_doc,
                    "genre": term if term not in language_specific_terms else None
                }
                audiobooks_for_term.append(book_data)

            if audiobooks_for_term:
                if term in language_specific_terms:
                    archive_language_audiobooks[term] = audiobooks_for_term
                else:
                    archive_genre_audiobooks[term] = audiobooks_for_term
                fetch_successful = True
        except requests.exceptions.Timeout as e:
            logger.error(f"TIMEOUT error fetching term '{term}' from Archive.org: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"RequestException error fetching term '{term}' from Archive.org: {e}")
        except Exception as e:
            logger.error(f"Generic error processing term '{term}' data from Archive.org: {e}", exc_info=True)

    combined_data = {
        "librivox_audiobooks": librivox_audiobooks,
        "archive_genre_audiobooks": archive_genre_audiobooks,
        "archive_language_audiobooks": archive_language_audiobooks
    }

    if fetch_successful:
        new_cache_duration = 6 * 60 * 60  # 6 hours in seconds (21600)
        logger.info(f"CACHE SET: Storing fetched data in cache (key: {cache_key}, duration: {new_cache_duration}s).")
        cache.set(cache_key, combined_data, new_cache_duration) 
        return combined_data
    else:
        logger.warning(f"FETCH UNSUCCESSFUL: No new data to cache. Returning potentially partial or None.")
        if librivox_audiobooks or archive_genre_audiobooks or archive_language_audiobooks:
            return combined_data
        else:
            return None

@require_GET
def api_audiobooks(request):
    cache_key = 'librivox_archive_audiobooks_data_v6'
    data = cache.get(cache_key)
    if data is not None:
        return JsonResponse(data, safe=False)
    else:
        return JsonResponse({"message": "Audiobook data is currently being updated or is not available. Please try again shortly."}, status=202)

def home(request):
    context = _get_full_context(request)
    cache_key = 'librivox_archive_audiobooks_data_v6'
    audiobook_data = cache.get(cache_key)
    context["librivox_audiobooks"] = []
    context["archive_genre_audiobooks"] = {}
    context["creator_audiobooks"] = []
    context["error_message"] = None
    if audiobook_data is not None:
        context["librivox_audiobooks"] = audiobook_data.get("librivox_audiobooks", [])
        english_genres = {}
        for genre, book_list in audiobook_data.get("archive_genre_audiobooks", {}).items():
            english_genres[genre] = [
                book for book in book_list
                if 'English' in book.get('language', 'English') or 'en' in book.get('language', 'en')
            ]
        context["archive_genre_audiobooks"] = english_genres
    else:
        context["error_message"] = "External audiobook listings are currently being updated. Please check back shortly."
    try:
        first_chapter_prefetch = Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order'), to_attr='first_chapter_list')
        creator_books_qs = Audiobook.objects.filter(status='PUBLISHED', is_creator_book=True, language__iexact='English').select_related('creator').prefetch_related(first_chapter_prefetch, Prefetch('reviews', queryset=Review.objects.select_related('user').order_by('-created_at'))).order_by('-publish_date')[:12]
        creator_books_list = []
        for book in creator_books_qs:
            first_chapter_audio_url = None
            first_chapter_title = None
            if hasattr(book, 'first_chapter_list') and book.first_chapter_list:
                first_chapter = book.first_chapter_list[0]
                first_chapter_title = first_chapter.chapter_name
                if first_chapter.audio_file: first_chapter_audio_url = first_chapter.audio_file.url
            creator_books_list.append({'source': 'creator', 'title': book.title, 'slug': book.slug, 'cover_image': book.cover_image.url if book.cover_image else None, 'author': book.author, 'creator': book.creator, 'first_chapter_audio_url': first_chapter_audio_url, 'first_chapter_title': first_chapter_title, 'is_creator_book': True, 'average_rating': book.average_rating, 'total_views': book.total_views, 'is_paid': book.is_paid, 'price': book.price, 'status': book.status, 'language': book.language, 'genre': book.genre})
        context["creator_audiobooks"] = creator_books_list
        if not creator_books_list and not context["librivox_audiobooks"] and not context["archive_genre_audiobooks"] and not context["error_message"]:
            context["error_message"] = "No English audiobooks are currently available from any source."
    except Exception as db_err:
        logger.error(f"Error fetching creator audiobooks for English homepage: {db_err}", exc_info=True)
        if not context["librivox_audiobooks"] and not context["archive_genre_audiobooks"] and not context["creator_audiobooks"]:
            context["error_message"] = "Failed to load any audiobooks at this time. Please try again later."
            if not messages.get_messages(request) and audiobook_data is None: messages.error(request, "We encountered an issue loading audiobook data.")
    return render(request, "audiobooks/English/English_Home.html", context)

def _render_genre_or_language_page(request, page_type, display_name, template_name, cache_key_segment, query_term):
    context = _get_full_context(request)
    cache_key = 'librivox_archive_audiobooks_data_v6'
    external_audiobook_data = cache.get(cache_key)
    context["display_name"] = display_name
    context["audiobooks_list"] = []
    context["creator_audiobooks"] = []
    context["error_message"] = None
    if external_audiobook_data:
        source_dict = external_audiobook_data.get(cache_key_segment, {})
        context["audiobooks_list"] = source_dict.get(query_term, [])
    else:
        context["error_message"] = f"External listings for {display_name} are currently being updated."
    try:
        first_chapter_prefetch = Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order'), to_attr='first_chapter_list')
        creator_books_query = Audiobook.objects.filter(status='PUBLISHED', is_creator_book=True)
        if page_type == "genre": creator_books_query = creator_books_query.filter(language__iexact='English', genre__iexact=query_term)
        elif page_type == "language": creator_books_query = creator_books_query.filter(language__iexact=query_term)
        creator_books_qs = creator_books_query.select_related('creator').prefetch_related(first_chapter_prefetch, Prefetch('reviews', queryset=Review.objects.select_related('user').order_by('-created_at'))).order_by('-publish_date')
        creator_books_list = []
        for book in creator_books_qs:
            first_chapter_audio_url = None
            first_chapter_title = None
            if hasattr(book, 'first_chapter_list') and book.first_chapter_list:
                first_chapter = book.first_chapter_list[0]
                first_chapter_title = first_chapter.chapter_name
                if first_chapter.audio_file: first_chapter_audio_url = first_chapter.audio_file.url
            creator_books_list.append({'source': 'creator', 'title': book.title, 'slug': book.slug, 'cover_image': book.cover_image.url if book.cover_image else None, 'author': book.author, 'creator': book.creator, 'first_chapter_audio_url': first_chapter_audio_url, 'first_chapter_title': first_chapter_title, 'is_creator_book': True, 'average_rating': book.average_rating, 'total_views': book.total_views, 'is_paid': book.is_paid, 'price': book.price, 'status': book.status, 'language': book.language, 'genre': book.genre})
        context["creator_audiobooks"] = creator_books_list
        if not creator_books_list and not context["audiobooks_list"] and not context["error_message"]:
            context["error_message"] = f"No audiobooks found for {display_name} at the moment."
    except Exception as db_err:
        logger.error(f"Error fetching creator audiobooks for {page_type} '{display_name}': {db_err}", exc_info=True)
        if not context["audiobooks_list"] and not context["creator_audiobooks"]:
            context["error_message"] = f"Failed to load audiobooks for {display_name}. Please try again later."
            if not messages.get_messages(request) and external_audiobook_data is None: messages.error(request, f"We encountered an issue loading data for {display_name}.")
    return render(request, template_name, context)

def genre_fiction(request): return _render_genre_or_language_page(request, "genre", "Fiction", 'audiobooks/English/genrefiction.html', "archive_genre_audiobooks", "Fiction")
def genre_mystery(request): return _render_genre_or_language_page(request, "genre", "Mystery", 'audiobooks/English/genremystery.html', "archive_genre_audiobooks", "Mystery")
def genre_thriller(request): return _render_genre_or_language_page(request, "genre", "Thriller", 'audiobooks/English/genrethriller.html', "archive_genre_audiobooks", "Thriller")
def genre_scifi(request): return _render_genre_or_language_page(request, "genre", "Science Fiction", 'audiobooks/English/genrescifi.html', "archive_genre_audiobooks", "Science Fiction")
def genre_fantasy(request): return _render_genre_or_language_page(request, "genre", "Fantasy", 'audiobooks/English/genrefantasy.html', "archive_genre_audiobooks", "Fantasy")
def genre_romance(request): return _render_genre_or_language_page(request, "genre", "Romance", 'audiobooks/English/genreromance.html', "archive_genre_audiobooks", "Romance")
def genre_biography(request): return _render_genre_or_language_page(request, "genre", "Biography", 'audiobooks/English/genrebiography.html', "archive_genre_audiobooks", "Biography")
def genre_history(request): return _render_genre_or_language_page(request, "genre", "History", 'audiobooks/English/genrehistory.html', "archive_genre_audiobooks", "History")
def genre_selfhelp(request): return _render_genre_or_language_page(request, "genre", "Self-Help", 'audiobooks/English/genreselfhelp.html', "archive_genre_audiobooks", "Self-Help")
def genre_business(request): return _render_genre_or_language_page(request, "genre", "Business", 'audiobooks/English/genrebusiness.html', "archive_genre_audiobooks", "Business")

def urdu_page(request): return _render_genre_or_language_page(request, "language", "Urdu", 'audiobooks/Urdu/Urdu_Home.html', "archive_language_audiobooks", "Urdu")
def punjabi_page(request): return _render_genre_or_language_page(request, "language", "Punjabi", 'audiobooks/Punjabi/Punjabi_Home.html', "archive_language_audiobooks", "Punjabi")
def sindhi_page(request): return _render_genre_or_language_page(request, "language", "Sindhi", 'audiobooks/Sindhi/Sindhi_Home.html', "archive_language_audiobooks", "Sindhi")


def audiobook_detail(request, audiobook_slug):
    audiobook_obj = None
    is_creator_book_page_flag = False
    context = _get_full_context(request)
    template_name = 'audiobook_detail.html' # Default for external books

    reviews_list = []
    user_review_object = None
    current_user_has_reviewed = False
    user_review_data_for_json = { "has_reviewed": False, "rating": 0, "comment": "", "user_id": None }
    if request.user.is_authenticated and hasattr(request.user, 'user_id'):
        user_review_data_for_json["user_id"] = request.user.user_id

    user_has_purchased = False
    chapters_to_display = []
    audiobook_lock_message = None
    context_audiobook_data = None # This will hold either the DB object or the dict for external books

    try:
        # Try to get from DB first (creator books and potentially cached external ones)
        audiobook_obj = Audiobook.objects.prefetch_related(
            Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order')),
            Prefetch('reviews', queryset=Review.objects.select_related('user').order_by('-created_at'))
        ).select_related('creator').get(slug=audiobook_slug)

        is_creator_book_page_flag = audiobook_obj.is_creator_book
        if is_creator_book_page_flag:
            template_name = 'audiobook_creator_details.html'

        reviews_list = audiobook_obj.reviews.all()
        if request.user.is_authenticated:
            try:
                user_review_object = Review.objects.get(audiobook=audiobook_obj, user=request.user)
                current_user_has_reviewed = True
                user_review_data_for_json.update({
                    "has_reviewed": True, "rating": user_review_object.rating,
                    "comment": user_review_object.comment or ""
                })
            except Review.DoesNotExist: pass
            except TypeError: # Handle case where request.user might not be a full User object
                logger.warning(f"TypeError checking review for {request.user} on {audiobook_slug}.")
        
        if is_creator_book_page_flag and audiobook_obj.is_paid:
            if request.user.is_authenticated and hasattr(request.user, 'has_purchased_audiobook'):
                user_has_purchased = request.user.has_purchased_audiobook(audiobook_obj)
            if not user_has_purchased:
                preview_chapter_count = getattr(audiobook_obj, 'preview_chapters', 0)
                if preview_chapter_count > 0:
                    plural_s = "s" if preview_chapter_count > 1 else ""
                    audiobook_lock_message = (
                        f"This is a premium audiobook. Purchase for full access (PKR {audiobook_obj.price:.2f}). "
                        f"You can preview the first {preview_chapter_count} chapter{plural_s}."
                    )
                else:
                    audiobook_lock_message = f"This is a premium audiobook. Purchase for full access (PKR {audiobook_obj.price:.2f}). No preview chapters available."

        all_db_chapters = audiobook_obj.chapters.all().order_by('chapter_order')
        preview_limit = 0
        if is_creator_book_page_flag and audiobook_obj.is_paid and not user_has_purchased:
            preview_limit = getattr(audiobook_obj, 'preview_chapters', 0)

        for i, chapter_db_obj in enumerate(all_db_chapters):
            is_accessible = True # Default for free/purchased or non-creator books handled by initial logic
            if is_creator_book_page_flag and audiobook_obj.is_paid and not user_has_purchased:
                is_accessible = i < preview_limit
            
            chapters_to_display.append({
                'object': chapter_db_obj, 'is_accessible': is_accessible,
                'audio_url': chapter_db_obj.audio_file.url if chapter_db_obj.audio_file else None,
                'chapter_title': chapter_db_obj.chapter_name,
                'duration': getattr(chapter_db_obj, 'duration_display', '--:--'), # Assuming duration_display is a property or field
                'chapter_index': i
            })
        context_audiobook_data = audiobook_obj # For creator books, this is the DB object

    except Audiobook.DoesNotExist:
        logger.info(f"Audiobook with slug '{audiobook_slug}' not in DB. Checking cache for external book.")
        cache_key = 'librivox_archive_audiobooks_data_v6'
        external_audiobook_data_cache = cache.get(cache_key)
        found_external_book_dict = None

        if external_audiobook_data_cache:
            for source_key in ["librivox_audiobooks", "archive_genre_audiobooks", "archive_language_audiobooks"]:
                if source_key == "librivox_audiobooks":
                    item_list = external_audiobook_data_cache.get(source_key, [])
                    for book_dict_item in item_list:
                        if book_dict_item.get('slug') == audiobook_slug:
                            found_external_book_dict = book_dict_item
                            break
                else: # For archive_genre_audiobooks and archive_language_audiobooks (which are dicts of lists)
                    for _, book_list_items in external_audiobook_data_cache.get(source_key, {}).items():
                        for book_dict_item in book_list_items:
                            if book_dict_item.get('slug') == audiobook_slug:
                                found_external_book_dict = book_dict_item
                                break
                        if found_external_book_dict: break
                if found_external_book_dict: break
        
        if found_external_book_dict:
            is_creator_book_page_flag = False # It's an external book
            template_name = 'audiobook_detail.html' # Ensure this is the correct template for external

            # Create or update a minimal Audiobook entry for reviews and tracking if it doesn't exist
            # This ensures reviews can be attached to a stable DB ID.
            audiobook_obj, created = Audiobook.objects.get_or_create(
                slug=audiobook_slug,
                defaults={
                    'title': found_external_book_dict.get('title', 'Unknown Title'),
                    'author': found_external_book_dict.get('author'),
                    'description': found_external_book_dict.get('description'), # Keep it short or consider not storing full desc
                    'language': found_external_book_dict.get('language'),
                    'genre': found_external_book_dict.get('genre'), # If available
                    'source': found_external_book_dict.get('source', 'librivox'), # Or 'archive'
                    'is_creator_book': False,
                    'creator': None,
                    'is_paid': False,
                    'price': Decimal('0.00'),
                    'status': 'PUBLISHED', # Assuming external books are always considered published
                    # cover_image_url: found_external_book_dict.get('cover_image') # If you want to store this
                }
            )
            if created:
                logger.info(f"Created new Audiobook DB entry for external book: {audiobook_slug} to allow reviews/tracking.")
            else: # If it exists, maybe update some fields if necessary, or just use it
                pass

            reviews_list = audiobook_obj.reviews.select_related('user').order_by('-created_at').all()
            if request.user.is_authenticated:
                try:
                    user_review_object = Review.objects.get(audiobook=audiobook_obj, user=request.user)
                    current_user_has_reviewed = True
                    user_review_data_for_json.update({
                        "has_reviewed": True, "rating": user_review_object.rating,
                        "comment": user_review_object.comment or ""
                    })
                except Review.DoesNotExist: pass
            
            # Populate chapters_to_display from the dictionary
            for i, ch_info in enumerate(found_external_book_dict.get('chapters', [])):
                chapters_to_display.append({
                    'object': None, # No DB object for external chapters unless you model them
                    'chapter_title': ch_info.get('chapter_title'),
                    'audio_url': ch_info.get('audio_url'),
                    'is_accessible': True, # External book chapters are generally all accessible
                    'duration': ch_info.get('duration', '--:--'), # If duration is available in cache
                    'chapter_index': i
                })
            
            context_audiobook_data = found_external_book_dict # For external books, this is the dict
            # Ensure essential keys for the template are present in the dict
            context_audiobook_data.setdefault('author', 'Unknown Author') # Default if not in dict
            context_audiobook_data['source'] = audiobook_obj.source # Ensure source is from DB obj
            # Add total_views and average_rating from the DB object
            context_audiobook_data.setdefault('total_views', audiobook_obj.total_views)
            context_audiobook_data.setdefault('average_rating', audiobook_obj.average_rating)


        else: # Not in DB and not in cache
            messages.error(request, "Audiobook not found or is not available.")
            logger.warning(f"Audiobook with slug '{audiobook_slug}' not found in DB or cache.")
            raise Http404("Audiobook not found or is not available.")

    # Log the view and increment view count for the DB object (audiobook_obj)
    if audiobook_obj: # Ensure we have a DB object to work with for logging and view counts
        current_user_for_log = request.user if request.user.is_authenticated else None
        
        # Create a view log entry regardless of whether total_views is incremented this time
        AudiobookViewLog.objects.create(audiobook=audiobook_obj, user=current_user_for_log)

        # Determine if total_views on the Audiobook model should be incremented
        should_increment_total_views = False
        if audiobook_obj.is_creator_book: # Always increment for creator books on each detail view load
            should_increment_total_views = True
        else: # For external books, limit view count increment to once per 24 hours per user/session
            twenty_four_hours_ago = timezone.now() - timezone.timedelta(hours=24)
            if request.user.is_authenticated:
                # Check if a view log for this user and book exists within the last 24 hours
                # The current view log was just created, so we check for count > 1 (meaning previous + current)
                # More accurately, check for a log *before* this current one.
                # Simplification: if this is the *first* view by this user for this book in the last 24h for this new log entry.
                if AudiobookViewLog.objects.filter(
                    audiobook=audiobook_obj, 
                    user=request.user, 
                    viewed_at__gte=twenty_four_hours_ago
                ).count() == 1: # Only the one we just created
                    should_increment_total_views = True
            else: # Anonymous user, use session
                last_viewed_timestamps = request.session.get('last_viewed_external_books', {})
                slug_last_viewed_str = last_viewed_timestamps.get(audiobook_obj.slug)
                
                if slug_last_viewed_str:
                    try:
                        slug_last_viewed_dt = timezone.datetime.fromisoformat(slug_last_viewed_str)
                        if settings.USE_TZ and timezone.is_naive(slug_last_viewed_dt):
                             slug_last_viewed_dt = timezone.make_aware(slug_last_viewed_dt, timezone.get_default_timezone())
                        
                        if timezone.now() >= slug_last_viewed_dt + timezone.timedelta(hours=24):
                            should_increment_total_views = True
                            last_viewed_timestamps[audiobook_obj.slug] = timezone.now().isoformat()
                            request.session['last_viewed_external_books'] = last_viewed_timestamps
                    except ValueError: # Handle cases where isoformat parsing might fail
                        should_increment_total_views = True
                        last_viewed_timestamps[audiobook_obj.slug] = timezone.now().isoformat()
                        request.session['last_viewed_external_books'] = last_viewed_timestamps
                else: # First view in session
                    should_increment_total_views = True
                    last_viewed_timestamps[audiobook_obj.slug] = timezone.now().isoformat()
                    request.session['last_viewed_external_books'] = last_viewed_timestamps

        if should_increment_total_views:
            Audiobook.objects.filter(pk=audiobook_obj.pk).update(total_views=F('total_views') + 1)
            audiobook_obj.refresh_from_db(fields=['total_views']) # Refresh the object
            # If context_audiobook_data is a dict (for external books), update its view count
            if isinstance(context_audiobook_data, dict):
                 context_audiobook_data['total_views'] = audiobook_obj.total_views


    context['audiobook'] = context_audiobook_data
    context['audiobook_db_id_for_review'] = audiobook_obj.audiobook_id if audiobook_obj else None
    context['is_creator_book_page'] = is_creator_book_page_flag
    context['reviews'] = reviews_list
    context['user_review_object'] = user_review_object
    context['current_user_has_reviewed'] = current_user_has_reviewed
    context['user_review_data_json'] = json.dumps(user_review_data_for_json)
    context['user_has_purchased'] = user_has_purchased
    context['chapters_to_display'] = chapters_to_display
    context['audiobook_lock_message'] = audiobook_lock_message

    if hasattr(settings, 'STRIPE_PUBLISHABLE_KEY'):
        context['STRIPE_PUBLISHABLE_KEY'] = settings.STRIPE_PUBLISHABLE_KEY

    return render(request, template_name, context)


@login_required
@require_POST
@csrf_protect # Ensure CSRF protection
def add_review(request, audiobook_slug):
    try:
        # Use the Audiobook DB object for review, whether it's a creator book or an external one (that was get_or_created)
        audiobook = get_object_or_404(Audiobook, slug=audiobook_slug)
        can_review = False

        # Logic to determine if a user can review:
        # 1. Non-paid (free) books can always be reviewed by logged-in users.
        # 2. Paid creator books require purchase.
        # (External books are usually free, if they were paid, this logic would need extension)
        if not audiobook.is_paid: # Covers free creator books and all external books (assumed free)
            can_review = True
        elif audiobook.is_paid and audiobook.is_creator_book: # Paid creator book
            if request.user.is_authenticated and hasattr(request.user, 'has_purchased_audiobook'):
                if request.user.has_purchased_audiobook(audiobook):
                    can_review = True
        
        if not can_review:
            return JsonResponse({'status': 'error', 'message': 'You must purchase this audiobook or it must be free to leave a review.'}, status=403)

        try:
            data = json.loads(request.body)
            rating_str = data.get('rating')
            comment = data.get('comment', '').strip()
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON format in request body.'}, status=400)

        try:
            rating = int(rating_str)
            if not 1 <= rating <= 5:
                raise ValueError("Rating must be between 1 and 5.")
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid rating value. Please provide a whole number between 1 and 5.'}, status=400)

        with transaction.atomic():
            review, created = Review.objects.update_or_create(
                audiobook=audiobook,
                user=request.user,
                defaults={'rating': rating, 'comment': comment}
            )
        
        # Recalculate average rating on the Audiobook model instance
        audiobook.refresh_from_db() # To get the latest review set for average calculation
        new_average_rating_val = audiobook.average_rating # This should be updated by the signal or model's save method

        message = "Review updated successfully!" if not created else "Review added successfully!"
        user_profile_pic_url = None
        if hasattr(review.user, 'profile_pic') and review.user.profile_pic:
            try: user_profile_pic_url = review.user.profile_pic.url
            except ValueError: pass # Handle missing file gracefully

        review_data = {
            'review_id': review.review_id, 'rating': review.rating, 'comment': review.comment or "",
            'user_id': getattr(review.user, 'user_id', getattr(review.user, 'id', None)), # Handle potential differences in user model id attribute
            'user_name': getattr(review.user, 'full_name', review.user.username) or review.user.username,
            'user_profile_pic': user_profile_pic_url, 'created_at': review.created_at.isoformat(),
            'timesince': timesince(review.created_at) + " ago",
        }
        return JsonResponse({'status': 'success', 'message': message, 'created': created, 'new_average_rating': str(new_average_rating_val) if new_average_rating_val is not None else "0.0", 'review_data': review_data})
    except Audiobook.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error in add_review for {audiobook_slug}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected server error occurred. Please try again.'}, status=500)

@csrf_exempt # Consider if this is safe or if you need CSRF for GET proxy
@require_GET
def stream_audio(request):
    audio_url_param = request.GET.get("url")
    if not audio_url_param: return JsonResponse({"error": "No audio URL provided"}, status=400)
    
    target_audio_url = audio_url_param
    parsed_url = urlparse(target_audio_url)

    # Check if it's a local media URL (relative to MEDIA_URL)
    is_local_media = target_audio_url.startswith(settings.MEDIA_URL) and not parsed_url.scheme and not parsed_url.netloc
    
    if is_local_media:
        try:
            # Ensure it's an absolute URI if it's local to make requests.get work if needed,
            # or handle serving directly from Django for local files (safer).
            # For simplicity, if you are proxying local files too via requests.get:
            if not target_audio_url.startswith(('http://', 'https://')):
                 target_audio_url = request.build_absolute_uri(target_audio_url)
        except Exception as e:
            logger.error(f"Error processing local audio URL for streaming: {e}")
            return HttpResponse("Error processing local audio URL", status=500)
    elif not all([parsed_url.scheme, parsed_url.netloc]): # Check if it's a valid absolute URL
        return HttpResponse(f"Invalid audio URL provided: {audio_url_param}", status=400)

    try:
        range_header = request.headers.get('Range', None)
        user_agent_host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "audiox.com" # Fallback
        proxy_headers = {'User-Agent': f'AudioXApp Audio Proxy/1.0 (+http://{user_agent_host})'}
        if range_header: proxy_headers['Range'] = range_header
        
        audio_stream_timeout = 45 # seconds
        response = requests.get(target_audio_url, stream=True, headers=proxy_headers, timeout=audio_stream_timeout)
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)

        content_type = response.headers.get('Content-Type', 'audio/mpeg')
        # Validate or guess content type if not explicitly audio
        if not content_type.lower().startswith('audio/'):
            guessed_type, _ = mimetypes.guess_type(target_audio_url)
            content_type = guessed_type if guessed_type and guessed_type.startswith('audio/') else 'audio/mpeg'

        def generate_audio_chunks():
            try:
                for chunk in response.iter_content(chunk_size=8192): # 8KB chunks
                    if chunk: yield chunk
            finally:
                response.close() # Ensure the response is closed

        streaming_response = StreamingHttpResponse(generate_audio_chunks(), content_type=content_type)
        
        # Forward relevant headers for streaming and content negotiation
        if 'Content-Range' in response.headers: streaming_response['Content-Range'] = response.headers['Content-Range']
        if 'Content-Length' in response.headers: streaming_response['Content-Length'] = response.headers['Content-Length']
        streaming_response['Accept-Ranges'] = 'bytes' # Important for seeking
        streaming_response.status_code = response.status_code # Forward the status code (e.g., 206 Partial Content)
        
        return streaming_response

    except requests.exceptions.Timeout:
        logger.error(f"Timeout streaming audio from: {target_audio_url}")
        return HttpResponse("Audio stream timed out from external source", status=408)
    except requests.exceptions.HTTPError as e_http:
        logger.error(f"HTTPError streaming audio from {target_audio_url}: {e_http.response.status_code} - {e_http.response.text[:200]}")
        return HttpResponse(f"Error fetching audio from external source: Status {e_http.response.status_code}", status=e_http.response.status_code)
    except requests.exceptions.RequestException as e_req: # Other network errors
        logger.error(f"RequestException streaming audio from {target_audio_url}: {e_req}")
        return HttpResponse("Error processing audio stream (could not connect to external source)", status=502) # Bad Gateway
    except SuspiciousOperation as e_susp: # If Django detects suspicious operations with the URL
        logger.warning(f"SuspiciousOperation in stream_audio: {e_susp}")
        return JsonResponse({"error": str(e_susp)}, status=400)
    except Exception as e_gen:
        logger.error(f"Generic error in stream_audio from {target_audio_url}: {e_gen}", exc_info=True)
        return HttpResponse("Internal server error during audio streaming", status=500)


@csrf_exempt # Consider if this is safe or if you need CSRF for GET proxy
@require_GET
def fetch_cover_image(request):
    image_url = request.GET.get("url")
    if not image_url: return JsonResponse({"error": "No image URL provided"}, status=400)

    target_image_url = image_url
    parsed_url = urlparse(image_url)
    
    is_local_media = image_url.startswith(settings.MEDIA_URL) and not parsed_url.scheme and not parsed_url.netloc
    if is_local_media:
        try:
            if not target_image_url.startswith(('http://', 'https://')):
                target_image_url = request.build_absolute_uri(target_image_url)
        except Exception as e:
            logger.error(f"Error processing local image URL for proxy: {e}")
            return HttpResponse("Error processing local image URL", status=500)
    elif not all([parsed_url.scheme, parsed_url.netloc]):
        return HttpResponse("Invalid image URL provided", status=400)

    try:
        user_agent_host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "AudioXApp.com"
        proxy_headers = {'User-Agent': f'AudioXApp Image Proxy/1.0 (+http://{user_agent_host})'}
        image_fetch_timeout = 30 # seconds
        
        response = requests.get(target_image_url, stream=True, timeout=image_fetch_timeout, headers=proxy_headers)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', 'image/jpeg') # Default to jpeg
        if not content_type.lower().startswith('image/'):
            guessed_type, _ = mimetypes.guess_type(target_image_url)
            content_type = guessed_type if guessed_type and guessed_type.startswith('image/') else 'image/jpeg'
        
        streaming_response = StreamingHttpResponse(response.iter_content(chunk_size=8192), content_type=content_type)
        if 'Content-Length' in response.headers: streaming_response['Content-Length'] = response.headers['Content-Length']
        streaming_response.status_code = response.status_code
        
        return streaming_response
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout fetching image from: {target_image_url}")
        return HttpResponse("Image fetch timed out", status=408)
    except requests.exceptions.HTTPError as e_http:
        logger.warning(f"HTTPError fetching image from {target_image_url}: {e_http.response.status_code}")
        return HttpResponse(f"Error fetching image: {e_http.response.status_code}", status=e_http.response.status_code)
    except requests.exceptions.RequestException as e_req:
        logger.warning(f"RequestException fetching image from {target_image_url}: {e_req}")
        return HttpResponse("Failed to fetch image", status=502)
    except SuspiciousOperation as e_susp:
        logger.warning(f"SuspiciousOperation in fetch_cover_image: {e_susp}")
        return JsonResponse({"error": str(e_susp)}, status=400)
    except Exception as e_gen:
        logger.error(f"Generic error in fetch_cover_image from {target_image_url}: {e_gen}", exc_info=True)
        return HttpResponse("Internal server error", status=500)


def search_results_view(request):
    query = request.GET.get('q', '').strip().lower()
    processed_results = []
    seen_slugs = set() # To avoid duplicates if a book is in DB and also from external source matching query
    common_context = _get_full_context(request)

    if query:
        # Search in creator-uploaded books (Audiobook model where is_creator_book=True)
        db_audiobooks = Audiobook.objects.filter(
            Q(title__icontains=query) | Q(author__icontains=query) | Q(creator__creator_name__icontains=query) |
            Q(genre__icontains=query) | Q(description__icontains=query), # Consider if description search is too broad/slow
            status='PUBLISHED', is_creator_book=True # Only search published creator books
        ).select_related('creator').distinct().order_by('-publish_date') # Order by relevance or date

        for book in db_audiobooks:
            if book.slug not in seen_slugs:
                processed_results.append({
                    'slug': book.slug, 'title': book.title, 'author': book.author, 
                    'cover_image_url': book.cover_image.url if book.cover_image else None,
                    'creator_name': book.creator.creator_name if book.creator else None,
                    'average_rating': book.average_rating, 'total_views': book.total_views,
                    'is_creator_book': True, 'source_type': 'creator',
                    'price': book.price, 'is_paid': book.is_paid,
                    'genre': book.genre, 'language': book.language
                })
                seen_slugs.add(book.slug)

        # Search in external audiobooks from cache
        cache_key = 'librivox_archive_audiobooks_data_v6'
        cached_data = cache.get(cache_key)
        if cached_data:
            external_sources_to_search = [
                ("librivox_audiobooks", "librivox"), 
                ("archive_genre_audiobooks", "archive.org"), 
                ("archive_language_audiobooks", "archive.org")
            ]
            for source_list_key, source_type_val in external_sources_to_search:
                if source_list_key == "librivox_audiobooks": # This is a list
                    item_list = cached_data.get(source_list_key, [])
                    for book_dict in item_list:
                        book_slug = book_dict.get('slug')
                        if book_slug and book_slug not in seen_slugs: # Check if already added from DB
                            # Check multiple fields for the query
                            title_match = query in book_dict.get('title', '').lower()
                            desc_match = query in book_dict.get('description', '').lower()
                            author_match = query in book_dict.get('author', '').lower() if book_dict.get('author') else False
                            genre_match = query in book_dict.get('genre', '').lower() if book_dict.get('genre') else False
                            lang_match = query in book_dict.get('language', '').lower() if book_dict.get('language') else False

                            if title_match or desc_match or author_match or genre_match or lang_match:
                                processed_results.append({
                                    'slug': book_slug, 'title': book_dict.get('title'), 
                                    'author': book_dict.get('author', 'LibriVox'), 
                                    'cover_image_url': book_dict.get('cover_image'), # This is already proxied URL
                                    'creator_name': None, 'average_rating': None, 'total_views': None, # External books might not have these tracked same way
                                    'is_creator_book': False, 'source_type': source_type_val,
                                    'price': Decimal("0.00"), 'is_paid': False,
                                    'genre': book_dict.get('genre'), 'language': book_dict.get('language')
                                })
                                seen_slugs.add(book_slug)
                else: # For archive_... which are dicts of lists
                    for term_key, term_books_list in cached_data.get(source_list_key, {}).items():
                        for book_dict in term_books_list:
                            book_slug = book_dict.get('slug')
                            if book_slug and book_slug not in seen_slugs:
                                title_match = query in book_dict.get('title', '').lower()
                                desc_match = query in book_dict.get('description', '').lower()
                                author_match = query in book_dict.get('author', '').lower()
                                # Archive books might have 'subjects' list instead of a single 'genre' string
                                subject_match = any(query in subject.lower() for subject in book_dict.get('subjects', []))
                                genre_match = query in book_dict.get('genre', '').lower() if book_dict.get('genre') else False
                                lang_match = query in book_dict.get('language', '').lower() if book_dict.get('language') else False
                                
                                if title_match or desc_match or author_match or subject_match or genre_match or lang_match:
                                    processed_results.append({
                                        'slug': book_slug, 'title': book_dict.get('title'), 
                                        'author': book_dict.get('author'), 
                                        'cover_image_url': book_dict.get('cover_image'), # Archive.org direct image URL
                                        'creator_name': None, 'average_rating': None, 'total_views': None,
                                        'is_creator_book': False, 'source_type': source_type_val,
                                        'price': Decimal("0.00"), 'is_paid': False,
                                        'genre': book_dict.get('genre'), 'language': book_dict.get('language')
                                    })
                                    seen_slugs.add(book_slug)
        else:
            logger.warning("Search: External audiobook cache is empty or not available.")
            messages.info(request, "External audiobook listings are currently being updated. Search results may be limited.")

    context_data = {
        'query': request.GET.get('q', '').strip(), 
        'results': processed_results,
        'page_title': f"Search Results for '{request.GET.get('q', '').strip()}'" if query else "Search Audiobooks"
    }
    context_data.update(common_context) # Add common context like user info, CSRF token
    return render(request, 'audiobooks/English/english_search.html', context_data)