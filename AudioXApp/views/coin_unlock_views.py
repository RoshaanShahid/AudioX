# Create a new file for coin unlock functionality

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.db import transaction
from django.conf import settings
import json
import logging

from ..models import Chapter, ChapterUnlock, CoinTransaction, User

logger = logging.getLogger(__name__)

CHAPTER_UNLOCK_COST = 50  # Coins required to unlock a chapter

@login_required
@require_POST
@csrf_protect
def unlock_chapter_with_coins(request):
    """
    Allow FREE users to unlock individual chapters with coins.
    """
    try:
        data = json.loads(request.body)
        chapter_id = data.get('chapter_id')
        
        if not chapter_id:
            return JsonResponse({
                'status': 'error',
                'message': 'Chapter ID is required.'
            }, status=400)
        
        # Get the chapter
        chapter = get_object_or_404(Chapter, pk=chapter_id)
        audiobook = chapter.audiobook
        
        # Validate that this is a free audiobook
        if audiobook.is_paid:
            return JsonResponse({
                'status': 'error',
                'message': 'This feature is only available for free audiobooks.'
            }, status=400)
        
        # Check if user is FREE (not premium)
        if request.user.subscription_type != 'FR':
            return JsonResponse({
                'status': 'error',
                'message': 'This feature is only available for free users. Premium users have full access.'
            }, status=400)
        
        # Check if chapter is already unlocked
        if request.user.has_unlocked_chapter(chapter):
            return JsonResponse({
                'status': 'error',
                'message': 'You have already unlocked this chapter.'
            }, status=400)
        
        # Check if user has enough coins
        if request.user.coins < CHAPTER_UNLOCK_COST:
            return JsonResponse({
                'status': 'error',
                'message': f'Insufficient coins. You need {CHAPTER_UNLOCK_COST} coins to unlock this chapter.',
                'coins_needed': CHAPTER_UNLOCK_COST,
                'user_coins': request.user.coins
            }, status=400)
        
        # Perform the unlock transaction
        with transaction.atomic():
            # Check again if chapter is already unlocked (race condition protection)
            if request.user.has_unlocked_chapter(chapter):
                return JsonResponse({
                    'status': 'success',
                    'message': f'Chapter "{chapter.chapter_name}" is already unlocked!',
                    'remaining_coins': request.user.coins,
                    'chapter_id': chapter_id
                })
            
            # Check coin balance again within transaction
            if request.user.coins < CHAPTER_UNLOCK_COST:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Insufficient coins. You need {CHAPTER_UNLOCK_COST} coins to unlock this chapter.',
                    'coins_needed': CHAPTER_UNLOCK_COST,
                    'user_coins': request.user.coins
                }, status=400)
            
            # Deduct coins from user
            request.user.coins -= CHAPTER_UNLOCK_COST
            request.user.save(update_fields=['coins'])
            
            # Create chapter unlock record using get_or_create to prevent duplicates
            chapter_unlock, created = ChapterUnlock.objects.get_or_create(
                user=request.user,
                chapter=chapter,
                defaults={'coins_spent': CHAPTER_UNLOCK_COST}
            )
            
            # If the unlock record already existed, refund the coins
            if not created:
                request.user.coins += CHAPTER_UNLOCK_COST
                request.user.save(update_fields=['coins'])
                return JsonResponse({
                    'status': 'success',
                    'message': f'Chapter "{chapter.chapter_name}" was already unlocked!',
                    'remaining_coins': request.user.coins,
                    'chapter_id': chapter_id
                })
            
            # Create coin transaction record
            CoinTransaction.objects.create(
                user=request.user,
                transaction_type='spent',
                amount=-CHAPTER_UNLOCK_COST,
                status='completed',
                description=f'Unlocked chapter: {chapter.chapter_name}',
                related_audiobook=audiobook
            )
            
            logger.info(f"User {request.user.username} unlocked chapter {chapter_id} for {CHAPTER_UNLOCK_COST} coins")
        
        return JsonResponse({
            'status': 'success',
            'message': f'Chapter "{chapter.chapter_name}" unlocked successfully!',
            'remaining_coins': request.user.coins,
            'chapter_id': chapter_id
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON data.'
        }, status=400)
    except Exception as e:
        logger.error(f"Error unlocking chapter: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': 'An unexpected error occurred. Please try again.'
        }, status=500)

@login_required
def check_chapter_unlock_eligibility(request, chapter_id):
    """
    Check if user can unlock a specific chapter and return relevant info.
    """
    try:
        chapter = get_object_or_404(Chapter, pk=chapter_id)
        audiobook = chapter.audiobook
        
        # Basic eligibility checks
        if audiobook.is_paid:
            return JsonResponse({
                'status': 'not_eligible',
                'reason': 'paid_audiobook',
                'message': 'This feature is only available for free audiobooks.'
            })
        
        if request.user.subscription_type != 'FR':
            return JsonResponse({
                'status': 'not_eligible',
                'reason': 'premium_user',
                'message': 'Premium users have full access to all chapters.'
            })
        
        # Check if already unlocked
        if request.user.has_unlocked_chapter(chapter):
            return JsonResponse({
                'status': 'already_unlocked',
                'message': 'You have already unlocked this chapter.'
            })
        
        # Check coin balance
        has_enough_coins = request.user.coins >= CHAPTER_UNLOCK_COST
        
        return JsonResponse({
            'status': 'eligible' if has_enough_coins else 'insufficient_coins',
            'coins_required': CHAPTER_UNLOCK_COST,
            'user_coins': request.user.coins,
            'coins_needed': max(0, CHAPTER_UNLOCK_COST - request.user.coins),
            'chapter_name': chapter.chapter_name,
            'audiobook_title': audiobook.title
        })
        
    except Exception as e:
        logger.error(f"Error checking chapter unlock eligibility: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': 'Could not check eligibility.'
        }, status=500)
