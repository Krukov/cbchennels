import json

from cbchannels import Consumers, consumer, apply_decorator
from channels.auth import channel_session_user_from_http, channel_session_user
from .models import Room
from .utils import get_room_or_error, catch_client_error


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

    @consumer(command="^join$")
    def chat_join(self, message):
        room = get_room_or_error(message["room"], message.user)
        room.websocket_group.add(message.reply_channel)
        message.channel_session['rooms'] = list(set(message.channel_session['rooms']).union([room.id]))
        message.reply_channel.send({
            "text": json.dumps({
                "join": str(room.id),
                "title": room.title,
            }),
        })

    @consumer(command="^leave$")
    def chat_leave(self, message):
        room = get_room_or_error(message["room"], message.user)
        room.websocket_group.discard(message.reply_channel)
        message.channel_session['rooms'] = list(set(message.channel_session['rooms']).difference([room.id]))
        message.reply_channel.send({
            "text": json.dumps({
                "leave": str(room.id),
            }),
        })

    @consumer(command="^send$")
    def chat_send(self, message):
        room = get_room_or_error(message["room"], message.user)
        room.send_message(message["message"], message.user)
