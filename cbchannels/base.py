import six
from copy import copy
from functools import wraps
from channels import include, route, Channel, DEFAULT_CHANNEL_LAYER

function = type(lambda: None)  # function class, use at isinstance


def consumer(name=None, **kwargs):
    """
    Decorator to mark class method as consumer
    """
    if isinstance(name, function) and not kwargs:
        name._consumer = {'name': name.__name__, 'filter': {}}
        return name

    def wrap(func):
        func._consumer = {'name': name or func.__name__, 'filter': kwargs}
        return func
    return wrap


def apply_decorator(decorator):
    def _decorator(func):
        @wraps(func)
        def _wrap(self, *args, **kwargs):
            return decorator(self.__class__._wrap(func, self._init_kwargs))(*args, **kwargs)
        return _wrap
    return _decorator


class Consumers(object):
    """Basic class for Class Base Consumers"""
    channel_name = None
    channel_sub_name = ['receive', ]
    filters = None
    path = ''
    channel_layer = None
    channel_alias = DEFAULT_CHANNEL_LAYER
    decorators = []
    _base_consumers = ['connect', 'disconnect', 'receive']
    _base = 'websocket'

    def __init__(self, **kwargs):
        self.message = self.reply_channel = self.kwargs = None
        self._init_kwargs = kwargs
        for key, value in six.iteritems(kwargs):
            if key in ['message', 'kwargs']:
                raise ValueError('Do not use "{}" key word at Consumers create'.format(key))
            setattr(self, key, value)

    @classmethod
    def _wrap(cls, func, init_kwargs):
        """
        Wrapper function for every consumer
        apply decorators and define self.message and self.kwargs
        """
        if getattr(func, '_wrapped', None):
            return func

        @wraps(func)
        def _consumer(message, **kwargs):
            self = cls(**init_kwargs)
            self.message = message
            self.reply_channel = getattr(message, 'reply_channel', None)
            self.kwargs = kwargs
            return func(self, message, **kwargs)

        for decorator in cls.get_decorators():
            _consumer = decorator(_consumer)

        _consumer._wrapped = True
        return _consumer

    @classmethod
    def as_consumer(cls, name, **kwargs):
        """
        Create consumer with given name and given kwargs
        :param name: name of consumer
        :param kwargs: key words arguments such as `channel_name` or `path`
        :return: func: consumer itself
        """
        return cls._wrap(cls._get(name), kwargs)

    @classmethod
    def as_routes(cls, **kwargs):
        """
        Create includes of all consumers
        :param kwargs:
        :return: key words arguments such as `channel_name` or `path`
        """
        self = cls(**kwargs)
        ws_routes = [route(cls._base + '.' + name, cls.as_consumer(name, **kwargs)) for name in cls._base_consumers]
        receive_routes = []
        for _consumer in self:
            r = route(self.get_channel_name(),
                      cls.as_consumer(_consumer._consumer['name'], **kwargs),
                      **_consumer._consumer['filter'])
            receive_routes.append(r)
        if receive_routes:
            return include([include(ws_routes, **self.get_filters()), include(receive_routes)])
        return include(ws_routes, **self.get_filters())

    def get_filters(self):
        filters = copy(self.filters) or {}
        if self.path:
            filters['path'] = self.path
        return filters

    @classmethod
    def get_decorators(cls):
        return cls.decorators[:]

    @classmethod
    def _get(cls, name):
        if name in cls._base_consumers:
            return getattr(cls, 'on_' + name)
        for attr_name, attr in cls.__dict__.items():
            if hasattr(attr, '_consumer') and attr._consumer['name'] == name:
                return attr

    def __iter__(self):
        for attr_name, attr in self.__class__.__dict__.items():
            if hasattr(attr, '_consumer'):
                yield attr

    def on_connect(self, message, **kwargs):
        pass

    def on_disconnect(self, message, **kwargs):
        pass

    def on_receive(self, message, **kwargs):
        if self.channel_name:
            content = copy(message.content)
            if self.reply_channel:
                content['reply_channel'] = message.reply_channel
            self.send(content)

    def send(self, content):
        content = self.on_send(content)
        self.channel.send(content)

    def on_send(self, content):
        return content

    def get_channel_name(self):
        name = [self.channel_name, ]
        name.extend(self.channel_sub_name)
        return '.'.join(name)

    @property
    def channel(self):
        return Channel(self.get_channel_name(), alias=self.channel_alias, channel_layer=self.channel_layer)


