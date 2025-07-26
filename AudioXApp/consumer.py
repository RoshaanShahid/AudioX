# AudioXApp/consumer.py

import json
import re
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import ChatRoom, ChatMessage, User, ChatRoomMember, Audiobook, MessageReaction
from django.utils import timezone
from django.core.files.base import ContentFile
import base64
import logging

logger = logging.getLogger(__name__)

# --- Enhanced Chat Consumer ---

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or not self.user.is_authenticated:
            logger.info(f"Unauthenticated WebSocket attempt. Closing connection.")
            await self.close()
            return
        
        try:
            self.room_id = self.scope['url_route']['kwargs']['room_id']
        except KeyError:
            logger.error("ChatConsumer.connect: 'room_id' not found in URL kwargs. Closing connection.")
            await self.close()
            return

        self.room_group_name = f'chat_{self.room_id}'

        try:
            self.room = await sync_to_async(ChatRoom.objects.get)(room_id=self.room_id)
        except ChatRoom.DoesNotExist:
            logger.warning(f"ChatConsumer.connect: ChatRoom with id {self.room_id} does not exist for user {self.user.username}. Closing connection.")
            await self.close()
            return
        except Exception as e:
            logger.error(f"ChatConsumer.connect: Error fetching room {self.room_id} for user {self.user.username}: {e}. Closing connection.", exc_info=True)
            await self.close()
            return

        # Check if user has permission to join this room
        has_permission = await self.check_room_permission()
        if not has_permission:
            logger.warning(f"ChatConsumer.connect: User {self.user.username} doesn't have permission to join room {self.room_id}.")
            await self.close()
            return

        try:
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
        except Exception as e:
            logger.error(f"ChatConsumer.connect: Error adding channel to group {self.room_group_name} for user {self.user.username}: {e}. Closing connection.", exc_info=True)
            await self.close()
            return

        await self.accept()
        logger.info(f"User {self.user.username} connected to room '{self.room.name}' (ID: {self.room_id}). Channel: {self.channel_name}.")

        # Send user joined notification
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'system_message_broadcast',
                'event_type': 'user_joined',
                'username': self.user.full_name or self.user.username,
                'user_id': str(self.user.user_id),
                'timestamp': timezone.now().isoformat()
            }
        )

    async def disconnect(self, close_code):
        username = self.user.username if hasattr(self, 'user') and self.user.is_authenticated else 'UnknownUser'
        room_id_display = self.room_id if hasattr(self, 'room_id') else 'UnknownRoom'
        logger.info(f"User {username} disconnecting from room {room_id_display}. Code: {close_code}")
        
        if hasattr(self, 'room_group_name') and self.user and self.user.is_authenticated:
            # Send user left notification
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'system_message_broadcast',
                    'event_type': 'user_left',
                    'username': self.user.full_name or self.user.username,
                    'user_id': str(self.user.user_id),
                    'timestamp': timezone.now().isoformat()
                }
            )
            
            # Stop typing indicator if user was typing
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_status_broadcast',
                    'typing_action': 'stop',
                    'user_name': self.user.full_name or self.user.username,
                    'user_id': str(self.user.user_id),
                }
            )
            
            try:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
            except Exception as e:
                logger.error(f"ChatConsumer.disconnect: Error removing channel from group {self.room_group_name} for user {username}: {e}", exc_info=True)

    async def receive(self, text_data):
        if not self.user or not self.user.is_authenticated:
            logger.warning("ChatConsumer.receive: Ignoring message from unauthenticated scope.")
            return

        try:
            data = json.loads(text_data)
            client_message_type = data.get('type')
            
            if client_message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif client_message_type == 'audiobook_recommendation':
                await self.handle_audiobook_recommendation(data)
            elif client_message_type == 'typing_start':
                await self.handle_typing_indicator(data, 'start')
            elif client_message_type == 'typing_stop':
                await self.handle_typing_indicator(data, 'stop')
            elif client_message_type == 'message_reaction':
                await self.handle_message_reaction(data)
            elif client_message_type == 'message_edit':
                await self.handle_message_edit(data)
            elif client_message_type == 'message_delete':
                await self.handle_message_delete(data)
            elif client_message_type == 'file_upload':
                await self.handle_file_upload(data)
            elif client_message_type == 'reply_message':
                await self.handle_reply_message(data)
            else:
                logger.warning(f"ChatConsumer.receive: Received unknown message type '{client_message_type}' from client {self.user.username}.")

        except json.JSONDecodeError:
            logger.error(f"ChatConsumer.receive: Error decoding JSON from user {self.user.username}: {text_data}", exc_info=True)
        except Exception as e:
            logger.error(f"ChatConsumer.receive: General error processing message from user {self.user.username}: {e}", exc_info=True)

    async def handle_chat_message(self, data):
        """Handle regular chat messages with mention detection"""
        message_content = data.get('message', '').strip()
        if not message_content:
            logger.info(f"ChatConsumer.handle_chat_message: Received empty message from user {self.user.username}.")
            return

        # Check if room is still open for interaction
        if not await self.is_room_open():
            logger.warning(f"ChatConsumer.handle_chat_message: User {self.user.username} tried to send message to closed room.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Room is closed and not accepting new messages.'
            }))
            return

        # Extract mentions from message
        mentioned_users = await self.extract_mentions(message_content)

        chat_message_obj = await self.save_chat_message(
            content=message_content,
            message_type_enum=ChatMessage.MessageTypeChoices.TEXT,
            mentioned_users=mentioned_users
        )
        
        if chat_message_obj:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_chat_message',
                    'message_id': str(chat_message_obj.message_id),
                    'username': self.user.full_name or self.user.username,
                    'user_id': str(self.user.user_id),
                    'profile_pic_url': self.user.profile_pic.url if self.user.profile_pic else None,
                    'content': chat_message_obj.content,
                    'timestamp': chat_message_obj.timestamp.isoformat(),
                    'message_type_server': chat_message_obj.message_type,
                    'mentioned_users': [str(user.user_id) for user in mentioned_users],
                    'reply_to': None,
                }
            )
        else:
            logger.error(f"ChatConsumer.handle_chat_message: Failed to save chat message from user {self.user.username}, not broadcasting.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to send message. Please try again.'
            }))

    async def handle_reply_message(self, data):
        """Handle reply messages"""
        message_content = data.get('message', '').strip()
        reply_to_id = data.get('reply_to')
        
        if not message_content or not reply_to_id:
            logger.warning(f"ChatConsumer.handle_reply_message: Missing content or reply_to from {self.user.username}.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid reply message data.'
            }))
            return

        # Check if room is still open for interaction
        if not await self.is_room_open():
            logger.warning(f"ChatConsumer.handle_reply_message: User {self.user.username} tried to send reply to closed room.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Room is closed and not accepting new messages.'
            }))
            return

        # Extract mentions from message
        mentioned_users = await self.extract_mentions(message_content)

        # Get the original message
        original_message = await self.get_message_by_id(reply_to_id)
        if not original_message:
            logger.warning(f"ChatConsumer.handle_reply_message: Original message {reply_to_id} not found.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Original message not found.'
            }))
            return

        chat_message_obj = await self.save_chat_message(
            content=message_content,
            message_type_enum=ChatMessage.MessageTypeChoices.TEXT,
            mentioned_users=mentioned_users,
            reply_to=original_message
        )
        
        if chat_message_obj:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_chat_message',
                    'message_id': str(chat_message_obj.message_id),
                    'username': self.user.full_name or self.user.username,
                    'user_id': str(self.user.user_id),
                    'profile_pic_url': self.user.profile_pic.url if self.user.profile_pic else None,
                    'content': chat_message_obj.content,
                    'timestamp': chat_message_obj.timestamp.isoformat(),
                    'message_type_server': chat_message_obj.message_type,
                    'mentioned_users': [str(user.user_id) for user in mentioned_users],
                    'reply_to': {
                        'id': str(original_message.message_id),
                        'content': original_message.content[:100],
                        'username': original_message.user.full_name or original_message.user.username if original_message.user else 'System'
                    },
                }
            )

    async def handle_file_upload(self, data):
        """Handle file uploads"""
        file_data = data.get('file_data')
        file_name = data.get('file_name')
        file_type = data.get('file_type')
        message_content = data.get('message', '').strip()
        
        if not file_data or not file_name:
            logger.warning(f"ChatConsumer.handle_file_upload: Missing file data from {self.user.username}.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid file upload data.'
            }))
            return

        # Check if room is still open for interaction
        if not await self.is_room_open():
            logger.warning(f"ChatConsumer.handle_file_upload: User {self.user.username} tried to upload file to closed room.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Room is closed and not accepting new messages.'
            }))
            return

        try:
            # Decode base64 file data
            file_content = base64.b64decode(file_data)
            
            # Check file size (10MB limit)
            if len(file_content) > 10 * 1024 * 1024:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'File size too large. Maximum 10MB allowed.'
                }))
                return
            
            file_obj = ContentFile(file_content, name=file_name)
            
            chat_message_obj = await self.save_chat_message(
                content=message_content or f"Shared a file: {file_name}",
                message_type_enum=ChatMessage.MessageTypeChoices.FILE_ATTACHMENT,
                file_attachment=file_obj
            )
            
            if chat_message_obj:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'broadcast_chat_message',
                        'message_id': str(chat_message_obj.message_id),
                        'username': self.user.full_name or self.user.username,
                        'user_id': str(self.user.user_id),
                        'profile_pic_url': self.user.profile_pic.url if self.user.profile_pic else None,
                        'content': chat_message_obj.content,
                        'timestamp': chat_message_obj.timestamp.isoformat(),
                        'message_type_server': chat_message_obj.message_type,
                        'file_attachment': {
                            'url': chat_message_obj.file_attachment.url,
                            'name': file_name,
                            'type': file_type
                        },
                    }
                )
        except Exception as e:
            logger.error(f"ChatConsumer.handle_file_upload: Error processing file upload: {e}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to upload file. Please try again.'
            }))

    async def handle_audiobook_recommendation(self, data):
        """Handle audiobook recommendation messages"""
        audiobook_id_str = data.get('audiobook_id')
        comment = data.get('comment', '').strip()

        if not audiobook_id_str:
            logger.warning(f"ChatConsumer.handle_audiobook_recommendation: No audiobook_id from {self.user.username}.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid audiobook recommendation data.'
            }))
            return

        try:
            audiobook_id = int(audiobook_id_str)
        except ValueError:
            logger.error(f"ChatConsumer.handle_audiobook_recommendation: Invalid audiobook_id format '{audiobook_id_str}' from user {self.user.username}.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid audiobook ID format.'
            }))
            return

        # Check if room is still open for interaction
        if not await self.is_room_open():
            logger.warning(f"ChatConsumer.handle_audiobook_recommendation: User {self.user.username} tried to send recommendation to closed room.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Room is closed and not accepting new messages.'
            }))
            return

        recommendation_msg_obj = await self.save_chat_message(
            content=comment,
            message_type_enum=ChatMessage.MessageTypeChoices.AUDIOBOOK_RECOMMENDATION,
            recommended_audiobook_id=audiobook_id
        )
        
        if recommendation_msg_obj:
            audiobook_details = await self.get_audiobook_details(audiobook_id)
            if audiobook_details:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'broadcast_chat_message',
                        'message_id': str(recommendation_msg_obj.message_id),
                        'username': self.user.full_name or self.user.username,
                        'user_id': str(self.user.user_id),
                        'profile_pic_url': self.user.profile_pic.url if self.user.profile_pic else None,
                        'content': recommendation_msg_obj.content, 
                        'timestamp': recommendation_msg_obj.timestamp.isoformat(),
                        'message_type_server': recommendation_msg_obj.message_type,
                        'recommended_audiobook': audiobook_details,
                    }
                )
            else:
                logger.error(f"ChatConsumer.handle_audiobook_recommendation: Failed to get audiobook details for ID {audiobook_id}, not broadcasting.")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Audiobook not found.'
                }))
        else:
            logger.error(f"ChatConsumer.handle_audiobook_recommendation: Failed to save recommendation message from user {self.user.username}, not broadcasting.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to send recommendation. Please try again.'
            }))

    async def handle_typing_indicator(self, data, action):
        """Handle typing start/stop indicators"""
        user_name = data.get('user_name') or self.user.full_name or self.user.username
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_status_broadcast',
                'typing_action': action,
                'user_name': user_name,
                'user_id': str(self.user.user_id),
                'timestamp': timezone.now().isoformat()
            }
        )

    async def handle_message_reaction(self, data):
        """Handle message reactions"""
        message_id = data.get('message_id')
        emoji = data.get('emoji')
        action = data.get('action', 'toggle')  # 'add', 'remove', or 'toggle'
        
        if not message_id or not emoji:
            logger.warning(f"ChatConsumer.handle_message_reaction: Missing data from {self.user.username}.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid reaction data.'
            }))
            return

        try:
            # For toggle action, determine whether to add or remove
            if action == 'toggle':
                existing_reaction = await self.get_user_reaction(message_id, emoji)
                action = 'remove' if existing_reaction else 'add'
            
            if action == 'add':
                reaction = await self.add_message_reaction(message_id, emoji)
                if reaction:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'reaction_broadcast',
                            'action': 'add',
                            'message_id': message_id,
                            'emoji': emoji,
                            'user_id': str(self.user.user_id),
                            'username': self.user.full_name or self.user.username,
                            'timestamp': timezone.now().isoformat()
                        }
                    )
            elif action == 'remove':
                removed = await self.remove_message_reaction(message_id, emoji)
                if removed:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'reaction_broadcast',
                            'action': 'remove',
                            'message_id': message_id,
                            'emoji': emoji,
                            'user_id': str(self.user.user_id),
                            'username': self.user.full_name or self.user.username,
                            'timestamp': timezone.now().isoformat()
                        }
                    )
        except Exception as e:
            logger.error(f"ChatConsumer.handle_message_reaction: Error processing reaction: {e}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to process reaction. Please try again.'
            }))

    async def handle_message_edit(self, data):
        """Handle message editing"""
        message_id = data.get('message_id')
        new_content = data.get('content', '').strip()
        
        if not message_id or not new_content:
            logger.warning(f"ChatConsumer.handle_message_edit: Missing data from {self.user.username}.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid edit data.'
            }))
            return

        edited_message = await self.edit_message(message_id, new_content)
        if edited_message:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'message_edit_broadcast',
                    'message_id': message_id,
                    'new_content': new_content,
                    'edited_at': edited_message.edited_at.isoformat(),
                    'user_id': str(self.user.user_id),
                }
            )
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to edit message. You can only edit your own messages.'
            }))

    async def handle_message_delete(self, data):
        """Handle message deletion"""
        message_id = data.get('message_id')
        
        if not message_id:
            logger.warning(f"ChatConsumer.handle_message_delete: Missing message_id from {self.user.username}.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid delete data.'
            }))
            return

        deleted = await self.delete_message(message_id)
        if deleted:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'message_delete_broadcast',
                    'message_id': message_id,
                    'user_id': str(self.user.user_id),
                    'timestamp': timezone.now().isoformat()
                }
            )
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to delete message. You can only delete your own messages.'
            }))

    async def broadcast_chat_message(self, event):
        """Broadcast chat messages to WebSocket"""
        message_to_send_to_client = {
            'type': event.get('message_type_server'),
            'message_id': event.get('message_id'),
            'username': event.get('username'),
            'user_id': event.get('user_id'),
            'profile_pic_url': event.get('profile_pic_url'),
            'content': event.get('content'),
            'timestamp': event.get('timestamp'),
            'mentioned_users': event.get('mentioned_users', []),
            'reply_to': event.get('reply_to'),
        }
        
        if event.get('message_type_server') == ChatMessage.MessageTypeChoices.AUDIOBOOK_RECOMMENDATION:
            message_to_send_to_client['recommended_audiobook'] = event.get('recommended_audiobook')
        
        if event.get('file_attachment'):
            message_to_send_to_client['file_attachment'] = event.get('file_attachment')
        
        try:
            await self.send(text_data=json.dumps(message_to_send_to_client))
        except Exception as e:
            logger.error(f"ChatConsumer.broadcast_chat_message: Error sending message to WebSocket client {self.channel_name}: {e}", exc_info=True)

    async def reaction_broadcast(self, event):
        """Broadcast reaction updates to WebSocket"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'reaction_update',
                'action': event.get('action'),
                'message_id': event.get('message_id'),
                'emoji': event.get('emoji'),
                'user_id': event.get('user_id'),
                'username': event.get('username'),
                'timestamp': event.get('timestamp')
            }))
        except Exception as e:
            logger.error(f"ChatConsumer.reaction_broadcast: Error sending reaction to WebSocket client {self.channel_name}: {e}", exc_info=True)

    async def message_edit_broadcast(self, event):
        """Broadcast message edits to WebSocket"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'message_edit',
                'message_id': event.get('message_id'),
                'new_content': event.get('new_content'),
                'edited_at': event.get('edited_at'),
                'user_id': event.get('user_id')
            }))
        except Exception as e:
            logger.error(f"ChatConsumer.message_edit_broadcast: Error sending edit to WebSocket client {self.channel_name}: {e}", exc_info=True)

    async def message_delete_broadcast(self, event):
        """Broadcast message deletions to WebSocket"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'message_delete',
                'message_id': event.get('message_id'),
                'user_id': event.get('user_id'),
                'timestamp': event.get('timestamp')
            }))
        except Exception as e:
            logger.error(f"ChatConsumer.message_delete_broadcast: Error sending deletion to WebSocket client {self.channel_name}: {e}", exc_info=True)

    async def system_message_broadcast(self, event):
        """Broadcast system messages to WebSocket"""
        message_to_send = {
            'type': 'system_message', 
            'event_type': event.get('event_type'),
            'username': event.get('username'),
            'user_id': event.get('user_id'),
            'timestamp': event.get('timestamp'),
        }
        try:
            await self.send(text_data=json.dumps(message_to_send))
        except Exception as e:
            logger.error(f"ChatConsumer.system_message_broadcast: Error sending system message to WebSocket client {self.channel_name}: {e}", exc_info=True)

    async def typing_status_broadcast(self, event):
        """Broadcast typing indicators to WebSocket"""
        # Don't send typing indicator back to the user who is typing
        if event.get('user_id') == str(self.user.user_id):
            return

        message_to_send = {
            'type': f"typing_{event.get('typing_action')}",
            'user_name': event.get('user_name'),
            'user_id': event.get('user_id'),
            'timestamp': event.get('timestamp'),
        }
        try:
            await self.send(text_data=json.dumps(message_to_send))
        except Exception as e:
            logger.error(f"ChatConsumer.typing_status_broadcast: Error sending typing status to WebSocket client {self.channel_name}: {e}", exc_info=True)

    @sync_to_async
    def extract_mentions(self, content):
        """Extract mentioned users from message content"""
        # Find all @username mentions
        mention_pattern = r'@(\w+)'
        usernames = re.findall(mention_pattern, content)
        
        if not usernames:
            return []
        
        # Get active room members with matching usernames
        mentioned_users = []
        for username in usernames:
            try:
                user = User.objects.get(
                    username__iexact=username,
                    chat_room_memberships__room=self.room,
                    chat_room_memberships__status=ChatRoomMember.StatusChoices.ACTIVE
                )
                mentioned_users.append(user)
            except User.DoesNotExist:
                continue
        
        return mentioned_users

    @sync_to_async
    def get_user_reaction(self, message_id, emoji):
        """Check if user has already reacted with this emoji"""
        try:
            return MessageReaction.objects.get(
                message__message_id=message_id,
                message__room=self.room,
                user=self.user,
                emoji=emoji
            )
        except MessageReaction.DoesNotExist:
            return None

    @sync_to_async
    def add_message_reaction(self, message_id, emoji):
        """Add a reaction to a message"""
        try:
            message = ChatMessage.objects.get(message_id=message_id, room=self.room)
            reaction, created = MessageReaction.objects.get_or_create(
                message=message,
                user=self.user,
                emoji=emoji
            )
            return reaction if created else None
        except ChatMessage.DoesNotExist:
            logger.error(f"Message {message_id} not found for reaction.")
            return None
        except Exception as e:
            logger.error(f"Error adding reaction: {e}", exc_info=True)
            return None

    @sync_to_async
    def remove_message_reaction(self, message_id, emoji):
        """Remove a reaction from a message"""
        try:
            reaction = MessageReaction.objects.get(
                message__message_id=message_id,
                message__room=self.room,
                user=self.user,
                emoji=emoji
            )
            reaction.delete()
            return True
        except MessageReaction.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error removing reaction: {e}", exc_info=True)
            return False

    @sync_to_async
    def edit_message(self, message_id, new_content):
        """Edit a message"""
        try:
            message = ChatMessage.objects.get(
                message_id=message_id,
                room=self.room,
                user=self.user
            )
            message.content = new_content
            message.is_edited = True
            message.edited_at = timezone.now()
            message.save()
            return message
        except ChatMessage.DoesNotExist:
            logger.error(f"Message {message_id} not found for editing.")
            return None
        except Exception as e:
            logger.error(f"Error editing message: {e}", exc_info=True)
            return None

    @sync_to_async
    def delete_message(self, message_id):
        """Delete a message"""
        try:
            message = ChatMessage.objects.get(
                message_id=message_id,
                room=self.room,
                user=self.user
            )
            message.delete()
            return True
        except ChatMessage.DoesNotExist:
            logger.error(f"Message {message_id} not found for deletion.")
            return False
        except Exception as e:
            logger.error(f"Error deleting message: {e}", exc_info=True)
            return False

    @sync_to_async
    def get_message_by_id(self, message_id):
        """Get a message by its ID"""
        try:
            return ChatMessage.objects.get(message_id=message_id, room=self.room)
        except ChatMessage.DoesNotExist:
            return None

    @sync_to_async
    def check_room_permission(self):
        """Check if user has permission to join this room"""
        try:
            # Room owner always has permission
            if self.room.owner == self.user:
                return True
            
            # Check if user is an active member
            membership = ChatRoomMember.objects.filter(
                room=self.room, 
                user=self.user, 
                status=ChatRoomMember.StatusChoices.ACTIVE
            ).first()
            
            return membership is not None
        except Exception as e:
            logger.error(f"ChatConsumer.check_room_permission: Error checking permission for user {self.user.username}: {e}", exc_info=True)
            return False

    @sync_to_async
    def is_room_open(self):
        """Check if room is still open for interaction"""
        try:
            # Refresh room data from database
            self.room.refresh_from_db()
            return self.room.is_open_for_interaction
        except Exception as e:
            logger.error(f"ChatConsumer.is_room_open: Error checking room status: {e}", exc_info=True)
            return False

    @sync_to_async
    def save_chat_message(self, content, message_type_enum=ChatMessage.MessageTypeChoices.TEXT, recommended_audiobook_id=None, mentioned_users=None, reply_to=None, file_attachment=None):
        """Save chat message to database"""
        audiobook_instance = None
        user_identifier = self.user.username if self.user else 'UnknownUser'
        room_identifier = self.room.name if hasattr(self, 'room') and self.room else 'UnknownRoom'

        if recommended_audiobook_id:
            try:
                audiobook_instance = Audiobook.objects.get(audiobook_id=recommended_audiobook_id)
            except Audiobook.DoesNotExist:
                logger.error(f"ChatConsumer.save_chat_message: Audiobook ID {recommended_audiobook_id} not found for recommendation by {user_identifier}.")
                return None 
            except Exception as e:
                logger.error(f"ChatConsumer.save_chat_message: Error fetching audiobook ID {recommended_audiobook_id}: {e}", exc_info=True)
                return None
        try:
            message = ChatMessage.objects.create(
                room=self.room,
                user=self.user,
                content=content,
                message_type=message_type_enum,
                recommended_audiobook=audiobook_instance,
                reply_to=reply_to,
                file_attachment=file_attachment
            )
            
            # Add mentioned users
            if mentioned_users:
                message.mentioned_users.set(mentioned_users)
            
            return message
        except Exception as e:
            logger.error(f"ChatConsumer.save_chat_message: Failed to save message for user {user_identifier} in room {room_identifier}: {e}", exc_info=True)
            return None

    @sync_to_async
    def get_audiobook_details(self, audiobook_id):
        """Get audiobook details for recommendations"""
        try:
            audiobook = Audiobook.objects.get(audiobook_id=audiobook_id)
            return {
                'id': str(audiobook.audiobook_id),
                'title': audiobook.title,
                'author': audiobook.author or "N/A", 
                'cover_image_url': audiobook.cover_image.url if audiobook.cover_image and hasattr(audiobook.cover_image, 'url') else None,
            }
        except Audiobook.DoesNotExist:
            logger.warning(f"ChatConsumer.get_audiobook_details: Audiobook details not found for ID {audiobook_id}.")
            return None
        except Exception as e:
            logger.error(f"ChatConsumer.get_audiobook_details: Error fetching audiobook details for ID {audiobook_id}: {e}", exc_info=True)
            return None