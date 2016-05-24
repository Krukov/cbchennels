import six
from copy import copy
from functools import wraps

try:
    from django.channels import include, route, Channel, DEFAULT_CHANNEL_LAYER
except ImportError:
    from channels import include, route, Channel, DEFAULT_CHANNEL_LAYER

from .exceptions import ConsumerError

_function = type(lambda: None)  # function class, use at isinstance


def consumer(_func=None, **kwargs):
    """
    Decorator to mark class method as consumer
    """
    if isinstance(_func, _function) and not kwargs:
        _func._consumer = {'filter': {}}
        return _func

    def wrap(func):
        func._consumer = {'filter': kwargs}
        return func
    return wrap


def apply_decorator(decorator):
    """Decorator for application decorator to consumers"""
    def _decorator(func):
        @wraps(func)
        def _wrap(self, *args, **kwargs):
            return decorator(self.__class__._wrap(func,
                                                  this=self))(*args, **kwargs)
        return _wrap
    return _decorator


class Consumers(object):
    """Basic class for Class Base Consumers"""
    channel_name = None
    filters = None  # filters for ws channels (external)
    path = ''
    decorators = []
    _channel_layer = None
    _channel_alias = DEFAULT_CHANNEL_LAYER

    def __init__(self, **kwargs):
        self.message = self.reply_channel = self.kwargs = None
        self._init_kwargs = kwargs
        for key, value in six.iteritems(kwargs):
            if key in ['message', 'kwargs', 'reply_channel']:
                raise ValueError('Do not use "{}" key word at '
                                 'Consumers create'.format(key))
            setattr(self, key, value)

    @classmethod
    def _wrap(cls, func, init_kwargs=None, this=None):
        """
        Wrapper function for every consumer
        apply decorators and define message, kwargs and reply_channel
        """
        if getattr(func, '_wrapped', None):
            return func

        @wraps(func)
        def _consumer(message, **kwargs):
            self = this or cls(**init_kwargs)
            self.message = message
            self.reply_channel = getattr(message, 'reply_channel', None)
            self.kwargs = copy(kwargs) or {}
            self.kwargs.update(message.content.get('_kwargs', {}))
            try:
                return func(self, message, **kwargs)
            except ConsumerError as e:
                self.send({'error': str(e)})

        for decorator in cls.get_decorators():
            _consumer = decorator(_consumer)

        _consumer._wrapped = True
        return _consumer

    @classmethod
    def _get_filters(cls, **kwargs):
        """Return filters for external channels"""
        filters = copy(kwargs.get('filters', None)) or copy(cls.filters) or {}
        path = kwargs.get('path', cls.path)
        if path:
            filters['path'] = path
        return filters

    @classmethod
    def _get_consumers(cls):
        """Generator yield internal consumers"""
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name)
            if hasattr(attr, '_consumer'):
                yield attr

    @classmethod
    def _get_channel_name(cls, **kwargs):
        """Return internal channel name"""

        if not cls.channel_name:
            raise ValueError('Set channel_name for consumers %s',  cls)
        return cls.channel_name

    # ROUTES API

    @classmethod
    def as_routes(cls, **kwargs):
        """
        Create includes of all consumers
        :param kwargs:
        :return: key words arguments such as `channel_name` or `path`
        """
        external_routes = [
            route('websocket.connect', cls._wrap(cls.on_connect, kwargs)),
            route('websocket.disconnect', cls._wrap(cls.on_disconnect, kwargs)),
            route('websocket.receive', cls._wrap(cls.on_receive, kwargs)),
        ]
        internal_routes = []
        for _consumer in cls._get_consumers():
            r = route(kwargs.get('channel_name') or cls._get_channel_name(**kwargs),
                      cls._wrap(_consumer, kwargs),
                      **_consumer._consumer['filter'])
            internal_routes.append(r)
        if internal_routes:
            return include([include(external_routes, **cls._get_filters(**kwargs)), include(internal_routes)])
        return include(external_routes, **cls._get_filters(**kwargs))

    # BASE CONSUMERS

    def on_connect(self, message, **kwargs):
        """Consumer for connection at external channel"""
        pass

    def on_disconnect(self, message, **kwargs):
        """Consumer for disconnection at external channel"""
        pass

    def on_receive(self, message, **kwargs):
        """Consumer for receive at external channel"""
        if self._get_channel_name():
            content = copy(message.content)
            if self.reply_channel:
                content['reply_channel'] = message.reply_channel
            if isinstance(content.get('reply_channel', None), Channel):
                content['reply_channel'] = content['reply_channel'].name
            if self.kwargs:
                content['_kwargs'] = self.kwargs
            self.send(content)

    def send(self, content):
        """Send content to internal channel"""
        self.channel.send(content)

    @property
    def channel(self):
        """Return internal channel"""
        return Channel(self._get_channel_name(**self._init_kwargs),
                       alias=self._channel_alias,
                       channel_layer=self._channel_layer)

    @classmethod
    def get_decorators(cls):
        return cls.decorators[:]
