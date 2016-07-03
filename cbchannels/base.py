from __future__ import unicode_literals

import json
from inspect import isfunction
from copy import copy
from functools import wraps

import six

try:
    from django.channels import include, route, Channel, DEFAULT_CHANNEL_LAYER
except ImportError:
    from channels import include, route, Channel, DEFAULT_CHANNEL_LAYER

from .exceptions import ConsumerError


def consumer(channel_name=None, **kwargs):
    """
    Decorator to mark class method as consumer
    """
    if isfunction(channel_name) and not kwargs:
        channel_name._consumer = {'filter': {}}
        return channel_name

    def wrap(func):
        func._consumer = {'filter': kwargs, 'channel_name': channel_name}
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
    decorators = []
    _channel_layer = None
    _channel_alias = DEFAULT_CHANNEL_LAYER

    def __init__(self, message=None, kwargs={}, **init_kwargs):
        self.message = message
        self.reply_channel = getattr(message, 'reply_channel', None)
        self.kwargs = copy(kwargs) or {}
        self.kwargs.update(message.content.get('_kwargs', {}))

        self._init_kwargs = init_kwargs
        for key, value in six.iteritems(init_kwargs):
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
            self = this or cls(message, kwargs, **init_kwargs)
            try:
                return func(self, message, **kwargs)
            except ConsumerError as e:
                self.send({'error': str(e)})

        for decorator in cls.get_decorators():
            _consumer = decorator(_consumer)

        _consumer._wrapped = True
        return _consumer

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
        if 'channel_name' in kwargs:
            return kwargs['channel_name']
        if cls.channel_name:
            return cls.channel_name
        raise ValueError('Set channel_name for consumers %s',  cls)

    # ROUTES API

    @classmethod
    def as_routes(cls, **kwargs):
        """
        Create includes of all consumers
        :param kwargs:
        :return: key words arguments such as `channel_name` or `path`
        """
        _routes = []
        for _consumer in cls._get_consumers():
            name = (_consumer._consumer.get('channel_name', None) or
                    kwargs.get('channel_name') or cls._get_channel_name(**kwargs))
            if callable(name):
                name = name(cls, **kwargs)
            filters = {key: value(cls, **kwargs) if callable(value) else value for key, value
                       in _consumer._consumer['filter'].items()}
            _routes.append(route(name, cls._wrap(_consumer, kwargs), **filters))
        return include(_routes)

    # BASE CONSUMERS

    @property
    def channel(self):
        """Return internal channel"""
        return Channel(self.get_channels_name(),
                       alias=self._channel_alias,
                       channel_layer=self._channel_layer)

    def get_channels_name(self):
        return self._get_channel_name(**self._init_kwargs)

    @classmethod
    def get_decorators(cls):
        return cls.decorators[:]

    def reply(self, content):
        self.message.reply_channel.send({"text": json.dumps(content)})


def _get_path(cls, **kwargs):
    return kwargs.get('path', cls.path)


class WebsocketConsumers(Consumers):
    path = ''

    @consumer('websocket.connect', path=_get_path)
    def ws_connect(self, message, **kwargs):
        return self.on_connect(message, **kwargs)

    @consumer('websocket.disconnect', path=_get_path)
    def ws_disconnect(self, message, **kwargs):
        return self.on_disconnect(message, **kwargs)

    @consumer('websocket.receive', path=_get_path)
    def ws_receive(self, message, **kwargs):
        return self.on_receive(message, **kwargs)

    def on_connect(self, message, **kwargs):
        """Consumer for connection at external channel"""
        pass

    def on_disconnect(self, message, **kwargs):
        """Consumer for disconnection at external channel"""
        pass

    def on_receive(self, message, **kwargs):
        """Consumer for receive message to the external channel"""
        if self.get_channels_name():
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

