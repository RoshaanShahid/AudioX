"""
AudioXApp Content Views
Handles audiobook content display, search, streaming, and related functionality
"""

import random
import requests
import feedparser
import mimetypes
import json
import os
import re
import time
import logging
from urllib.parse import urlparse, quote
from decimal import Decimal
from collections import defaultdict

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse, Http404, FileResponse
from django.contrib import messages
from django.core.cache import cache
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Prefetch, Avg, F, Count
from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.utils.timesince import timesince
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.middleware.csrf import get_token
from django.core.paginator import Paginator
from django.templatetags.static import static


from ..models import (
    Audiobook, Chapter, Review, User, AudiobookPurchase,
    CreatorEarning, Creator, AudiobookViewLog, ContentReport, ListeningHistory,
    ChapterUnlock
)
from .utils import _get_full_context

logger = logging.getLogger(__name__)

# ==========================================
# CONSTANTS AND CONFIGURATIONS
# ==========================================

LANGUAGE_GENRE_MAPPING = {
    'English': [
        'Fiction', 'Mystery', 'Thriller', 'Science Fiction', 'Fantasy',
        'Romance', 'Biography', 'History', 'Self Help', 'Business'
    ],
    'Urdu': [
        'Novel Afsana', 'Shayari', 'Tareekh', 'Safarnama',
        'Mazah', 'Bachon Ka Adab', 'Mazhabi Adab'
    ],
    'Punjabi': ['Qissa Lok', 'Geet'],
    'Sindhi': ['Lok Adab', 'Shayari']
}

CACHE_KEY = 'librivox_archive_audiobooks_data_v7'
CACHE_DURATION = 6 * 60 * 60  # 6 hours
FREE_PREVIEW_CHAPTERS = getattr(settings, 'FREE_PREVIEW_CHAPTERS_COUNT', 1)
DEFAULT_COVER_IMAGE = static('img/default_book_cover.png')
CHAPTER_UNLOCK_COST = 50 # NEW: Define chapter unlock cost


# ==========================================
# UTILITY FUNCTIONS
# ==========================================

def parse_duration_to_seconds(duration_str):
    """Convert duration string to seconds"""
    if duration_str is None:
        return None
    if isinstance(duration_str, (int, float)):
        return int(duration_str)
    if not isinstance(duration_str, str):
        return None

    duration_str = duration_str.strip()
    parts = duration_str.split(':')

    try:
        if len(parts) == 3:  # HH:MM:SS
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))
        elif len(parts) == 2:  # MM:SS
            return int(parts[0]) * 60 + int(float(parts[2]))
        elif len(parts) == 1:  # SS
            return int(float(duration_str))
    except ValueError:
        pass

    try:
        return int(float(duration_str))
    except ValueError:
        return None


def get_chapter_accessibility(chapter, audiobook, user, chapter_index):
    """
    Determine if a user can access a specific chapter based on AudioX access control rules:
    
    1. PAID creator audiobooks: Both FREE and PREMIUM users must purchase
    2. FREE audiobooks (external, admin-added, or creator-set-as-free):
        - PREMIUM users: Full access to all chapters
        - FREE users: Only first chapter access, unless unlocked with coins
        - Unauthenticated users: Only first chapter access
        
    Args:
        chapter: Chapter instance
        audiobook: Audiobook instance  
        user: User instance (can be AnonymousUser)
        chapter_index: 0-based index of the chapter
        
    Returns:
        tuple: (bool: True if accessible, str: lock_reason or None)
    """
    
    # For PAID creator audiobooks - both free and premium users must purchase
    if audiobook.is_creator_book and audiobook.is_paid:
        if not user.is_authenticated:
            is_preview = chapter.is_preview_eligible or (chapter_index < FREE_PREVIEW_CHAPTERS)
            return (is_preview, "purchase_required" if not is_preview else None)
        
        has_purchased = user.has_purchased_audiobook(audiobook)
        return (has_purchased, "purchase_required" if not has_purchased else None)
    
    # For FREE audiobooks (external, admin-added, or creator-set-as-free)
    if not audiobook.is_paid:
        is_first_chapter = chapter_index == 0

        if not user.is_authenticated:
            return (is_first_chapter, "premium_required" if not is_first_chapter else None)

        # Check user subscription type
        if user.subscription_type == 'PR':  # Premium user
            return (True, None)  # Full access to all chapters
        else:  # Free user (subscription_type == 'FR')
            if is_first_chapter:
                return (True, None)
            
            # NEW: Check if this specific chapter has been unlocked by the user
            has_unlocked_chapter = ChapterUnlock.objects.filter(user=user, chapter=chapter).exists()
            if has_unlocked_chapter:
                return (True, None)
            
            return (False, "coin_unlock_available")
            
    # Fallback - should not reach here with current audiobook types
    return (False, "unknown")


def calculate_relevance_score(book, query):
    """Calculate relevance score for search results"""
    if not query:
        return 1.0

    score = 0.0
    query_lower = query.lower()

    # Title match (highest weight)
    if query_lower in book.title.lower():
        score += 0.4
        if book.title.lower().startswith(query_lower):
            score += 0.2

    # Author match
    if book.author and query_lower in book.author.lower():
        score += 0.2

    # Genre match
    if book.genre and query_lower in book.genre.lower():
        score += 0.1

    # Creator match
    if hasattr(book, 'creator') and book.creator and book.creator.creator_name:
        if query_lower in book.creator.creator_name.lower():
            score += 0.1

    # Description match
    if book.description and query_lower in book.description.lower():
        score += 0.1

    # Boost popular books
    if book.total_views > 1000:
        score += 0.1

    return min(score, 1.0)


def sort_search_results(results, query):
    """Sort search results by relevance and popularity"""
    if query:
        return sorted(
            results,
            key=lambda x: (x.get('relevance_score', 0), x.get('total_views', 0)),
            reverse=True
        )
    else:
        return sorted(
            results,
            key=lambda x: (x.get('total_views', 0), x.get('publish_date') or ''),
            reverse=True
        )

# ==========================================
# EXTERNAL DATA FETCHING
# ==========================================

def fetch_audiobooks_data():
    """Fetch and cache audiobook data from external sources"""
    cached_data = cache.get(CACHE_KEY)
    if cached_data:
        logger.info(f"CACHE HIT: Using cached data for audiobooks (key: {CACHE_KEY})")
        return cached_data

    logger.info(f"CACHE MISS: Fetching fresh data for audiobooks (key: {CACHE_KEY})")

    librivox_audiobooks = []
    archive_genre_audiobooks = {}
    archive_language_audiobooks = {}
    fetch_successful = False

    # RSS feeds for LibriVox
    rss_feeds = [
        "https://librivox.org/rss/47", "https://librivox.org/rss/52",
        "https://librivox.org/rss/53", "https://librivox.org/rss/54",
        "https://librivox.org/rss/59", "https://librivox.org/rss/60",
        "https://librivox.org/rss/61", "https://librivox.org/rss/62"
    ]

    session = requests.Session()
    user_agent_host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "AudioXApp.com"
    headers = {'User-Agent': f'AudioXApp/1.0 (+http://{user_agent_host})'}

    # Fetch LibriVox data
    for rss_url in rss_feeds:
        try:
            response = session.get(rss_url, timeout=45, headers=headers)
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

                # Extract audio URL from enclosures
                if entry.enclosures:
                    for enc in entry.enclosures:
                        if 'audio' in enc.get('type', '').lower():
                            audio_url = enc.href
                            break

                # Fallback to links
                if not audio_url and entry.links:
                    for link_entry in entry.links:
                        if ('audio' in link_entry.get('type', '').lower() or
                                any(link_entry.href.lower().endswith(ext) for ext in ['.mp3', '.ogg', '.m4a', '.wav'])):
                            audio_url = link_entry.href
                            break

                if not audio_url:
                    continue

                chapter_title = entry.title.replace('"', '').strip() if entry.title else 'Untitled Chapter'
                chapter_duration = None
                if hasattr(entry, 'itunes_duration'):
                    chapter_duration = parse_duration_to_seconds(entry.itunes_duration)

                chapters_data.append({
                    "chapter_title": chapter_title,
                    "audio_url": audio_url,
                    "duration_seconds": chapter_duration
                })

            if not chapters_data:
                logger.info(f"No chapters with audio found for audiobook in {rss_url}")
                continue

            title = feed.feed.get('title', 'Unknown Title').replace('LibriVox', '').strip()
            description = feed.feed.get('summary', feed.feed.get('itunes_summary', 'No description available.'))
            author = feed.feed.get('author', feed.feed.get('itunes_author', 'Various Authors'))

            cover_image_url = None
            if hasattr(feed.feed, 'image') and hasattr(feed.feed.image, 'href'):
                cover_image_url = feed.feed.image.href

            slug = slugify(title) if title and title != 'Unknown Title' else f'librivox-book-{random.randint(1000,9999)}'

            librivox_audiobooks.append({
                "source": "librivox",
                "title": title,
                "description": description,
                "author": author,
                "cover_image": cover_image_url or DEFAULT_COVER_IMAGE,
                "chapters": chapters_data,
                "first_chapter_audio_url": chapters_data[0]["audio_url"] if chapters_data else None,
                "first_chapter_title": chapters_data[0]["chapter_title"] if chapters_data else None,
                "slug": slug,
                "is_creator_book": False,
                "total_views": 0,
                "average_rating": None,
                "is_paid": False,
                "price": Decimal("0.00"),
                "language": feed.feed.get('language', 'en')
            })
            fetch_successful = True

        except requests.exceptions.Timeout as e:
            logger.error(f"TIMEOUT error fetching RSS feed {rss_url}: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"RequestException error fetching RSS feed {rss_url}: {e}")
        except Exception as e:
            logger.error(f"Generic error processing RSS feed {rss_url}: {e}", exc_info=True)

    # Fetch Archive.org data
    base_url = "https://archive.org/advancedsearch.php"
    search_terms = ["Fiction", "Mystery", "Thriller", "Science Fiction", "Fantasy",
                    "Romance", "Biography", "History", "Self-Help", "Business",
                    "Urdu", "Punjabi", "Sindhi"]
    language_specific_terms = ["Urdu", "Punjabi", "Sindhi"]

    for i, term in enumerate(search_terms):
        if i > 0:
            time.sleep(1)  # Rate limiting

        # Build query based on term type
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
            response = session.get(base_url, params=params, timeout=30, headers=headers)
            response.raise_for_status()
            data = response.json()
            docs = data.get('response', {}).get('docs', [])

            logger.info(f"For term '{term}', Archive.org API returned {len(docs)} documents")

            audiobooks_for_term = []
            for doc in docs:
                identifier = doc.get('identifier')
                if not identifier:
                    continue

                # Get detailed metadata
                meta_url = f"https://archive.org/metadata/{identifier}"
                meta_resp = session.get(meta_url, timeout=30, headers=headers)
                meta_resp.raise_for_status()
                item_metadata = meta_resp.json()

                # Extract book information
                doc_title = doc.get('title', 'Unknown Title')
                creator_data = doc.get('creator', 'Unknown Author')
                author = ', '.join(creator_data) if isinstance(creator_data, list) else creator_data
                description_data = doc.get('description', 'No description available.')
                description = ' '.join(description_data) if isinstance(description_data, list) else description_data
                subjects = doc.get('subject', [])
                language = doc.get('language', 'English')
                if isinstance(language, list):
                    language = language[0] if language else 'English'

                # Extract chapters from files
                files = item_metadata.get("files", [])
                chapters = []
                for file_item in files:
                    if (file_item.get("format") in ["VBR MP3", "MP3", "64Kbps MP3", "128Kbps MP3"]
                            and "name" in file_item):
                        chapter_title = str(file_item.get("title", file_item.get("name", 'Untitled Chapter'))).replace('"', '').strip()
                        duration = parse_duration_to_seconds(file_item.get('length') or file_item.get('duration'))

                        chapters.append({
                            "chapter_title": chapter_title,
                            "audio_url": f"https://archive.org/download/{identifier}/{quote(file_item['name'])}",
                            "duration_seconds": duration
                        })

                if not chapters:
                    continue

                slug = slugify(doc_title) if doc_title != 'Unknown Title' else f'archive-{term.lower().replace(" ", "-")}-{random.randint(1000,9999)}'

                book_data = {
                    "source": "archive",
                    "title": doc_title,
                    "description": description,
                    "author": author,
                    "cover_image": f"https://archive.org/services/img/{identifier}" or DEFAULT_COVER_IMAGE,
                    "chapters": chapters,
                    "first_chapter_audio_url": chapters[0]["audio_url"] if chapters else None,
                    "first_chapter_title": chapters[0]["chapter_title"] if chapters else None,
                    "slug": slug,
                    "is_creator_book": False,
                    "total_views": 0,
                    "average_rating": None,
                    "is_paid": False,
                    "price": Decimal("0.00"),
                    "subjects": subjects,
                    "language": language,
                    "genre": term if term not in language_specific_terms else None
                }
                audiobooks_for_term.append(book_data)

            if audiobooks_for_term:
                if term in language_specific_terms:
                    if term not in archive_language_audiobooks:
                        archive_language_audiobooks[term] = []
                    archive_language_audiobooks[term].extend(audiobooks_for_term)
                else:
                    archive_genre_audiobooks[term] = audiobooks_for_term
                fetch_successful = True

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTPError for API term '{term}': {e.response.status_code if e.response else 'No response'}")
        except Exception as e:
            logger.error(f"Error processing API term '{term}': {e}", exc_info=True)

    # Manual language items (specific high-quality content)
    manual_language_items = {
        "Urdu": [
            "Ashra-Mubashra-Darussalam-Urdu-Audio-MP3-CD",
            "Tafsir-ibne-kaseer-kathir-urdu-----audio-mp3-hq",
            "iman-syed-suleiman-nadvi",
            "Seerat-e-Khulfa-e-Rashideen----Audio-MP3"
        ],
        "Punjabi": [],
        "Sindhi": []
    }

    # Process manual items
    for lang_key, item_ids in manual_language_items.items():
        if not item_ids:
            continue

        if lang_key not in archive_language_audiobooks:
            archive_language_audiobooks[lang_key] = []

        current_slugs = {b.get('slug') for b in archive_language_audiobooks[lang_key]}

        for item_id in item_ids:
            try:
                time.sleep(0.5)  # Rate limiting

                meta_url = f"https://archive.org/metadata/{item_id}"
                meta_resp = session.get(meta_url, timeout=30, headers=headers)
                meta_resp.raise_for_status()
                item_metadata = meta_resp.json()

                metadata = item_metadata.get('metadata', item_metadata)
                title = metadata.get('title', f"Unknown Title - {item_id}")

                if title.startswith("Unknown Title -"):
                    continue

                creator_data = metadata.get('creator', 'Unknown Author')
                author = ', '.join(creator_data) if isinstance(creator_data, list) else creator_data
                description_data = metadata.get('description', 'No description available.')
                description = ' '.join(description_data) if isinstance(description_data, list) else description_data
                language = metadata.get('language', lang_key)
                if isinstance(language, list):
                    language = language[0] if language else lang_key
                subjects = metadata.get('subject', [])

                # Extract chapters
                files = item_metadata.get("files", [])
                chapters = []
                for file_item in files:
                    if (file_item.get("format") in ["VBR MP3", "MP3", "64Kbps MP3", "128Kbps MP3"]
                            and "name" in file_item):
                        chapter_title = str(file_item.get("title", file_item.get("name", 'Untitled Chapter'))).replace('"', '').strip()
                        duration = parse_duration_to_seconds(file_item.get('length') or file_item.get('duration'))

                        chapters.append({
                            "chapter_title": chapter_title,
                            "audio_url": f"https://archive.org/download/{item_id}/{quote(file_item['name'])}",
                            "duration_seconds": duration
                        })

                if not chapters:
                    continue

                slug = slugify(title) if not title.startswith("Unknown Title") else f'archive-manual-{lang_key.lower()}-{item_id.replace("_", "-")}'

                if slug not in current_slugs:
                    book_data = {
                        "source": "archive",
                        "title": title,
                        "description": description,
                        "author": author,
                        "cover_image": f"https://archive.org/services/img/{item_id}" or DEFAULT_COVER_IMAGE,
                        "chapters": chapters,
                        "first_chapter_audio_url": chapters[0]["audio_url"] if chapters else None,
                        "first_chapter_title": chapters[0]["chapter_title"] if chapters else None,
                        "slug": slug,
                        "is_creator_book": False,
                        "total_views": 0,
                        "average_rating": None,
                        "is_paid": False,
                        "price": Decimal("0.00"),
                        "subjects": subjects,
                        "language": language,
                        "genre": None
                    }
                    archive_language_audiobooks[lang_key].append(book_data)
                    current_slugs.add(slug)
                    fetch_successful = True

            except Exception as e:
                logger.error(f"Error processing manual item '{item_id}' for language '{lang_key}': {e}", exc_info=True)

    # Cache the results
    combined_data = {
        "librivox_audiobooks": librivox_audiobooks,
        "archive_genre_audiobooks": archive_genre_audiobooks,
        "archive_language_audiobooks": archive_language_audiobooks
    }

    if fetch_successful:
        logger.info(f"CACHE SET: Storing fetched data in cache (key: {CACHE_KEY}, duration: {CACHE_DURATION}s)")
        cache.set(CACHE_KEY, combined_data, CACHE_DURATION)
        return combined_data
    else:
        logger.warning("FETCH UNSUCCESSFUL: No new data to cache")
        return combined_data if any([librivox_audiobooks, archive_genre_audiobooks, archive_language_audiobooks]) else None

# ==========================================
# SEARCH FUNCTIONALITY - FIXED
# ==========================================

def search_creator_audiobooks(query, language_filter, genre_filter, creator_filter, seen_slugs):
    """Search creator and admin audiobooks with optimized database queries"""
    results = []

    try:
        # Build query to include ALL published audiobooks (creator + admin)
        db_query = Q(status='PUBLISHED')

        if language_filter:
            db_query &= Q(language__iexact=language_filter)

        if genre_filter:
            genre_q = (
                Q(genre__icontains=genre_filter) |
                Q(genre__iexact=genre_filter) |
                Q(genre__istartswith=genre_filter)
            )
            db_query &= genre_q

        if creator_filter:
            # Only apply creator filter to creator books
            creator_q = (
                Q(creator__creator_name__icontains=creator_filter) |
                Q(creator__user__username__icontains=creator_filter) |
                Q(creator__user__first_name__icontains=creator_filter) |
                Q(creator__user__last_name__icontains=creator_filter)
            )
            db_query &= (Q(is_creator_book=True) & creator_q)

        if query:
            text_search_q = (
                Q(title__icontains=query) |
                Q(description__icontains=query) |
                Q(author__icontains=query) |
                Q(genre__icontains=query) |
                Q(creator__creator_name__icontains=query)
            )
            db_query &= text_search_q

        # Execute optimized query
        audiobooks = (
            Audiobook.objects.filter(db_query)
            .select_related('creator', 'creator__user')
            .prefetch_related('reviews')
            .annotate(
                review_count=Count('reviews'),
                avg_rating=Avg('reviews__rating')
            )
            .distinct()
            .order_by('-publish_date', '-total_views')
        )

        # Process results
        for book in audiobooks:
            if book.slug not in seen_slugs:
                relevance_score = calculate_relevance_score(book, query)

                # Handle both creator and admin audiobooks
                creator_name = None
                source_type = 'platform'  # Default for admin audiobooks

                if book.is_creator_book and book.creator:
                    creator_name = book.creator.creator_name
                    source_type = 'creator'
                elif not book.is_creator_book:
                    # Admin/platform audiobook
                    if book.source == 'librivox':
                        source_type = 'librivox'
                    elif book.source == 'archive':
                        source_type = 'archive.org'
                    else:
                        source_type = 'platform'

                results.append({
                    'slug': book.slug,
                    'title': book.title,
                    'author': book.author,
                    'cover_image_url': book.cover_image.url if book.cover_image else DEFAULT_COVER_IMAGE,
                    'creator_name': creator_name,
                    'average_rating': book.avg_rating or book.average_rating,
                    'total_views': book.total_views,
                    'review_count': book.review_count,
                    'is_creator_book': book.is_creator_book,
                    'source_type': source_type,
                    'price': book.price,
                    'is_paid': book.is_paid,
                    'genre': book.genre,
                    'language': book.language,
                    'publish_date': book.publish_date,
                    'relevance_score': relevance_score,
                    'description': book.description[:200] + '...' if len(book.description) > 200 else book.description
                })
                seen_slugs.add(book.slug)

    except Exception as e:
        logger.error(f"Error searching audiobooks: {str(e)}")

    return results


def search_external_audiobooks(query, language_filter, genre_filter, creator_filter, seen_slugs):
    """Search external audiobooks - FIXED VERSION"""
    results = []

    # Skip if creator filter is applied (external books don't have creators)
    if creator_filter:
        return results

    try:
        # Get cached data from your management command
        cached_data = cache.get(CACHE_KEY)
        if not cached_data:
            logger.warning(f"No cached external data found for key: {CACHE_KEY}")
            return results

        logger.info(f"Found cached external data with keys: {list(cached_data.keys())}")

        # Search LibriVox audiobooks
        librivox_books = cached_data.get('librivox_audiobooks', [])
        logger.info(f"Searching {len(librivox_books)} LibriVox books")

        librivox_matches = 0
        for book_dict in librivox_books:
            if _matches_external_filters(book_dict, query, language_filter, genre_filter):
                book_slug = book_dict.get('slug')
                if book_slug and book_slug not in seen_slugs:
                    results.append(_format_external_result(book_dict, 'librivox'))
                    seen_slugs.add(book_slug)
                    librivox_matches += 1

        logger.info(f"LibriVox matches: {librivox_matches}")

        # Search Archive.org audiobooks
        archive_matches = 0
        for source_key in ['archive_genre_audiobooks', 'archive_language_audiobooks']:
            source_data = cached_data.get(source_key, {})
            logger.info(f"Searching {source_key} with {len(source_data)} categories")

            for category_name, books_list in source_data.items():
                for book_dict in books_list:
                    if _matches_external_filters(book_dict, query, language_filter, genre_filter):
                        book_slug = book_dict.get('slug')
                        if book_slug and book_slug not in seen_slugs:
                            results.append(_format_external_result(book_dict, 'archive.org'))
                            seen_slugs.add(book_slug)
                            archive_matches += 1

        logger.info(f"Archive.org matches: {archive_matches}")
        logger.info(f"External search completed: {len(results)} total results")

    except Exception as e:
        logger.error(f"Error searching external audiobooks: {str(e)}", exc_info=True)

    return results


def _matches_external_filters(book_dict, query, language_filter, genre_filter):
    """Check if external book matches all applied filters - SIMPLIFIED"""
    # Check query match
    if query:
        query_lower = query.lower()
        title_match = query_lower in book_dict.get('title', '').lower()
        author_match = query_lower in book_dict.get('author', '').lower()
        desc_match = query_lower in book_dict.get('description', '').lower()
        if not (title_match or author_match or desc_match):
            return False

    # Check language filter
    if language_filter:
        book_language = book_dict.get('language', 'English')
        if isinstance(book_language, list):
            language_match = any(language_filter.lower() in str(lang).lower() for lang in book_language)
        else:
            language_match = language_filter.lower() in str(book_language).lower()
        if not language_match:
            return False

    # Check genre filter
    if genre_filter:
        book_genre = book_dict.get('genre', '')
        book_subjects = book_dict.get('subjects', [])

        genre_match = False
        if book_genre and genre_filter.lower() in book_genre.lower():
            genre_match = True
        elif book_subjects:
            genre_match = any(genre_filter.lower() in str(subject).lower() for subject in book_subjects)

        if not genre_match:
            return False

    return True


def _format_external_result(book_dict, source_type):
    """Format external book data for consistent result structure"""
    return {
        'slug': book_dict.get('slug'),
        'title': book_dict.get('title', 'Unknown Title'),
        'author': book_dict.get('author', 'Unknown Author'),
        'cover_image_url': book_dict.get('cover_image') or DEFAULT_COVER_IMAGE,
        'creator_name': None,
        'average_rating': book_dict.get('average_rating'),
        'total_views': book_dict.get('total_views', 0),
        'review_count': 0,
        'is_creator_book': False,
        'source_type': source_type,
        'price': Decimal("0.00"),
        'is_paid': False,
        'genre': book_dict.get('genre', 'Fiction'),
        'language': book_dict.get('language', 'English'),
        'publish_date': None,
        'relevance_score': 1.0,
        'description': book_dict.get('description', '')[:200] + '...' if len(book_dict.get('description', '')) > 200 else book_dict.get('description', '')
    }


def get_featured_audiobooks(seen_slugs):
    """Get featured/trending audiobooks when no search filters are applied"""
    results = []

    try:
        # Include all published audiobooks
        trending_books = (
            Audiobook.objects.filter(status='PUBLISHED')
            .select_related('creator')
            .annotate(
                review_count=Count('reviews'),
                avg_rating=Avg('reviews__rating')
            )
            .order_by('-total_views', '-publish_date')[:20]
        )

        for book in trending_books:
            if book.slug not in seen_slugs:
                # Handle both creator and admin audiobooks
                creator_name = None
                source_type = 'platform'

                if book.is_creator_book and book.creator:
                    creator_name = book.creator.creator_name
                    source_type = 'creator'
                elif not book.is_creator_book:
                    if book.source == 'librivox':
                        source_type = 'librivox'
                    elif book.source == 'archive':
                        source_type = 'archive.org'
                    else:
                        source_type = 'platform'

                results.append({
                    'slug': book.slug,
                    'title': book.title,
                    'author': book.author,
                    'cover_image_url': book.cover_image.url if book.cover_image else DEFAULT_COVER_IMAGE,
                    'creator_name': creator_name,
                    'average_rating': book.avg_rating or book.average_rating,
                    'total_views': book.total_views,
                    'review_count': book.review_count,
                    'is_creator_book': book.is_creator_book,
                    'source_type': source_type,
                    'price': book.price,
                    'is_paid': book.is_paid,
                    'genre': book.genre,
                    'language': book.language,
                    'publish_date': book.publish_date,
                    'relevance_score': 1.0,
                    'description': book.description[:200] + '...' if len(book.description) > 200 else book.description
                })
                seen_slugs.add(book.slug)

    except Exception as e:
        logger.error(f"Error getting featured audiobooks: {str(e)}")

    return results


def search_results_view(request):
    """Enhanced search view with improved performance and seamless filtering"""
    # Get search parameters
    query = request.GET.get('q', '').strip()
    language_filter = request.GET.get('language', '').strip()
    genre_filter = request.GET.get('genre', '').strip()
    creator_filter = request.GET.get('creator', '').strip()
    page_number = request.GET.get('page', 1)

    # Initialize results
    processed_results = []
    seen_slugs = set()
    common_context = _get_full_context(request)

    # Determine if any filters are applied
    has_any_filter = bool(query or language_filter or genre_filter or creator_filter)

    if has_any_filter:
        # Search all database audiobooks (creator + admin + external)
        processed_results.extend(
            search_creator_audiobooks(query, language_filter, genre_filter, creator_filter, seen_slugs)
        )

        # Search cached external audiobooks
        processed_results.extend(
            search_external_audiobooks(query, language_filter, genre_filter, creator_filter, seen_slugs)
        )
    else:
        # Show featured content when no filters applied
        processed_results.extend(get_featured_audiobooks(seen_slugs))

    # Sort results
    processed_results = sort_search_results(processed_results, query)

    # Implement pagination
    paginator = Paginator(processed_results, 20)
    try:
        page_obj = paginator.get_page(page_number)
    except:
        page_obj = paginator.get_page(1)

    # Generate page title
    if query:
        page_title = f"Search Results for '{query}'"
    else:
        title_parts = []
        if language_filter:
            title_parts.append(f"{language_filter} Audiobooks")
        if genre_filter:
            title_parts.append(f"{genre_filter}")
        if creator_filter:
            title_parts.append(f"by {creator_filter}")
        page_title = " - ".join(title_parts) if title_parts else "Browse Audiobooks"

    # Generate filter summary
    filters = []
    if language_filter:
        filters.append(f"Language: {language_filter}")
    if genre_filter:
        filters.append(f"Genre: {genre_filter}")
    if creator_filter:
        filters.append(f"Creator: {creator_filter}")
    filter_summary = " | ".join(filters) if filters else None

    # Prepare context
    context_data = {
        'query': query,
        'results': page_obj.object_list,
        'page_obj': page_obj,
        'page_title': page_title,
        'current_language_filter': language_filter,
        'current_genre_filter': genre_filter,
        'current_creator_filter': creator_filter,
        'total_results': len(processed_results),
        'has_filters': has_any_filter,
        'search_performed': has_any_filter,
        'filter_summary': filter_summary
    }

    context_data.update(common_context)
    return render(request, 'audiobooks/English/english_search.html', context_data)

# ==========================================
# FILTER OPTIONS API
# ==========================================

def get_filter_options(request):
    """Enhanced filter options endpoint with language-specific genre mapping"""
    language = request.GET.get('language', '').strip()
    genre = request.GET.get('genre', '').strip()

    try:
        # Start with published creator audiobooks
        audiobooks_query = Audiobook.objects.filter(
            status='PUBLISHED',
            is_creator_book=True
        ).select_related('creator')

        # Apply language filter
        if language:
            audiobooks_query = audiobooks_query.filter(language__iexact=language)

        # Apply genre filter
        if genre:
            audiobooks_query = audiobooks_query.filter(
                Q(genre__icontains=genre) | Q(genre__iexact=genre)
            )

        # Get available genres based on language preference
        if language and language in LANGUAGE_GENRE_MAPPING:
            available_genres = LANGUAGE_GENRE_MAPPING[language]
        else:
            # Get genres from database
            db_genres = list(
                audiobooks_query.values_list('genre', flat=True)
                .distinct()
                .exclude(genre__isnull=True)
                .exclude(genre__exact='')
            )

            if not language:
                # Include all predefined genres
                all_predefined_genres = []
                for lang_genres in LANGUAGE_GENRE_MAPPING.values():
                    all_predefined_genres.extend(lang_genres)
                available_genres = list(set(db_genres + all_predefined_genres))
            else:
                available_genres = db_genres

        # Get available creators
        available_creators = list(
            audiobooks_query.filter(creator__isnull=False)
            .values_list('creator__creator_name', flat=True)
            .distinct()
            .exclude(creator__creator_name__isnull=True)
            .exclude(creator__creator_name__exact='')
        )

        # Include external audiobook data
        cached_data = cache.get(CACHE_KEY)
        external_genres = set()

        if cached_data:
            # Process external data for additional options
            for source_key in ['librivox_audiobooks', 'archive_genre_audiobooks', 'archive_language_audiobooks']:
                if source_key == 'librivox_audiobooks':
                    books = cached_data.get(source_key, [])
                    for book in books:
                        if _matches_language_filter(book, language) and book.get('genre'):
                            external_genres.add(book['genre'])
                else:
                    source_data = cached_data.get(source_key, {})
                    for term_books in source_data.values():
                        for book in term_books:
                            if _matches_language_filter(book, language):
                                if book.get('genre'):
                                    external_genres.add(book.get('genre'))
                                for subject in book.get('subjects', []):
                                    if subject and len(subject) < 50:
                                        external_genres.add(subject)

        # Combine genres (only if not using predefined mapping)
        if not (language and language in LANGUAGE_GENRE_MAPPING):
            available_genres.extend(list(external_genres))
            available_genres = list(set(available_genres))

        # Clean and sort
        available_genres = sorted([g for g in available_genres if g and len(g.strip()) > 0])
        available_creators = sorted([c for c in available_creators if c and len(c.strip()) > 0])

        return JsonResponse({
            'genres': available_genres,
            'creators': available_creators,
            'total_audiobooks': audiobooks_query.count(),
            'language_specific': language in LANGUAGE_GENRE_MAPPING if language else False
        })

    except Exception as e:
        logger.error(f"Error in get_filter_options: {str(e)}")
        return JsonResponse({
            'genres': LANGUAGE_GENRE_MAPPING.get(language, []) if language else [],
            'creators': [],
            'total_audiobooks': 0,
            'error': 'Failed to load filter options'
        })


def _matches_language_filter(book, language_filter):
    """Check if book matches language filter"""
    if not language_filter:
        return True

    book_language = book.get('language', 'English')
    if isinstance(book_language, list):
        return any(language_filter.lower() in str(lang).lower() for lang in book_language)
    else:
        return language_filter.lower() in str(book_language).lower()

# ==========================================
# MAIN VIEW FUNCTIONS
# ==========================================

def home(request):
    """Enhanced home page with better data organization"""
    context = _get_full_context(request)

    # Get cached audiobook data
    audiobook_data = cache.get(CACHE_KEY)
    librivox_audiobooks = []
    archive_genre_audiobooks = defaultdict(list)
    context["error_message"] = None

    # Collect external book slugs for database lookup
    all_external_slugs = set()
    if audiobook_data:
        for book_dict in audiobook_data.get("librivox_audiobooks", []):
            if book_dict.get('slug'):
                all_external_slugs.add(book_dict.get('slug'))

        for genre, book_list in audiobook_data.get("archive_genre_audiobooks", {}).items():
            for book_dict in book_list:
                if book_dict.get('slug'):
                    all_external_slugs.add(book_dict.get('slug'))

        for lang_key, book_list in audiobook_data.get("archive_language_audiobooks", {}).items():
            for book_dict in book_list:
                if book_dict.get('slug'):
                    all_external_slugs.add(book_dict.get('slug'))

    # Get database stats for external books
    db_book_stats = {}
    if all_external_slugs:
        db_instances = Audiobook.objects.filter(
            slug__in=list(all_external_slugs),
            is_creator_book=False
        )
        for db_book in db_instances:
            db_book_stats[db_book.slug] = {
                'total_views': db_book.total_views,
                'average_rating': db_book.average_rating,
                'author': db_book.author,
                'title': db_book.title,
                'cover_image': db_book.cover_image.url if db_book.cover_image else DEFAULT_COVER_IMAGE
            }

    # Process cached data
    if audiobook_data:
        # Process LibriVox books
        cached_librivox_books = audiobook_data.get("librivox_audiobooks", [])
        for book_data in cached_librivox_books:
            slug = book_data.get('slug')
            if slug and slug in db_book_stats:
                book_data.update(db_book_stats[slug])
            else:
                book_data.setdefault('total_views', 0)
                book_data.setdefault('average_rating', None)
                book_data.setdefault('cover_image', DEFAULT_COVER_IMAGE)
            librivox_audiobooks.append(book_data)

        # Process Archive.org genre books (English only)
        cached_archive_genres = audiobook_data.get("archive_genre_audiobooks", {})
        for genre, book_list in cached_archive_genres.items():
            english_books = []
            for book_data in book_list:
                lang = book_data.get('language', 'English')
                is_english = False

                if isinstance(lang, list):
                    is_english = any(str(l).lower().strip() in ['english', 'en', 'eng'] for l in lang)
                elif isinstance(lang, str):
                    is_english = lang.lower().strip() in ['english', 'en', 'eng']

                if is_english:
                    slug = book_data.get('slug')
                    if slug and slug in db_book_stats:
                        book_data.update(db_book_stats[slug])
                    else:
                        book_data.setdefault('total_views', 0)
                        book_data.setdefault('average_rating', None)
                        book_data.setdefault('cover_image', DEFAULT_COVER_IMAGE)
                    english_books.append(book_data)

            if english_books:
                archive_genre_audiobooks[genre].extend(english_books)
    else:
        context["error_message"] = "External audiobook listings are currently being updated. Please check back shortly."
        logger.warning("Audiobook data cache was empty")

    # Add platform books
    try:
        platform_books = Audiobook.objects.filter(
            status='PUBLISHED',
            creator__isnull=True,
            language__iexact='English'
        ).order_by('genre', '-publish_date')

        for book in platform_books:
            book_dict = {
                'slug': book.slug,
                'title': book.title,
                'author': book.author,
                'cover_image': book.cover_image.url if book.cover_image else DEFAULT_COVER_IMAGE,
                'average_rating': book.average_rating,
                'total_views': book.total_views,
                'is_paid': book.is_paid,
                'price': book.price,
                'creator': None,
            }

            if book.genre == 'Other':
                librivox_audiobooks.insert(0, book_dict)
            else:
                archive_genre_audiobooks[book.genre].insert(0, book_dict)

    except Exception as e:
        logger.error(f"Error fetching platform audiobooks: {e}", exc_info=True)

    # Get creator audiobooks
    try:
        creator_books = Audiobook.objects.filter(
            status='PUBLISHED',
            creator__isnull=False,
            language__iexact='English'
        ).select_related('creator').order_by('-publish_date')[:12]

        context["creator_audiobooks"] = list(creator_books)
    except Exception as e:
        logger.error(f"Error fetching creator audiobooks: {e}", exc_info=True)
        context["creator_audiobooks"] = []

    context["librivox_audiobooks"] = librivox_audiobooks
    context["archive_genre_audiobooks"] = dict(archive_genre_audiobooks)

    # Check if any content is available
    if (not context.get("creator_audiobooks") and
        not context.get("librivox_audiobooks") and
        not context.get("archive_genre_audiobooks") and
        not context.get("error_message")):
        context["error_message"] = "No English audiobooks are currently available."

    return render(request, "audiobooks/English/English_Home.html", context)


def audiobook_detail(request, audiobook_slug):
    """Enhanced audiobook detail view with improved security and performance"""
    if not request.user.is_authenticated:
        login_url = reverse('AudioXApp:login')
        current_url = request.get_full_path()
        return redirect(f"{login_url}?next={current_url}")

    context = _get_full_context(request)
    audiobook_obj = None
    found_external_book_dict = None

    try:
        # Get audiobook with optimized queries
        audiobook_obj = Audiobook.objects.prefetch_related(
            Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order')),
            'reviews__user'
        ).select_related('creator').get(slug=audiobook_slug)

        # Handle external audiobooks
        if not audiobook_obj.is_creator_book:
            external_data = cache.get(CACHE_KEY)
            if external_data:
                found_external_book_dict = _find_external_book(external_data, audiobook_slug)

                if found_external_book_dict:
                    _sync_external_chapters(audiobook_obj, found_external_book_dict)
                    # Refresh audiobook object
                    audiobook_obj = Audiobook.objects.prefetch_related(
                        Prefetch('chapters', queryset=Chapter.objects.order_by('chapter_order')),
                        'reviews__user'
                    ).select_related('creator').get(slug=audiobook_slug)

    except Audiobook.DoesNotExist:
        # Try to create from external data
        audiobook_obj = _create_from_external_data(audiobook_slug)
        if not audiobook_obj:
            messages.error(request, "Audiobook not found.")
            raise Http404("Audiobook not found.")

    except Exception as e:
        logger.error(f"Error fetching audiobook {audiobook_slug}: {e}", exc_info=True)
        messages.error(request, "An error occurred while loading this audiobook.")
        raise Http404("Failed to load audiobook.")

    # Record view
    _record_audiobook_view(request.user, audiobook_obj)

    # Check purchase status
    user_has_purchased = False
    if (audiobook_obj.is_creator_book and audiobook_obj.is_paid and
        request.user.is_authenticated):
        user_has_purchased = request.user.has_purchased_audiobook(audiobook_obj)

    is_in_library = False
    if request.user.is_authenticated:
        is_in_library = request.user.library_audiobooks.filter(pk=audiobook_obj.pk).exists()

    # Process chapters
    chapters_to_display = []
    audiobook_lock_message = None

    for i, chapter in enumerate(audiobook_obj.chapters.all()):
        is_accessible, lock_reason = get_chapter_accessibility(chapter, audiobook_obj, request.user, i)

        if (audiobook_obj.is_creator_book and audiobook_obj.is_paid and
            not user_has_purchased and not is_accessible):
            audiobook_lock_message = f"This is a premium audiobook. Purchase for PKR {audiobook_obj.price} to unlock all chapters."

        chapters_to_display.append({
            'chapter_title': chapter.chapter_name,
            'audio_url_template': chapter.get_streaming_url(),
            'is_accessible': is_accessible,
            'lock_reason': lock_reason,
            'duration_seconds': chapter.duration_seconds,
            'chapter_index': i,
            'chapter_id': chapter.pk,
            'unlock_cost': CHAPTER_UNLOCK_COST, # NEW: Add unlock cost
        })

    # Get listening history
    listening_history_data = {}
    if request.user.is_authenticated:
        history_records = ListeningHistory.objects.filter(
            user=request.user,
            chapter__audiobook=audiobook_obj
        ).select_related('chapter')

        for record in history_records:
            listening_history_data[str(record.chapter.pk)] = {
                'position': record.last_position_seconds,
                'completed': record.is_completed
            }

    # Get reviews
    reviews = audiobook_obj.reviews.select_related('user').order_by('-created_at')
    user_review = None
    if request.user.is_authenticated:
        user_review = reviews.filter(user=request.user).first()
    
    # ✅ NEW: Determine if user can review
    can_user_review = False
    if request.user.is_authenticated:
        if not audiobook_obj.is_paid:
            can_user_review = True
        elif audiobook_obj.is_paid and user_has_purchased:
            can_user_review = True
        # Note: This logic could be expanded (e.g., allow reviews for external books always)
        # but for now, it mirrors the check in the `add_review` view.


    # Get recommendations
    recommended_audiobooks = _get_recommendations(audiobook_obj, max_count=5)

    # ✅ NEW: Prepare context data for JavaScript (renamed from page_context)
    page_context_data_dict = {
        "isAuthenticated": request.user.is_authenticated,
        "csrfToken": get_token(request),
        "audiobookId": str(audiobook_obj.audiobook_id) if audiobook_obj.audiobook_id else None,
        "audiobookSlug": audiobook_obj.slug,
        "audiobookTitle": audiobook_obj.title,
        "addReviewUrl": reverse('AudioXApp:add_review', kwargs={'audiobook_slug': audiobook_obj.slug}),
        "addToLibraryApiUrl": reverse('AudioXApp:toggle_library_item'),
        "myLibraryUrl": reverse('AudioXApp:my_library_page'),
        "loginUrl": f"{reverse('AudioXApp:login')}?next={request.path}",
        "getAiSummaryUrl": reverse('AudioXApp:get_ai_summary', kwargs={'audiobook_id': audiobook_obj.audiobook_id or 0}),
        "updateListeningProgressUrl": reverse('AudioXApp:update_listening_progress'),
        "audiobookAuthor": audiobook_obj.author,
        "audiobookLanguage": audiobook_obj.language,
        "audiobookGenre": audiobook_obj.genre,
        "isCreatorBook": audiobook_obj.is_creator_book,
        "generateAudioClipUrl": reverse('AudioXApp:generate_audio_clip'),
        "stripePublishableKey": getattr(settings, 'STRIPE_PUBLISHABLE_KEY', None),
        "createCheckoutSessionUrl": reverse('AudioXApp:create_checkout_session') if audiobook_obj.is_creator_book and audiobook_obj.is_paid else None,
        "audiobookPrice": str(audiobook_obj.price) if audiobook_obj.is_paid else "0.00",
        "maxAudioClipDurationSeconds": getattr(settings, 'MAX_AUDIO_CLIP_DURATION_SECONDS', 300),
        "userId": str(request.user.user_id) if request.user.is_authenticated else None,
        "userFullName": request.user.full_name or request.user.username if request.user.is_authenticated else None,
        "userProfilePicUrl": request.user.profile_pic.url if (request.user.is_authenticated and
                                                                hasattr(request.user, 'profile_pic') and
                                                                request.user.profile_pic) else None,
        "current_user_has_reviewed": bool(user_review),
        "user_review_object": {
            'rating': user_review.rating,
            'comment': user_review.comment
        } if user_review else None,
        "checkCoinEligibilityUrl": reverse('AudioXApp:check_coin_purchase_eligibility', kwargs={'audiobook_slug': audiobook_obj.slug}),
        "purchaseWithCoinsUrl": reverse('AudioXApp:purchase_audiobook_with_coins'),
        "recordVisitUrl": reverse('AudioXApp:record_audiobook_visit'),
        "buyCoinsUrl": reverse('AudioXApp:buycoins'),
        "userSubscriptionType": request.user.subscription_type if request.user.is_authenticated else "FR",
        "subscriptionUrl": reverse('AudioXApp:subscribe'),
        "unlockChapterUrl": reverse('AudioXApp:unlock_chapter_with_coins'),
        "is_in_library": is_in_library,
    }

    # Prepare audiobook data for display
    if audiobook_obj.is_creator_book:
        audiobook_data_for_display = audiobook_obj
    else:
        audiobook_data_for_display = {
            'title': audiobook_obj.title,
            'author': audiobook_obj.author,
            'description': audiobook_obj.description,
            'language': audiobook_obj.language,
            'genre': audiobook_obj.genre,
            'source': audiobook_obj.source,
            'is_creator_book': False,
            'total_views': audiobook_obj.total_views,
            'average_rating': audiobook_obj.average_rating,
            'is_paid': audiobook_obj.is_paid,
            'price': audiobook_obj.price,
            'cover_image': (audiobook_obj.cover_image.url if audiobook_obj.cover_image
                            else (found_external_book_dict.get('cover_image') if found_external_book_dict else DEFAULT_COVER_IMAGE))
        }

    # Update context
    context.update({
        'audiobook': audiobook_obj,
        'audiobook_data_for_display': audiobook_data_for_display,
        'is_creator_book_page': audiobook_obj.is_creator_book,
        'reviews': reviews,
        'user_review_object': user_review,
        'current_user_has_reviewed': bool(user_review),
        'user_has_purchased': user_has_purchased,
        'chapters_to_display': chapters_to_display,
        'audiobook_lock_message': audiobook_lock_message,
        'recommended_audiobooks': recommended_audiobooks,
        'listening_history_json': json.dumps(listening_history_data),
        # ✅ NEW CONTEXT VARIABLES ADDED HERE
        'page_context_data_dict': json.dumps(page_context_data_dict),
        'can_user_review': can_user_review,
        'is_in_library': is_in_library,
    })

    return render(request, 'audiobook_detail.html', context)


def trending_audiobooks_view(request):
    """Display trending audiobooks"""
    context = _get_full_context(request)

    try:
        trending_books = Audiobook.objects.filter(
            status='PUBLISHED'
        ).select_related('creator').order_by('-total_views')[:10]

        context["trending_audiobooks"] = list(trending_books)

        if not context["trending_audiobooks"]:
            context["error_message"] = "No trending audiobooks found at the moment. Check back later!"

    except Exception as e:
        logger.error(f"Error fetching trending audiobooks: {e}", exc_info=True)
        context["error_message"] = "Could not load trending audiobooks due to a server error."
        context["trending_audiobooks"] = []

    return render(request, "audiobooks/trending_audiobooks.html", context)

# ==========================================
# HELPER FUNCTIONS FOR AUDIOBOOK DETAIL
# ==========================================

def _find_external_book(external_data, audiobook_slug):
    """Find external book data by slug"""
    for source_key in ["librivox_audiobooks", "archive_genre_audiobooks", "archive_language_audiobooks"]:
        if source_key in ["archive_genre_audiobooks", "archive_language_audiobooks"]:
            for _, book_list in external_data.get(source_key, {}).items():
                for book_dict in book_list:
                    if book_dict.get('slug') == audiobook_slug:
                        return book_dict
        else:
            for book_dict in external_data.get(source_key, []):
                if book_dict.get('slug') == audiobook_slug:
                    return book_dict
    return None


def _sync_external_chapters(audiobook_obj, external_book_dict):
    """Sync external book chapters with database"""
    with transaction.atomic():
        for i, ch_info in enumerate(external_book_dict.get('chapters', [])):
            external_identifier = f"ext-{audiobook_obj.slug}-{i}"

            Chapter.objects.update_or_create(
                audiobook=audiobook_obj,
                chapter_order=i,
                defaults={
                    'chapter_name': ch_info.get('chapter_title', f"Chapter {i+1}"),
                    'external_audio_url': ch_info.get('audio_url'),
                    'duration_seconds': ch_info.get('duration_seconds', 0),
                    'is_preview_eligible': True,
                    'external_chapter_identifier': external_identifier
                }
            )


def _create_from_external_data(audiobook_slug):
    """Create audiobook from external data if not found in database"""
    external_data = cache.get(CACHE_KEY)
    if not external_data:
        return None

    found_external_book_dict = _find_external_book(external_data, audiobook_slug)
    if not found_external_book_dict:
        return None

    try:
        with transaction.atomic():
            audiobook_obj = Audiobook.objects.create(
                slug=audiobook_slug,
                title=found_external_book_dict.get('title', 'Unknown Title'),
                author=found_external_book_dict.get('author'),
                description=found_external_book_dict.get('description', "No description provided."),
                language=found_external_book_dict.get('language'),
                genre=found_external_book_dict.get('genre'),
                source=found_external_book_dict.get('source', 'archive'),
                is_creator_book=False,
                creator=None,
                is_paid=False,
                price=Decimal('0.00'),
                status='PUBLISHED'
            )

            _sync_external_chapters(audiobook_obj, found_external_book_dict)

            logger.info(f"Created new audiobook from external data: {audiobook_slug}")
            return audiobook_obj

    except Exception as e:
        logger.error(f"Error creating audiobook from external data: {e}", exc_info=True)
        return None


def _record_audiobook_view(user, audiobook_obj):
    """Record audiobook view with rate limiting"""
    current_user = user if user.is_authenticated else None
    should_count_view = True

    if current_user:
        twenty_four_hours_ago = timezone.now() - timezone.timedelta(hours=24)
        recent_view_exists = AudiobookViewLog.objects.filter(
            audiobook=audiobook_obj,
            user=current_user,
            viewed_at__gte=twenty_four_hours_ago
        ).exists()

        if recent_view_exists:
            should_count_view = False

    if should_count_view:
        with transaction.atomic():
            AudiobookViewLog.objects.create(audiobook=audiobook_obj, user=current_user)
            Audiobook.objects.filter(pk=audiobook_obj.pk).update(total_views=F('total_views') + 1)
            audiobook_obj.refresh_from_db(fields=['total_views'])


def _get_recommendations(audiobook_obj, max_count=5):
    """Get recommended audiobooks based on current audiobook"""
    recommended_audiobooks = []
    seen_slugs = {audiobook_obj.slug}

    # Get database recommendations
    if audiobook_obj.language:
        db_query = Audiobook.objects.filter(
            status='PUBLISHED',
            is_creator_book=True,
            language__iexact=audiobook_obj.language
        ).exclude(slug__in=list(seen_slugs)).annotate(
            calculated_average_rating=Avg('reviews__rating')
        )

        # Prefer same genre
        if audiobook_obj.genre and audiobook_obj.genre != 'Other':
            genre_recs = list(db_query.filter(
                genre__iexact=audiobook_obj.genre
            ).order_by('-calculated_average_rating', '?')[:max_count])

            for rec in genre_recs:
                if rec.slug not in seen_slugs and len(recommended_audiobooks) < max_count:
                    recommended_audiobooks.append(rec)
                    seen_slugs.add(rec.slug)

        # Fill remaining slots with other books in same language
        if len(recommended_audiobooks) < max_count:
            exclude_q = Q()
            if audiobook_obj.genre and audiobook_obj.genre != 'Other':
                exclude_q = Q(genre__iexact=audiobook_obj.genre)

            other_recs = list(db_query.exclude(exclude_q).order_by(
                '-calculated_average_rating', '?'
            )[:max_count - len(recommended_audiobooks)])

            for rec in other_recs:
                if rec.slug not in seen_slugs and len(recommended_audiobooks) < max_count:
                    recommended_audiobooks.append(rec)
                    seen_slugs.add(rec.slug)

    # Add external recommendations if needed
    if len(recommended_audiobooks) < max_count:
        external_data = cache.get(CACHE_KEY)
        if external_data:
            potential_external_recs = []

            # Get external books from same language
            for book_dict in external_data.get("librivox_audiobooks", []):
                if (book_dict.get('slug') != audiobook_obj.slug and
                    book_dict.get('slug') not in seen_slugs and
                    _matches_language_filter(book_dict, audiobook_obj.language)):
                    potential_external_recs.append(book_dict)

            for term_key, term_books in external_data.get("archive_genre_audiobooks", {}).items():
                for book_dict in term_books:
                    if (book_dict.get('slug') != audiobook_obj.slug and
                        book_dict.get('slug') not in seen_slugs and
                        _matches_language_filter(book_dict, audiobook_obj.language)):
                        potential_external_recs.append(book_dict)

            for lang_key, lang_books in external_data.get("archive_language_audiobooks", {}).items():
                for book_dict in lang_books:
                    if (book_dict.get('slug') != audiobook_obj.slug and
                        book_dict.get('slug') not in seen_slugs and
                        audiobook_obj.language and audiobook_obj.language.lower() == lang_key.lower()):
                        potential_external_recs.append(book_dict)

            # Prioritize by genre match
            genre_matches = []
            other_matches = []

            for book_dict in potential_external_recs:
                book_genre = book_dict.get('genre', '')
                book_subjects = book_dict.get('subjects', [])

                genre_match = False
                if audiobook_obj.genre:
                    if book_genre and audiobook_obj.genre.lower() in book_genre.lower():
                        genre_match = True
                    elif any(audiobook_obj.genre.lower() in str(subject).lower() for subject in book_subjects):
                        genre_match = True

                if genre_match:
                    genre_matches.append(book_dict)
                else:
                    other_matches.append(book_dict)

            # Randomize and combine
            random.shuffle(genre_matches)
            random.shuffle(other_matches)
            sorted_external_recs = genre_matches + other_matches

            # Add to recommendations
            for book_dict in sorted_external_recs:
                if len(recommended_audiobooks) >= max_count:
                    break

                ext_slug = book_dict.get('slug')
                if ext_slug and ext_slug not in seen_slugs:
                    try:
                        # Create or get shell audiobook
                        shell_audiobook, _ = Audiobook.objects.get_or_create(
                            slug=ext_slug,
                            defaults={
                                'title': book_dict.get('title', 'Unknown Title'),
                                'author': book_dict.get('author'),
                                'description': book_dict.get('description', "No description provided."),
                                'language': book_dict.get('language'),
                                'genre': book_dict.get('genre'),
                                'source': book_dict.get('source', 'archive'),
                                'is_creator_book': False,
                                'creator': None,
                                'is_paid': False,
                                'price': Decimal('0.00'),
                                'status': 'PUBLISHED'
                            }
                        )

                        # Update book dict with database values
                        book_dict['average_rating'] = shell_audiobook.average_rating
                        book_dict['total_views'] = shell_audiobook.total_views
                        if shell_audiobook.cover_image:
                            book_dict['cover_image'] = shell_audiobook.cover_image.url
                        else:
                            book_dict['cover_image'] = DEFAULT_COVER_IMAGE

                    except Exception as e:
                        logger.error(f"Error creating recommendation shell: {e}")
                        book_dict['average_rating'] = None
                        book_dict['total_views'] = 0
                        book_dict['cover_image'] = DEFAULT_COVER_IMAGE

                    # Ensure creator field format
                    if 'author' in book_dict and 'creator' not in book_dict:
                        book_dict['creator'] = {'creator_name': book_dict['author']}
                    elif 'creator' in book_dict and isinstance(book_dict['creator'], str):
                        book_dict['creator'] = {'creator_name': book_dict['creator']}

                    recommended_audiobooks.append(book_dict)
                    seen_slugs.add(ext_slug)

    return recommended_audiobooks

# ==========================================
# LANGUAGE AND GENRE PAGES
# ==========================================

def _render_genre_or_language_page(request, page_type, display_name, template_name,
                                 cache_key_segment, query_term, language_for_genre_page=None):
    """Unified function for rendering genre and language pages"""
    context = _get_full_context(request)
    current_page_language = language_for_genre_page or (query_term if page_type == "language" else "English")

    context.update({
        "display_name": display_name,
        "page_language": current_page_language,
        "page_genre": query_term if page_type == "genre" else None
    })

    processed_external_books = []

    # Get external audiobook data
    external_data = cache.get(CACHE_KEY)
    cached_books = []

    if external_data:
        source_dict = external_data.get(cache_key_segment, {})

        if page_type == "language":
            cached_books = source_dict.get(query_term, [])
        elif page_type == "genre":
            if language_for_genre_page:
                # Filter by genre within language
                books_in_language = source_dict.get(language_for_genre_page, [])
                for book in books_in_language:
                    book_subjects = book.get('subjects', [])
                    book_genre = (book.get('genre') or "").lower()

                    if isinstance(book_subjects, str):
                        book_subjects = [s.strip() for s in book_subjects.split(';')]

                    genre_match = query_term.lower() in book_genre
                    if not genre_match and isinstance(book_subjects, list):
                        genre_match = any(
                            query_term.lower() in str(subject).lower()
                            for subject in book_subjects
                        )

                    if genre_match:
                        cached_books.append(book)
            else:
                cached_books = source_dict.get(query_term, [])

    # Get database stats for external books
    external_slugs = {book.get('slug') for book in cached_books if book.get('slug')}
    db_stats = {}

    if external_slugs:
        db_instances = Audiobook.objects.filter(
            slug__in=list(external_slugs),
            is_creator_book=False
        )
        for db_book in db_instances:
            db_stats[db_book.slug] = {
                'total_views': db_book.total_views,
                'average_rating': db_book.average_rating,
                'author': db_book.author,
                'title': db_book.title,
                'cover_image': db_book.cover_image.url if db_book.cover_image else DEFAULT_COVER_IMAGE
            }

    # Process external books
    for book_data in cached_books:
        slug = book_data.get('slug')
        if slug and slug in db_stats:
            book_data.update(db_stats[slug])
        else:
            book_data.setdefault('total_views', 0)
            book_data.setdefault('average_rating', None)
            book_data.setdefault('cover_image', DEFAULT_COVER_IMAGE)
        processed_external_books.append(book_data)

    # Add platform books
    try:
        platform_query = Audiobook.objects.filter(
            status='PUBLISHED',
            creator__isnull=True
        )

        if page_type == "language":
            platform_query = platform_query.filter(language__iexact=current_page_language)
        elif page_type == "genre":
            platform_query = platform_query.filter(
                language__iexact=current_page_language,
                genre__iexact=query_term
            )

        platform_books = platform_query.order_by('-publish_date')

        for book in platform_books:
            processed_external_books.insert(0, {
                'slug': book.slug,
                'title': book.title,
                'author': book.author,
                'cover_image': book.cover_image.url if book.cover_image else DEFAULT_COVER_IMAGE,
                'average_rating': book.average_rating,
                'total_views': book.total_views,
                'is_paid': book.is_paid,
                'price': book.price,
                'creator': None,
            })

    except Exception as e:
        logger.error(f"Error fetching platform books for {display_name}: {e}", exc_info=True)

    context["audiobooks_list"] = processed_external_books

    # Get creator audiobooks
    try:
        creator_query = Audiobook.objects.filter(
            status='PUBLISHED',
            creator__isnull=False
        )

        if page_type == "genre":
            creator_query = creator_query.filter(
                language__iexact=current_page_language,
                genre__iexact=query_term
            )
        elif page_type == "language":
            creator_query = creator_query.filter(language__iexact=current_page_language)

        context["creator_audiobooks"] = list(
            creator_query.select_related('creator').order_by('-publish_date')
        )

    except Exception as e:
        logger.error(f"Error fetching creator audiobooks for {display_name}: {e}", exc_info=True)
        context["creator_audiobooks"] = []

    # Set error message if no content
    if not context.get("creator_audiobooks") and not processed_external_books:
        context["error_message"] = f"فی الحال '{display_name}' کے لیے کوئی آڈیو کتابیں دستیاب نہیں ہیں۔"

    return render(request, template_name, context)

# Genre page views
def genre_fiction(request):
    return _render_genre_or_language_page(
        request, "genre", "Fiction", 'audiobooks/English/genrefiction.html',
        "archive_genre_audiobooks", "Fiction"
    )

def genre_mystery(request):
    return _render_genre_or_language_page(
        request, "genre", "Mystery", 'audiobooks/English/genremystery.html',
        "archive_genre_audiobooks", "Mystery"
    )

def genre_thriller(request):
    return _render_genre_or_language_page(
        request, "genre", "Thriller", 'audiobooks/English/genrethriller.html',
        "archive_genre_audiobooks", "Thriller"
    )

def genre_scifi(request):
    return _render_genre_or_language_page(
        request, "genre", "Science Fiction", 'audiobooks/English/genrescifi.html',
        "archive_genre_audiobooks", "Science Fiction"
    )

def genre_fantasy(request):
    return _render_genre_or_language_page(
        request, "genre", "Fantasy", 'audiobooks/English/genrefantasy.html',
        "archive_genre_audiobooks", "Fantasy"
    )

def genre_romance(request):
    return _render_genre_or_language_page(
        request, "genre", "Romance", 'audiobooks/English/genreromance.html',
        "archive_genre_audiobooks", "Romance"
    )

def genre_biography(request):
    return _render_genre_or_language_page(
        request, "genre", "Biography", 'audiobooks/English/genrebiography.html',
        "archive_genre_audiobooks", "Biography"
    )

def genre_history(request):
    return _render_genre_or_language_page(
        request, "genre", "History", 'audiobooks/English/genrehistory.html',
        "archive_genre_audiobooks", "History"
    )

def genre_selfhelp(request):
    return _render_genre_or_language_page(
        request, "genre", "Self-Help", 'audiobooks/English/genreselfhelp.html',
        "archive_genre_audiobooks", "Self-Help"
    )

def genre_business(request):
    return _render_genre_or_language_page(
        request, "genre", "Business", 'audiobooks/English/genrebusiness.html',
        "archive_genre_audiobooks", "Business"
    )

# Language page views
def urdu_page(request):
    return _render_genre_or_language_page(
        request, "language", "Urdu", 'audiobooks/Urdu/Urdu_Home.html',
        "archive_language_audiobooks", "Urdu"
    )

def punjabi_page(request):
    return _render_genre_or_language_page(
        request, "language", "Punjabi", 'audiobooks/Punjabi/Punjabi_Home.html',
        "archive_language_audiobooks", "Punjabi"
    )

def sindhi_page(request):
    return _render_genre_or_language_page(
        request, "language", "Sindhi", 'audiobooks/Sindhi/Sindhi_Home.html',
        "archive_language_audiobooks", "Sindhi"
    )

# Urdu genre pages
def urdu_genre_novel_afsana(request):
    return _render_genre_or_language_page(
        request, "genre", "Urdu Novel & Afsana", 'audiobooks/Urdu/genre_novel_afsana.html',
        "archive_language_audiobooks", "Novel Afsana", language_for_genre_page="Urdu"
    )

def urdu_genre_shayari(request):
    return _render_genre_or_language_page(
        request, "genre", "Urdu Shayari", 'audiobooks/Urdu/genre_shayari.html',
        "archive_language_audiobooks", "Shayari", language_for_genre_page="Urdu"
    )

def urdu_genre_tareekh(request):
    return _render_genre_or_language_page(
        request, "genre", "Urdu Tareekh", 'audiobooks/Urdu/genre_tareekh.html',
        "archive_language_audiobooks", "Tareekh", language_for_genre_page="Urdu"
    )

def urdu_genre_safarnama(request):
    return _render_genre_or_language_page(
        request, "genre", "Urdu Safarnama", 'audiobooks/Urdu/genre_safarnama.html',
        "archive_language_audiobooks", "Safarnama", language_for_genre_page="Urdu"
    )

def urdu_genre_mazah(request):
    return _render_genre_or_language_page(
        request, "genre", "Urdu Mazah", 'audiobooks/Urdu/genre_mazah.html',
        "archive_language_audiobooks", "Mazah", language_for_genre_page="Urdu"
    )

def urdu_genre_bachon_ka_adab(request):
    return _render_genre_or_language_page(
        request, "genre", "Urdu Bachon ka Adab", 'audiobooks/Urdu/genre_bachon_ka_adab.html',
        "archive_language_audiobooks", "Bachon ka Adab", language_for_genre_page="Urdu"
    )

def urdu_genre_mazhabi_adab(request):
    return _render_genre_or_language_page(
        request, "genre", "Urdu Mazhabi Adab", 'audiobooks/Urdu/genre_mazhabi_adab.html',
        "archive_language_audiobooks", "Mazhabi Adab", language_for_genre_page="Urdu"
    )

# Punjabi genre pages
def punjabi_genre_qissalok(request):
    return _render_genre_or_language_page(
        request, "genre", "Punjabi Qissa Lok", 'audiobooks/Punjabi/genre_qissalok.html',
        "archive_language_audiobooks", "Qissalok", language_for_genre_page="Punjabi"
    )

def punjabi_genre_geet(request):
    return _render_genre_or_language_page(
        request, "genre", "Punjabi Geet", 'audiobooks/Punjabi/genre_geet.html',
        "archive_language_audiobooks", "Geet", language_for_genre_page="Punjabi"
    )

# Sindhi genre pages
def sindhi_genre_lok_adab(request):
    return _render_genre_or_language_page(
        request, "genre", "Sindhi Lok Adab", 'audiobooks/Sindhi/genre_lok_adab.html',
        "archive_language_audiobooks", "Lok Adab", language_for_genre_page="Sindhi"
    )

def sindhi_genre_shayari(request):
    return _render_genre_or_language_page(
        request, "genre", "Sindhi Shayari", 'audiobooks/Sindhi/genre_shayari.html',
        "archive_language_audiobooks", "Shayari", language_for_genre_page="Sindhi"
    )

# ==========================================
# REVIEW AND INTERACTION VIEWS
# ==========================================

@login_required
@require_POST
@csrf_protect
def add_review(request, audiobook_slug):
    """Add or update audiobook review"""
    try:
        audiobook = get_object_or_404(Audiobook, slug=audiobook_slug)

        # Check if user can review
        can_review = False
        if not audiobook.is_paid:
            can_review = True
        elif audiobook.is_paid and audiobook.is_creator_book:
            if request.user.is_authenticated and hasattr(request.user, 'has_purchased_audiobook'):
                can_review = request.user.has_purchased_audiobook(audiobook)
        else:
            can_review = True

        if not can_review:
            return JsonResponse({
                'status': 'error',
                'message': 'You must purchase this audiobook to leave a review.'
            }, status=403)

        # Parse request data
        try:
            data = json.loads(request.body)
            rating_str = data.get('rating')
            comment = data.get('comment', '').strip()
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON format in request body.'
            }, status=400)

        # Validate rating
        try:
            rating = int(rating_str)
            if not 1 <= rating <= 5:
                raise ValueError("Rating must be between 1 and 5.")
        except (ValueError, TypeError):
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid rating value. Please provide a number between 1 and 5.'
            }, status=400)

        # Create or update review
        with transaction.atomic():
            review, created = Review.objects.update_or_create(
                audiobook=audiobook,
                user=request.user,
                defaults={'rating': rating, 'comment': comment}
            )

        audiobook.refresh_from_db()
        new_average_rating = audiobook.average_rating
        message = "Review updated successfully!" if not created else "Review added successfully!"

        # Prepare user profile pic URL
        user_profile_pic_url = None
        if hasattr(review.user, 'profile_pic') and review.user.profile_pic:
            try:
                user_profile_pic_url = review.user.profile_pic.url
            except ValueError:
                pass

        # Prepare review data
        review_data = {
            'review_id': review.review_id,
            'rating': review.rating,
            'comment': review.comment or "",
            'user_id': review.user.user_id,
            'user_name': review.user.full_name or review.user.username,
            'user_profile_pic': user_profile_pic_url,
            'created_at': review.created_at.isoformat(),
            'timesince': timesince(review.created_at) + " ago"
        }

        return JsonResponse({
            'status': 'success',
            'message': message,
            'created': created,
            'new_average_rating': str(new_average_rating) if new_average_rating is not None else "0.0",
            'review_data': review_data
        })

    except Audiobook.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Audiobook not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error in add_review for {audiobook_slug}: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': 'An unexpected server error occurred. Please try again.'
        }, status=500)


# ✅ NEW VIEW ADDED TO HANDLE CHAPTER UNLOCKING
@login_required
@require_POST
@csrf_protect
def unlock_chapter_with_coins(request):
    """Unlock a single chapter for a FREE user using coins."""
    try:
        data = json.loads(request.body)
        chapter_id = data.get('chapter_id')

        if not chapter_id:
            return JsonResponse({'status': 'error', 'message': 'Chapter ID is required.'}, status=400)

        chapter_to_unlock = get_object_or_404(Chapter, pk=chapter_id)
        user = request.user

        # Security Checks
        if user.subscription_type != 'FR':
            return JsonResponse({'status': 'error', 'message': 'This feature is only for free-tier users.'}, status=403)
        
        if chapter_to_unlock.audiobook.is_paid:
            return JsonResponse({'status': 'error', 'message': 'This chapter belongs to a paid audiobook and cannot be unlocked with coins.'}, status=403)

        if ChapterUnlock.objects.filter(user=user, chapter=chapter_to_unlock).exists():
            return JsonResponse({'status': 'success', 'message': 'Chapter already unlocked.'})

        # Transaction Logic
        with transaction.atomic():
            # Re-fetch user with select_for_update to prevent race conditions
            user_for_update = User.objects.select_for_update().get(pk=user.pk)
            
            if user_for_update.coins < CHAPTER_UNLOCK_COST:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Insufficient coins.'
                }, status=400)
            
            user_for_update.coins -= CHAPTER_UNLOCK_COST
            user_for_update.save()
            
            ChapterUnlock.objects.create(user=user_for_update, chapter=chapter_to_unlock)
        
        return JsonResponse({
            'status': 'success',
            'message': 'Chapter unlocked successfully!',
            'new_coin_balance': user.coins
        })

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid request format.'}, status=400)
    except Chapter.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Chapter not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error unlocking chapter with coins for user {request.user.pk}: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An internal error occurred.'}, status=500)


# ==========================================
# STREAMING AND MEDIA VIEWS
# ==========================================

@require_GET
def stream_audio(request):
    """Stream audio with enhanced security and access control"""
    audio_url_param = request.GET.get("url")
    if not audio_url_param:
        return JsonResponse({"error": "No audio URL provided"}, status=400)

    # Security check for paid audiobook chapters
    chapter_id = request.GET.get("chapter_id")
    audiobook_slug = request.GET.get("audiobook_slug")

    if chapter_id and audiobook_slug:
        try:
            chapter = get_object_or_404(Chapter, pk=chapter_id)
            audiobook = chapter.audiobook

            # Verify audiobook slug matches
            if audiobook.slug != audiobook_slug:
                logger.warning(f"Audiobook slug mismatch in stream_audio: expected {audiobook.slug}, got {audiobook_slug}")
                return JsonResponse({"error": "Invalid audiobook reference"}, status=400)
            
            # ✅ NEW: ADDED SECURITY CHECK using get_chapter_accessibility
            # Determine chapter index for accessibility check
            try:
                # This is an approximation, for perfect accuracy an ordered list is needed.
                chapter_index = list(audiobook.chapters.order_by('chapter_order').values_list('pk', flat=True)).index(chapter.pk)
            except (ValueError, Chapter.DoesNotExist):
                chapter_index = 0 # Fallback for safety

            is_accessible, reason = get_chapter_accessibility(chapter, audiobook, request.user, chapter_index)

            if not is_accessible:
                logger.warning(f"Unauthorized stream attempt for chapter {chapter_id} by user {request.user.pk if request.user.is_authenticated else 'Anonymous'}. Reason: {reason}")
                return JsonResponse({"error": "Access Denied", "message": "You do not have permission to stream this chapter."}, status=403)
            # END OF NEW SECURITY CHECK


            # Check access for paid creator audiobooks (This block is now partially redundant but kept for safety)
            if audiobook.is_creator_book and audiobook.is_paid:
                if not request.user.is_authenticated:
                    return JsonResponse({"error": "Authentication required for paid content"}, status=401)

                user_has_purchased = request.user.has_purchased_audiobook(audiobook)
                is_preview_chapter = chapter.is_preview_eligible or (chapter.chapter_order < FREE_PREVIEW_CHAPTERS)

                if not user_has_purchased and not is_preview_chapter:
                    logger.warning(f"Unauthorized access attempt to paid chapter {chapter_id} by user {request.user.pk}")
                    return JsonResponse({
                        "error": "Purchase required",
                        "message": f"This audiobook costs PKR {audiobook.price}. Please purchase to access this chapter.",
                        "audiobook_slug": audiobook.slug,
                        "is_paid": True,
                        "price": str(audiobook.price)
                    }, status=403)

                logger.info(f"Authorized access to paid chapter {chapter_id} by user {request.user.pk}")

        except Chapter.DoesNotExist:
            logger.error(f"Chapter {chapter_id} not found in stream_audio")
            return JsonResponse({"error": "Chapter not found"}, status=404)
        except Exception as e:
            logger.error(f"Error checking access permissions in stream_audio: {e}", exc_info=True)
            return JsonResponse({"error": "Access verification failed"}, status=500)

    target_audio_url = audio_url_param
    parsed_url = urlparse(target_audio_url)
    is_local_media = False

    # Check if it's a local media file
    if target_audio_url.startswith(settings.MEDIA_URL):
        if not parsed_url.scheme and not parsed_url.netloc:
            is_local_media = True

    if is_local_media:
        # Handle local media files
        try:
            relative_path = target_audio_url[len(settings.MEDIA_URL):] if target_audio_url.startswith(settings.MEDIA_URL) else target_audio_url
            file_path = os.path.join(settings.MEDIA_ROOT, relative_path)

            if not os.path.exists(file_path) or os.path.isdir(file_path):
                logger.error(f"Local audio file not found: {file_path}")
                return HttpResponse("Audio file not found.", status=404)

            file_size = os.path.getsize(file_path)
            content_type = mimetypes.guess_type(file_path)[0] or 'audio/mpeg'

            # Handle range requests for seeking
            range_header = request.headers.get('Range')
            if range_header:
                range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
                if range_match:
                    start = int(range_match.group(1))
                    end = int(range_match.group(2)) if range_match.group(2) else file_size - 1

                    if start >= file_size:
                        return HttpResponse("Requested range not satisfiable", status=416)

                    end = min(end, file_size - 1)
                    content_length = end - start + 1

                    def file_iterator():
                        with open(file_path, 'rb') as f:
                            f.seek(start)
                            remaining = content_length
                            while remaining > 0:
                                chunk_size = min(8192, remaining)
                                chunk = f.read(chunk_size)
                                if not chunk:
                                    break
                                remaining -= len(chunk)
                                yield chunk

                    response = StreamingHttpResponse(file_iterator(), content_type=content_type, status=206)
                    response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
                    response['Content-Length'] = str(content_length)
                    response['Accept-Ranges'] = 'bytes'

                    logger.info(f"Streaming local file with range: {file_path} (bytes {start}-{end})")
                    return response

            # Stream entire file
            logger.info(f"Streaming local file: {file_path}")
            response = FileResponse(open(file_path, 'rb'), content_type=content_type)
            response['Accept-Ranges'] = 'bytes'
            response['Content-Length'] = str(file_size)
            return response

        except Exception as e:
            logger.error(f"Error streaming local audio file {target_audio_url}: {e}", exc_info=True)
            return HttpResponse("Error streaming local audio file.", status=500)

    elif not all([parsed_url.scheme, parsed_url.netloc]):
        logger.error(f"Invalid external audio URL format: {audio_url_param}")
        return HttpResponse(f"Invalid audio URL provided: {audio_url_param}", status=400)

    else:
        # Handle external audio URLs
        try:
            range_header = request.headers.get('Range', None)
            user_agent_host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "audiox.com"
            proxy_headers = {'User-Agent': f'AudioXApp Audio Proxy/1.0 (+http://{user_agent_host})'}

            if range_header:
                proxy_headers['Range'] = range_header

            logger.info(f"Proxying external audio from: {target_audio_url}")
            response_ext = requests.get(target_audio_url, stream=True, headers=proxy_headers, timeout=(10, 60))
            response_ext.raise_for_status()

            content_type = response_ext.headers.get('Content-Type', 'audio/mpeg')
            if not content_type.lower().startswith('audio/'):
                guessed_type, _ = mimetypes.guess_type(target_audio_url)
                content_type = guessed_type if guessed_type and guessed_type.startswith('audio/') else 'audio/mpeg'

            logger.info(f"Streaming external content with type: {content_type}, status: {response_ext.status_code}")
            streaming_response = StreamingHttpResponse(
                response_ext.iter_content(chunk_size=8192),
                content_type=content_type,
                status=response_ext.status_code
            )

            # Copy relevant headers
            if 'Content-Range' in response_ext.headers:
                streaming_response['Content-Range'] = response_ext.headers['Content-Range']
            if 'Content-Length' in response_ext.headers:
                streaming_response['Content-Length'] = response_ext.headers['Content-Length']

            streaming_response['Accept-Ranges'] = response_ext.headers.get('Accept-Ranges', 'bytes')
            return streaming_response

        except requests.exceptions.Timeout:
            logger.error(f"Timeout streaming external audio from: {target_audio_url}")
            return HttpResponse("Audio stream timed out from external source.", status=408)
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTPError streaming external audio from {target_audio_url}: {e.response.status_code if e.response else 'No response'}")
            return HttpResponse(f"Error fetching audio from external source: Status {e.response.status_code if e.response else 'Unknown'}", status=e.response.status_code if e.response else 502)
        except requests.exceptions.RequestException as e:
            logger.error(f"RequestException streaming external audio from {target_audio_url}: {e}")
            return HttpResponse("Error processing audio stream.", status=502)
        except SuspiciousOperation as e:
            logger.warning(f"SuspiciousOperation in stream_audio: {e}")
            return JsonResponse({"error": str(e)}, status=400)
        except Exception as e:
            logger.error(f"Generic error in stream_audio from {target_audio_url}: {e}", exc_info=True)
            return HttpResponse("Internal server error during audio streaming.", status=500)


@csrf_exempt
@require_GET
def fetch_cover_image(request):
    """Fetch and proxy cover images"""
    image_url = request.GET.get("url")
    if not image_url:
        return JsonResponse({"error": "No image URL provided"}, status=400)

    target_image_url = image_url
    parsed_url = urlparse(image_url)
    is_local_media = (image_url.startswith(settings.MEDIA_URL) and
                      not parsed_url.scheme and not parsed_url.netloc)

    if is_local_media:
        try:
            if not target_image_url.startswith(('http://', 'https://')):
                target_image_url = request.build_absolute_uri(target_image_url)
        except Exception as e:
            logger.error(f"Error processing local image URL: {e}")
            return HttpResponse("Error processing local image URL", status=500)
    elif not all([parsed_url.scheme, parsed_url.netloc]):
        return HttpResponse("Invalid image URL provided", status=400)

    try:
        user_agent_host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "AudioXApp.com"
        proxy_headers = {'User-Agent': f'AudioXApp Image Proxy/1.0 (+http://{user_agent_host})'}

        response = requests.get(target_image_url, stream=True, timeout=30, headers=proxy_headers)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', 'image/jpeg')
        if not content_type.lower().startswith('image/'):
            guessed_type, _ = mimetypes.guess_type(target_image_url)
            content_type = guessed_type if guessed_type and guessed_type.startswith('image/') else 'image/jpeg'

        streaming_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type=content_type
        )

        if 'Content-Length' in response.headers:
            streaming_response['Content-Length'] = response.headers['Content-Length']

        streaming_response.status_code = response.status_code
        return streaming_response

    except requests.exceptions.Timeout:
        logger.warning(f"Timeout fetching image from: {target_image_url}")
        return HttpResponse("Image fetch timed out", status=408)
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTPError fetching image from {target_image_url}: {e.response.status_code if e.response else 'No response'}")
        return HttpResponse(f"Error fetching image: {e.response.status_code if e.response else 'Unknown'}", status=e.response.status_code if e.response else 502)
    except requests.exceptions.RequestException as e:
        logger.warning(f"RequestException fetching image from {target_image_url}: {e}")
        return HttpResponse("Failed to fetch image", status=502)
    except SuspiciousOperation as e:
        logger.warning(f"SuspiciousOperation in fetch_cover_image: {e}")
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        logger.error(f"Generic error in fetch_cover_image from {target_image_url}: {e}", exc_info=True)
        return HttpResponse("Internal server error", status=500)

# ==========================================
# CONTENT REPORTING
# ==========================================

@require_POST
@login_required
@csrf_protect
def submit_content_report_view(request, audiobook_id):
    """Submit content report for audiobook"""
    audiobook = get_object_or_404(Audiobook, audiobook_id=audiobook_id)
    reason = request.POST.get('reason')
    details = request.POST.get('details', '').strip()

    if not reason or reason not in [choice[0] for choice in ContentReport.ReportReason.choices]:
        messages.error(request, "You must select a valid reason for the report.")
        return redirect('AudioXApp:audiobook_detail', audiobook_slug=audiobook.slug)

    try:
        ContentReport.objects.create(
            reported_by=request.user,
            audiobook=audiobook,
            reason=reason,
            details=details
        )
        messages.success(request, "Thank you for your report. Our moderation team will review it.")

    except IntegrityError:
        messages.warning(request, "You have already submitted a report for this audiobook.")
        return redirect('AudioXApp:audiobook_detail', audiobook_slug=audiobook.slug)
    except Exception as e:
        logger.error(f"Error saving content report for audiobook {audiobook_id} by user {request.user.pk}: {e}", exc_info=True)
        messages.error(request, "An error occurred while submitting your report.")
        return redirect('AudioXApp:audiobook_detail', audiobook_slug=audiobook.slug)

    # Auto-moderation based on report threshold
    report_threshold = 10

    with transaction.atomic():
        audiobook_locked = Audiobook.objects.select_for_update().get(pk=audiobook.pk)

        if audiobook_locked.moderation_status == Audiobook.ModerationStatusChoices.APPROVED:
            unique_reporter_count = ContentReport.objects.filter(
                audiobook=audiobook_locked
            ).values('reported_by').distinct().count()

            if unique_reporter_count >= report_threshold:
                audiobook_locked.moderation_status = Audiobook.ModerationStatusChoices.NEEDS_REVIEW
                audiobook_locked.moderation_notes = f"Content automatically flagged for review after receiving {unique_reporter_count} unique user reports."
                audiobook_locked.save()
                logger.info(f"Audiobook ID {audiobook_locked.audiobook_id} ('{audiobook_locked.title}') flagged for moderation due to user reports.")

    return redirect('AudioXApp:audiobook_detail', audiobook_slug=audiobook.slug)

# ==========================================
# DEBUG AND ADMIN VIEWS
# ==========================================

@require_GET
def debug_external_audiobooks(request):
    """Debug view to check external audiobook cache status"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Admin access required'}, status=403)

    try:
        cached_data = cache.get(CACHE_KEY)

        if not cached_data:
            return JsonResponse({
                'success': False,
                'message': 'No cached data found',
                'cache_key': CACHE_KEY,
                'suggestions': [
                    'Run: python manage.py populate_audiobook_cache',
                    'Check if cache backend is working',
                    'Verify CACHE_KEY matches management command'
                ]
            })

        # Analyze cached data
        librivox_count = len(cached_data.get('librivox_audiobooks', []))
        archive_genres = cached_data.get('archive_genre_audiobooks', {})
        archive_languages = cached_data.get('archive_language_audiobooks', {})

        genre_breakdown = {genre: len(books) for genre, books in archive_genres.items()}
        language_breakdown = {lang: len(books) for lang, books in archive_languages.items()}

        # Sample data for verification
        sample_librivox = cached_data.get('librivox_audiobooks', [])[:2]
        sample_archive = []
        for genre, books in list(archive_genres.items())[:2]:
            if books:
                sample_archive.append({
                    'genre': genre,
                    'sample_book': books[0]
                })

        return JsonResponse({
            'success': True,
            'cache_key': CACHE_KEY,
            'cache_status': 'ACTIVE',
            'data_summary': {
                'librivox_audiobooks': librivox_count,
                'archive_genre_audiobooks': len(archive_genres),
                'archive_language_audiobooks': len(archive_languages),
                'total_external_books': librivox_count + sum(len(books) for books in archive_genres.values()) + sum(len(books) for books in archive_languages.values())
            },
            'genre_breakdown': genre_breakdown,
            'language_breakdown': language_breakdown,
            'sample_data': {
                'librivox_sample': sample_librivox,
                'archive_sample': sample_archive
            },
            'cache_duration_hours': CACHE_DURATION / 3600,
            'last_updated': 'Available in cache'
        })

    except Exception as e:
        logger.error(f"Error in debug_external_audiobooks: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'message': 'Error checking cache status'
        }, status=500)


@require_POST
@csrf_protect
def refresh_external_audiobooks(request):
    """Admin view to manually refresh external audiobook cache"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Admin access required'}, status=403)

    try:
        # Clear existing cache
        cache.delete(CACHE_KEY)
        logger.info(f"Cleared cache for key: {CACHE_KEY}")

        # Fetch fresh data
        start_time = time.time()
        fresh_data = fetch_audiobooks_data()
        fetch_duration = time.time() - start_time

        if fresh_data:
            librivox_count = len(fresh_data.get('librivox_audiobooks', []))
            archive_genres = fresh_data.get('archive_genre_audiobooks', {})
            archive_languages = fresh_data.get('archive_language_audiobooks', {})

            return JsonResponse({
                'success': True,
                'message': 'External audiobook cache refreshed successfully',
                'fetch_duration_seconds': round(fetch_duration, 2),
                'data_summary': {
                    'librivox_audiobooks': librivox_count,
                    'archive_genre_audiobooks': len(archive_genres),
                    'archive_language_audiobooks': len(archive_languages),
                    'total_books': librivox_count + sum(len(books) for books in archive_genres.values()) + sum(len(books) for books in archive_languages.values())
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Failed to fetch fresh external audiobook data',
                'fetch_duration_seconds': round(fetch_duration, 2)
            })

    except Exception as e:
        logger.error(f"Error in refresh_external_audiobooks: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'message': 'Error refreshing cache'
        }, status=500)