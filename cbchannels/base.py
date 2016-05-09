import six
from copy import copy
from functools import wraps
from channels import include, route, Channel, DEFAULT_CHANNEL_LAYER

_function = type(lambda: None)  # function class, use at isinstance


def consumer(name=None, **kwargs):
    """
    Decorator to mark class method as consumer
    """
    if isinstance(name, _function) and not kwargs:
        name._consumer = {'filter': {}}
        return name

    def wrap(func):
        func._consumer = {'filter': kwargs}
        return func
    return wrap


def apply_decorator(decorator):
    """Decorator for application decorator to consumers"""
    def _decorator(func):
        @wraps(func)
        def _wrap(self, *args, **kwargs):
            return decorator(self.__class__._wrap(func, this=self))(*args, **kwargs)
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
            if key in ['message', 'kwargs']:
                raise ValueError('Do not use "{}" key word at Consumers create'.format(key))
            setattr(self, key, value)

    @classmethod
    def _wrap(cls, func, init_kwargs=None, this=None):
        """
        Wrapper function for every consumer
        apply decorators and define self.message and self.kwargs
        """
        if getattr(func, '_wrapped', None):
            return func

        @wraps(func)
        def _consumer(message, **kwargs):
            self = this or cls(**init_kwargs)
            self.message = message
            self.reply_channel = getattr(message, 'reply_channel', None)
            self.kwargs = kwargs
            return func(self, message, **kwargs)

        for decorator in cls.decorators:
            _consumer = decorator(_consumer)

        _consumer._wrapped = True
        return _consumer

    def __get_filters(self):
        """Return filters for external channels"""
        filters = copy(self.filters) or {}
        if self.path:
            filters['path'] = self.path
        return filters

    def __get_consumers(self):
        """Generator yield internal consumers"""
        for attr_name, attr in self.__class__.__dict__.items():
            if hasattr(attr, '_consumer'):
                yield attr

    def __get_channel_name(self):
        """Return internal channel name with 'receive suffix'"""
        return '.'.join([self.channel_name, 'receive'])

    # ROUTES API

    @classmethod
    def as_routes(cls, **kwargs):
        """
        Create includes of all consumers
        :param kwargs:
        :return: key words arguments such as `channel_name` or `path`
        """
        self = cls(**kwargs)
        external_routes = [
            route('websocket.connect', cls._wrap(cls.on_connect, kwargs)),
            route('websocket.disconnect', cls._wrap(cls.on_disconnect, kwargs)),
            route('websocket.receive', cls._wrap(cls.on_receive, kwargs)),
        ]
        internal_routes = []
        for _consumer in self.__get_consumers():
            r = route(self.__get_channel_name(),
                      cls._wrap(_consumer, kwargs),
                      **_consumer._consumer['filter'])
            internal_routes.append(r)
        if internal_routes:
            return include([include(external_routes, **self.__get_filters()), include(internal_routes)])
        return include(external_routes, **self.__get_filters())

    # BASE CONSUMERS

    def on_connect(self, message, **kwargs):
        """Consumer for connection at external channel"""
        pass

    def on_disconnect(self, message, **kwargs):
        """Consumer for disconnection at external channel"""
        pass

    def on_receive(self, message, **kwargs):
        """Consumer for receive at external channel"""
        if self.channel_name:
            content = copy(message.content)
            if self.reply_channel:
                content['reply_channel'] = message.reply_channel
            self.send(content)

    def send(self, content):
        """Send content to internal channel"""
        self.channel.send(content)

    @property
    def channel(self):
        """Return internal channel"""
        return Channel(self.__get_channel_name(), alias=self._channel_alias, channel_layer=self._channel_layer)


