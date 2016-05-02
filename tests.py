from functools import wraps
from unittest import TestCase

from cbchannels import Consumers, consumer, apply_decorator

from channels import include
from channels.message import Message
from asgiref.inmemory import ChannelLayer as ImMemoryChannelLayer


class MainTest(TestCase):

    def test_get_consumer(self):
        class Test(Consumers):
            @consumer(path='/hello')
            def test(this, message):
                return message

            @consumer
            def do(self, message):
                return 'do'

        self.assertTrue(Test().get('test'))
        self.assertEqual(Test().get('test')('message'), 'message')
        self.assertEqual(Test().get('test')._consumer['name'], 'test')

        self.assertEqual(Test().get('do')('message'), 'do')
        self.assertEqual(Test().get('do')._consumer['name'], 'do')

    def test_as_consumer(self):
        class Test(Consumers):
            @consumer(path='/hello')
            def test(this, message):
                return message

        self.assertEqual(Test.as_consumer('test')('message'), 'message')

    def test_as_routes(self):

        class Test(Consumers):
            @consumer(tag='test')
            def test(this, message):
                return message

            @consumer
            def do(self, message):
                return 'do'

            def on_connect(self, message):
                return 'connect'

        channel_layer = ImMemoryChannelLayer()
        routes = Test.as_routes(channel_name='test', path='^new$', channel_layer=channel_layer)
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

            def on_connect(self, message):
                return 'connect'

        channel_layer = ImMemoryChannelLayer()
        routes = Test.as_routes(channel_layer=channel_layer)
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

            @apply_decorator(decor2)
            def on_connect(self, message, slug=None):
                self.slug = slug
                return message

            @consumer(tag='(?P<tag>[^/]+)')
            @apply_decorator(decor2)
            def tags(self, message, tag):
                return self.message, self.kwargs, self.slug

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
        self.assertEqual(_consumer(message, **kwargs)[1], {'tag': 'test'})
        self.assertEqual(_consumer(message, **kwargs)[2], 'new')
