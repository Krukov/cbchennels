
from functools import wraps
from unittest import TestCase

try:
    from django.channels import include
    from django.channels.message import Message
except ImportError:
    from channels import include
    from channels.message import Message

from asgiref.inmemory import ChannelLayer as ImMemoryChannelLayer

from cbchannels import WebsocketConsumers as Consumers, consumer, apply_decorator
from .features import apply_routes, HttpClient


class MainTest(TestCase):

    def test_dynamic_channels_names(self):

        class Test(Consumers):

            channel_name = 'test1'

            @consumer
            def test(self, message):
                return self.channel_name

        channel_layer = ImMemoryChannelLayer()
        test = Test.as_routes(_channel_layer=channel_layer)
        test_2 = Test.as_routes(channel_name='test', _channel_layer=channel_layer)
        client = HttpClient()

        with apply_routes([test]):
            client.send_and_consume(u'websocket.receive')

        with apply_routes([test_2]):
            client.send_and_consume(u'websocket.receive')

        self.assertEqual(len(channel_layer._channels), 2, channel_layer._channels.keys())
        self.assertIn('test', channel_layer._channels.keys())

    def test_as_routes(self):

        class Test(Consumers):
            channel_name = 'test'

            @consumer(tag='test')
            def test(this, message):
                return message

            @consumer
            def do(this, message):
                return 'do'

            def on_connect(this, message):
                return 'connect'

        channel_layer = ImMemoryChannelLayer()
        routes = Test.as_routes(channel_name='test', path='^new$', _channel_layer=channel_layer)
        self.assertTrue(isinstance(routes, include))
        self.assertEqual(routes.channel_names(), {'websocket.receive', 'websocket.connect',
                                                  'test', 'websocket.disconnect'})
        self.assertEqual(len(routes.routing), 5)

        self.assertEqual(routes.match(Message({'new': ''}, 'websocket.receive', channel_layer)), None)
        m = Message({'path': 'new'}, 'websocket.connect', channel_layer)
        self.assertEqual(routes.match(m)[0](m), 'connect')

        message = Message({'path': 'new', 'tag': 'test'}, 'websocket.receive', channel_layer)
        routes.match(message)[0](message)
        self.assertEqual(channel_layer.receive_many(['test', ])[1], {'path': 'new', 'tag': 'test'})

    def test_as_routes_without_custom_routes(self):
        class Test(Consumers):
            path = '^new$'
            channel_name = 'test'

            def on_connect(this, message):
                return 'connect'

        channel_layer = ImMemoryChannelLayer()
        routes = Test.as_routes(_channel_layer=channel_layer)
        self.assertTrue(isinstance(routes, include))
        self.assertEqual(routes.channel_names(), {'websocket.receive', 'websocket.connect', 'websocket.disconnect'})
        self.assertEqual(len(routes.routing), 3)

        self.assertEqual(routes.match(Message({'new': ''}, 'websocket.receive', channel_layer)), None)
        m = Message({'path': 'new'}, 'websocket.connect', channel_layer)
        self.assertEqual(routes.match(m)[0](m), 'connect')

        message = Message({'path': 'new', 'tag': 'test'}, 'websocket.receive', channel_layer)

        self.assertEqual(routes.match(message)[0](message), None)

    def test_as_consumers_with_decor(self):
        def decor(_consumer):
            @wraps(_consumer)
            def _wrap(message, *args, **kwargs):
                message.decor = True
                return _consumer(message, *args, **kwargs)
            return _wrap

        def decor2(_consumer):
            @wraps(_consumer)
            def _wrap(message, *args, **kwargs):
                message.decor2 = True
                return _consumer(message, *args, **kwargs)

            return _wrap

        class Test(Consumers):
            path = '^/(?P<slug>[^/]+)'
            channel_name = 'test'
            decorators = [decor, ]
            slug = 'slug'

            @apply_decorator(decor2)
            def on_connect(this, message, slug=None):
                this.slug = slug
                return message

            @consumer(tag='(?P<tag>[^/]+)')
            @apply_decorator(decor2)
            def tags(this, message, tag):
                return this.message, this.kwargs, this.slug

        channel_layer = ImMemoryChannelLayer()
        routes = Test.as_routes(channel_layer=channel_layer)

        message = Message({'path': '/new'}, 'websocket.connect', channel_layer)
        _consumer, kwargs = routes.match(message)
        self.assertEqual(kwargs, {'slug': 'new'})
        self.assertEqual(_consumer.__name__, 'ws_connect')
        self.assertTrue(_consumer(message, **kwargs).decor2)
        self.assertTrue(_consumer(message, **kwargs).decor)

        message = Message({'path': '/new', 'tag': 'test'}, 'test', channel_layer)
        _consumer, kwargs = routes.match(message)
        self.assertEqual(kwargs, {'tag': 'test'})
        self.assertTrue(_consumer(message, **kwargs)[0].decor)
        self.assertTrue(_consumer(message, **kwargs)[0].decor2)
        self.assertEqual(_consumer(message, **kwargs)[1], {'tag': 'test'})
        self.assertEqual(_consumer(message, **kwargs)[2], 'slug')

    def test_super_problem(self):
        def decor(_consumer):
            @wraps(_consumer)
            def _wrap(message, *args, **kwargs):
                message.test_mark = '1'
                message.test_mark_decor = '1'
                return _consumer(message, *args, **kwargs)

            return _wrap

        class A(Consumers):

            @apply_decorator(decor)
            def on_connect(this, message, **kwargs):
                this.test_mark = '2'
                this.test_mark_a = '2'

        class B(A):
            def on_connect(this, message, **kwargs):
                super(B, this).on_connect(message, **kwargs)
                this.test_mark = '3'
                this.test_mark_b = '3'
                return this

        channel_layer = ImMemoryChannelLayer()

        routes = B.as_routes(channel_layer=channel_layer)
        message = Message({'path': '/new'}, 'websocket.connect', channel_layer)
        _consumer, kwargs = routes.match(message)
        res = _consumer(message, **kwargs)
        self.assertTrue(res.test_mark, '3')
        self.assertTrue(res.message.test_mark_decor, '1')
        self.assertTrue(res.test_mark_a, '2')
        self.assertTrue(res.test_mark_b, '3')

    def test_passing_kwargs_and_reply_channel(self):

        class Test(Consumers):
            path = '^/(?P<slug>[^/]+)/(?P<pk>\d+)/?'
            channel_name = 'test'

            @consumer(tag='(?P<test>[^/]+)')
            def test(this, message, test):
                this.reply_channel.send({'test': test, 'kwargs': message.content['_kwargs']['slug'],
                                         'slug': this.kwargs.get('slug', None)})

        with apply_routes([Test.as_routes()]):
            client = HttpClient()
            client.send_and_consume(u'websocket.connect', content={'path': '/name/123/'})
            client.send_and_consume(u'websocket.receive', content={'path': '/name/123', 'tag': 'tag'})
            client.consume(u'test')
            content = client.receive()

            self.assertDictEqual(content, {'test': 'tag', 'slug': 'name', 'kwargs': 'name'})
