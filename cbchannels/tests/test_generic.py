
from contextlib import contextmanager

from channels.tests import ChannelTestCase
from channels import routing, asgi, DEFAULT_CHANNEL_LAYER, Channel
from django.contrib.auth.models import AnonymousUser

from cbchannels import Consumers, consumer, apply_decorator
from cbchannels.generic import GroupMixin, UserMixin


class BaseTestCase(ChannelTestCase):
    @contextmanager
    def apply_consumers(self, consumers):
        channel_layer = asgi.channel_layers[DEFAULT_CHANNEL_LAYER]
        old_routing, old_router = channel_layer.routing, channel_layer.router
        channel_layer.routing = [consumers.as_routes(), ]
        channel_layer.router = routing.Router(channel_layer.routing)

        def _(channel):
            message = self.get_next_message(channel)
            consumer, kwargs = channel_layer.router.match(message)
            return consumer(message, **kwargs)

        yield _
        channel_layer.routing = old_routing
        channel_layer.router = old_router


class TestGeneric(BaseTestCase):

    def test_group_consumers(self):

        class _GroupConsumers(GroupMixin, Consumers):
            channel_name = 'test'
            path = '/test'

        with self.apply_consumers(_GroupConsumers) as resolver:
            Channel('websocket.connect').send({'path': '/test', 'reply_channel': 'test.reply_channel'})
            Channel('websocket.receive').send(
                {'message': 'test', 'path': '/test', 'reply_channel': 'test.reply_channel'})

            resolver('websocket.connect')
            resolver('websocket.receive')

        channel_layer = asgi.channel_layers[DEFAULT_CHANNEL_LAYER]
        self.assertTrue('test' in channel_layer._groups.keys())
        self.assertTrue('test.reply_channel' in channel_layer._groups['test'].keys())

    def test_group_consumers_with_kwargs_in_path(self):
        class _GroupConsumers(GroupMixin, Consumers):
            path = '/test/(?P<test>\d+)'
            group_name = 'test_{test}'

        with self.apply_consumers(_GroupConsumers) as resolver:
            Channel('websocket.connect').send({'path': '/test/123', 'reply_channel': 'test.reply_channel'})
            Channel('websocket.receive').send(
                {'message': 'test', 'path': '/test/123', 'reply_channel': 'test.reply_channel'})

            resolver('websocket.connect')
            resolver('websocket.receive')

        channel_layer = asgi.channel_layers[DEFAULT_CHANNEL_LAYER]
        self.assertTrue('test_123' in channel_layer._groups.keys())
        self.assertTrue('test.reply_channel' in channel_layer._groups['test_123'].keys())

    def test_user_consumer(self):
        class _Consumers(UserMixin, Consumers):
            path = '/test/(?P<test>\d+)'
            channel_name = 'test'

            @consumer
            def test(self, *args, **kwargs):
                return self.user

        with self.apply_consumers(_Consumers) as resolver:
            Channel('websocket.connect').send({'path': '/test/123', 'reply_channel': 'test.reply_channel'})
            Channel('websocket.receive').send(
                {'message': 'test', 'path': '/test/123', 'reply_channel': 'test.reply_channel'})

            resolver('websocket.connect')
            resolver('websocket.receive')
            user = resolver('test.receive')

            self.assertTrue(isinstance(user, AnonymousUser))

            # TODO: messages with session
