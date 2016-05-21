
try:
    from django.channels.auth import channel_session_user_from_http, channel_session_user
    from django.channels.sessions import channel_session, http_session
except ImportError:
    from channels.auth import channel_session_user_from_http, channel_session_user
    from channels.sessions import channel_session, http_session

from ..base import apply_decorator


class UserMixin(object):

    @classmethod
    def get_decorators(cls):
        decorators = super(UserMixin, cls).get_decorators()
        decorators.append(channel_session_user)
        if channel_session in decorators:
            decorators.remove(channel_session)  # channel_session_user already include channel_session decorator
        return decorators

    @apply_decorator(channel_session_user_from_http)
    def on_connect(self, *args, **kwargs):
        return super(UserMixin, self).on_connect(*args, **kwargs)

    @property
    def user(self):
        return self.message.user
