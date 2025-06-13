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

from AudioXApp.models import ChatRoom, ChatRoomMember, User, Audiobook, ChatRoomInvitation, ChatMessage

import logging
logger = logging.getLogger(__name__)

# --- Chatroom Feature Views ---

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

        if not room_name: errors['name'] = 'Chat room name cannot be empty.'
        elif len(room_name) > 100: errors['name'] = 'Chat room name cannot exceed 100 characters.'
        elif ChatRoom.objects.filter(name__iexact=room_name, status=ChatRoom.RoomStatusChoices.ACTIVE).exists(): 
            errors['name'] = 'An active chat room with this name already exists.'
        if not room_description: errors['description'] = 'Description cannot be empty.'
        elif len(room_description) > 500: errors['description'] = 'Description cannot exceed 500 characters.'
        valid_language_codes = [choice[0] for choice in ChatRoom.LANGUAGE_CHOICES]
        if not room_language: errors['language'] = 'Please select a language for the chat room.'
        elif room_language not in valid_language_codes: errors['language'] = 'Invalid language selected.'

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
            
            return redirect(reverse('AudioXApp:chatroom_detail', kwargs={'room_id': chat_room.room_id}))
        except Exception as e:
            logger.error(f"Error creating chat room: {e}", exc_info=True)
            messages.error(request, "An unexpected error occurred while creating the chat room.")
            context = {'form_values': form_values, 'form_errors': {'general_error': 'Server error.'}, 'language_choices': ChatRoom.LANGUAGE_CHOICES}
            return render(request, self.template_name, context)

class ChatRoomDetailView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    template_name = 'features/community_chatrooms/chatroom_detail.html'

    def get(self, request, room_id, *args, **kwargs):
        invitation_feedback = request.session.pop('invitation_feedback', None)
        creation_feedback = request.session.pop('creation_feedback', None)
        popup_feedback = invitation_feedback or creation_feedback

        chat_room = get_object_or_404(ChatRoom.objects.select_related('owner'), room_id=room_id)
        
        membership = ChatRoomMember.objects.filter(room=chat_room, user=request.user).first()

        if not membership or membership.status != ChatRoomMember.StatusChoices.ACTIVE:
            if chat_room.owner == request.user:
                if not membership:
                    membership, _ = ChatRoomMember.objects.update_or_create(
                        room=chat_room, user=request.user,
                        defaults={'role': ChatRoomMember.RoleChoices.ADMIN, 'status': ChatRoomMember.StatusChoices.ACTIVE, 'left_at': None}
                    )
                elif membership.status != ChatRoomMember.StatusChoices.ACTIVE:
                    membership.status = ChatRoomMember.StatusChoices.ACTIVE
                    membership.role = ChatRoomMember.RoleChoices.ADMIN 
                    membership.left_at = None
                    membership.save(update_fields=['status', 'role', 'left_at'])
            elif chat_room.status == ChatRoom.RoomStatusChoices.CLOSED:
                request.session['room_action_feedback'] = {'type': 'info', 'text': f"The chat room '{chat_room.name}' is closed."}
                return redirect(reverse('AudioXApp:chatroom_home'))
            else: 
                request.session['room_action_feedback'] = {'type': 'error', 'text': f"You are not an active member of '{chat_room.name}'. You might need an invitation to join or rejoin."}
                return redirect(reverse('AudioXApp:chatroom_home'))
        
        can_invite_users = False
        if chat_room.is_open_for_interaction and membership and membership.status == ChatRoomMember.StatusChoices.ACTIVE:
            if chat_room.owner == request.user or membership.role == ChatRoomMember.RoleChoices.ADMIN:
                can_invite_users = True

        messages_qs = chat_room.messages.select_related('user', 'recommended_audiobook', 'recommended_audiobook__creator__user').order_by('timestamp')[:200]
        active_members = chat_room.room_memberships.filter(status=ChatRoomMember.StatusChoices.ACTIVE).select_related('user').order_by('-role', 'user__full_name')
        free_audiobooks = Audiobook.objects.filter(is_paid=False, status='PUBLISHED').select_related('creator__user').order_by('title')[:50]
        
        context = {
            'chat_room': chat_room,
            'chat_log_entries': messages_qs,
            'members': active_members, 
            'current_user_membership': membership,
            'can_invite_users': can_invite_users,
            'free_audiobooks': free_audiobooks,
            'on_chatroom_detail_page': True,
            'popup_feedback': popup_feedback, 
        }
        return render(request, self.template_name, context)

class LeaveChatRoomView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')

    @transaction.atomic
    def post(self, request, room_id, *args, **kwargs):
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

class InviteUserToChatRoomView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    def post(self, request, room_id):
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
            try: validate_email(invited_email)
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
                        except Exception as e:
                            logger.error(f"Error creating invitation for {invited_email} to room {room_id}: {e}", exc_info=True)
                            feedback_for_session = {'type': 'error', 'text': "Could not send invitation due to a server error."}
                except User.DoesNotExist:
                    feedback_for_session = {'type': 'error', 'text': f"No user found with email: {invited_email}."}
        
        if feedback_for_session:
            request.session['invitation_feedback'] = feedback_for_session
            
        return redirect(redirect_url)

class ChatInvitationsListView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    template_name = 'features/community_chatrooms/chat_invitations.html'
    def get(self, request, *args, **kwargs):
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

class RespondToChatInvitationView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    @transaction.atomic
    def post(self, request, invitation_id, *args, **kwargs):
        action = request.POST.get('action', '').lower()
        feedback_for_session = None 
        redirect_page = reverse_lazy('AudioXApp:chat_invitations')

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
            else:
                feedback_for_session = {'type': 'error', 'text': "Invalid action specified."}
        except Http404:
            feedback_for_session = {'type': 'error', 'text': "Invitation not found or already responded to."}
        
        if feedback_for_session:
            request.session['invitation_response_feedback'] = feedback_for_session

        return redirect(redirect_page)

class MyChatRoomsView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    template_name = 'features/community_chatrooms/my_chatrooms.html' 

    def get(self, request, *args, **kwargs):
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

class JoinedChatRoomsView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    template_name = 'features/community_chatrooms/joined_chatrooms.html'

    def get(self, request, *args, **kwargs):
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

class PastChatRoomsView(LoginRequiredMixin, View):
    login_url = reverse_lazy('account_login')
    template_name = 'features/community_chatrooms/past_chatrooms.html'

    def get(self, request, *args, **kwargs):
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