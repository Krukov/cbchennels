
import copy
import random
import string
from functools import wraps

from django.apps import apps
from django.conf import settings

from channels import DEFAULT_CHANNEL_LAYER
from channels.message import Message
from channels.asgi import channel_layers
from channels.routing import include, Router
from channels.sessions import session_for_reply_channel


class HttpClient(object):

    def __init__(self, alias=DEFAULT_CHANNEL_LAYER):
        self.reply_channel = alias + ''.join([random.choice(string.ascii_letters) for _ in range(5)])
        self.alias = alias
        self._session = None
        self._headers = {}
        self._cookies = {}

    def set_cookie(self, key, value):
        """
        Set cookie
        """
        self._cookies[key] = value

    def set_header(self, key, value):
        """
        Set header
        """
        if key == 'cookie':
            raise ValueError('Use set_cookie method for cookie header')
        self._headers[key] = value

    def get_cookies(self):
        """Return cookies"""
        cookies = copy.copy(self._cookies)
        if apps.is_installed('django.contrib.sessions'):
            cookies[settings.SESSION_COOKIE_NAME] = self.session.session_key
        return cookies

    @property
    def headers(self):
        headers = copy.deepcopy(self._headers)
        headers.setdefault('cookie', _encoded_cookies(self.get_cookies()))
        return headers

    @property
    def session(self):
        """Session as Lazy property: check that django.contrib.sessions is installed"""
        if not apps.is_installed('django.contrib.sessions'):
            raise EnvironmentError('Add django.contrib.sessions to the INSTALLED_APPS to use session')
        if not self._session:
            self._session = session_for_reply_channel(self.reply_channel)
        return self._session

    def send(self, to, content={}):
        """
        Send a message to a channel.
        Adds reply_channel name and channel_session to the message.
        """
        content = copy.deepcopy(content)
        content.setdefault('reply_channel', self.reply_channel)
        content.setdefault('path', '/')
        content.setdefault('headers', self.headers)
        self.channel_layer.send(to, content)

    def login(self, **credentials):
        """
        Returns True if login is possible; False if the provided credentials
        are incorrect, or the user is inactive, or if the sessions framework is
        not available.
        """
        from django.contrib.auth import authenticate
        user = authenticate(**credentials)
        if user and user.is_active and apps.is_installed('django.contrib.sessions'):
            self._login(user)
            return True
        else:
            return False

    def force_login(self, user, backend=None):
        if backend is None:
            backend = settings.AUTHENTICATION_BACKENDS[0]
        user.backend = backend
        self._login(user)

    def _login(self, user):
        from django.contrib.auth import login

        # Fake http request
        request = type('FakeRequest', (object,), {'session': self.session, 'META': {}})
        login(request, user)

        # Save the session values.
        self.session.save()

    @property
    def channel_layer(self):
        return channel_layers[self.alias]

    def get_next_message(self, channel):
        recv_channel, content = channel_layers[self.alias].receive_many([channel])
        if recv_channel is None:
            return
        return Message(content, recv_channel, channel_layers[self.alias])

    def consume(self, channel):
        message = self.get_next_message(channel)
        if message:
            consumer, kwargs = self.channel_layer.router.match(message)
            return consumer(message, **kwargs)

    def send_and_consume(self, channel, content={}):
        self.send(channel, content)
        return self.consume(channel)

    def receive(self):
        message = self.get_next_message(self.reply_channel)
        if message:
            return message.content


def _encoded_cookies(cookies):
    """Encode dict of cookies to ascii string"""
    return ('&'.join('{0}={1}'.format(k, v) for k, v in cookies.items())).encode("ascii")


class apply_routes(object):

    def __init__(self, routes, aliases=[DEFAULT_CHANNEL_LAYER]):
        self._aliases = aliases
        self.routes = routes
        self._old_routing = {}

    def enter(self):
        for alias in self._aliases:
            channel_layer = channel_layers[DEFAULT_CHANNEL_LAYER]
            self._old_routing[alias] = channel_layer.routing
            if isinstance(self.routes, (list, tuple)):
                if isinstance(self.routes[0], (list, tuple)):
                    routes = list(map(include, self.routes))
                else:
                    routes = self.routes

            channel_layer.routing = routes
            channel_layer.router = Router(routes)

    def exit(self, exc_type=None, exc_val=None, exc_tb=None):
        for alias in self._aliases:
            channel_layer = channel_layers[DEFAULT_CHANNEL_LAYER]
            channel_layer.routing = self._old_routing[alias]
            channel_layer.router = Router(self._old_routing[alias])

    __enter__ = enter
    __exit__ = exit

    def __call__(self, test_func):
        if isinstance(test_func, type):
            old_setup = test_func.setUp
            old_teardown = test_func.tearDown

            def new_setup(this):
                self.enter()
                old_setup(this)

            def new_teardown(this):
                self.exit()
                old_teardown(this)

            test_func.setUp = new_setup
            test_func.tearDown = new_teardown
            return test_func
        else:
            @wraps(test_func)
            def inner(*args, **kwargs):
                with self:
                    return test_func(*args, **kwargs)
            return inner
