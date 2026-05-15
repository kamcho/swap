import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Conversation, Message, Block
from .utils import contains_phone_number


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'
        self.user = self.scope['user']

        if self.user.is_anonymous:
            await self.close()
            return

        is_participant = await self.check_participant()
        if not is_participant:
            await self.close()
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Mark existing unread messages as read when user opens the chat
        await self.mark_messages_read()

        # Notify the other participant that messages have been read
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'messages_read',
                'reader_id': self.user.id,
            }
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_text = data.get('message', '').strip()

            if not message_text:
                return

            # 1. Block Check
            if await self.check_blocked():
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'You cannot send messages to this user.',
                }))
                return

            # 2. Phone Number Check
            if contains_phone_number(message_text):
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Message blocked! Sharing phone numbers is strictly prohibited to avoid scams. A repeat violation will have you burnt (permanently banned) from our platform.',
                }))
                return

            # 3. Save Message
            msg = await self.save_message(message_text)

            # 3. Broadcast to the chat room (CRITICAL - Do this first!)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message_text,
                    'sender_id': self.user.id,
                    'sender_name': f'{self.user.first_name} {self.user.last_name}',
                    'timestamp': msg['timestamp'],
                    'message_id': msg['id'],
                }
            )

            # 4. Notify inboxes (Non-critical - wrap in try/except)
            try:
                participant_ids = await self.get_participant_ids()
                for p_id in participant_ids:
                    await self.channel_layer.group_send(
                        f'inbox_{p_id}',
                        {
                            'type': 'inbox_update',
                            'conversation_id': int(self.conversation_id),
                            'message_preview': message_text[:100],
                            'sender_id': self.user.id,
                            'sender_name': f'{self.user.first_name} {self.user.last_name}',
                            'timestamp': msg['timestamp'],
                            'unread_count': await self.get_unread_count(p_id),
                            'total_unread_count': await self.get_total_unread_count(p_id),
                        }
                    )
            except Exception as e:
                print(f"Inbox notification error: {str(e)}")

        except Exception as e:
            print(f"Major error in ChatConsumer.receive: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Message failed to send. Please try again.',
            }))

    async def chat_message(self, event):
        is_mine = event['sender_id'] == self.user.id

        if not is_mine:
            await self.mark_single_message_read(event['message_id'])

        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'timestamp': event['timestamp'],
            'is_mine': is_mine,
            'is_read': not is_mine,
        }))

        if not is_mine:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'messages_read',
                    'reader_id': self.user.id,
                }
            )

    async def messages_read(self, event):
        if event['reader_id'] != self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'read_receipt',
            }))

    # ----- Database helpers -----

    @database_sync_to_async
    def check_participant(self):
        return Conversation.objects.filter(
            id=self.conversation_id,
            participants=self.user
        ).exists()

    @database_sync_to_async
    def save_message(self, text):
        conversation = Conversation.objects.get(id=self.conversation_id)
        msg = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            text=text,
        )
        conversation.save()
        return {
            'id': msg.id,
            'timestamp': msg.created_at.strftime('%H:%M'),
        }

    @database_sync_to_async
    def mark_messages_read(self):
        Message.objects.filter(
            conversation_id=self.conversation_id,
            is_read=False
        ).exclude(sender=self.user).update(is_read=True)

    @database_sync_to_async
    def mark_single_message_read(self, message_id):
        Message.objects.filter(id=message_id, is_read=False).update(is_read=True)

    @database_sync_to_async
    def get_participant_ids(self):
        conv = Conversation.objects.get(id=self.conversation_id)
        return list(conv.participants.all().values_list('id', flat=True))

    @database_sync_to_async
    def get_unread_count(self, user_id):
        return Message.objects.filter(
            conversation_id=self.conversation_id,
            is_read=False
        ).exclude(sender_id=user_id).count()

    @database_sync_to_async
    def get_total_unread_count(self, user_id):
        return Message.objects.filter(
            conversation__participants__id=user_id,
            is_read=False
        ).exclude(sender_id=user_id).count()

    @database_sync_to_async
    def check_blocked(self):
        conv = Conversation.objects.get(id=self.conversation_id)
        partner = conv.participants.exclude(id=self.user.id).first()
        if partner:
            return Block.is_blocked(self.user, partner)
        return False


class InboxConsumer(AsyncWebsocketConsumer):
    """Listens for new message notifications to update the inbox in real-time."""

    async def connect(self):
        self.user = self.scope['user']

        if self.user.is_anonymous:
            await self.close()
            return

        self.inbox_group = f'inbox_{self.user.id}'

        await self.channel_layer.group_add(
            self.inbox_group,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'inbox_group'):
            await self.channel_layer.group_discard(
                self.inbox_group,
                self.channel_name
            )

    async def inbox_update(self, event):
        """Push inbox updates to the connected client."""
        await self.send(text_data=json.dumps({
            'type': 'inbox_update',
            'conversation_id': event['conversation_id'],
            'message_preview': event['message_preview'],
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'timestamp': event['timestamp'],
            'unread_count': event['unread_count'],
        }))
