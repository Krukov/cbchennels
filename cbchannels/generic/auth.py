
try:
    from django.channels.auth import (channel_session_user_from_http,
                                      channel_session_user)
    from django.channels.sessions import channel_session
except ImportError:
    from channels.auth import (channel_session_user_from_http,
                               channel_session_user)
    from channels.sessions import channel_session


class UserMixin(object):

    @classmethod
    def get_decorators(cls, **kwargs):
        decorators = super(UserMixin, cls).get_decorators(**kwargs)
        decorators.append(channel_session_user)
        if channel_session in decorators:
            # channel_session_user already include channel_session decorator
            decorators.remove(channel_session)
        return decorators

    def on_connect(self, *args, **kwargs):
        return channel_session_user_from_http(super(UserMixin, self).on_connect)(*args, **kwargs)

    @property
    def user(self):
        return self.message.user
