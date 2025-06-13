# AudioXApp/views/content_views.py

import random
import requests
import feedparser
import mimetypes
import json
import os
from urllib.parse import urlparse, quote, parse_qs, urlencode
from django.db.models import Q
from decimal import Decimal, InvalidOperation
import datetime
import time
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse, Http404, FileResponse
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
from django.core.files.base import ContentFile
from django.middleware.csrf import get_token
import logging
from ..models import Audiobook, Chapter, Review, User, AudiobookPurchase, CreatorEarning, Creator, AudiobookViewLog
from .utils import _get_full_context

logger = logging.getLogger(__name__)

# --- Helper Functions ---

def parse_duration_to_seconds(duration_str):
    if duration_str is None:
        return None
    if isinstance(duration_str, (int, float)):
        return int(duration_str)
    if not isinstance(duration_str, str):
        return None
    duration_str = duration_str.strip()
    parts = duration_str.split(':')
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(float(parts[1]))
        elif len(parts) == 1:
            return int(float(duration_str))
    except ValueError:
        pass
    try:
        return int(float(duration_str))
    except ValueError:
        return None

# --- Data Fetching and Caching ---

def fetch_audiobooks_data():
    cache_key = 'librivox_archive_audiobooks_data_v7'
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.info(f"CACHE HIT: Using cached data for audiobooks (key: {cache_key}).")
        return cached_data

    logger.info(f"CACHE MISS: Fetching fresh data for audiobooks (key: {cache_key})...")
    librivox_audiobooks = []
    archive_genre_audiobooks = {}
    archive_language_audiobooks = {}
    fetch_successful = False
    rss_feeds = ["https://librivox.org/rss/47", "https://librivox.org/rss/52", "https://librivox.org/rss/53", "https://librivox.org/rss/54", "https://librivox.org/rss/59", "https://librivox.org/rss/60", "https://librivox.org/rss/61", "https://librivox.org/rss/62"]
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

            chapters_data_for_book = []
            for entry in feed.entries:
                audio_url = None
                if entry.enclosures:
                    for enc in entry.enclosures:
                        if 'audio' in enc.get('type', '').lower():
                            audio_url = enc.href
                            break
                if not audio_url and entry.links:
                    for link_entry in entry.links:
                        if 'audio' in link_entry.get('type', '').lower() or any(link_entry.href.lower().endswith(ext) for ext in ['.mp3', '.ogg', '.m4a', '.wav']):
                            audio_url = link_entry.href
                            break
                if not audio_url:
                    continue

                chapter_title = entry.title.replace('"', '').strip() if entry.title else 'Untitled Chapter'
                chapter_duration_seconds = None
                if hasattr(entry, 'itunes_duration'):
                    chapter_duration_seconds = parse_duration_to_seconds(entry.itunes_duration)
                chapters_data_for_book.append({"chapter_title": chapter_title, "audio_url": audio_url, "duration_seconds": chapter_duration_seconds})

            if not chapters_data_for_book:
                logger.info(f"No chapters with audio found for audiobook in {rss_url}")
                continue

            title = feed.feed.get('title', 'Unknown Title').replace('LibriVox', '').strip()
            description = feed.feed.get('summary', feed.feed.get('itunes_summary', 'No description available.'))
            author = feed.feed.get('author', feed.feed.get('itunes_author', 'Various Authors'))
            cover_image_original_url = None
            if hasattr(feed.feed, 'image') and hasattr(feed.feed.image, 'href'):
                cover_image_original_url = feed.feed.image.href

            slug = slugify(title) if title and title != 'Unknown Title' else f'librivox-book-{random.randint(1000,9999)}'
            cover_image_for_dict = cover_image_original_url
            first_chapter_original_audio_url = chapters_data_for_book[0]["audio_url"] if chapters_data_for_book else None
            first_chapter_title = chapters_data_for_book[0]["chapter_title"] if chapters_data_for_book else None
            librivox_audiobooks.append({"source": "librivox", "title": title, "description": description, "author": author, "cover_image": cover_image_for_dict, "chapters": chapters_data_for_book, "first_chapter_audio_url": first_chapter_original_audio_url, "first_chapter_title": first_chapter_title, "slug": slug, "is_creator_book": False, "total_views": 0, "average_rating": None, "is_paid": False, "price": Decimal("0.00"), "language": feed.feed.get('language', 'en')})
            fetch_successful = True
        except requests.exceptions.Timeout as e:
            logger.error(f"TIMEOUT error fetching RSS feed {rss_url}: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"RequestException error fetching RSS feed {rss_url}: {e}")
        except Exception as e:
            logger.error(f"Generic error processing RSS feed {rss_url}: {e}", exc_info=True)

    base_url = "https://archive.org/advancedsearch.php"
    search_terms = ["Fiction", "Mystery", "Thriller", "Science Fiction", "Fantasy", "Romance", "Biography", "History", "Self-Help", "Business", "Urdu", "Punjabi", "Sindhi"]
    language_specific_terms = ["Urdu", "Punjabi", "Sindhi"]
    archive_timeout = 30
    term_index_api_search = 0

    for term in search_terms:
        if term_index_api_search > 0: time.sleep(1)
        term_index_api_search += 1
        query_string = ""
        if term in language_specific_terms:
            query_string = f'language:"{term}" AND collection:librivoxaudio AND mediatype:audio'
        else:
            query_string = f'subject:"{term}" AND collection:librivoxaudio AND mediatype:audio'
        params = {"q": query_string, "fl[]": ["identifier", "title", "creator", "description", "subject", "language"], "rows": 10, "output": "json"}
        try:
            response = session.get(base_url, params=params, timeout=archive_timeout, headers=headers)
            response.raise_for_status()
            data = response.json()
            docs = data.get('response', {}).get('docs', [])
            logger.info(f"For term '{term}' (API Search), Archive.org API returned {len(docs)} documents. numFound: {data.get('response', {}).get('numFound', 'N/A')}")
            audiobooks_for_term = []
            for doc_api_data in docs:
                identifier = doc_api_data.get('identifier')
                doc_title = doc_api_data.get('title', 'Unknown Title')
                creator_data = doc_api_data.get('creator', 'Unknown Author')
                author_from_doc = ', '.join(creator_data) if isinstance(creator_data, list) else creator_data
                description_data = doc_api_data.get('description', 'No description available.')
                description_from_doc = ' '.join(description_data) if isinstance(description_data, list) else description_data
                subjects = doc_api_data.get('subject', [])
                language_from_doc = doc_api_data.get('language', 'English')
                if isinstance(language_from_doc, list): language_from_doc = language_from_doc[0] if language_from_doc else 'English'
                if not identifier:
                    logger.warning(f"API Doc for term '{term}' (Title: '{doc_title}') has no identifier. Skipping.")
                    continue
                meta_url = f"https://archive.org/metadata/{identifier}"
                meta_resp = session.get(meta_url, timeout=archive_timeout, headers=headers)
                meta_resp.raise_for_status()
                item_full_metadata_api = meta_resp.json()
                files_metadata_api = item_full_metadata_api.get("files", [])
                chapters_from_api = []
                for f_item in files_metadata_api:
                    if f_item.get("format") in ["VBR MP3", "MP3", "64Kbps MP3", "128Kbps MP3"] and "name" in f_item:
                        chapter_title_raw = f_item.get("title", f_item.get("name", 'Untitled Chapter'))
                        chapter_title = str(chapter_title_raw).replace('"', '').strip()
                        chapter_duration_seconds = None
                        raw_length = f_item.get('length') or f_item.get('duration')
                        if raw_length:
                            chapter_duration_seconds = parse_duration_to_seconds(raw_length)
                        chapters_from_api.append({"chapter_title": chapter_title, "audio_url": f"https://archive.org/download/{identifier}/{quote(f_item['name'])}", "duration_seconds": chapter_duration_seconds})
                if not chapters_from_api:
                    logger.warning(f"No chapters extracted for API doc ID: {identifier} (Title: '{doc_title}', term: '{term}'). Skipping.")
                    continue
                slug = slugify(doc_title) if doc_title and doc_title != 'Unknown Title' else f'archive-api-{term.lower().replace(" ", "-")}-{random.randint(1000,9999)}'
                book_data = {"source": "archive", "title": doc_title, "description": description_from_doc, "author": author_from_doc, "cover_image": f"https://archive.org/services/img/{identifier}", "chapters": chapters_from_api, "first_chapter_audio_url": chapters_from_api[0]["audio_url"] if chapters_from_api else None, "first_chapter_title": chapters_from_api[0]["chapter_title"] if chapters_from_api else None, "slug": slug, "is_creator_book": False, "total_views": 0, "average_rating": None, "is_paid": False, "price": Decimal("0.00"), "subjects": subjects, "language": language_from_doc, "genre": term if term not in language_specific_terms else None}
                audiobooks_for_term.append(book_data)
            if audiobooks_for_term:
                if term in language_specific_terms:
                    if term not in archive_language_audiobooks: archive_language_audiobooks[term] = []
                    archive_language_audiobooks[term].extend(audiobooks_for_term)
                else:
                    archive_genre_audiobooks[term] = audiobooks_for_term
                fetch_successful = True
        except requests.exceptions.HTTPError as e_http:
            logger.error(f"HTTPError for API term '{term}' (URL: {e_http.request.url if e_http.request else 'N/A'}): {e_http.response.status_code} - {e_http.response.text if e_http.response else 'No response body'}", exc_info=False)
        except Exception as e:
            logger.error(f"Error processing API term '{term}': {e}", exc_info=True)

    manual_language_items = {"Urdu": ["Ashra-Mubashra-Darussalam-Urdu-Audio-MP3-CD", "Tafsir-ibne-kaseer-kathir-urdu-----audio-mp3-hq", "iman-syed-suleiman-nadvi", "Seerat-e-Khulfa-e-Rashideen----Audio-MP3"], "Punjabi": [], "Sindhi": []}
    processed_manual_ids_this_run = set()
    for lang_key, item_ids_list in manual_language_items.items():
        if not item_ids_list: continue
        if lang_key not in archive_language_audiobooks: archive_language_audiobooks[lang_key] = []
        current_slugs_for_lang = {b.get('slug') for b in archive_language_audiobooks[lang_key]}
        for item_identifier in item_ids_list:
            if item_identifier in processed_manual_ids_this_run: continue
            try:
                time.sleep(0.5)
                meta_url = f"https://archive.org/metadata/{item_identifier}"
                meta_resp = session.get(meta_url, timeout=archive_timeout, headers=headers)
                meta_resp.raise_for_status()
                item_full_metadata = meta_resp.json()
                item_doc_data = item_full_metadata.get('metadata')
                doc_title_manual = (item_doc_data or item_full_metadata).get('title', f"Unknown Title - {item_identifier}")
                creator_data_manual = (item_doc_data or item_full_metadata).get('creator', 'Unknown Author')
                description_from_doc_manual = (item_doc_data or item_full_metadata).get('description', 'No description available.')
                language_from_doc_manual = (item_doc_data or item_full_metadata).get('language', lang_key)
                subjects_manual = (item_doc_data or item_full_metadata).get('subject', [])
                if doc_title_manual.startswith("Unknown Title -"): logger.warning(f"Could not determine title for manual item {item_identifier}. Skipping."); continue
                author_from_doc_manual = ', '.join(creator_data_manual) if isinstance(creator_data_manual, list) else creator_data_manual
                if isinstance(description_from_doc_manual, list): description_from_doc_manual = ' '.join(description_from_doc_manual)
                if isinstance(language_from_doc_manual, list): language_from_doc_manual = language_from_doc_manual[0] if language_from_doc_manual else lang_key
                files_metadata_manual = item_full_metadata.get("files", [])
                chapters_for_manual_item = []
                for f_item_manual in files_metadata_manual:
                    if f_item_manual.get("format") in ["VBR MP3", "MP3", "64Kbps MP3", "128Kbps MP3"] and "name" in f_item_manual:
                        chapter_title_raw_manual = f_item_manual.get("title", f_item_manual.get("name", 'Untitled Chapter'))
                        chapter_title_manual = str(chapter_title_raw_manual).replace('"', '').strip()
                        manual_chapter_duration_seconds = None
                        raw_length_manual = f_item_manual.get('length') or f_item_manual.get('duration')
                        if raw_length_manual:
                            manual_chapter_duration_seconds = parse_duration_to_seconds(raw_length_manual)
                        chapters_for_manual_item.append({"chapter_title": chapter_title_manual, "audio_url": f"https://archive.org/download/{item_identifier}/{quote(f_item_manual['name'])}", "duration_seconds": manual_chapter_duration_seconds})
                if not chapters_for_manual_item:
                    logger.warning(f"No chapters extracted for manual item ID: {item_identifier} (Title: '{doc_title_manual}', language: {lang_key}). Skipping.")
                    continue
                slug_manual = slugify(doc_title_manual) if doc_title_manual and not doc_title_manual.startswith("Unknown Title") else f'archive-manual-{lang_key.lower()}-{item_identifier.replace("_", "-")}'
                book_data_manual = {"source": "archive", "title": doc_title_manual, "description": description_from_doc_manual, "author": author_from_doc_manual, "cover_image": f"https://archive.org/services/img/{item_identifier}", "chapters": chapters_for_manual_item, "first_chapter_audio_url": chapters_for_manual_item[0]["audio_url"] if chapters_for_manual_item else None, "first_chapter_title": chapters_for_manual_item[0]["chapter_title"] if chapters_for_manual_item else None, "slug": slug_manual, "is_creator_book": False, "total_views": 0, "average_rating": None, "is_paid": False, "price": Decimal("0.00"), "subjects": subjects_manual, "language": language_from_doc_manual, "genre": None}
                if slug_manual not in current_slugs_for_lang:
                    archive_language_audiobooks[lang_key].append(book_data_manual)
                    current_slugs_for_lang.add(slug_manual)
                    fetch_successful = True
                else:
                    logger.info(f"Manual book with slug '{slug_manual}' (ID: {item_identifier}) already exists for language '{lang_key}'. Skipping.")
                processed_manual_ids_this_run.add(item_identifier)
            except requests.exceptions.HTTPError as e_http:
                logger.error(f"HTTPError for manual item ID '{item_identifier}' (URL: {e_http.request.url if e_http.request else 'N/A'}): {e_http.response.status_code}", exc_info=False)
            except Exception as e:
                logger.error(f"Error processing manually specified item ID '{item_identifier}' for language '{lang_key}': {e}", exc_info=True)

    combined_data = {"librivox_audiobooks": librivox_audiobooks, "archive_genre_audiobooks": archive_genre_audiobooks, "archive_language_audiobooks": archive_language_audiobooks}
    if fetch_successful:
        new_cache_duration = 6 * 60 * 60
        logger.info(f"CACHE SET: Storing fetched data in cache (key: {cache_key}, duration: {new_cache_duration}s).")
        final_lang_count = sum(len(v) for v in archive_language_audiobooks.values())
        logger.info(f"Final counts: LibriVox: {len(librivox_audiobooks)}, Archive Genres: {sum(len(v) for v in archive_genre_audiobooks.values())}, Archive Languages: {final_lang_count}")
        cache.set(cache_key, combined_data, new_cache_duration)
        return combined_data
    else:
        logger.warning(f"FETCH UNSUCCESSFUL: No new data to cache. Returning potentially partial or None.")
        final_lang_count_fail = sum(len(v) for v in archive_language_audiobooks.values())
        if librivox_audiobooks or archive_genre_audiobooks or archive_language_audiobooks:
            logger.info(f"Final counts (partial/failed fetch): LibriVox: {len(librivox_audiobooks)}, Archive Genres: {sum(len(v) for v in archive_genre_audiobooks.values())}, Archive Languages: {final_lang_count_fail}")
            return combined_data
        else:
            return None

# --- Core Content Views ---

def home(request):
    context = _get_full_context(request)
    cache_key = 'librivox_archive_audiobooks_data_v7'
    audiobook_data_from_cache = cache.get(cache_key)
    librivox_audiobooks_final = []
    archive_genre_audiobooks_final = {}
    cached_archive_genres = None
    context["error_message"] = None
    all_external_book_slugs = set()
    if audiobook_data_from_cache:
        for book_dict in audiobook_data_from_cache.get("librivox_audiobooks", []):
            if book_dict.get('slug'):
                all_external_book_slugs.add(book_dict.get('slug'))
        for genre, book_list in audiobook_data_from_cache.get("archive_genre_audiobooks", {}).items():
            for book_dict in book_list:
                if book_dict.get('slug'):
                    all_external_book_slugs.add(book_dict.get('slug'))
        for lang_key, book_list_lang in audiobook_data_from_cache.get("archive_language_audiobooks", {}).items():
            for book_dict_lang in book_list_lang:
                if book_dict_lang.get('slug'):
                    all_external_book_slugs.add(book_dict_lang.get('slug'))

    db_book_stats = {}
    if all_external_book_slugs:
        db_instances = Audiobook.objects.filter(slug__in=list(all_external_book_slugs), is_creator_book=False)
        for db_book in db_instances:
            db_book_stats[db_book.slug] = {'total_views': db_book.total_views, 'average_rating': db_book.average_rating, 'author': db_book.author, 'title': db_book.title, 'cover_image': db_book.cover_image.url if db_book.cover_image else None}

    if audiobook_data_from_cache:
        cached_librivox_books = audiobook_data_from_cache.get("librivox_audiobooks", [])
        for book_data in cached_librivox_books:
            slug = book_data.get('slug')
            if slug and slug in db_book_stats:
                book_data['total_views'] = db_book_stats[slug]['total_views']
                book_data['average_rating'] = db_book_stats[slug]['average_rating']
                book_data['author'] = db_book_stats[slug].get('author', book_data.get('author'))
                book_data['title'] = db_book_stats[slug].get('title', book_data.get('title'))
                if db_book_stats[slug].get('cover_image'): 
                    book_data['cover_image'] = db_book_stats[slug]['cover_image']
            else: 
                book_data.setdefault('total_views', 0)
                book_data.setdefault('average_rating', None)
            librivox_audiobooks_final.append(book_data)
        cached_archive_genres = audiobook_data_from_cache.get("archive_genre_audiobooks", {})
        if not cached_archive_genres:
            logger.warning("'archive_genre_audiobooks' is empty or not found in cache.")
        for genre, book_list in cached_archive_genres.items():
            english_books_for_genre = []
            for i, book_data in enumerate(book_list): 
                lang = book_data.get('language', 'English') 
                is_english = False
                if isinstance(lang, list): 
                    is_english = any(str(l).lower().strip() in ['english', 'en', 'eng'] for l in lang)
                elif isinstance(lang, str): 
                    is_english = lang.lower().strip() in ['english', 'en', 'eng']
                if is_english:
                    slug = book_data.get('slug')
                    if slug and slug in db_book_stats:
                        book_data['total_views'] = db_book_stats[slug]['total_views']
                        book_data['average_rating'] = db_book_stats[slug]['average_rating']
                        book_data['author'] = db_book_stats[slug].get('author', book_data.get('author'))
                        book_data['title'] = db_book_stats[slug].get('title', book_data.get('title'))
                        if db_book_stats[slug].get('cover_image'):
                            book_data['cover_image'] = db_book_stats[slug]['cover_image']
                    else: 
                        book_data.setdefault('total_views', 0)
                        book_data.setdefault('average_rating', None)
                    english_books_for_genre.append(book_data)
            if english_books_for_genre:
                archive_genre_audiobooks_final[genre] = english_books_for_genre
            elif book_list: 
                logger.warning(f"Genre '{genre}' had {len(book_list)} books from cache, but none were identified as English after filtering.")
    else:
        context["error_message"] = "External audiobook listings are currently being updated or the cache is empty. Please check back shortly."
        logger.warning("Audiobook data cache was empty or not found.")

    context["librivox_audiobooks"] = librivox_audiobooks_final
    context["archive_genre_audiobooks"] = archive_genre_audiobooks_final
    if not archive_genre_audiobooks_final and cached_archive_genres:
        logger.warning("'archive_genre_audiobooks_final' is empty, but 'cached_archive_genres' was not. This suggests the English filter removed all items.")

    creator_books_list = []
    try:
        first_chapter_prefetch = Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order'), to_attr='first_chapter_list')
        creator_books_qs = Audiobook.objects.filter(status='PUBLISHED', is_creator_book=True, language__iexact='English').select_related('creator').prefetch_related(first_chapter_prefetch, Prefetch('reviews', queryset=Review.objects.select_related('user').order_by('-created_at'))).order_by('-publish_date')[:12] 
        for book in creator_books_qs:
            first_chapter_audio_url = None
            first_chapter_title = None
            if hasattr(book, 'first_chapter_list') and book.first_chapter_list:
                first_chapter = book.first_chapter_list[0]
                first_chapter_title = first_chapter.chapter_name
                if first_chapter.audio_file and hasattr(first_chapter.audio_file, 'url'):
                    first_chapter_audio_url = first_chapter.audio_file.url
            creator_books_list.append({'source': 'creator', 'title': book.title, 'slug': book.slug, 'cover_image': book.cover_image.url if book.cover_image else None, 'author': book.author, 'creator': book.creator, 'first_chapter_audio_url': first_chapter_audio_url, 'first_chapter_title': first_chapter_title, 'is_creator_book': True, 'average_rating': book.average_rating, 'total_views': book.total_views, 'is_paid': book.is_paid, 'price': book.price, 'status': book.status, 'language': book.language, 'genre': book.genre})
        context["creator_audiobooks"] = creator_books_list
        if not creator_books_list and not librivox_audiobooks_final and not archive_genre_audiobooks_final and not context["error_message"]:
            context["error_message"] = "No English audiobooks are currently available from any source."
    except Exception as db_err:
        logger.error(f"Error fetching creator audiobooks for English homepage: {db_err}", exc_info=True)
        if not context.get("librivox_audiobooks") and not context.get("archive_genre_audiobooks") and not creator_books_list:
            if not context.get("error_message"): 
                context["error_message"] = "Failed to load any audiobooks at this time. Please try again later."
    if audiobook_data_from_cache is None and not context.get("error_message"):
        logger.warning("Home page loaded but external audiobook cache was None. This might be during cache repopulation.")
    return render(request, "audiobooks/English/English_Home.html", context)

def search_results_view(request):
    query = request.GET.get('q', '').strip().lower()
    processed_results = []
    seen_slugs = set()
    common_context = _get_full_context(request)
    if query:
        db_audiobooks = Audiobook.objects.filter(Q(title__icontains=query) | Q(author__icontains=query) | Q(creator__creator_name__icontains=query) | Q(genre__icontains=query) | Q(description__icontains=query), status='PUBLISHED', is_creator_book=True).select_related('creator').distinct().order_by('-publish_date')
        for book in db_audiobooks:
            if book.slug not in seen_slugs:
                processed_results.append({'slug': book.slug, 'title': book.title, 'author': book.author, 'cover_image_url': book.cover_image.url if book.cover_image else None, 'creator_name': book.creator.creator_name if book.creator else None, 'average_rating': book.average_rating, 'total_views': book.total_views, 'is_creator_book': True, 'source_type': 'creator', 'price': book.price, 'is_paid': book.is_paid, 'genre': book.genre, 'language': book.language})
                seen_slugs.add(book.slug)
        cache_key = 'librivox_archive_audiobooks_data_v7'
        cached_data = cache.get(cache_key)
        if cached_data:
            external_sources_to_search = [("librivox_audiobooks", "librivox"), ("archive_genre_audiobooks", "archive.org"), ("archive_language_audiobooks", "archive.org")]
            for source_list_key, source_type_val in external_sources_to_search:
                if source_list_key == "librivox_audiobooks":
                    item_list = cached_data.get(source_list_key, [])
                    for book_dict in item_list:
                        book_slug = book_dict.get('slug')
                        if book_slug and book_slug not in seen_slugs:
                            title_match = query in book_dict.get('title', '').lower()
                            desc_match = query in book_dict.get('description', '').lower()
                            author_match = query in book_dict.get('author', '').lower() if book_dict.get('author') else False
                            genre_match = query in book_dict.get('genre', '').lower() if book_dict.get('genre') else False
                            lang_match = query in book_dict.get('language', '').lower() if book_dict.get('language') else False
                            if title_match or desc_match or author_match or genre_match or lang_match:
                                processed_results.append({'slug': book_slug, 'title': book_dict.get('title'), 'author': book_dict.get('author', 'LibriVox'), 'cover_image_url': book_dict.get('cover_image'), 'creator_name': None, 'average_rating': None, 'total_views': None, 'is_creator_book': False, 'source_type': source_type_val, 'price': Decimal("0.00"), 'is_paid': False, 'genre': book_dict.get('genre'), 'language': book_dict.get('language')})
                                seen_slugs.add(book_slug)
                else:
                    for term_key, term_books_list in cached_data.get(source_list_key, {}).items():
                        for book_dict in term_books_list:
                            book_slug = book_dict.get('slug')
                            if book_slug and book_slug not in seen_slugs:
                                title_match = query in book_dict.get('title', '').lower()
                                desc_match = query in book_dict.get('description', '').lower()
                                author_match = query in book_dict.get('author', '').lower()
                                subject_match = any(query in subject.lower() for subject in book_dict.get('subjects', []))
                                genre_match = query in book_dict.get('genre', '').lower() if book_dict.get('genre') else False
                                lang_match = query in book_dict.get('language', '').lower() if book_dict.get('language') else False
                                if title_match or desc_match or author_match or subject_match or genre_match or lang_match:
                                    processed_results.append({'slug': book_slug, 'title': book_dict.get('title'), 'author': book_dict.get('author'), 'cover_image_url': book_dict.get('cover_image'), 'creator_name': None, 'average_rating': None, 'total_views': None, 'is_creator_book': False, 'source_type': source_type_val, 'price': Decimal("0.00"), 'is_paid': False, 'genre': book_dict.get('genre'), 'language': book_dict.get('language')})
                                    seen_slugs.add(book_slug)
        else:
            logger.warning("Search: External audiobook cache is empty or not available.")
            messages.info(request, "External audiobook listings are currently being updated. Search results may be limited.")
    context_data = {'query': request.GET.get('q', '').strip(), 'results': processed_results, 'page_title': f"Search Results for '{request.GET.get('q', '').strip()}'" if query else "Search Audiobooks"}
    context_data.update(common_context)
    return render(request, 'audiobooks/English/english_search.html', context_data)

def audiobook_detail(request, audiobook_slug):
    audiobook_obj = None
    found_external_book_dict = None
    is_creator_book_page_flag = False
    context = _get_full_context(request)
    template_name = 'audiobook_detail.html'
    reviews_list = []
    user_review_object = None
    current_user_has_reviewed = False
    user_has_purchased = False
    audiobook_lock_message = None 
    chapters_to_display = []
    try:
        audiobook_obj = Audiobook.objects.prefetch_related(Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order')), 'reviews__user').select_related('creator').get(slug=audiobook_slug)
        is_creator_book_page_flag = audiobook_obj.is_creator_book
        if not is_creator_book_page_flag: 
            cache_key = 'librivox_archive_audiobooks_data_v7'
            external_audiobook_data_cache = cache.get(cache_key)
            if external_audiobook_data_cache:
                for book_dict_item in external_audiobook_data_cache.get("librivox_audiobooks", []):
                    if book_dict_item.get('slug') == audiobook_slug:
                        found_external_book_dict = book_dict_item
                        break
                if not found_external_book_dict:
                    for source_key in ["archive_genre_audiobooks", "archive_language_audiobooks"]:
                        for _, book_list_items in external_audiobook_data_cache.get(source_key, {}).items():
                            for book_dict_item in book_list_items:
                                if book_dict_item.get('slug') == audiobook_slug:
                                    found_external_book_dict = book_dict_item
                                    break
                            if found_external_book_dict: break
                        if found_external_book_dict: break
            if not found_external_book_dict:
                logger.warning(f"External book (slug: {audiobook_slug}) placeholder found in DB, but its full chapter data not in current cache.")
    except Audiobook.DoesNotExist:
        logger.info(f"Audiobook with slug '{audiobook_slug}' not in DB. Checking cache for external book.")
        cache_key = 'librivox_archive_audiobooks_data_v7'
        external_audiobook_data_cache = cache.get(cache_key)
        if external_audiobook_data_cache:
            for book_dict_item in external_audiobook_data_cache.get("librivox_audiobooks", []):
                if book_dict_item.get('slug') == audiobook_slug: found_external_book_dict = book_dict_item; break
            if not found_external_book_dict:
                for source_key in ["archive_genre_audiobooks", "archive_language_audiobooks"]:
                    for _, book_list_items in external_audiobook_data_cache.get(source_key, {}).items():
                        for book_dict_item in book_list_items:
                            if book_dict_item.get('slug') == audiobook_slug: found_external_book_dict = book_dict_item; break
                        if found_external_book_dict: break
                    if found_external_book_dict: break
        if found_external_book_dict:
            is_creator_book_page_flag = False
            audiobook_obj, created = Audiobook.objects.get_or_create(slug=audiobook_slug, defaults={'title': found_external_book_dict.get('title', 'Unknown Title'), 'author': found_external_book_dict.get('author'), 'description': found_external_book_dict.get('description',"No description provided."), 'language': found_external_book_dict.get('language'), 'genre': found_external_book_dict.get('genre'), 'source': found_external_book_dict.get('source', 'archive'), 'is_creator_book': False, 'creator': None, 'is_paid': False, 'price': Decimal('0.00'), 'status': 'PUBLISHED'})
            if created:
                logger.info(f"Created new Audiobook DB entry shell for external book: {audiobook_slug}.")
        else:
            messages.error(request, "Audiobook not found.")
            raise Http404("Audiobook not found.")

    context_audiobook_data_for_display = {}
    if is_creator_book_page_flag and audiobook_obj:
        context_audiobook_data_for_display = audiobook_obj 
    elif found_external_book_dict and audiobook_obj:
        context_audiobook_data_for_display = found_external_book_dict.copy()
        context_audiobook_data_for_display['title'] = audiobook_obj.title 
        context_audiobook_data_for_display['author'] = audiobook_obj.author
        context_audiobook_data_for_display['description'] = audiobook_obj.description
        if audiobook_obj.cover_image and hasattr(audiobook_obj.cover_image, 'url'):
            try:
                context_audiobook_data_for_display['cover_image'] = audiobook_obj.cover_image.url
            except ValueError:
                context_audiobook_data_for_display['cover_image'] = found_external_book_dict.get('cover_image')
        else:
            context_audiobook_data_for_display['cover_image'] = found_external_book_dict.get('cover_image')
        context_audiobook_data_for_display['source'] = audiobook_obj.source
        context_audiobook_data_for_display['total_views'] = audiobook_obj.total_views
        context_audiobook_data_for_display['average_rating'] = audiobook_obj.average_rating 
    elif audiobook_obj: 
        context_audiobook_data_for_display = audiobook_obj 
        is_creator_book_page_flag = audiobook_obj.is_creator_book
        logger.warning(f"Audiobook {audiobook_slug} from DB (is_creator_book={is_creator_book_page_flag}), but not found in external cache. Chapters might be missing if external.")
    else:
        raise Http404("Audiobook data could not be prepared.")

    if audiobook_obj:
        current_user_for_log = request.user if request.user.is_authenticated else None
        AudiobookViewLog.objects.create(audiobook=audiobook_obj, user=current_user_for_log)
        Audiobook.objects.filter(pk=audiobook_obj.pk).update(total_views=F('total_views') + 1)
        audiobook_obj.refresh_from_db(fields=['total_views'])
        if isinstance(context_audiobook_data_for_display, dict):
            context_audiobook_data_for_display['total_views'] = audiobook_obj.total_views
            context_audiobook_data_for_display['average_rating'] = audiobook_obj.average_rating 
        reviews_list = audiobook_obj.reviews.select_related('user').order_by('-created_at')
        if request.user.is_authenticated:
            user_review_object = reviews_list.filter(user=request.user).first()
            if user_review_object:
                current_user_has_reviewed = True

    if audiobook_obj and is_creator_book_page_flag:
        all_db_chapters = audiobook_obj.chapters.all()
        if audiobook_obj.is_paid and request.user.is_authenticated and hasattr(request.user, 'has_purchased_audiobook'):
            user_has_purchased = request.user.has_purchased_audiobook(audiobook_obj)
        preview_limit_count = 1 if all_db_chapters.exists() else 0 
        for i, chapter_db_obj in enumerate(all_db_chapters):
            is_accessible = True
            if audiobook_obj.is_paid and not user_has_purchased:
                is_accessible = chapter_db_obj.is_preview_eligible or (i < preview_limit_count and not any(c.is_preview_eligible for c in all_db_chapters))
            chapters_to_display.append({'chapter_title': chapter_db_obj.chapter_name, 'audio_url_template': chapter_db_obj.get_streaming_url(), 'is_accessible': is_accessible, 'duration_seconds': chapter_db_obj.duration_seconds, 'chapter_index': i, 'chapter_id': str(chapter_db_obj.chapter_id)})
    elif found_external_book_dict:
        external_chapters_raw = found_external_book_dict.get('chapters', [])
        for i, ch_info in enumerate(external_chapters_raw):
            external_audio_url = ch_info.get('audio_url')
            streaming_url_template = None
            if external_audio_url:
                streaming_url_template = reverse('AudioXApp:stream_audio') + f'?url={quote(external_audio_url)}'
            chapters_to_display.append({'chapter_title': ch_info.get('chapter_title'), 'audio_url_template': streaming_url_template, 'is_accessible': True, 'duration_seconds': ch_info.get('duration_seconds'), 'chapter_index': i, 'chapter_id': f"ext-{audiobook_obj.slug}-{i}" if audiobook_obj else f"ext-unknown-{i}"})

    page_context_for_js = {"isAuthenticated": request.user.is_authenticated, "csrfToken": get_token(request), "audiobookId": str(audiobook_obj.audiobook_id) if audiobook_obj and audiobook_obj.audiobook_id else None, "audiobookSlug": audiobook_obj.slug if audiobook_obj else None, "audiobookTitle": audiobook_obj.title if audiobook_obj else (found_external_book_dict.get('title', "Audiobook") if found_external_book_dict else "Audiobook"), "addReviewUrl": reverse('AudioXApp:add_review', kwargs={'audiobook_slug': audiobook_obj.slug}) if audiobook_obj else "#error-no-slug-for-review", "addToLibraryApiUrl": reverse('AudioXApp:toggle_library_item'), "myLibraryUrl": reverse('AudioXApp:my_library_page'), "loginUrl": f"{reverse('AudioXApp:login')}?next={urlencode({'next': request.path})}", "getAiSummaryUrl": reverse('AudioXApp:get_ai_summary', kwargs={'audiobook_id': audiobook_obj.audiobook_id}) if audiobook_obj and audiobook_obj.audiobook_id else reverse('AudioXApp:get_ai_summary', kwargs={'audiobook_id': 0}), "updateListeningProgressUrl": reverse('AudioXApp:update_listening_progress'), "postChapterCommentUrlBase": "URL_STILL_NEEDS_DEFINITION_post_chapter_comment", "getChapterCommentsUrlBase": "URL_STILL_NEEDS_DEFINITION_get_chapter_comments", "audiobookAuthor": audiobook_obj.author if audiobook_obj else (found_external_book_dict.get('author') if found_external_book_dict else "Unknown Author"), "audiobookLanguage": audiobook_obj.language if audiobook_obj else (found_external_book_dict.get('language') if found_external_book_dict else "N/A"), "audiobookGenre": audiobook_obj.genre if audiobook_obj else (found_external_book_dict.get('genre') if found_external_book_dict else "N/A"), "isCreatorBook": is_creator_book_page_flag, "generateAudioClipUrl": reverse('AudioXApp:generate_audio_clip'), "stripePublishableKey": settings.STRIPE_PUBLISHABLE_KEY if hasattr(settings, 'STRIPE_PUBLISHABLE_KEY') else None, "createCheckoutSessionUrl": reverse('AudioXApp:create_checkout_session') if is_creator_book_page_flag and audiobook_obj and audiobook_obj.is_paid else None, "audiobookPrice": str(audiobook_obj.price) if audiobook_obj and audiobook_obj.is_paid else "0.00"}
    if request.user.is_authenticated:
        page_context_for_js["userId"] = str(request.user.user_id) 
        page_context_for_js["userFullName"] = request.user.full_name or request.user.username
        page_context_for_js["userProfilePicUrl"] = request.user.profile_pic.url if hasattr(request.user, 'profile_pic') and request.user.profile_pic else None
    else:
        page_context_for_js["userId"] = None
        page_context_for_js["userFullName"] = None
        page_context_for_js["userProfilePicUrl"] = None

    recommended_audiobooks_list = []
    seen_recommended_slugs = set()
    current_book_slug_for_exclusion = None
    if audiobook_obj and audiobook_obj.slug:
        current_book_slug_for_exclusion = audiobook_obj.slug
    elif found_external_book_dict and found_external_book_dict.get('slug'):
        current_book_slug_for_exclusion = found_external_book_dict.get('slug')
    if current_book_slug_for_exclusion:
        seen_recommended_slugs.add(current_book_slug_for_exclusion)

    current_book_language = None
    current_book_genre = None
    if isinstance(context_audiobook_data_for_display, Audiobook):
        current_book_language = context_audiobook_data_for_display.language
        current_book_genre = context_audiobook_data_for_display.genre
    elif isinstance(context_audiobook_data_for_display, dict):
        current_book_language = context_audiobook_data_for_display.get('language')
        current_book_genre = context_audiobook_data_for_display.get('genre')
        if not current_book_genre and 'subjects' in context_audiobook_data_for_display:
            subjects = context_audiobook_data_for_display.get('subjects')
            if isinstance(subjects, list) and subjects:
                current_book_genre = subjects[0]
            elif isinstance(subjects, str):
                current_book_genre = subjects.split(';')[0].strip() if subjects.split(';')[0].strip() else None

    logger.info(f"Reco Details - Current Book: Slug='{current_book_slug_for_exclusion}', Lang='{current_book_language}', Genre='{current_book_genre}'")
    max_recommendations = 5
    if current_book_language:
        db_recs_query_base = Audiobook.objects.filter(status='PUBLISHED', is_creator_book=True, language__iexact=current_book_language).exclude(slug__in=list(seen_recommended_slugs)).annotate(calculated_average_rating=Avg('reviews__rating'))
        if current_book_genre:
            genre_specific_db_recs = list(db_recs_query_base.filter(genre__iexact=current_book_genre).order_by('-calculated_average_rating', '?')[:max_recommendations])
            for rec in genre_specific_db_recs:
                if rec.slug not in seen_recommended_slugs and len(recommended_audiobooks_list) < max_recommendations:
                    recommended_audiobooks_list.append(rec)
                    seen_recommended_slugs.add(rec.slug)
        if len(recommended_audiobooks_list) < max_recommendations:
            exclude_q = Q()
            if current_book_genre:
                exclude_q = Q(genre__iexact=current_book_genre)
            other_lang_db_recs = list(db_recs_query_base.exclude(exclude_q).order_by('-calculated_average_rating', '?')[:max_recommendations - len(recommended_audiobooks_list)])
            for rec in other_lang_db_recs:
                if rec.slug not in seen_recommended_slugs and len(recommended_audiobooks_list) < max_recommendations:
                    recommended_audiobooks_list.append(rec)
                    seen_recommended_slugs.add(rec.slug)

    if len(recommended_audiobooks_list) < max_recommendations and current_book_language:
        cache_key_external = 'librivox_archive_audiobooks_data_v7'
        external_audiobook_data_cache = cache.get(cache_key_external)
        if external_audiobook_data_cache:
            potential_external_recs_for_lang = []
            for book_dict in external_audiobook_data_cache.get("librivox_audiobooks", []):
                book_lang_ext = book_dict.get('language', 'en') 
                if book_lang_ext and current_book_language.lower() in book_lang_ext.lower() and book_dict.get('slug') not in seen_recommended_slugs:
                    potential_external_recs_for_lang.append(book_dict)
            archive_lang_books = external_audiobook_data_cache.get("archive_language_audiobooks", {})
            if isinstance(archive_lang_books, dict) and current_book_language in archive_lang_books:
                for book_dict in archive_lang_books[current_book_language]:
                    if book_dict.get('slug') not in seen_recommended_slugs:
                        potential_external_recs_for_lang.append(book_dict)
            archive_genre_books = external_audiobook_data_cache.get("archive_genre_audiobooks", {})
            if isinstance(archive_genre_books, dict):
                for genre_key, book_list in archive_genre_books.items():
                    for book_dict in book_list:
                        book_lang_ext = book_dict.get('language')
                        if book_lang_ext and current_book_language.lower() in book_lang_ext.lower() and book_dict.get('slug') not in seen_recommended_slugs:
                            if not any(p_rec.get('slug') == book_dict.get('slug') for p_rec in potential_external_recs_for_lang):
                                potential_external_recs_for_lang.append(book_dict)
            unique_external_recs_by_slug = {}
            for book_dict in potential_external_recs_for_lang:
                slug_val = book_dict.get('slug')
                if slug_val and slug_val not in unique_external_recs_by_slug:
                    unique_external_recs_by_slug[slug_val] = book_dict
            sorted_external_recs = []
            if current_book_genre:
                genre_matches = []
                other_matches = []
                for slug, book_dict_item in unique_external_recs_by_slug.items():
                    book_g_ext = book_dict_item.get('genre', '')
                    book_s_ext = book_dict_item.get('subjects', [])
                    if isinstance(book_s_ext, str): book_s_ext = [s.strip() for s in book_s_ext.split(';')]
                    genre_match_found = (book_g_ext and current_book_genre.lower() in book_g_ext.lower()) or any(current_book_genre.lower() in s.lower() for s in book_s_ext if isinstance(s, str))
                    if genre_match_found:
                        genre_matches.append(book_dict_item)
                    else:
                        other_matches.append(book_dict_item)
                random.shuffle(genre_matches)
                random.shuffle(other_matches)
                sorted_external_recs = genre_matches + other_matches
            else:
                sorted_external_recs = list(unique_external_recs_by_slug.values())
                random.shuffle(sorted_external_recs)
            for book_dict_ext in sorted_external_recs:
                if len(recommended_audiobooks_list) >= max_recommendations:
                    break
                ext_slug = book_dict_ext.get('slug')
                if ext_slug and ext_slug not in seen_recommended_slugs:
                    if 'author' in book_dict_ext and 'creator' not in book_dict_ext:
                        book_dict_ext['creator'] = {'creator_name': book_dict_ext['author']}
                    elif 'creator' in book_dict_ext and isinstance(book_dict_ext['creator'], str):
                        book_dict_ext['creator'] = {'creator_name': book_dict_ext['creator']}
                    try:
                        shell_for_rec = Audiobook.objects.get(slug=ext_slug, is_creator_book=False)
                        book_dict_ext['average_rating'] = shell_for_rec.average_rating
                        book_dict_ext['total_views'] = shell_for_rec.total_views
                    except Audiobook.DoesNotExist:
                        book_dict_ext['average_rating'] = None
                        book_dict_ext['total_views'] = 0
                    recommended_audiobooks_list.append(book_dict_ext)
                    seen_recommended_slugs.add(ext_slug)
    logger.info(f"Found {len(recommended_audiobooks_list)} recommendations for '{current_book_slug_for_exclusion}'.")

    context['audiobook'] = audiobook_obj
    context['audiobook_data_for_display'] = context_audiobook_data_for_display
    context['is_creator_book_page'] = is_creator_book_page_flag
    context['reviews'] = reviews_list
    context['user_review_object'] = user_review_object
    context['current_user_has_reviewed'] = current_user_has_reviewed
    context['user_has_purchased'] = user_has_purchased
    context['chapters_to_display'] = chapters_to_display
    context['audiobook_lock_message'] = audiobook_lock_message
    context['page_context_data_dict'] = page_context_for_js
    context['recommended_audiobooks'] = recommended_audiobooks_list
    return render(request, template_name, context)

def trending_audiobooks_view(request):
    context = _get_full_context(request)
    try:
        trending_books_qs = Audiobook.objects.filter(status='PUBLISHED').select_related('creator').order_by('-total_views')[:10]
        context["trending_audiobooks"] = list(trending_books_qs)
        if not context["trending_audiobooks"]:
            context["error_message"] = "No trending audiobooks found at the moment. Check back later!"
    except Exception as e:
        logger.error(f"Error fetching trending audiobooks: {e}", exc_info=True)
        context["error_message"] = "Could not load trending audiobooks due to a server error."
        context["trending_audiobooks"] = []
    return render(request, "audiobooks/trending_audiobooks.html", context)

# --- Page Rendering Views ---

def _render_genre_or_language_page(request, page_type, display_name, template_name, cache_key_segment, query_term, language_for_genre_page=None):
    context = _get_full_context(request)
    cache_key = 'librivox_archive_audiobooks_data_v7'
    external_audiobook_data_cache = cache.get(cache_key)
    context["display_name"] = display_name
    context["page_language"] = language_for_genre_page or (query_term if page_type == "language" else "English")
    context["page_genre"] = query_term if page_type == "genre" else None
    processed_external_books = []
    context["error_message"] = None
    cached_book_list_for_term = []
    if external_audiobook_data_cache:
        source_dict_for_external = external_audiobook_data_cache.get(cache_key_segment, {})
        if page_type == "language":
            cached_book_list_for_term = source_dict_for_external.get(query_term, [])
        elif page_type == "genre":
            if language_for_genre_page:
                books_of_the_language = source_dict_for_external.get(language_for_genre_page, [])
                for book_in_lang in books_of_the_language:
                    book_subjects = book_in_lang.get('subjects', [])
                    book_genre_field = (book_in_lang.get('genre') or "").lower()
                    if isinstance(book_subjects, str): book_subjects = [s.strip() for s in book_subjects.split(';')]
                    genre_match = query_term.lower() in book_genre_field
                    if not genre_match and isinstance(book_subjects, list):
                        genre_match = any(query_term.lower() in (s.lower() if isinstance(s, str) else "") for s in book_subjects)
                    if genre_match:
                        cached_book_list_for_term.append(book_in_lang)
                if not books_of_the_language:
                    logger.warning(f"No external books found for language '{language_for_genre_page}' in cache segment '{cache_key_segment}' for genre page '{display_name}'.")
                elif not cached_book_list_for_term:
                    logger.info(f"External books for lang '{language_for_genre_page}' found, but none matched genre '{query_term}'.")
            else: 
                cached_book_list_for_term = source_dict_for_external.get(query_term, [])
    if not cached_book_list_for_term and not context.get("error_message"):
        context["error_message"] = f"فی الحال '{display_name}' کے لیے عوامی آرکائیوز سے کوئی آڈیو کتابیں دستیاب نہیں ہیں۔"
    external_book_slugs_from_cache = {book.get('slug') for book in cached_book_list_for_term if book.get('slug')}
    db_book_stats_map = {}
    if external_book_slugs_from_cache:
        db_instances = Audiobook.objects.filter(slug__in=list(external_book_slugs_from_cache), is_creator_book=False)
        for db_book in db_instances:
            db_book_stats_map[db_book.slug] = {'total_views': db_book.total_views, 'average_rating': db_book.average_rating, 'author': db_book.author, 'title': db_book.title, 'cover_image': db_book.cover_image.url if db_book.cover_image else None}

    for book_data_cache in cached_book_list_for_term:
        slug = book_data_cache.get('slug')
        if slug and slug in db_book_stats_map:
            book_data_cache['total_views'] = db_book_stats_map[slug]['total_views']
            book_data_cache['average_rating'] = db_book_stats_map[slug]['average_rating']
            book_data_cache['author'] = db_book_stats_map[slug].get('author', book_data_cache.get('author'))
            book_data_cache['title'] = db_book_stats_map[slug].get('title', book_data_cache.get('title'))
            if db_book_stats_map[slug].get('cover_image'):
                book_data_cache['cover_image'] = db_book_stats_map[slug]['cover_image']
        else:
            book_data_cache.setdefault('total_views', 0)
            book_data_cache.setdefault('average_rating', None)
        processed_external_books.append(book_data_cache)
    context["audiobooks_list"] = processed_external_books
    creator_books_final_list = []
    try:
        first_chapter_prefetch = Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order'), to_attr='first_chapter_list')
        creator_books_query = Audiobook.objects.filter(status='PUBLISHED', is_creator_book=True)
        current_page_language = context["page_language"]
        if page_type == "genre":
            creator_books_query = creator_books_query.filter(language__iexact=current_page_language, genre__iexact=query_term)
        elif page_type == "language":
            creator_books_query = creator_books_query.filter(language__iexact=current_page_language)
        creator_books_qs = creator_books_query.select_related('creator').prefetch_related(first_chapter_prefetch, Prefetch('reviews', queryset=Review.objects.select_related('user').order_by('-created_at'))).order_by('-publish_date')
        for book in creator_books_qs:
            first_chapter_audio_url = None
            first_chapter_title = None
            if hasattr(book, 'first_chapter_list') and book.first_chapter_list:
                first_chapter = book.first_chapter_list[0]
                first_chapter_title = first_chapter.chapter_name
                if first_chapter.audio_file and hasattr(first_chapter.audio_file, 'url'):
                    first_chapter_audio_url = first_chapter.audio_file.url
            creator_books_final_list.append({'source': 'creator', 'title': book.title, 'slug': book.slug, 'cover_image': book.cover_image.url if book.cover_image else None, 'author': book.author, 'creator': book.creator, 'first_chapter_audio_url': first_chapter_audio_url, 'first_chapter_title': first_chapter_title, 'is_creator_book': True, 'average_rating': book.average_rating, 'total_views': book.total_views, 'is_paid': book.is_paid, 'price': book.price, 'status': book.status, 'language': book.language, 'genre': book.genre})
        context["creator_audiobooks"] = creator_books_final_list
        if not creator_books_final_list and not processed_external_books and not context.get("error_message"):
            context["error_message"] = f"فی الحال '{display_name}' کے لیے کوئی آڈیو کتابیں دستیاب نہیں ہیں۔"
    except Exception as db_err:
        logger.error(f"Error fetching creator audiobooks for {page_type} '{display_name}' (Lang: {current_page_language}, Query: {query_term}): {db_err}", exc_info=True)
        if not processed_external_books and not creator_books_final_list and not context.get("error_message"):
            context["error_message"] = f"'{display_name}' کے لیے آڈیو کتابیں لوڈ کرنے میں ناکامی۔ براہ کرم کچھ دیر بعد کوشش کریں."
    if not messages.get_messages(request) and external_audiobook_data_cache is None and not context.get("error_message"):
        messages.error(request, f"'{display_name}' کے لیے ڈیٹا لوڈ کرنے میں ایک مسئلہ درپیش ہے۔")
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
def urdu_genre_novel_afsana(request): return _render_genre_or_language_page(request, "genre", "Urdu Novel & Afsana", 'audiobooks/Urdu/genre_novel_afsana.html', "archive_language_audiobooks", "Novel Afsana", language_for_genre_page="Urdu")
def urdu_genre_shayari(request): return _render_genre_or_language_page(request, "genre", "Urdu Shayari", 'audiobooks/Urdu/genre_shayari.html', "archive_language_audiobooks", "Shayari", language_for_genre_page="Urdu")
def urdu_genre_tareekh(request): return _render_genre_or_language_page(request, "genre", "Urdu Tareekh", 'audiobooks/Urdu/genre_tareekh.html', "archive_language_audiobooks", "Tareekh", language_for_genre_page="Urdu")
def urdu_genre_safarnama(request): return _render_genre_or_language_page(request, "genre", "Urdu Safarnama", 'audiobooks/Urdu/genre_safarnama.html', "archive_language_audiobooks", "Safarnama", language_for_genre_page="Urdu")
def urdu_genre_mazah(request): return _render_genre_or_language_page(request, "genre", "Urdu Mazah", 'audiobooks/Urdu/genre_mazah.html', "archive_language_audiobooks", "Mazah", language_for_genre_page="Urdu")
def urdu_genre_bachon_ka_adab(request): return _render_genre_or_language_page(request, "genre", "Urdu Bachon ka Adab", 'audiobooks/Urdu/genre_bachon_ka_adab.html', "archive_language_audiobooks", "Bachon ka Adab", language_for_genre_page="Urdu")
def urdu_genre_mazhabi_adab(request): return _render_genre_or_language_page(request, "genre", "Urdu Mazhabi Adab", 'audiobooks/Urdu/genre_mazhabi_adab.html', "archive_language_audiobooks", "Mazhabi Adab", language_for_genre_page="Urdu")
def punjabi_genre_qissalok(request): return _render_genre_or_language_page(request, "genre", "Punjabi Qissa Lok", 'audiobooks/Punjabi/genre_qissalok.html', "archive_language_audiobooks", "Qissalok", language_for_genre_page="Punjabi")
def punjabi_genre_geet(request): return _render_genre_or_language_page(request, "genre", "Punjabi Geet", 'audiobooks/Punjabi/genre_geet.html', "archive_language_audiobooks", "Geet", language_for_genre_page="Punjabi")
def sindhi_genre_lok_adab(request): return _render_genre_or_language_page(request, "genre", "Sindhi Lok Adab", 'audiobooks/Sindhi/genre_lok_adab.html', "archive_language_audiobooks", "Lok Adab", language_for_genre_page="Sindhi")
def sindhi_genre_shayari(request): return _render_genre_or_language_page(request, "genre", "Sindhi Shayari", 'audiobooks/Sindhi/genre_shayari.html', "archive_language_audiobooks", "Shayari", language_for_genre_page="Sindhi")

# --- API and Streaming Views ---

@login_required
@require_POST
@csrf_protect
def add_review(request, audiobook_slug):
    try:
        audiobook = get_object_or_404(Audiobook, slug=audiobook_slug)
        can_review = False
        if not audiobook.is_paid:
            can_review = True
        elif audiobook.is_paid:
            if audiobook.is_creator_book:
                if request.user.is_authenticated and hasattr(request.user, 'has_purchased_audiobook'):
                    if request.user.has_purchased_audiobook(audiobook):
                        can_review = True
            else:
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
            review, created = Review.objects.update_or_create(audiobook=audiobook, user=request.user, defaults={'rating': rating, 'comment': comment})
        audiobook.refresh_from_db() 
        new_average_rating_val = audiobook.average_rating
        message = "Review updated successfully!" if not created else "Review added successfully!"
        user_profile_pic_url = None
        if hasattr(review.user, 'profile_pic') and review.user.profile_pic:
            try: user_profile_pic_url = review.user.profile_pic.url
            except ValueError: pass 
        review_data = {'review_id': review.review_id, 'rating': review.rating, 'comment': review.comment or "", 'user_id': review.user.user_id, 'user_name': review.user.full_name or review.user.username, 'user_profile_pic': user_profile_pic_url, 'created_at': review.created_at.isoformat(), 'timesince': timesince(review.created_at) + " ago"}
        return JsonResponse({'status': 'success', 'message': message, 'created': created, 'new_average_rating': str(new_average_rating_val) if new_average_rating_val is not None else "0.0", 'review_data': review_data})
    except Audiobook.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error in add_review for {audiobook_slug}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An unexpected server error occurred. Please try again.'}, status=500)

@require_GET
def stream_audio(request):
    audio_url_param = request.GET.get("url")
    if not audio_url_param:
        return JsonResponse({"error": "No audio URL provided"}, status=400)
    target_audio_url = audio_url_param
    parsed_url = urlparse(target_audio_url)
    is_local_media = False
    if target_audio_url.startswith(settings.MEDIA_URL):
        if not parsed_url.scheme and not parsed_url.netloc:
            is_local_media = True
    if is_local_media:
        try:
            relative_media_path = target_audio_url[len(settings.MEDIA_URL):] if target_audio_url.startswith(settings.MEDIA_URL) else target_audio_url
            file_system_path = os.path.join(settings.MEDIA_ROOT, relative_media_path)
            if not os.path.exists(file_system_path) or os.path.isdir(file_system_path):
                logger.error(f"Local audio file not found or is directory: {file_system_path}")
                return HttpResponse("Audio file not found.", status=404)
            logger.info(f"Streaming local file: {file_system_path}")
            return FileResponse(open(file_system_path, 'rb'), as_attachment=False)
        except Exception as e:
            logger.error(f"Error streaming local audio file {target_audio_url}: {e}", exc_info=True)
            return HttpResponse("Error streaming local audio file.", status=500)
    elif not all([parsed_url.scheme, parsed_url.netloc]):
        logger.error(f"Invalid external audio URL format: {audio_url_param}")
        return HttpResponse(f"Invalid audio URL provided: {audio_url_param}", status=400)
    else:
        try:
            range_header = request.headers.get('Range', None)
            user_agent_host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "audiox.com"
            proxy_headers = {'User-Agent': f'AudioXApp Audio Proxy/1.0 (+http://{user_agent_host})'}
            if range_header:
                proxy_headers['Range'] = range_header
            logger.info(f"Proxying external audio from: {target_audio_url} with headers: {proxy_headers}")
            audio_stream_timeout = (10, 60)
            response_ext = requests.get(target_audio_url, stream=True, headers=proxy_headers, timeout=audio_stream_timeout)
            response_ext.raise_for_status()
            content_type = response_ext.headers.get('Content-Type', 'audio/mpeg')
            if not content_type.lower().startswith('audio/'):
                guessed_type, _ = mimetypes.guess_type(target_audio_url)
                content_type = guessed_type if guessed_type and guessed_type.startswith('audio/') else 'audio/mpeg'
            logger.info(f"Streaming external content with type: {content_type}, status: {response_ext.status_code}")
            streaming_response = StreamingHttpResponse(response_ext.iter_content(chunk_size=8192), content_type=content_type, status=response_ext.status_code)
            if 'Content-Range' in response_ext.headers:
                streaming_response['Content-Range'] = response_ext.headers['Content-Range']
            if 'Content-Length' in response_ext.headers:
                streaming_response['Content-Length'] = response_ext.headers['Content-Length']
            streaming_response['Accept-Ranges'] = response_ext.headers.get('Accept-Ranges', 'bytes')
            return streaming_response
        except requests.exceptions.Timeout:
            logger.error(f"Timeout streaming external audio from: {target_audio_url}")
            return HttpResponse("Audio stream timed out from external source.", status=408)
        except requests.exceptions.HTTPError as e_http:
            logger.error(f"HTTPError streaming external audio from {target_audio_url}: {e_http.response.status_code} - {e_http.response.text[:200] if e_http.response else 'No body'}")
            return HttpResponse(f"Error fetching audio from external source: Status {e_http.response.status_code}", status=e_http.response.status_code)
        except requests.exceptions.RequestException as e_req:
            logger.error(f"RequestException streaming external audio from {target_audio_url}: {e_req}")
            return HttpResponse("Error processing audio stream (could not connect to external source).", status=502)
        except SuspiciousOperation as e_susp:
            logger.warning(f"SuspiciousOperation in stream_audio: {e_susp}")
            return JsonResponse({"error": str(e_susp)}, status=400)
        except Exception as e_gen:
            logger.error(f"Generic error in stream_audio from {target_audio_url}: {e_gen}", exc_info=True)
            return HttpResponse("Internal server error during audio streaming.", status=500)

@csrf_exempt
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
        image_fetch_timeout = 30
        response = requests.get(target_image_url, stream=True, timeout=image_fetch_timeout, headers=proxy_headers)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', 'image/jpeg')
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