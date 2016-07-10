from __future__ import unicode_literals

import json
from inspect import isfunction
from copy import copy
from functools import wraps

import six

try:
    from django.channels import include, route, Channel
except ImportError:
    from channels import include, route, Channel

from .exceptions import ConsumerError


def consumer(channel_name=None, decorators=[], **kwargs):
    """
    Decorator to mark class method as consumer
    """
    if isfunction(channel_name) and not kwargs:
        channel_name._consumer = {'filter': {}, 'decorators': []}
        return channel_name

    def wrap(func):
        func._consumer = {'filter': kwargs, 'channel_name': channel_name, 'decorators': decorators}
        return func
    return wrap


class Consumers(object):
    """Basic class for Class Base Consumers"""
    channel_name = None
    decorators = []

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
    def _wrap(cls, func, init_kwargs=None):
        """
        Wrapper function for every consumer
        apply decorators and define message, kwargs and reply_channel
        """
        if getattr(func, '_wrapped', None):
            return func

        @wraps(func)
        def _consumer(message, **kwargs):
            self = cls(message, kwargs, **init_kwargs)
            try:
                return func(self, message, **kwargs)
            except Exception as e:
                self.at_exception(e)

        for decorator in cls.get_decorators(**init_kwargs):
            _consumer = decorator(_consumer)

        for decorator in func._consumer['decorators']:
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

    @classmethod
    def _get_filter_value(cls, consumer, key, **kwargs):
        """
        Return filter value for given consumer and key
        """
        return cls._get_callable_value(consumer._consumer['filter'][key], **kwargs)

    @classmethod
    def _get_callable_value(cls, value, **kwargs):
        if callable(value):
            return value(cls, **kwargs)
        if isinstance(value, classmethod):
            return getattr(cls, value.__func__.__name__)(**kwargs)
        if isinstance(value, staticmethod):
            return value.__func__(**kwargs)
        return value

    @classmethod
    def _get_channel_name_for_consumer(cls, consumer, **kwargs):
        value = consumer._consumer.get('channel_name', None)
        return cls._get_callable_value(value, **kwargs) or kwargs.get('channel_name') or cls._get_channel_name(**kwargs)

    def at_exception(self, e):
        if isinstance(e, ConsumerError):
            return self.reply({'error': str(e)})
        raise e

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
            name = cls._get_channel_name_for_consumer(_consumer, **kwargs)
            if callable(name):
                name = name(cls, **kwargs)
            filters = {key: cls._get_filter_value(_consumer, key, **kwargs) for key
                       in _consumer._consumer['filter'].keys()}
            _routes.append(route(name, cls._wrap(_consumer, kwargs), **filters))
        return include(_routes)

    # BASE CONSUMERS

    def get_channel_name(self):
        return self._get_channel_name(**self._init_kwargs)

    @classmethod
    def get_decorators(cls, **kwargs):
        return copy(cls.decorators)

    def reply(self, content):
        self.reply_channel.send(content)


class WebsocketConsumers(Consumers):
    path = ''

    @classmethod
    def _get_path(cls, **kwargs):
        return kwargs.get('path', cls.path)

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
        pass

    def on_disconnect(self, message, **kwargs):
        pass

    def on_receive(self, message, **kwargs):
        if self.get_channel_name():
            content = copy(message.content)
            if self.reply_channel:
                content['reply_channel'] = message.reply_channel
            if isinstance(content.get('reply_channel', None), Channel):
                content['reply_channel'] = content['reply_channel'].name
            if self.kwargs:
                content['_kwargs'] = self.kwargs
            self.send(content)

    @property
    def channel(self):
        return Channel(self.get_channel_name())

    def send(self, content):
        """Send content to internal channel"""
        self.channel.send(content)

    def reply(self, text):
        super(WebsocketConsumers, self).reply({"text": json.dumps(text)})
