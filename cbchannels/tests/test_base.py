from __future__ import unicode_literals

from functools import wraps

from channels import include, DEFAULT_CHANNEL_LAYER
from channels.message import Message
from channels.tests import apply_routes, HttpClient, ChannelTestCase
from channels.asgi import channel_layers

from cbchannels import WebsocketConsumers as Consumers, consumer


class MainTest(ChannelTestCase):

    def test_dynamic_channels_names(self):

        class Test(Consumers):

            channel_name = 'test1'

            @consumer
            def test(self, message):
                return self.channel_name

        test = Test.as_routes()
        test_2 = Test.as_routes(channel_name='test')
        client = HttpClient()

        with apply_routes([test]):
            client.send_and_consume(u'websocket.receive')

        with apply_routes([test_2]):
            client.send_and_consume(u'websocket.receive')
        channel_layer = channel_layers[DEFAULT_CHANNEL_LAYER]

        self.assertEqual(len(channel_layer._channels), 3, channel_layer._channels.keys())
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

        channel_layer = channel_layers[DEFAULT_CHANNEL_LAYER]
        routes = Test.as_routes(channel_name='test', path='^new$')
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

        routes = Test.as_routes()
        self.assertTrue(isinstance(routes, include))
        self.assertEqual(routes.channel_names(), {'websocket.receive', 'websocket.connect', 'websocket.disconnect'})
        self.assertEqual(len(routes.routing), 3)

        channel_layer = channel_layers[DEFAULT_CHANNEL_LAYER]
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

            def on_connect(this, message, slug=None):
                this.slug = slug
                return message

            @consumer(tag='(?P<tag>[^/]+)', decorators=[decor2])
            def tags(this, message, tag):
                return this.message, this.kwargs, this.slug

        routes = Test.as_routes()
        channel_layer = channel_layers[DEFAULT_CHANNEL_LAYER]
        message = Message({'path': '/new'}, 'websocket.connect', channel_layer)
        _consumer, kwargs = routes.match(message)
        self.assertEqual(kwargs, {'slug': 'new'})
        self.assertEqual(_consumer.__name__, 'ws_connect')
        self.assertTrue(_consumer(message, **kwargs).decor)

        message = Message({'path': '/new', 'tag': 'test'}, 'test', channel_layer)
        _consumer, kwargs = routes.match(message)
        self.assertEqual(kwargs, {'tag': 'test'})
        self.assertTrue(_consumer(message, **kwargs)[0].decor)
        self.assertTrue(_consumer(message, **kwargs)[0].decor2)
        self.assertEqual(_consumer(message, **kwargs)[1], {'tag': 'test'})
        self.assertEqual(_consumer(message, **kwargs)[2], 'slug')

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

    def test_filters_and_routing(self):
        class Test(Consumers):
            channel_name = 'test'
            mark = 'default'

            @consumer(tag='test')
            def test(this, message):
                this.reply_channel.send({'status': 'ok'})

            @consumer('test2', tag='test')
            def test2(this, message):
                this.reply_channel.send({'status': 'ok', 'mark': this.mark})

        with apply_routes([Test.as_routes(), Test.as_routes(channel_name='test3', mark='new')]):
            client = HttpClient()
            self.assertIsNone(client.send_and_consume(u'test', content={'tag': 'tag'}, fail_on_none=False))

            client.send_and_consume(u'test', content={'tag': 'test'})

            self.assertDictEqual(client.receive(), {'status': 'ok'})
            client.consume('test', fail_on_none=False)
            self.assertIsNone(client.receive())

            client.send_and_consume(u'test3', content={'tag': 'test'})

            self.assertDictEqual(client.receive(), {'status': 'ok'})
            client.consume('test3', fail_on_none=False)
            self.assertIsNone(client.receive())

            client.send_and_consume(u'test2', content={'tag': 'test'})
            self.assertDictEqual(client.receive(), {'status': 'ok', 'mark': 'default'})
            client.consume('test2', fail_on_none=False)
            self.assertIsNone(client.receive())
