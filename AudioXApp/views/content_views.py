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
from django.db.models import Prefetch, Avg
from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.utils.timesince import timesince
from django.db import transaction
from django.utils import timezone # Ensure timezone is imported if used

import logging
logger = logging.getLogger(__name__)

from ..models import Audiobook, Chapter, Review, User, AudiobookPurchase, CreatorEarning, Creator
from .utils import _get_full_context

# --- External Data Fetching (Background Task Recommended) ---

def fetch_audiobooks_data():
    """
    Fetches audiobook data from LibriVox RSS feeds and Archive.org.
    Caches the results. Intended for background execution.
    """
    cache_key = 'librivox_archive_audiobooks_data_v5'
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.info(f"CACHE HIT: Using cached data for audiobooks (key: {cache_key}).")
        return cached_data

    logger.info(f"CACHE MISS: Fetching fresh data for audiobooks (key: {cache_key})...")
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
                    quoted_image_url = quote(cover_image_original_url, safe='')
                    cover_image_proxy_url = reverse('AudioXApp:fetch_cover_image') + f'?url={quoted_image_url}'
                except Exception as url_err:
                    logger.error(f"Error creating proxy URL for {cover_image_original_url}: {url_err}")

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
            logger.error(f"TIMEOUT error fetching RSS feed {rss_url}: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"RequestException error fetching RSS feed {rss_url}: {e}")
        except Exception as e:
            logger.error(f"Generic error processing RSS feed {rss_url}: {e}", exc_info=True)

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
                            "audio_url": f"https://archive.org/download/{identifier}/{quote(f_item['name'])}"
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
                    "subjects": subjects,
                }
                audiobooks_for_term.append(book_data)

            if audiobooks_for_term:
                if term in ["Urdu", "Punjabi", "Sindhi"]:
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
        logger.info(f"CACHE SET: Storing fetched data in cache (key: {cache_key}, duration: 3600s).")
        cache.set(cache_key, combined_data, 3600)
        return combined_data
    else:
        logger.warning(f"FETCH UNSUCCESSFUL: No new data to cache. Returning potentially partial or None.")
        if librivox_audiobooks or archive_genre_audiobooks or archive_language_audiobooks:
            return combined_data
        else:
            return None

# --- API Endpoint for Cached Data ---

@require_GET
def api_audiobooks(request):
    """API endpoint to get cached audiobook data."""
    cache_key = 'librivox_archive_audiobooks_data_v5'
    data = cache.get(cache_key)

    if data is not None:
        return JsonResponse(data, safe=False)
    else:
        return JsonResponse({"message": "Audiobook data is currently being updated or is not available. Please try again shortly."}, status=202)

# --- Homepage and Genre/Language Views ---

def home(request):
    """Renders the English home page with audiobooks."""
    context = _get_full_context(request)
    cache_key = 'librivox_archive_audiobooks_data_v5'

    audiobook_data = cache.get(cache_key)

    context["librivox_audiobooks"] = []
    context["archive_genre_audiobooks"] = {}
    context["creator_audiobooks"] = []
    context["error_message"] = None

    if audiobook_data is not None:
        logger.info(f"CACHE HIT for English homepage (external): Using cached data (key: {cache_key}).")
        context["librivox_audiobooks"] = audiobook_data.get("librivox_audiobooks", [])
        english_genres = {}
        for genre, book_list in audiobook_data.get("archive_genre_audiobooks", {}).items():
            english_genres[genre] = [
                book for book in book_list
                if 'English' in book.get('subjects', []) or not any(lang in book.get('subjects', []) for lang in ["Urdu", "Punjabi", "Sindhi"])
            ]
        context["archive_genre_audiobooks"] = english_genres

    else:
        logger.warning(f"CACHE MISS for English homepage (external): No data in cache (key: {cache_key}).")
        context["error_message"] = (
            "External audiobook listings are currently being updated. "
            "Please check back shortly. In the meantime, enjoy content from our creators!"
        )

    try:
        first_chapter_prefetch = Prefetch(
            'chapters',
            queryset=Chapter.objects.order_by('chapter_order'),
            to_attr='first_chapter_list'
        )

        creator_books_qs = Audiobook.objects.filter(
            status='PUBLISHED',
            language__iexact='English'
        ).select_related('creator').prefetch_related(
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
                'language': book.language,
                'genre': book.genre
            })
        context["creator_audiobooks"] = creator_books_list

        if not creator_books_list and not context["librivox_audiobooks"] and not context["archive_genre_audiobooks"]:
             if not context["error_message"]:
                 context["error_message"] = "No English audiobooks are currently available from any source."

    except Exception as db_err:
        logger.error(f"Error fetching creator audiobooks for English homepage: {db_err}", exc_info=True)
        if not context["librivox_audiobooks"] and not context["archive_genre_audiobooks"] and not context["creator_audiobooks"]:
            context["error_message"] = "Failed to load any audiobooks at this time. Please try again later."
            if not messages.get_messages(request) and audiobook_data is None:
                 messages.error(request, "We encountered an issue loading audiobook data.")

    return render(request, "audiobooks/English/English_Home.html", context)


def _render_genre_or_language_page(request, page_type, display_name, template_name, cache_key_segment, query_term):
    """
    Helper function to render genre-specific or language-specific pages.
    Fetches both external (cached) and creator-uploaded audiobooks.
    """
    context = _get_full_context(request)
    cache_key = 'librivox_archive_audiobooks_data_v5'

    external_audiobook_data = cache.get(cache_key)

    context["display_name"] = display_name
    context["audiobooks_list"] = []
    context["creator_audiobooks"] = []
    context["error_message"] = None

    if external_audiobook_data:
        logger.info(f"CACHE HIT for _render_genre_or_language_page (external): Using cached data (key: {cache_key}).")
        source_dict = external_audiobook_data.get(cache_key_segment, {})
        context["audiobooks_list"] = source_dict.get(query_term, [])
    else:
        logger.warning(f"CACHE MISS for _render_genre_or_language_page (external): No data in cache (key: {cache_key}).")
        context["error_message"] = (
            f"External listings for {display_name} are currently being updated. "
            "Please check back shortly. In the meantime, enjoy content from our creators!"
        )

    try:
        first_chapter_prefetch = Prefetch(
            'chapters',
            queryset=Chapter.objects.order_by('chapter_order'),
            to_attr='first_chapter_list'
        )

        creator_books_query = Audiobook.objects.filter(status='PUBLISHED')

        if page_type == "genre":
            creator_books_query = creator_books_query.filter(
                language__iexact='English',
                genre__iexact=query_term
            )
        elif page_type == "language":
            creator_books_query = creator_books_query.filter(
                language__iexact=query_term
            )
        else:
             logger.error(f"Unexpected page_type '{page_type}' in _render_genre_or_language_page.")
             pass

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
                'language': book.language,
                'genre': book.genre
            })
        context["creator_audiobooks"] = creator_books_list

        if not creator_books_list and not context["audiobooks_list"]:
            if not context["error_message"]:
                 context["error_message"] = f"No audiobooks found for {display_name} at the moment."

    except Exception as db_err:
        logger.error(f"Error fetching creator audiobooks for {page_type} '{display_name}': {db_err}", exc_info=True)
        if not context["audiobooks_list"] and not context["creator_audiobooks"]:
            context["error_message"] = f"Failed to load audiobooks for {display_name}. Please try again later."
            if not messages.get_messages(request) and external_audiobook_data is None:
                 messages.error(request, f"We encountered an issue loading data for {display_name}.")

    return render(request, template_name, context)

# --- Specific Genre Views (calls helper) ---

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

# --- Specific Language Views (calls helper) ---

def urdu_page(request):
    return _render_genre_or_language_page(request, "language", "Urdu", 'audiobooks/Urdu/Urdu_Home.html', "archive_language_audiobooks", "Urdu")

def punjabi_page(request):
    return _render_genre_or_language_page(request, "language", "Punjabi", 'audiobooks/Punjabi/Punjabi_Home.html', "archive_language_audiobooks", "Punjabi")

def sindhi_page(request):
    return _render_genre_or_language_page(request, "language", "Sindhi", 'audiobooks/Sindhi/Sindhi_Home.html', "archive_language_audiobooks", "Sindhi")

# --- Audiobook Detail and Review Views ---

@login_required
def audiobook_detail(request, audiobook_slug):
    """Renders the detail page for an audiobook."""
    audiobook_data = None
    is_creator_book = False
    context = _get_full_context(request)
    template_name = 'audiobook_detail.html'

    reviews_list = []
    user_review_object = None
    current_user_has_reviewed = False

    user_review_data_for_json = {
        "has_reviewed": False,
        "rating": 0,
        "comment": "",
        "user_id": None
    }
    if request.user.is_authenticated and hasattr(request.user, 'user_id'):
        user_review_data_for_json["user_id"] = request.user.user_id

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

        reviews_list = audiobook_obj.reviews.all()

        if request.user.is_authenticated:
            try:
                user_review_object = Review.objects.get(audiobook=audiobook_obj, user=request.user)
                current_user_has_reviewed = True

                user_review_data_for_json["has_reviewed"] = True
                user_review_data_for_json["rating"] = user_review_object.rating
                user_review_data_for_json["comment"] = user_review_object.comment or ""
            except Review.DoesNotExist:
                pass
            except TypeError:
                logger.warning(f"TypeError while checking review for user {request.user.username} on {audiobook_slug}.")
                current_user_has_reviewed = False
                user_review_object = None
                user_review_data_for_json["has_reviewed"] = False


        if audiobook_obj.is_paid:
            if request.user.is_authenticated and hasattr(request.user, 'has_purchased_audiobook'):
                user_has_purchased = request.user.has_purchased_audiobook(audiobook_obj)

            if not user_has_purchased:
                is_premium_subscriber = (request.user.is_authenticated and
                                         hasattr(request.user, 'subscription_type') and
                                         request.user.subscription_type == 'PR')

                if audiobook_obj.preview_chapters > 0:
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
                else:
                    can_preview_chapters = False
                    audiobook_lock_message = f"This is a premium audiobook. Purchase for full access (PKR {audiobook_obj.price:.2f}). No preview chapters available."

        all_db_chapters = audiobook_obj.chapters.all().order_by('chapter_order')
        preview_limit = audiobook_obj.preview_chapters if audiobook_obj.is_paid and not user_has_purchased and can_preview_chapters else 0

        for i, chapter_obj in enumerate(all_db_chapters):
            is_accessible = False
            if not audiobook_obj.is_paid or user_has_purchased:
                is_accessible = True
            elif can_preview_chapters and i < preview_limit:
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
                else:
                    for _, book_list in external_audiobook_data_cache.get(source_key, {}).items():
                        for book_dict in book_list:
                            if book_dict.get('slug') == audiobook_slug:
                                found_external_book = book_dict
                                break
                        if found_external_book: break
                if found_external_book: break

        if found_external_book:
            audiobook_data = found_external_book
            is_creator_book = False
            template_name = 'audiobook_detail.html'

            reviews_list = []
            user_review_object = None
            current_user_has_reviewed = False
            user_review_data_for_json["has_reviewed"] = False

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
                messages.error(request, "Audiobook found, but chapter data is missing.")
                logger.error(f"External audiobook with slug '{audiobook_slug}' found in cache but has no chapter data.")
                raise Http404("Audiobook chapters not available.")

        else:
            messages.error(request, "Audiobook not found or is not available.")
            logger.warning(f"Audiobook with slug '{audiobook_slug}' not found in DB or cache.")
            raise Http404("Audiobook not found or is not available.")

    context['audiobook'] = audiobook_data
    context['is_creator_book'] = is_creator_book
    context['reviews'] = reviews_list
    context['user_review_object'] = user_review_object
    context['current_user_has_reviewed'] = current_user_has_reviewed
    context['user_review_data_json'] = json.dumps(user_review_data_for_json)
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

@login_required
@require_POST
@csrf_protect
def add_review(request, audiobook_slug):
    """
    Handles adding or updating a review for a creator-uploaded audiobook.
    Expects a JSON payload with 'rating' and 'comment'.
    """
    try:
        audiobook = get_object_or_404(
            Audiobook,
            slug=audiobook_slug,
            status='PUBLISHED'
        )
        if not hasattr(audiobook, 'creator') or not audiobook.creator:
             return JsonResponse({'status': 'error', 'message': 'Reviews are only supported for creator-uploaded audiobooks.'}, status=400)

        can_review = False
        if not audiobook.is_paid:
            can_review = True
        elif request.user.is_authenticated and hasattr(request.user, 'has_purchased_audiobook'):
            if request.user.has_purchased_audiobook(audiobook):
                can_review = True

        if not can_review:
            return JsonResponse({
                'status': 'error',
                'message': 'You must purchase this audiobook or it must be free to leave a review.'
            }, status=403)

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

        new_average_rating = audiobook.average_rating
        message = "Review updated successfully!" if not created else "Review added successfully!"

        user_profile_pic_url = None
        if hasattr(review.user, 'profile_pic') and review.user.profile_pic:
            try:
                user_profile_pic_url = review.user.profile_pic.url
            except ValueError:
                pass

        review_data = {
            'review_id': review.review_id,
            'rating': review.rating,
            'comment': review.comment or "",
            'user_id': getattr(review.user, 'user_id', getattr(review.user, 'id', None)),
            'user_name': getattr(review.user, 'full_name', review.user.username) or review.user.username,
            'user_profile_pic': user_profile_pic_url,
            'created_at': review.created_at.isoformat(),
            'timesince': timesince(review.created_at) + " ago",
        }

        return JsonResponse({
            'status': 'success',
            'message': message,
            'created': created,
            'new_average_rating': str(new_average_rating) if new_average_rating is not None else "0.0",
            'review_data': review_data
        })

    except Audiobook.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found or not available for review.'}, status=404)
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'An unexpected server error occurred. Please try again.'}, status=500)

# --- Content Proxy Views ---

@csrf_exempt
@require_GET
def stream_audio(request):
    """Streams audio content from a given URL, handling local and external files."""
    audio_url_param = request.GET.get("url")
    if not audio_url_param:
        return JsonResponse({"error": "No audio URL provided"}, status=400)

    target_audio_url = audio_url_param
    parsed_url = urlparse(target_audio_url)

    is_local_media = target_audio_url.startswith(settings.MEDIA_URL) and not parsed_url.scheme and not parsed_url.netloc

    if is_local_media:
        try:
            if not target_audio_url.startswith(('http://', 'https://')):
                target_audio_url = request.build_absolute_uri(target_audio_url)
        except Exception:
            return HttpResponse("Error processing local audio URL", status=500)
    elif not all([parsed_url.scheme, parsed_url.netloc]):
        return HttpResponse(f"Invalid audio URL provided: {audio_url_param}", status=400)

    try:
        range_header = request.headers.get('Range', None)
        user_agent_host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "audiox.com"
        proxy_headers = {'User-Agent': f'AudioXApp Audio Proxy/1.0 (+http://{user_agent_host})'}

        if range_header:
            proxy_headers['Range'] = range_header

        audio_stream_timeout = 45
        response = requests.get(target_audio_url, stream=True, headers=proxy_headers, timeout=audio_stream_timeout)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', 'audio/mpeg')
        if not content_type.lower().startswith('audio/'):
            guessed_type, _ = mimetypes.guess_type(target_audio_url)
            if guessed_type and guessed_type.startswith('audio/'):
                content_type = guessed_type
            else:
                content_type = 'audio/mpeg'

        def generate_audio_chunks():
            try:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            finally:
                response.close()

        streaming_response = StreamingHttpResponse(generate_audio_chunks(), content_type=content_type)

        if 'Content-Range' in response.headers:
            streaming_response['Content-Range'] = response.headers['Content-Range']
        if 'Content-Length' in response.headers:
            streaming_response['Content-Length'] = response.headers['Content-Length']
        streaming_response['Accept-Ranges'] = 'bytes'
        streaming_response.status_code = response.status_code

        return streaming_response

    except requests.exceptions.Timeout:
        return HttpResponse("Audio stream timed out from external source", status=408)
    except requests.exceptions.HTTPError as e_http:
        return HttpResponse(f"Error fetching audio from external source: Status {e_http.response.status_code}", status=e_http.response.status_code)
    except requests.exceptions.RequestException:
        return HttpResponse("Error processing audio stream (could not connect to external source)", status=502)
    except SuspiciousOperation as e_susp:
        return JsonResponse({"error": str(e_susp)}, status=400)
    except Exception:
        return HttpResponse("Internal server error during audio streaming", status=500)


@csrf_exempt
@require_GET
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
        except Exception:
            return HttpResponse("Error processing local image URL", status=500)
    elif not all([parsed_url.scheme, parsed_url.netloc]):
        return HttpResponse("Invalid image URL provided", status=400)

    try:
        user_agent_host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "AudioXApp.com"
        proxy_headers = {'User-Agent': f'AudioXApp Image Proxy/1.0 (+http://{user_agent_host})'}

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

        streaming_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192), content_type=content_type
        )
        if 'Content-Length' in response.headers:
            streaming_response['Content-Length'] = response.headers['Content-Length']
        streaming_response.status_code = response.status_code
        return streaming_response

    except requests.exceptions.Timeout:
        return HttpResponse("Image fetch timed out", status=408)
    except requests.exceptions.HTTPError as e_http:
        return HttpResponse(f"Error fetching image: {e_http.response.status_code}", status=e_http.response.status_code)
    except requests.exceptions.RequestException:
        return HttpResponse("Failed to fetch image", status=502)
    except SuspiciousOperation as e_susp:
        return JsonResponse({"error": str(e_susp)}, status=400)
    except Exception:
        return HttpResponse("Internal server error", status=500)

def search_results_view(request):
    """
    Handles the search query and displays results from published audiobooks
    from both the local database (creator uploads) and cached external sources.
    Searches in audiobook title, author, and creator's name (for DB) or description/subjects (for cache).
    """
    query = request.GET.get('q', '').strip().lower() # Convert query to lowercase for case-insensitive search
    processed_results = []
    seen_slugs = set()

    common_context = _get_full_context(request)

    if query:
        # 1. Search Database (Creator Uploads)
        db_audiobooks = Audiobook.objects.filter(
            Q(title__icontains=query) |
            Q(author__icontains=query) |
            Q(creator__creator_name__icontains=query),
            status='PUBLISHED'
        ).select_related('creator').distinct().order_by('-publish_date')

        for book in db_audiobooks:
            if book.slug not in seen_slugs:
                processed_results.append({
                    'slug': book.slug,
                    'title': book.title,
                    'author': book.author,
                    'cover_image_url': book.cover_image.url if book.cover_image else None,
                    'creator_name': book.creator.creator_name if book.creator else None,
                    'average_rating': book.average_rating,
                    'total_views': book.total_views,
                    'is_creator_book': True, # Flag to identify DB books if needed in template
                    'source_type': 'database',
                    'price': book.price,
                    'is_paid': book.is_paid,
                    # Add any other fields your template might expect for DB books
                })
                seen_slugs.add(book.slug)

        # 2. Search Cached Data (LibriVox, Archive.org)
        cache_key = 'librivox_archive_audiobooks_data_v5' # Make sure this matches your cache key
        cached_data = cache.get(cache_key)

        if cached_data:
            # Search LibriVox cached data
            librivox_books = cached_data.get("librivox_audiobooks", [])
            for book_dict in librivox_books:
                book_slug = book_dict.get('slug')
                if book_slug and book_slug not in seen_slugs:
                    title_match = query in book_dict.get('title', '').lower()
                    desc_match = query in book_dict.get('description', '').lower()
                    # Librivox author might be in description or a generic "Various"
                    author_match = query in book_dict.get('author', '').lower() if book_dict.get('author') else False

                    if title_match or desc_match or author_match:
                        processed_results.append({
                            'slug': book_slug,
                            'title': book_dict.get('title'),
                            'author': book_dict.get('author', 'LibriVox'), # Provide a default if author isn't clear
                            'cover_image_url': book_dict.get('cover_image'), # Assuming this is already a URL
                            'creator_name': None,
                            'average_rating': None, # Cached items likely don't have this
                            'total_views': None,    # Cached items likely don't have this
                            'is_creator_book': False,
                            'source_type': 'librivox',
                            'price': Decimal("0.00"), # External books are free
                            'is_paid': False,
                            # Add any other fields your template might expect for cached books
                        })
                        seen_slugs.add(book_slug)

            # Search Archive.org (Genre and Language specific) cached data
            archive_sources = [
                cached_data.get("archive_genre_audiobooks", {}),
                cached_data.get("archive_language_audiobooks", {})
            ]
            for source_dict in archive_sources:
                for term_books in source_dict.values():
                    for book_dict in term_books:
                        book_slug = book_dict.get('slug')
                        if book_slug and book_slug not in seen_slugs:
                            title_match = query in book_dict.get('title', '').lower()
                            desc_match = query in book_dict.get('description', '').lower()
                            author_match = query in book_dict.get('author', '').lower()
                            subject_match = False
                            if isinstance(book_dict.get('subjects'), list):
                                subject_match = any(query in subject.lower() for subject in book_dict.get('subjects', []))

                            if title_match or desc_match or author_match or subject_match:
                                processed_results.append({
                                    'slug': book_slug,
                                    'title': book_dict.get('title'),
                                    'author': book_dict.get('author'),
                                    'cover_image_url': book_dict.get('cover_image'), # Assuming this is already a URL
                                    'creator_name': None,
                                    'average_rating': None,
                                    'total_views': None,
                                    'is_creator_book': False,
                                    'source_type': 'archive.org',
                                    'price': Decimal("0.00"), # External books are free
                                    'is_paid': False,
                                })
                                seen_slugs.add(book_slug)
        else:
            logger.warning("Search: External audiobook cache is empty or not available.")


    # Prepare the final context for the template
    context_data = {
        'query': request.GET.get('q', '').strip(), # Original query for display
        'results': processed_results,
        'page_title': f"Search Results for '{request.GET.get('q', '').strip()}'" if query else "Search Audiobooks",
    }
    context_data.update(common_context) # Add common context

    return render(request, 'audiobooks/English/english_search.html', context_data)

# --- Static Pages ---

def ourteam(request): return render(request, 'company/ourteam.html', _get_full_context(request))
def paymentpolicy(request): return render(request, 'legal/paymentpolicy.html', _get_full_context(request))
def privacypolicy(request): return render(request, 'legal/privacypolicy.html', _get_full_context(request))
def piracypolicy(request): return render(request, 'legal/piracypolicy.html', _get_full_context(request))
def termsandconditions(request): return render(request, 'legal/termsandconditions.html', _get_full_context(request))
def aboutus(request): return render(request, 'company/aboutus.html', _get_full_context(request))
def contactus(request): return render(request, 'company/contactus.html', _get_full_context(request))
