from channels import Group
from .base import Consumers


class GroupMixin(object):
    group_name = None

    def get_group_name(self):
        return self.group_name or self.channel_name

    def group_send(self, content):
        Group(self.get_group_name(), alias=self.channel_alias, channel_layer=self.channel_layer) \
            .send(content)

    def on_connect(self, message, **kwargs):
        super(GroupMixin, self).on_connect(message, **kwargs)
        Group(self.get_group_name(), alias=self.channel_alias, channel_layer=self.channel_layer) \
            .add(self.reply_channel)

    def on_disconnect(self, message, **kwargs):
        super(GroupMixin, self).on_disconnect(message, **kwargs)
        Group(self.get_group_name(), alias=self.channel_alias, channel_layer=self.channel_layer) \
            .discard(self.reply_channel)

    def on_receive(self, message, **kwargs):
        super(GroupMixin, self).on_receive(message, **kwargs)
        self.group_send(message.content)


class GroupConsumers(GroupMixin, Consumers):
    pass


class ModelMixin(object):
    model = None
    queryset = None
    serializer = None

    def get_queryset(self):
        return self.queryset or self.model.objects.all()