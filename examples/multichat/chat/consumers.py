import json

from django.utils.functional import cached_property
from cbchannels import Consumers, consumer, apply_decorator
from channels.auth import channel_session_user_from_http, channel_session_user

from .models import Room
from .exceptions import ClientError
from .utils import catch_client_error

PK = '(?P<pk>\d+)'


class ChatConsumers(Consumers):
    path = r"^/chat/stream"
    channel_name = 'chat'
    decorators = [channel_session_user, catch_client_error]

    @apply_decorator(channel_session_user_from_http)
    def on_connect(self, message):
        message.channel_session['rooms'] = []

    def on_disconnect(self, message):
        for room_id in message.channel_session.get("rooms", []):
            try:
                room = Room.objects.get(pk=room_id)
                room.websocket_group.discard(message.reply_channel)
            except Room.DoesNotExist:
                pass

    def on_receive(self, message):
        payload = json.loads(message['text'])
        payload['reply_channel'] = message.content['reply_channel']
        self.send(payload)

    @consumer(command="^join$", room=PK)
    def chat_join(self, message, **kwargs):
        self.group.add(message.reply_channel)
        message.channel_session['rooms'] = list(set(message.channel_session['rooms']).union([self.room.id]))
        message.reply_channel.send({
            "text": json.dumps({
                "join": str(self.room.id),
                "title": self.room.title,
            }),
        })

    @consumer(command="^leave$", room=PK)
    def chat_leave(self, message, **kwargs):
        self.group.discard(message.reply_channel)
        message.channel_session['rooms'] = list(set(message.channel_session['rooms']).difference([self.room.id]))
        message.reply_channel.send({
            "text": json.dumps({
                "leave": str(self.room.id),
            }),
        })

    @consumer(command="^send$", room=PK)
    def chat_send(self, message, **kwargs):
        self.send_message(message["message"])

    @cached_property
    def room(self):
        """
        Tries to fetch a room for the user, checking permissions along the way.
        """
        # Find the room they requested (by ID)
        try:
            room = Room.objects.get(pk=self.kwargs['pk'])
        except Room.DoesNotExist:
            raise ClientError("ROOM_INVALID")
        # Check permissions
        if room.staff_only and not self.message.user.is_staff:
            raise ClientError("ROOM_ACCESS_DENIED")
        return room

    @property
    def group(self):
        """
        Returns the Channels Group that sockets should subscribe to to get sent
        messages as they are generated.
        """
        return self.room.websocket_group

    def send_message(self, message):
        """
        Called to send a message to the room on behalf of a user.
        """
        # Send out the message to everyone in the room
        self.group.send({
            "text": json.dumps({
                "room": str(self.room.id),
                "message": message,
                "username": self.message.user.username,
            }),
        })