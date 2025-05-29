# AudioXApp/consumer.py

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from .models import ChatRoom, ChatMessage, User, ChatRoomMember, Audiobook
from django.utils import timezone

import logging
logger = logging.getLogger(__name__) # Standard logger for the app

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
                message_content = data.get('message', '').strip()
                if message_content:
                    chat_message_obj = await self.save_chat_message(
                        content=message_content,
                        message_type_enum=ChatMessage.MessageTypeChoices.TEXT
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
                            }
                        )
                    else:
                        logger.error(f"ChatConsumer.receive: Failed to save chat message from user {self.user.username} in room {self.room.name}, not broadcasting.")
                else:
                    logger.info(f"ChatConsumer.receive: Received empty chat_message content from user {self.user.username}.")
            
            elif client_message_type == 'audiobook_recommendation':
                audiobook_id_str = data.get('audiobook_id')
                comment = data.get('comment', '').strip()

                if audiobook_id_str:
                    try:
                        audiobook_id = int(audiobook_id_str)
                    except ValueError:
                        logger.error(f"ChatConsumer.receive: Invalid audiobook_id format '{audiobook_id_str}' from user {self.user.username}.")
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
                            logger.error(f"ChatConsumer.receive: Failed to get audiobook details for ID {audiobook_id} for recommendation by {self.user.username}, not broadcasting.")
                    else:
                        logger.error(f"ChatConsumer.receive: Failed to save recommendation message from user {self.user.username}, not broadcasting.")
                else:
                    logger.warning(f"ChatConsumer.receive: Received audiobook_recommendation without audiobook_id from {self.user.username}.")
            else:
                logger.warning(f"ChatConsumer.receive: Received unknown message type '{client_message_type}' from client {self.user.username}.")

        except json.JSONDecodeError:
            logger.error(f"ChatConsumer.receive: Error decoding JSON from user {self.user.username}: {text_data}", exc_info=True)
        except Exception as e:
            logger.error(f"ChatConsumer.receive: General error processing message from user {self.user.username}: {e}", exc_info=True)

    async def broadcast_chat_message(self, event):
        message_to_send_to_client = {
            'type': event.get('message_type_server'),
            'message_id': event.get('message_id'),
            'username': event.get('username'),
            'user_id': event.get('user_id'),
            'profile_pic_url': event.get('profile_pic_url'),
            'content': event.get('content'),
            'timestamp': event.get('timestamp'),
        }
        if event.get('message_type_server') == ChatMessage.MessageTypeChoices.AUDIOBOOK_RECOMMENDATION:
            message_to_send_to_client['recommended_audiobook'] = event.get('recommended_audiobook')
        
        try:
            await self.send(text_data=json.dumps(message_to_send_to_client))
        except Exception as e:
            logger.error(f"ChatConsumer.broadcast_chat_message: Error sending message to WebSocket client {self.channel_name}: {e}", exc_info=True)

    async def system_message_broadcast(self, event):
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

    @sync_to_async
    def save_chat_message(self, content, message_type_enum=ChatMessage.MessageTypeChoices.TEXT, recommended_audiobook_id=None):
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
                recommended_audiobook=audiobook_instance
            )
            # Consider removing this info log if too verbose for normal operation
            # logger.info(f"ChatConsumer.save_chat_message: Message saved (ID: {message.message_id}) for user {user_identifier} in room {room_identifier}.")
            return message
        except Exception as e:
            logger.error(f"ChatConsumer.save_chat_message: Failed to save message for user {user_identifier} in room {room_identifier}: {e}", exc_info=True)
            return None

    @sync_to_async
    def get_audiobook_details(self, audiobook_id):
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