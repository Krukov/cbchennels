from functools import wraps
from unittest import TestCase

try:
    from django.channels import include
    from django.channels.message import Message
except ImportError:
    from channels import include
    from channels.message import Message

from asgiref.inmemory import ChannelLayer as ImMemoryChannelLayer

from cbchannels import Consumers, consumer, apply_decorator


class MainTest(TestCase):

    def test_as_routes(self):

        class Test(Consumers):
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
                                                  'test.receive', 'websocket.disconnect'})
        self.assertEqual(len(routes.routing), 2)
        self.assertEqual(len(routes.routing[0].routing), 3)
        self.assertEqual(len(routes.routing[1].routing), 2)

        self.assertEqual(routes.match(Message({'new': ''}, 'websocket.receive', channel_layer)), None)
        self.assertEqual(routes.match(Message({'path': 'new'}, 'websocket.connect', channel_layer))[0](''), 'connect')

        message = Message({'path': 'new', 'tag': 'test'}, 'websocket.receive', channel_layer)
        routes.match(message)[0](message)
        self.assertEqual(channel_layer.receive_many(['test.receive', ])[1], {'path': 'new', 'tag': 'test'})

    def test_as_routes_without_custom_routes(self):
        class Test(Consumers):
            path = '^new$'

            def on_connect(this, message):
                return 'connect'

        channel_layer = ImMemoryChannelLayer()
        routes = Test.as_routes(_channel_layer=channel_layer)
        self.assertTrue(isinstance(routes, include))
        self.assertEqual(routes.channel_names(), {'websocket.receive', 'websocket.connect', 'websocket.disconnect'})
        self.assertEqual(len(routes.routing), 3)

        self.assertEqual(routes.match(Message({'new': ''}, 'websocket.receive', channel_layer)), None)
        self.assertEqual(routes.match(Message({'path': 'new'}, 'websocket.connect', channel_layer))[0](''), 'connect')

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
        self.assertEqual(_consumer.__name__, 'on_connect')
        self.assertTrue(_consumer(message, **kwargs).decor2)
        self.assertTrue(_consumer(message, **kwargs).decor)

        message = Message({'path': '/new', 'tag': 'test'}, 'test.receive', channel_layer)
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
