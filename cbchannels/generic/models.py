from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core import serializers
from django.core.paginator import InvalidPage, Paginator
from django.utils.translation import ugettext as _

try:
    from django.channels import Group
except ImportError:
    from channels import Group

from ..base import Consumers
from ..exceptions import ConsumerError
from .base import GroupMixin


class SimpleSerializer(object):

    def __init__(self, instance, **kwargs):
        self.instance = instance
        self.kwargs = kwargs

    @property
    def data(self):
        return serializers.serialize(self.kwargs.get('format', 'json'), [self.instance])


class SingleObjectMixin(object):
    model = None
    queryset = None
    slug_field = 'pk'
    slug_path_kwarg = 'pk'

    def get_queryset(self):
        return self.queryset or self.model._default_manager.all()

    @property
    def instance(self):
        queryset = self.get_queryset()
        slug = self.kwargs.get(self.slug_path_kwarg)

        queryset = queryset.filter(**{self.slug_field: slug})
        try:
            return queryset.get()
        except queryset.model.DoesNotExist:
            raise ConsumerError(_("No %(verbose_name)s found matching the query") %
                                {'verbose_name': queryset.model._meta.verbose_name})


class ObjectSubscribeConsumers(GroupMixin, SingleObjectMixin, Consumers):
    serializer = SimpleSerializer
    _group_name = '{i.__module__}_{i.__class__.__name__}_{slug_field}_{cls}'

    def get_group_name(self, **kwargs):
        return self.get_group_name_for_instance(self.instance)

    @classmethod
    def get_group_name_for_instance(cls, instance):
        return cls._group_name.format(i=instance, slug_field=getattr(instance, cls.slug_field), cls=cls.__name__)

    @classmethod
    def as_routes(cls, **kwargs):
        receiver(post_save, sender=cls.model or cls.queryset.model)(cls._post_save)
        return super(ObjectSubscribeConsumers, cls).as_routes(**kwargs)

    def _get_channel_name(self):
        self.channel_name = self.channel_name or self.get_group_name()
        return super(ObjectSubscribeConsumers, self)._get_channel_name()

    @classmethod
    def _post_save(cls, sender, instance, created, **kwargs):
        _model_data = cls.serializer(instance).data
        data = {"created" if created else "updated": _model_data}
        Group(cls.get_group_name_for_instance(instance), alias=cls._channel_alias,
              channel_layer=cls._channel_layer).send(data)

    def on_connect(self, message, **kwargs):
        super(ObjectSubscribeConsumers, self).on_connect(message, **kwargs)
        self.get_group().add(self.reply_channel)

    def on_disconnect(self, message, **kwargs):
        super(ObjectSubscribeConsumers, self).on_disconnect(message, **kwargs)
        self.get_group().discard(self.reply_channel)


class MultipleObjectMixin(object):
    queryset = None
    model = None
    paginate_by = None
    paginate_orphans = 0
    context_object_name = None
    paginator_class = Paginator
    page_kwarg = 'page'
    ordering = None

    def get_queryset(self):
        return self.queryset or self.model._default_manager.all()

    def paginate_queryset(self):
        queryset = self.get_queryset()
        paginator = self.paginator_class(queryset, self.paginate_by, self.paginate_orphans)
        page = self.kwargs.get(self.page_kwarg)
        try:
            page_number = int(page)
        except ValueError:
            if page == 'last':
                page_number = paginator.num_pages
            else:
                raise ConsumerError(_("Page is not 'last', nor can it be converted to an int."))
        try:
            page = paginator.page(page_number)
            return (paginator, page, page.object_list, page.has_other_pages())
        except InvalidPage as e:
            raise ConsumerError(_('Invalid page (%(page_number)s): %(message)s') % {
                'page_number': page_number,
                'message': str(e)
            })


class ModelSubscribeConsumers(GroupMixin, Consumers):
    serializer = SimpleSerializer
    _group_name = '{m.__module__}.{m.__name__}.{cls.__module__}.{cls.__name__}'

    @classmethod
    def get_group_name(cls, **kwargs):
        return cls._group_name.format(m=cls.model or cls.queryset.model)

    @classmethod
    def as_routes(cls, **kwargs):
        receiver(post_save, sender=cls.model or cls.queryset.model)(cls._post_save)
        return super(ModelSubscribeConsumers, cls).as_routes(**kwargs)

    def _get_channel_name(self):
        self.channel_name = self.channel_name or self.get_group_name(self)
        return super(ModelSubscribeConsumers, self)._get_channel_name()

    @classmethod
    def _post_save(cls, sender, instance, created, **kwargs):
        if cls.queryset:
            if not cls.queryset.get(pk=instance.pk):
                return
        _model_data = cls.serializer(instance).data
        data = {"created" if created else "updated": _model_data}
        Group(cls.get_group_name(), alias=cls._channel_alias,
              channel_layer=cls._channel_layer).send(data)

    def on_connect(self, message, **kwargs):
        super(ModelSubscribeConsumers, self).on_connect(message, **kwargs)
        self.get_group().add(self.reply_channel)

    def on_disconnect(self, message, **kwargs):
        super(ModelSubscribeConsumers, self).on_disconnect(message, **kwargs)
        self.get_group().discard(self.reply_channel)
