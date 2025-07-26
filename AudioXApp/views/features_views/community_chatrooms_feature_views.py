# AudioXApp/views/features_views/community_chatrooms_feature_views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.db.models import Count, Q
from django.contrib import messages
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError, ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from AudioXApp.models import ChatRoom, ChatRoomMember, User, Audiobook, ChatRoomInvitation, ChatMessage
from AudioXApp.models import MessageReaction

import logging
logger = logging.getLogger(__name__)

from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Prefetch

# --- Enhanced Chatroom Feature Views ---

class ChatroomWelcomeView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    template_name = 'features/community_chatrooms/chatroom_welcome.html'

    def get(self, request, *args, **kwargs):
        context = {
            'on_chatroom_welcome_page': True,
            'on_explore_chatrooms_page': False,
            'on_my_rooms_page': False,
            'on_joined_rooms_page': False,
            'on_past_rooms_page': False,
            'on_chat_invitations_page': False
        }
        return render(request, self.template_name, context)

class CommunityChatroomHomeView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    template_name = 'features/community_chatrooms/community_chatroom_home.html'

    def get(self, request, *args, **kwargs):
        try:
            chat_rooms_query = ChatRoom.objects.filter(
                status=ChatRoom.RoomStatusChoices.ACTIVE
            ).exclude(
                owner=request.user
            ).annotate(
                num_members=Count('room_memberships__user', filter=Q(room_memberships__status=ChatRoomMember.StatusChoices.ACTIVE), distinct=True)
            ).select_related('owner').order_by('-created_at')
            
            form_errors = request.session.pop('create_room_form_errors', None)
            form_values = request.session.pop('create_room_form_values', None)
            popup_feedback = request.session.pop('invitation_response_feedback', None)
            home_popup_feedback = request.session.pop('room_action_feedback', popup_feedback)

            context = {
                'chat_rooms': chat_rooms_query,
                'on_chatroom_list_page': True,
                'on_explore_chatrooms_page': True,
                'form_errors': form_errors,
                'form_values': form_values,
                'popup_feedback': home_popup_feedback,
            }
            return render(request, self.template_name, context)
        except Exception as e:
            logger.error(f"Error in CommunityChatroomHomeView: {e}", exc_info=True)
            messages.error(request, "An error occurred while loading the chatroom home page.")
            return redirect('AudioXApp:chatroom_welcome')

class CreateChatRoomView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    template_name = 'features/community_chatrooms/chatroom_create_form.html'

    def get(self, request, *args, **kwargs):
        context = {
            'form_values': request.session.pop('create_room_form_values', {}),
            'form_errors': request.session.pop('create_room_form_errors', {}),
            'language_choices': ChatRoom.LANGUAGE_CHOICES
        }
        return render(request, self.template_name, context)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        room_name = request.POST.get('name', '').strip()
        room_description = request.POST.get('description', '').strip()
        room_language = request.POST.get('language', '').strip()
        room_cover_image = request.FILES.get('cover_image')
        errors = {}
        form_values = {'name': room_name, 'description': room_description, 'language': room_language}

        # Enhanced validation
        if not room_name: 
            errors['name'] = 'Chat room name cannot be empty.'
        elif len(room_name) > 100: 
            errors['name'] = 'Chat room name cannot exceed 100 characters.'
        elif len(room_name) < 3:
            errors['name'] = 'Chat room name must be at least 3 characters long.'
        elif ChatRoom.objects.filter(name__iexact=room_name, status=ChatRoom.RoomStatusChoices.ACTIVE).exists():
            errors['name'] = 'An active chat room with this name already exists.'
            
        if not room_description: 
            errors['description'] = 'Description cannot be empty.'
        elif len(room_description) > 500: 
            errors['description'] = 'Description cannot exceed 500 characters.'
        elif len(room_description) < 10:
            errors['description'] = 'Description must be at least 10 characters long.'
            
        valid_language_codes = [choice[0] for choice in ChatRoom.LANGUAGE_CHOICES]
        if not room_language: 
            errors['language'] = 'Please select a language for the chat room.'
        elif room_language not in valid_language_codes: 
            errors['language'] = 'Invalid language selected.'

        # Validate cover image if provided
        if room_cover_image:
            if room_cover_image.size > 5 * 1024 * 1024:  # 5MB limit
                errors['cover_image'] = 'Cover image must be less than 5MB.'
            elif not room_cover_image.content_type.startswith('image/'):
                errors['cover_image'] = 'Only image files are allowed for cover image.'

        if errors:
            messages.error(request, "Please correct the errors below.")
            context = {'form_values': form_values, 'form_errors': errors, 'language_choices': ChatRoom.LANGUAGE_CHOICES}
            return render(request, self.template_name, context)
            
        try:
            chat_room = ChatRoom(
                name=room_name,
                description=room_description,
                language=room_language,
                owner=request.user,
                cover_image=room_cover_image,
                status=ChatRoom.RoomStatusChoices.ACTIVE
            )
            chat_room.save()
            
            ChatRoomMember.objects.update_or_create(
                room=chat_room,
                user=request.user,
                defaults={'role': ChatRoomMember.RoleChoices.ADMIN, 'status': ChatRoomMember.StatusChoices.ACTIVE, 'left_at': None}
            )
            
            request.session['creation_feedback'] = {'type': 'success', 'text': f"Chat room '{chat_room.name}' created successfully!"}
            
            # Clear cached room list
            cache.delete('active_chatrooms_list')
            
            return redirect(reverse('AudioXApp:chatroom_detail', kwargs={'room_id': chat_room.room_id}))
        except IntegrityError as e:
            logger.error(f"Integrity error creating chat room: {e}", exc_info=True)
            errors['name'] = 'A chat room with this name already exists.'
            context = {'form_values': form_values, 'form_errors': errors, 'language_choices': ChatRoom.LANGUAGE_CHOICES}
            return render(request, self.template_name, context)
        except Exception as e:
            logger.error(f"Error creating chat room: {e}", exc_info=True)
            messages.error(request, "An unexpected error occurred while creating the chat room.")
            context = {'form_values': form_values, 'form_errors': {'general_error': 'Server error.'}, 'language_choices': ChatRoom.LANGUAGE_CHOICES}
            return render(request, self.template_name, context)

class LoadMoreMessagesView(LoginRequiredMixin, View):
    """API endpoint for loading more messages with pagination"""
    login_url = reverse_lazy('account_login')
    
    def get(self, request, room_id, *args, **kwargs):
        try:
            chat_room = get_object_or_404(ChatRoom, room_id=room_id)
            
            # Check if user has access to this room
            membership = ChatRoomMember.objects.filter(
                room=chat_room, 
                user=request.user, 
                status=ChatRoomMember.StatusChoices.ACTIVE
            ).first()
            
            if not membership and chat_room.owner != request.user:
                return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
            
            # Get pagination parameters
            page = int(request.GET.get('page', 1))
            page_size = min(int(request.GET.get('page_size', 50)), 100)  # Max 100 messages per request
            before_message_id = request.GET.get('before')  # For cursor-based pagination
            
            # Build query with optimized prefetching
            messages_query = chat_room.messages.select_related(
                'user', 'recommended_audiobook', 'reply_to', 'reply_to__user'
            ).prefetch_related(
                Prefetch('reactions', queryset=MessageReaction.objects.select_related('user')),
                'mentioned_users'
            )
            
            # Apply cursor-based pagination if before_message_id is provided
            if before_message_id:
                try:
                    before_message = ChatMessage.objects.get(message_id=before_message_id)
                    messages_query = messages_query.filter(timestamp__lt=before_message.timestamp)
                except ChatMessage.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'Invalid cursor'}, status=400)
            
            # Order by timestamp descending for pagination, then reverse for display
            messages = list(messages_query.order_by('-timestamp')[:page_size])
            messages.reverse()  # Display in chronological order
            
            # Serialize messages
            messages_data = []
            for message in messages:
                # Get user's reactions for this message
                user_reactions = set(
                    message.reactions.filter(user=request.user).values_list('emoji', flat=True)
                )
                
                message_data = {
                    'message_id': str(message.message_id),
                    'user_id': str(message.user.user_id) if message.user else None,
                    'username': message.user.username if message.user else 'System',
                    'full_name': message.user.full_name if message.user else 'System',
                    'profile_pic_url': message.user.profile_pic.url if message.user and message.user.profile_pic else None,
                    'content': message.content,
                    'message_type': message.message_type,
                    'timestamp': message.timestamp.isoformat(),
                    'is_edited': message.is_edited,
                    'edited_at': message.edited_at.isoformat() if message.edited_at else None,
                    'reactions': message.reaction_summary,
                    'user_reactions': list(user_reactions),
                    'mentioned_users': [str(user.user_id) for user in message.mentioned_users.all()],
                }
                
                # Add reply information
                if message.reply_to:
                    message_data['reply_to'] = {
                        'id': str(message.reply_to.message_id),
                        'content': message.reply_to.content[:100],
                        'username': message.reply_to.user.full_name or message.reply_to.user.username if message.reply_to.user else 'System'
                    }
                
                # Add audiobook recommendation
                if message.recommended_audiobook:
                    message_data['recommended_audiobook'] = {
                        'id': str(message.recommended_audiobook.audiobook_id),
                        'title': message.recommended_audiobook.title,
                        'author': message.recommended_audiobook.author or 'N/A',
                        'cover_image_url': message.recommended_audiobook.cover_image.url if message.recommended_audiobook.cover_image else None,
                    }
                
                # Add file attachment
                if message.file_attachment:
                    message_data['file_attachment'] = {
                        'url': message.file_attachment.url,
                        'name': message.file_attachment.name.split('/')[-1],
                    }
                
                messages_data.append(message_data)
            
            # Determine if there are more messages
            has_more = len(messages) == page_size
            next_cursor = str(messages[0].message_id) if messages and has_more else None
            
            return JsonResponse({
                'success': True,
                'messages': messages_data,
                'has_more': has_more,
                'next_cursor': next_cursor,
                'count': len(messages_data)
            })
        except Exception as e:
            logger.error(f"Error in LoadMoreMessagesView: {e}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'Internal server error'}, status=500)

class GetRoomStatsView(LoginRequiredMixin, View):
    """Get cached room statistics for performance"""
    login_url = reverse_lazy('account_login')
    
    def get(self, request, room_id, *args, **kwargs):
        try:
            chat_room = get_object_or_404(ChatRoom, room_id=room_id)
            
            # Check if user has access to this room
            membership = ChatRoomMember.objects.filter(
                room=chat_room, 
                user=request.user, 
                status=ChatRoomMember.StatusChoices.ACTIVE
            ).first()
            
            if not membership and chat_room.owner != request.user:
                return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
            
            # Try to get cached stats first
            cache_key = f"room_stats_{room_id}"
            stats = cache.get(cache_key)
            
            if not stats:
                # Calculate and cache stats
                active_members_count = ChatRoomMember.objects.filter(
                    room=chat_room,
                    status=ChatRoomMember.StatusChoices.ACTIVE
                ).count()
                
                total_messages = ChatMessage.objects.filter(room=chat_room).count()
                
                recent_activity = ChatMessage.objects.filter(
                    room=chat_room,
                    timestamp__gte=timezone.now() - timezone.timedelta(hours=24)
                ).count()
                
                stats = {
                    'active_members': active_members_count,
                    'total_messages': total_messages,
                    'recent_activity_24h': recent_activity,
                    'room_age_days': (timezone.now() - chat_room.created_at).days,
                    'is_active': chat_room.status == ChatRoom.RoomStatusChoices.ACTIVE,
                }
                
                # Cache for 5 minutes
                cache.set(cache_key, stats, 300)
            
            return JsonResponse({'success': True, 'stats': stats})
        except Exception as e:
            logger.error(f"Error in GetRoomStatsView: {e}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'Internal server error'}, status=500)

# Enhanced ChatRoomDetailView with caching optimizations
class ChatRoomDetailView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    template_name = 'features/community_chatrooms/chatroom_detail.html'

    def get(self, request, room_id, *args, **kwargs):
        try:
            invitation_feedback = request.session.pop('invitation_feedback', None)
            creation_feedback = request.session.pop('creation_feedback', None)
            popup_feedback = invitation_feedback or creation_feedback

            # Use select_related to reduce database queries
            chat_room = get_object_or_404(ChatRoom.objects.select_related('owner'), room_id=room_id)
            
            # Cache room metadata
            cache_key = f"room_metadata_{room_id}"
            room_metadata = cache.get(cache_key)
            
            if not room_metadata:
                room_metadata = {
                    'member_count': chat_room.room_memberships.filter(
                        status=ChatRoomMember.StatusChoices.ACTIVE
                    ).count(),
                    'message_count': chat_room.messages.count(),
                    'created_at': chat_room.created_at.isoformat(),
                }
                cache.set(cache_key, room_metadata, 300)  # Cache for 5 minutes
            
            membership = ChatRoomMember.objects.filter(room=chat_room, user=request.user).first()

            # Check if the user is already an active member
            is_active_member = membership and membership.status == ChatRoomMember.StatusChoices.ACTIVE

            if not is_active_member:
                # The owner should always be able to enter and have their membership reactivated.
                if chat_room.owner == request.user:
                    membership, _ = ChatRoomMember.objects.update_or_create(
                        room=chat_room, user=request.user,
                        defaults={'role': ChatRoomMember.RoleChoices.ADMIN, 'status': ChatRoomMember.StatusChoices.ACTIVE, 'left_at': None}
                    )
                
                # Nobody can enter a closed room.
                elif chat_room.status == ChatRoom.RoomStatusChoices.CLOSED:
                    request.session['room_action_feedback'] = {'type': 'info', 'text': f"The chat room '{chat_room.name}' is closed."}
                    return redirect(reverse('AudioXApp:chatroom_home'))

                # If a membership record exists, it means the user was once a member and has left. They now need an invitation.
                elif membership:
                    request.session['room_action_feedback'] = {'type': 'error', 'text': f"You have previously left '{chat_room.name}' and require an invitation to rejoin."}
                    return redirect(reverse('AudioXApp:chatroom_home'))
                
                # If no membership record exists at all and the room is active, it's a first-time join.
                elif not membership and chat_room.status == ChatRoom.RoomStatusChoices.ACTIVE:
                    membership = ChatRoomMember.objects.create(
                        room=chat_room,
                        user=request.user,
                        role=ChatRoomMember.RoleChoices.MEMBER,
                        status=ChatRoomMember.StatusChoices.ACTIVE
                    )
                    # Set feedback for a successful first-time join.
                    popup_feedback = {'type': 'success', 'text': f"Welcome! You have successfully joined '{chat_room.name}'."}
                    
                    # Invalidate room metadata cache
                    cache.delete(cache_key)

                # A catch-all for any other state; redirects and requires an invitation.
                else:
                    request.session['room_action_feedback'] = {'type': 'error', 'text': f"You cannot join '{chat_room.name}' at this time. An invitation may be required."}
                    return redirect(reverse('AudioXApp:chatroom_home'))
            
            can_invite_users = False
            can_manage_members = False
            if chat_room.is_open_for_interaction and membership and membership.status == ChatRoomMember.StatusChoices.ACTIVE:
                if chat_room.owner == request.user or membership.role == ChatRoomMember.RoleChoices.ADMIN:
                    can_invite_users = True
                    can_manage_members = True

            # Optimized message fetching - load only recent messages initially
            # The rest will be loaded via AJAX pagination
            initial_message_limit = 50
            messages_qs = chat_room.messages.select_related(
                'user', 'recommended_audiobook', 'recommended_audiobook__creator__user', 'reply_to', 'reply_to__user'
            ).prefetch_related(
                Prefetch('reactions', queryset=MessageReaction.objects.select_related('user')),
                'mentioned_users'
            ).order_by('-timestamp')[:initial_message_limit]
            
            # Reverse for chronological display
            recent_messages = list(messages_qs)
            recent_messages.reverse()
            
            # Add current user's reactions to each message for template usage
            for message in recent_messages:
                user_reactions = set()
                for reaction in message.reactions.all():
                    if reaction.user == request.user:
                        user_reactions.add(reaction.emoji)
                message.current_user_reactions = user_reactions
            
            # Cache active members list
            members_cache_key = f"room_members_{room_id}"
            active_members = cache.get(members_cache_key)
            
            if not active_members:
                active_members = list(chat_room.room_memberships.filter(
                    status=ChatRoomMember.StatusChoices.ACTIVE
                ).select_related('user').order_by('-role', 'user__full_name'))
                cache.set(members_cache_key, active_members, 180)  # Cache for 3 minutes
            
            # Cache free audiobooks
            audiobooks_cache_key = "free_audiobooks_list"
            free_audiobooks = cache.get(audiobooks_cache_key)
            
            if not free_audiobooks:
                free_audiobooks = list(Audiobook.objects.filter(
                    is_paid=False, status='PUBLISHED'
                ).select_related('creator__user').order_by('title')[:50])
                cache.set(audiobooks_cache_key, free_audiobooks, 900)  # Cache for 15 minutes
            
            context = {
                'chat_room': chat_room,
                'chat_log_entries': recent_messages,
                'members': active_members, 
                'current_user_membership': membership,
                'can_invite_users': can_invite_users,
                'can_manage_members': can_manage_members,
                'free_audiobooks': free_audiobooks,
                'room_metadata': room_metadata,
                'initial_message_limit': initial_message_limit,
                'has_more_messages': len(recent_messages) == initial_message_limit,
                'on_chatroom_detail_page': True,
                'popup_feedback': popup_feedback, 
            }
            return render(request, self.template_name, context)
        except Exception as e:
            logger.error(f"Error in ChatRoomDetailView: {e}", exc_info=True)
            messages.error(request, "An error occurred while loading the chat room.")
            return redirect('AudioXApp:chatroom_home')

class LeaveChatRoomView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')

    @transaction.atomic
    def post(self, request, room_id, *args, **kwargs):
        try:
            chat_room = get_object_or_404(ChatRoom, room_id=room_id)
            redirect_url_home = reverse_lazy('AudioXApp:chatroom_home')
            now = timezone.now()

            if chat_room.owner == request.user:
                if chat_room.status == ChatRoom.RoomStatusChoices.CLOSED:
                    request.session['room_action_feedback'] = {'type': 'info', 'text': f"Chat room '{chat_room.name}' is already closed."}
                    return redirect(redirect_url_home)

                room_name = chat_room.name
                chat_room.status = ChatRoom.RoomStatusChoices.CLOSED
                chat_room.save(update_fields=['status', 'updated_at'])

                ChatRoomMember.objects.filter(
                    room=chat_room,
                    status=ChatRoomMember.StatusChoices.ACTIVE
                ).update(
                    status=ChatRoomMember.StatusChoices.ROOM_DISMISSED,
                    left_at=now
                )
                
                ChatMessage.objects.create(
                    room=chat_room,
                    message_type=ChatMessage.MessageTypeChoices.ROOM_CLOSED,
                    content=f"This room has been closed by the owner, {request.user.full_name or request.user.username}."
                )
                
                # Clear cache
                cache.delete(f"room_metadata_{room_id}")
                cache.delete(f"room_members_{room_id}")
                
                request.session['room_action_feedback'] = {'type': 'success', 'text': f"You have closed the chat room: '{room_name}'. Other members have been notified."}
                return redirect(redirect_url_home)
            
            try:
                membership = ChatRoomMember.objects.get(room=chat_room, user=request.user)
                if chat_room.status == ChatRoom.RoomStatusChoices.CLOSED:
                    request.session['room_action_feedback'] = {'type': 'info', 'text': f"The chat room '{chat_room.name}' is closed. You are no longer an active member."}
                    if membership.status == ChatRoomMember.StatusChoices.ACTIVE:
                        membership.status = ChatRoomMember.StatusChoices.ROOM_DISMISSED
                        membership.left_at = now
                        membership.save(update_fields=['status', 'left_at'])
                    return redirect(redirect_url_home)

                if membership.status == ChatRoomMember.StatusChoices.ACTIVE:
                    membership.status = ChatRoomMember.StatusChoices.LEFT
                    membership.left_at = now
                    membership.save(update_fields=['status', 'left_at'])
                    
                    # Clear cache
                    cache.delete(f"room_metadata_{room_id}")
                    cache.delete(f"room_members_{room_id}")
                    
                    request.session['room_action_feedback'] = {'type': 'success', 'text': f"You have left the room: {chat_room.name}."}
                elif membership.status == ChatRoomMember.StatusChoices.LEFT:
                    request.session['room_action_feedback'] = {'type': 'info', 'text': f"You have already left the room: {chat_room.name}."}
                else:
                    request.session['room_action_feedback'] = {'type': 'info', 'text': f"Your status in '{chat_room.name}' is '{membership.get_status_display()}'."}
                return redirect(redirect_url_home)
            except ChatRoomMember.DoesNotExist:
                request.session['room_action_feedback'] = {'type': 'warning', 'text': "You were not a member of this room."}
                return redirect(redirect_url_home)
        except Exception as e:
            logger.error(f"Error leaving room {room_id} for user {request.user.user_id}: {e}", exc_info=True)
            request.session['room_action_feedback'] = {'type': 'error', 'text': "Could not leave the room due to an error."}
            return redirect(reverse('AudioXApp:chatroom_detail', kwargs={'room_id': room_id}))

# Enhanced Member Management Views

class ManageMemberView(LoginRequiredMixin, View):
    """Enhanced member management for room owners and admins"""
    login_url = reverse_lazy('account_login')
    
    @transaction.atomic
    def post(self, request, room_id, *args, **kwargs):
        try:
            chat_room = get_object_or_404(ChatRoom, room_id=room_id)
            action = request.POST.get('action')
            target_user_id = request.POST.get('user_id')
            
            if not action or not target_user_id:
                return JsonResponse({'success': False, 'error': 'Missing required parameters'}, status=400)
            
            # Check permissions
            current_membership = ChatRoomMember.objects.filter(
                room=chat_room, 
                user=request.user, 
                status=ChatRoomMember.StatusChoices.ACTIVE
            ).first()
            
            is_owner = chat_room.owner == request.user
            is_admin = current_membership and current_membership.role == ChatRoomMember.RoleChoices.ADMIN
            
            if not (is_owner or is_admin):
                return JsonResponse({'success': False, 'error': 'Insufficient permissions'}, status=403)
            
            try:
                target_user = User.objects.get(user_id=target_user_id)
                target_membership = ChatRoomMember.objects.get(
                    room=chat_room, 
                    user=target_user,
                    status=ChatRoomMember.StatusChoices.ACTIVE
                )
                
                # Prevent actions on room owner
                if target_user == chat_room.owner:
                    return JsonResponse({'success': False, 'error': 'Cannot perform actions on room owner'}, status=400)
                
                # Handle different actions
                if action == 'promote':
                    if is_owner:  # Only owners can promote to admin
                        target_membership.role = ChatRoomMember.RoleChoices.ADMIN
                        target_membership.save()
                        
                        # Clear cache
                        cache.delete(f"room_members_{room_id}")
                        
                        return JsonResponse({
                            'success': True, 
                            'message': f'{target_user.full_name or target_user.username} promoted to admin',
                            'new_role': 'admin'
                        })
                    else:
                        return JsonResponse({'success': False, 'error': 'Only room owners can promote members'}, status=403)
                        
                elif action == 'demote':
                    if is_owner:  # Only owners can demote admins
                        target_membership.role = ChatRoomMember.RoleChoices.MEMBER
                        target_membership.save()
                        
                        # Clear cache
                        cache.delete(f"room_members_{room_id}")
                        
                        return JsonResponse({
                            'success': True, 
                            'message': f'{target_user.full_name or target_user.username} demoted to member',
                            'new_role': 'member'
                        })
                    else:
                        return JsonResponse({'success': False, 'error': 'Only room owners can demote admins'}, status=403)
                        
                elif action == 'kick':
                    target_membership.status = ChatRoomMember.StatusChoices.LEFT
                    target_membership.left_at = timezone.now()
                    target_membership.save()
                    
                    # Send system message
                    ChatMessage.objects.create(
                        room=chat_room,
                        message_type=ChatMessage.MessageTypeChoices.USER_LEFT,
                        content=f"{target_user.full_name or target_user.username} was removed from the room."
                    )
                    
                    # Clear cache
                    cache.delete(f"room_metadata_{room_id}")
                    cache.delete(f"room_members_{room_id}")
                    
                    return JsonResponse({
                        'success': True, 
                        'message': f'{target_user.full_name or target_user.username} removed from room'
                    })
                    
                else:
                    return JsonResponse({'success': False, 'error': 'Invalid action'}, status=400)
                    
            except User.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
            except ChatRoomMember.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'User is not a member of this room'}, status=404)
        except Exception as e:
            logger.error(f"Error managing member: {e}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'Server error occurred'}, status=500)

class GetMemberStatusView(LoginRequiredMixin, View):
    """Get online status and activity information for members"""
    login_url = reverse_lazy('account_login')
    
    def get(self, request, room_id, *args, **kwargs):
        try:
            chat_room = get_object_or_404(ChatRoom, room_id=room_id)
            
            # Check if user has access to this room
            membership = ChatRoomMember.objects.filter(
                room=chat_room, 
                user=request.user, 
                status=ChatRoomMember.StatusChoices.ACTIVE
            ).first()
            
            if not membership and chat_room.owner != request.user:
                return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
            
            # Get all active members with their last activity
            members = ChatRoomMember.objects.filter(
                room=chat_room,
                status=ChatRoomMember.StatusChoices.ACTIVE
            ).select_related('user').order_by('-role', 'user__full_name')
            
            member_data = []
            for member in members:
                # Calculate last seen (simplified - would need Redis for real-time tracking)
                last_message = ChatMessage.objects.filter(
                    room=chat_room,
                    user=member.user
                ).order_by('-timestamp').first()
                
                member_data.append({
                    'user_id': str(member.user.user_id),
                    'username': member.user.username,
                    'full_name': member.user.full_name or member.user.username,
                    'profile_pic_url': member.user.profile_pic.url if member.user.profile_pic else None,
                    'role': member.role,
                    'is_owner': member.user == chat_room.owner,
                    'joined_at': member.joined_at.isoformat(),
                    'last_activity': last_message.timestamp.isoformat() if last_message else member.joined_at.isoformat(),
                    'is_online': False,  # Would be determined by Redis/WebSocket tracking
                })
            
            return JsonResponse({'success': True, 'members': member_data})
        except Exception as e:
            logger.error(f"Error in GetMemberStatusView: {e}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'Internal server error'}, status=500)

class InviteUserToChatRoomView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    
    def post(self, request, room_id):
        try:
            chat_room = get_object_or_404(ChatRoom, room_id=room_id)
            invited_email = request.POST.get('email', '').strip().lower()
            redirect_url = reverse('AudioXApp:chatroom_detail', kwargs={'room_id': room_id})
            feedback_for_session = None

            if not chat_room.is_open_for_interaction:
                feedback_for_session = {'type': 'error', 'text': f"Cannot invite users to a closed room ('{chat_room.name}')."}
                request.session['invitation_feedback'] = feedback_for_session
                return redirect(redirect_url)

            current_user_membership = ChatRoomMember.objects.filter(room=chat_room, user=request.user, status=ChatRoomMember.StatusChoices.ACTIVE).first()
            can_invite = (chat_room.owner == request.user) or (current_user_membership and current_user_membership.role == ChatRoomMember.RoleChoices.ADMIN)

            if not can_invite:
                feedback_for_session = {'type': 'error', 'text': "You do not have permission to invite users to this room."}
            elif not invited_email:
                feedback_for_session = {'type': 'error', 'text': "Email address is required."}
            else:
                try: 
                    validate_email(invited_email)
                except DjangoValidationError:
                    feedback_for_session = {'type': 'error', 'text': "Invalid email address format."}
                else:
                    try:
                        target_user = User.objects.get(email__iexact=invited_email)
                        if target_user == request.user:
                            feedback_for_session = {'type': 'warning', 'text': "You cannot invite yourself."}
                        elif ChatRoomMember.objects.filter(room=chat_room, user=target_user, status=ChatRoomMember.StatusChoices.ACTIVE).exists():
                            feedback_for_session = {'type': 'warning', 'text': f"User '{target_user.full_name}' is already an active member of this room."}
                        elif ChatRoomInvitation.objects.filter(room=chat_room, invited_user=target_user, status=ChatRoomInvitation.StatusChoices.PENDING).exists():
                            feedback_for_session = {'type': 'info', 'text': f"An invitation is already pending for '{target_user.full_name}' for this room."}
                        else:
                            try:
                                ChatRoomInvitation.objects.create(room=chat_room, invited_by=request.user, invited_user=target_user)
                                feedback_for_session = {'type': 'success', 'text': f"Invitation sent to {target_user.full_name} ({invited_email})."}
                            except IntegrityError:
                                feedback_for_session = {'type': 'warning', 'text': f"Pending invitation already exists for '{target_user.full_name}'."}
                    except User.DoesNotExist:
                        feedback_for_session = {'type': 'error', 'text': f"No user found with email: {invited_email}."}
            
            if feedback_for_session:
                request.session['invitation_feedback'] = feedback_for_session
                
            return redirect(redirect_url)
        except Exception as e:
            logger.error(f"Error in InviteUserToChatRoomView: {e}", exc_info=True)
            request.session['invitation_feedback'] = {'type': 'error', 'text': "An error occurred while sending the invitation."}
            return redirect(reverse('AudioXApp:chatroom_detail', kwargs={'room_id': room_id}))

class ChatInvitationsListView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    template_name = 'features/community_chatrooms/chat_invitations.html'
    
    def get(self, request, *args, **kwargs):
        try:
            popup_feedback = request.session.pop('invitation_response_feedback', None)
            pending_invitations = ChatRoomInvitation.objects.filter(
                invited_user=request.user,
                status=ChatRoomInvitation.StatusChoices.PENDING,
                room__status=ChatRoom.RoomStatusChoices.ACTIVE
            ).select_related('room', 'invited_by').order_by('-created_at')
            
            context = {
                'pending_invitations': pending_invitations,
                'on_chat_invitations_page': True,
                'popup_feedback': popup_feedback,
                'on_explore_chatrooms_page': False
            }
            return render(request, self.template_name, context)
        except Exception as e:
            logger.error(f"Error in ChatInvitationsListView: {e}", exc_info=True)
            messages.error(request, "An error occurred while loading your invitations.")
            return redirect('AudioXApp:chatroom_welcome')

class RespondToChatInvitationView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    
    @transaction.atomic
    def post(self, request, invitation_id, *args, **kwargs):
        try:
            action = request.POST.get('action', '').lower()
            feedback_for_session = None
            redirect_page = reverse_lazy('AudioXApp:chat_invitations')

            if action not in ['accept', 'decline']:
                feedback_for_session = {'type': 'error', 'text': "Invalid action specified."}
                request.session['invitation_response_feedback'] = feedback_for_session
                return redirect(redirect_page)

            try:
                invitation = get_object_or_404(ChatRoomInvitation.objects.select_related('room'),
                                               invitation_id=invitation_id,
                                               invited_user=request.user,
                                               status=ChatRoomInvitation.StatusChoices.PENDING)
                chat_room = invitation.room

                if not chat_room.is_open_for_interaction:
                    feedback_for_session = {'type': 'error', 'text': f"Cannot join '{chat_room.name}' as it is currently closed."}
                    invitation.status = ChatRoomInvitation.StatusChoices.EXPIRED
                    invitation.save(update_fields=['status','updated_at'])
                elif action == 'accept':
                    try:
                        ChatRoomMember.objects.update_or_create(
                            room=chat_room,
                            user=request.user,
                            defaults={'role': ChatRoomMember.RoleChoices.MEMBER, 'status': ChatRoomMember.StatusChoices.ACTIVE, 'left_at': None}
                        )
                        invitation.status = ChatRoomInvitation.StatusChoices.ACCEPTED
                        invitation.save(update_fields=['status', 'updated_at'])
                        
                        # Clear cache
                        cache.delete(f"room_metadata_{chat_room.room_id}")
                        cache.delete(f"room_members_{chat_room.room_id}")
                        
                        request.session['invitation_feedback'] = {'type': 'success', 'text': f"Successfully joined room: '{chat_room.name}'."}
                        redirect_page = reverse('AudioXApp:chatroom_detail', kwargs={'room_id': chat_room.room_id})
                    except Exception as e:
                        logger.error(f"Error accepting invitation {invitation_id}: {e}", exc_info=True)
                        feedback_for_session = {'type': 'error', 'text': "Error joining room."}
                elif action == 'decline':
                    try:
                        invitation.status = ChatRoomInvitation.StatusChoices.DECLINED
                        invitation.save(update_fields=['status', 'updated_at'])
                        feedback_for_session = {'type': 'info', 'text': f"Declined invitation to join '{chat_room.name}'."}
                    except Exception as e:
                        logger.error(f"Error declining invitation {invitation_id}: {e}", exc_info=True)
                        feedback_for_session = {'type': 'error', 'text': "Error declining invitation."}
            except Http404:
                feedback_for_session = {'type': 'error', 'text': "Invitation not found or already responded to."}
            
            if feedback_for_session:
                request.session['invitation_response_feedback'] = feedback_for_session

            return redirect(redirect_page)
        except Exception as e:
            logger.error(f"Error in RespondToChatInvitationView: {e}", exc_info=True)
            request.session['invitation_response_feedback'] = {'type': 'error', 'text': "An error occurred while processing your response."}
            return redirect(reverse_lazy('AudioXApp:chat_invitations'))

class MyChatRoomsView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    template_name = 'features/community_chatrooms/my_chatrooms.html'

    def get(self, request, *args, **kwargs):
        try:
            my_rooms = ChatRoom.objects.filter(owner=request.user).annotate(
                num_members=Count('room_memberships__user', filter=Q(room_memberships__status=ChatRoomMember.StatusChoices.ACTIVE), distinct=True)
            ).select_related('owner').order_by('-status', '-created_at')
            
            popup_feedback = request.session.pop('my_rooms_feedback', None)

            context = {
                'my_chat_rooms': my_rooms,
                'on_my_rooms_page': True,
                'popup_feedback': popup_feedback,
                'on_explore_chatrooms_page': False
            }
            return render(request, self.template_name, context)
        except Exception as e:
            logger.error(f"Error in MyChatRoomsView: {e}", exc_info=True)
            messages.error(request, "An error occurred while loading your chat rooms.")
            return redirect('AudioXApp:chatroom_welcome')

class JoinedChatRoomsView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    template_name = 'features/community_chatrooms/joined_chatrooms.html'

    def get(self, request, *args, **kwargs):
        try:
            joined_memberships = ChatRoomMember.objects.filter(
                user=request.user,
                status=ChatRoomMember.StatusChoices.ACTIVE,
                room__status=ChatRoom.RoomStatusChoices.ACTIVE
            ).exclude(
                room__owner=request.user
            ).select_related('room', 'room__owner').order_by('-joined_at')

            joined_chat_rooms_with_data = []
            for membership in joined_memberships:
                room = membership.room
                room.num_members = room.room_memberships.filter(status=ChatRoomMember.StatusChoices.ACTIVE).count()
                joined_chat_rooms_with_data.append(room)
                
            popup_feedback = request.session.pop('joined_rooms_feedback', None)

            context = {
                'joined_chat_rooms': joined_chat_rooms_with_data,
                'on_joined_rooms_page': True,
                'popup_feedback': popup_feedback,
                'on_explore_chatrooms_page': False
            }
            return render(request, self.template_name, context)
        except Exception as e:
            logger.error(f"Error in JoinedChatRoomsView: {e}", exc_info=True)
            messages.error(request, "An error occurred while loading your joined chat rooms.")
            return redirect('AudioXApp:chatroom_welcome')

class PastChatRoomsView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    template_name = 'features/community_chatrooms/past_chatrooms.html'

    def get(self, request, *args, **kwargs):
        try:
            past_memberships = ChatRoomMember.objects.filter(
                user=request.user,
                status__in=[ChatRoomMember.StatusChoices.LEFT, ChatRoomMember.StatusChoices.ROOM_DISMISSED]
            ).select_related('room', 'room__owner').order_by('-left_at')

            past_rooms_data = []
            for membership in past_memberships:
                room = membership.room
                if room:
                    room.num_members = room.room_memberships.filter(status=ChatRoomMember.StatusChoices.ACTIVE).count()
                    past_rooms_data.append({
                        'room': room,
                        'left_at': membership.left_at,
                        'status_when_left': membership.get_status_display()
                    })

            history_tracking_implemented = True
            popup_feedback = request.session.pop('past_rooms_feedback', None)
            feature_message = None
            if not past_rooms_data:
                feature_message = "You have no past chat rooms in your history."
            
            context = {
                'past_chat_rooms_data': past_rooms_data,
                'on_past_rooms_page': True,
                'popup_feedback': popup_feedback,
                'history_tracking_implemented': history_tracking_implemented,
                'feature_message': feature_message,
                'on_explore_chatrooms_page': False
            }
            return render(request, self.template_name, context)
        except Exception as e:
            logger.error(f"Error in PastChatRoomsView: {e}", exc_info=True)
            messages.error(request, "An error occurred while loading your past chat rooms.")
            return redirect('AudioXApp:chatroom_welcome')