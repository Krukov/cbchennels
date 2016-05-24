import copy
import json
import hashlib
from functools import partial

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.forms.models import model_to_dict
from django.core import serializers
from django.core.serializers.json import DjangoJSONEncoder
from django.core.paginator import InvalidPage, Paginator
from django.utils.translation import ugettext as _

try:
    from django.channels import Group
except ImportError:
    from channels import Group

from ..base import Consumers, consumer
from ..exceptions import ConsumerError
from .base import GroupMixin


def _md5(message):
    md5 = hashlib.md5()
    md5.update(message.encode())
    return md5.hexdigest()


class SimpleSerializer(object):

    def __init__(self, instance=None, data=None, **kwargs):
        self.instance = instance
        self._data = data
        self._validated_data = None
        self.kwargs = kwargs

    @property
    def data(self):
        return json.dumps(model_to_dict(self.instance, **self.kwargs), cls=DjangoJSONEncoder)

    def is_valid(self):
        self._validated_data = json.loads(self.data, cls=DjangoJSONEncoder)
        return True

    @property
    def validated_data(self):
        return self._validated_data


class DjangoSerializer(SimpleSerializer):

    @property
    def data(self):
        if not self._data:
            self._data = serializers.serialize(self.kwargs.get('format', 'json'), [self.instance], **self.kwargs)
        return self._data

    def is_valid(self):
        self._validated_data = serializers.deserialize(self.kwargs.get('format', 'json'), self.data, **self.kwargs)
        return True


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
    serializer_class = SimpleSerializer
    serializer_kwargs = {}
    _group_name = '{i.__module__}_{i.__class__.__name__}_{slug_field}_{uid}'
    _uid = None

    def get_group_name(self, **kwargs):
        return self.get_group_name_for_instance(
            (self.model or self.queryset.model)(**{self.slug_field: self.kwargs[self.slug_path_kwarg]}),
            self._uid
        )

    @classmethod
    def get_group_name_for_instance(cls, instance, uid):
        return cls._group_name.format(i=instance, slug_field=getattr(instance, cls.slug_field), uid=uid)

    @classmethod
    def as_routes(cls, **kwargs):
        if 'queryset' in kwargs:
            model = kwargs['queryset'].model
        else:
            model = kwargs.get('model') or cls.model or cls.queryset.model
        dispatch_uid = _md5(str(cls) + str(kwargs))
        kwargs['_uid'] = dispatch_uid
        receiver(post_save, sender=model, weak=False, dispatch_uid=dispatch_uid)(partial(cls._post_save, **kwargs))
        return super(ObjectSubscribeConsumers, cls).as_routes(**kwargs)

    def _get_channel_name(self):
        self.channel_name = self.channel_name or self.get_group_name()
        return super(ObjectSubscribeConsumers, self)._get_channel_name()

    @classmethod
    def _post_save(cls, sender, instance, created, update_fields, _uid, **kwargs):
        serializer_kwargs = copy.deepcopy(cls.serializer_kwargs)
        serializer_kwargs.update(kwargs.get('serializer_kwargs', {}))
        if 'fields' in serializer_kwargs and update_fields:
            serializer_kwargs['fields'] = set(serializer_kwargs['fields']).intersection(update_fields)

        _model_data = cls.serializer_class(instance, **serializer_kwargs).data
        data = {"created" if created else "updated": _model_data}
        Group(cls.get_group_name_for_instance(instance, uid=_uid), alias=cls._channel_alias,
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
    serializer_class = SimpleSerializer
    _group_name = '{m.__module__}.{m.__name__}.{cls.__module__}.{cls.__name__}'

    @classmethod
    def get_group_name(cls, **kwargs):
        return cls._group_name.format(m=cls.model or cls.queryset.model)

    @classmethod
    def as_routes(cls, **kwargs):
        if 'queryset' in kwargs:
            model = kwargs['queryset'].model
        else:
            model = kwargs.get('model') or cls.model or cls.queryset.model
        receiver(post_save, sender=model)(cls._post_save)
        return super(ModelSubscribeConsumers, cls).as_routes(**kwargs)

    def _get_channel_name(self):
        self.channel_name = self.channel_name or self.get_group_name(self)
        return super(ModelSubscribeConsumers, self)._get_channel_name()

    @classmethod
    def _post_save(cls, sender, instance, created, **kwargs):
        if cls.queryset:
            if not cls.queryset.get(pk=instance.pk):
                return
        _model_data = cls.serializer_class(instance).data
        data = {"created" if created else "updated": _model_data}
        Group(cls.get_group_name(), alias=cls._channel_alias,
              channel_layer=cls._channel_layer).send(data)

    def on_connect(self, message, **kwargs):
        super(ModelSubscribeConsumers, self).on_connect(message, **kwargs)
        self.get_group().add(self.reply_channel)

    def on_disconnect(self, message, **kwargs):
        super(ModelSubscribeConsumers, self).on_disconnect(message, **kwargs)
        self.get_group().discard(self.reply_channel)


class CreateMixin(SingleObjectMixin):
    serializer_class = SimpleSerializer

    @consumer(action='create', data='.+')
    def create(self, message):
        serializer = self.serializer_class(data=message.content['data'])
        if serializer.is_valid():
            self.get_queryset().model._default_manager.create(**serializer.validated_data)
        self.reply_channel.send({'response': 'ok'})


class GetMixin(SingleObjectMixin):
    serializer_class = SimpleSerializer

    @consumer(action='get')
    def get(self, message):
        self.reply_channel.send({'response': self.serializer_class(instance=self.instance).data})


class UpdateMixin(SingleObjectMixin):
    serializer_class = SimpleSerializer

    @consumer(action='update', data='.+')
    def update(self, message):
        serializer = self.serializer_class(data=message.content['data'])
        if serializer.is_valid():
            pass
        self.reply_channel.send({'response': 'ok'})


class DeleteMixin(SingleObjectMixin):

    @consumer(action='delete')
    def delete(self, message):
        self.instance.delete()
        self.reply_channel.send({'response': 'ok'})
