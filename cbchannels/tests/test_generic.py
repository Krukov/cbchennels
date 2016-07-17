from __future__ import unicode_literals

from channels import asgi, DEFAULT_CHANNEL_LAYER
from channels.tests import ChannelTestCase, HttpClient, apply_routes

from django.contrib.auth.models import AnonymousUser, User

from cbchannels import WebsocketConsumers as Consumers, consumer
from cbchannels.generic.base import GroupConsumers
from cbchannels.generic.auth import UserMixin


class TestGeneric(ChannelTestCase):
    client_class = HttpClient

    def test_group_consumers(self):

        class _GroupConsumers(GroupConsumers):
            channel_name = 'test'
            path = '/test'

        with apply_routes([_GroupConsumers.as_routes()]):
            self.client.send_and_consume(u'websocket.connect', {'path': '/test', 'reply_channel': 'test.reply_channel'})
            self.client.send_and_consume(u'websocket.receive',
                                         {'text': 'test', 'path': '/test', 'reply_channel': 'test.reply_channel'})

        channel_layer = asgi.channel_layers[DEFAULT_CHANNEL_LAYER]
        self.assertTrue('test' in channel_layer._groups.keys())
        self.assertTrue('test.reply_channel' in channel_layer._groups['test'].keys())

    def test_group_consumers_with_kwargs_in_path(self):
        class _GroupConsumers(GroupConsumers):
            path = '/test/(?P<test>\d+)'
            group_name = 'test_{test}'
            channel_name = 'test'

        with apply_routes([_GroupConsumers.as_routes()]):
            self.client.send_and_consume(u'websocket.connect',
                                         {'path': '/test/123', 'reply_channel': 'test.reply_channel'})
            self.client.send_and_consume(u'websocket.receive',
                                         {'text': 'test', 'path': '/test/123', 'reply_channel': 'test.reply_channel'})

        channel_layer = asgi.channel_layers[DEFAULT_CHANNEL_LAYER]
        self.assertTrue('test_123' in channel_layer._groups.keys())
        self.assertTrue('test.reply_channel' in channel_layer._groups['test_123'].keys())

    def test_user_consumer(self):
        User.objects.create_user('test', 'test@test.test', '123')

        class _Consumers(UserMixin, Consumers):
            path = '/test/(?P<test>\d+)'
            channel_name = 'test'

            @consumer
            def test(self, *args, **kwargs):
                self.message.reply_channel.send({'test': 123})
                return self.user

        with apply_routes([_Consumers.as_routes(), ]):
            self.client.send_and_consume(u'websocket.connect', {'path': '/test/123'})
            self.client.send_and_consume(u'websocket.receive', {'message': 'test', 'path': '/test/123'})
            user = self.client.consume(u'test')
            self.assertTrue(isinstance(user, AnonymousUser))
            self.client.send_and_consume(u'websocket.disconnect', {'path': '/test/123'})

            self.client.login(username='test', password='123')
            self.client.send_and_consume(u'websocket.connect', {'path': '/test/123'})
            self.client.send_and_consume(u'websocket.receive', {'message': 'test', 'path': '/test/123'})
            user = self.client.consume(u'test')
            self.assertTrue(isinstance(user, User))
            self.assertDictEqual(self.client.receive(), {'test': 123})
