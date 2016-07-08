
try:
    from django.channels import Group
    from django.channels.sessions import channel_session, http_session
except ImportError:
    from channels import Group
    from channels.sessions import channel_session, http_session

from ..base import consumer, WebsocketConsumers


class GroupMixin(object):
    group_name = None

    def get_group_name(self, **kwargs):
        return (self.group_name or self.channel_name).format(**kwargs)

    def get_group(self):
        return Group(self.get_group_name(**self.kwargs))

    def broadcast(self, content):
        self.get_group().send(content)


class GroupConsumers(GroupMixin, WebsocketConsumers):
    """
        Add reply_channel to the Group at connect and broadcast at receive

        Usage:

        class MyGroupConsumers(GroupConsumers):
            path = '(?P<id>\d+)'
            group_name = 'test_{id}'
        """

    def on_connect(self, message, **kwargs):
        super(GroupConsumers, self).on_connect(message, **kwargs)
        self.get_group().add(self.reply_channel)

    def on_disconnect(self, message, **kwargs):
        super(GroupConsumers, self).on_disconnect(message, **kwargs)
        self.get_group().discard(self.reply_channel)

    def on_receive(self, message, **kwargs):
        super(GroupConsumers, self).on_receive(message, **kwargs)
        self.broadcast(message.content)


class SessionMixin(object):
    """
    Add access to the user sessions (http and channels)
    """

    @classmethod
    def get_decorators(cls, **kwargs):
        decorators = super(SessionMixin, cls).get_decorators(**kwargs)
        decorators.append(http_session)
        decorators.append(channel_session)
        return decorators

    @property
    def session(self):
        return self.message.channel_session

    @property
    def http_session(self):
        return self.message.http_session


class PermissionMixin(object):
    permissions = []

    def _check_permission(self):
        for perm in self.permissions:
            if not perm(self):
                return False
        return True

    def on_receive(self, *args, **kwargs):
        if self._check_permission():
            super(PermissionMixin, self).on_receive(*args, **kwargs)


class RoomConsumers(SessionMixin, WebsocketConsumers):
    auth = False

    @property
    def user(self):
        if self.auth:
            return self.message.user

    @classmethod
    def get_decorators(cls, **kwargs):
        if cls.auth or kwargs.get('auth', False):
            from channels.auth import channel_session_user
            decorators = super(RoomConsumers, cls).get_decorators(**kwargs)
            decorators.append(channel_session_user)
            return decorators

    def on_connect(self, *args, **kwargs):
        if self.auth:
            from channels.auth import channel_session_user_from_http
            return channel_session_user_from_http(super(RoomConsumers, self).on_connect)(*args, **kwargs)

    def on_receive(self, *args, **kwargs):
        if self.auth and self.user:
            super(RoomConsumers, self).on_receive(*args, **kwargs)

    @property
    def room(self):
        return self.message.get('room') + self.message.content['path']

    @consumer(command="^join$")
    def join(self, message):
        self.session['rooms'].add(self.room)

    @consumer(command="^leave$")
    def leave(self, message):
        self.session['rooms'].remove(self.room)

    @consumer(command="^send$")
    def send(self, message):
        if self.room in self.session:
            self.room_group.send(self.get_room_message())

    def get_room_message(self):
        return {'text': self.message.content['text'], 'room': self.room, }

    @property
    def room_group(self):
        return Group(self.room)


class NoReceiveMixin(object):
    """
    Mixin - overwrite on_receive method as blank
    """

    def on_receive(self, message, **kwargs):
        pass
