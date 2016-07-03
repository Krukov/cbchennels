import copy
import hashlib
from functools import partial

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.paginator import InvalidPage, Paginator
from django.utils.functional import cached_property
from django.utils.translation import ugettext as _

try:
    from django.channels import Group
except ImportError:
    from channels import Group

from ..base import WebsocketConsumers, consumer
from ..exceptions import ConsumerError
from .base import GroupMixin, NoReceiveMixin
from .serializers import SimpleSerializer


def _md5(message):
    """
    Calculate md5 hash of message
    """
    md5 = hashlib.md5()
    md5.update(message.encode())
    return md5.hexdigest()


class SingleObjectMixin(object):
    """
    Mixin Provides the ability to retrieve a single object for further manipulation.
    """
    model = None
    queryset = None
    slug_field = 'pk'
    slug_path_kwarg = 'pk'
    _channel_name_template = '{i.__module__}_{i.__name__}_{slug_field}'

    @classmethod
    def _get_channel_name(cls, **kwargs):
        try:
            return super(SingleObjectMixin, cls)._get_channel_name(**kwargs)
        except ValueError:
            pass

        if 'queryset' in kwargs:
            model = kwargs['queryset'].model
        else:
            model = kwargs.get('model') or cls.model or cls.queryset.model
        t = cls._channel_name_template
        return cls.channel_name or t.format(i=model, slug_field=kwargs.get('slug_field', cls.slug_field))

    def get_queryset(self):
        return self.queryset or self.model._default_manager.all()

    @cached_property
    def instance(self):
        queryset = self.get_queryset()
        slug = self.kwargs.get(self.slug_path_kwarg)

        queryset = queryset.filter(**{self.slug_field: slug})
        try:
            return queryset.get()
        except queryset.model.DoesNotExist:
            raise ConsumerError(_("No %(verbose_name)s found matching the query") %
                                {'verbose_name': queryset.model._meta.verbose_name})


class SerializerMixin(object):
    """
    Mixin Provides the ability to use serializers.
    """
    serializer_class = SimpleSerializer
    serializer_kwargs = {}

    def get_serializer(self, **kwargs):
        kwargs.update(self.serializer_kwargs)
        return self.serializer_class(**kwargs)


class ObjectSubscribeConsumers(NoReceiveMixin, GroupMixin, SingleObjectMixin, WebsocketConsumers):
    """
    Consumers collection which Provides the ability to subscribe for object changes
    """
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

    @classmethod
    def _post_save(cls, sender, instance, created, update_fields, _uid, **kwargs):
        serializer_kwargs = copy.deepcopy(cls.serializer_kwargs)
        serializer_kwargs.update(kwargs.get('serializer_kwargs', {}))
        if 'fields' in serializer_kwargs and update_fields:
            serializer_kwargs['fields'] = set(serializer_kwargs['fields']).intersection(update_fields) or ['_']

        _model_data = cls.serializer_class(instance, **serializer_kwargs).data
        if _model_data:
            data = {"created" if created else "updated": _model_data}
            Group(cls.get_group_name_for_instance(instance, uid=_uid)).send(data)

    def on_connect(self, message, **kwargs):
        super(ObjectSubscribeConsumers, self).on_connect(message, **kwargs)
        self.get_group().add(self.reply_channel)

    def on_disconnect(self, message, **kwargs):
        super(ObjectSubscribeConsumers, self).on_disconnect(message, **kwargs)
        self.get_group().discard(self.reply_channel)


class MultipleObjectMixin(object):
    """
    Mixin Provides the ability to retrieve collection of objects for further manipulation
    """
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


class ModelSubscribeConsumers(NoReceiveMixin, SingleObjectMixin, GroupMixin, WebsocketConsumers):
    """
    Consumers collection which Provides the ability to subscribe for models updates ()
    """
    serializer_class = SimpleSerializer
    serializer_kwargs = {}
    _group_name = '{m.__module__}.{m.__name__}.{uid}'
    _uid = None

    @classmethod
    def get_group_name_for_model(cls, model, uid):
        return cls._group_name.format(m=model, uid=uid)

    def get_group_name(self, **kwargs):
        return self.get_group_name_for_model(self.model or self.queryset.model, uid=self._uid)

    @classmethod
    def as_routes(cls, **kwargs):
        if 'queryset' in kwargs:
            model = kwargs['queryset'].model
        else:
            model = kwargs.get('model') or cls.model or cls.queryset.model
        dispatch_uid = _md5(str(cls) + str(kwargs))
        kwargs['_uid'] = dispatch_uid
        kwargs.setdefault('queryset', cls.queryset)
        receiver(post_save, sender=model, weak=False, dispatch_uid=dispatch_uid)(partial(cls._post_save, **kwargs))
        return super(ModelSubscribeConsumers, cls).as_routes(**kwargs)

    def get_channels_name(self):
        self.channel_name = self.channel_name or self.get_group_name()
        return super(ModelSubscribeConsumers, self).get_channels_name()

    @classmethod
    def _post_save(cls, sender, instance, created, update_fields, _uid, **kwargs):
        if kwargs.get('queryset'):
            if not kwargs['queryset'].exists(pk=instance.pk):
                return
        serializer_kwargs = copy.deepcopy(cls.serializer_kwargs)
        serializer_kwargs.update(kwargs.get('serializer_kwargs', {}))
        if 'fields' in serializer_kwargs and update_fields:
            serializer_kwargs['fields'] = set(serializer_kwargs['fields']).intersection(update_fields) or ['_']

        _model_data = cls.serializer_class(instance, **serializer_kwargs).data
        if _model_data:
            data = {"created" if created else "updated": _model_data}

            Group(cls.get_group_name_for_model(sender, _uid), alias=cls._channel_alias,
                  channel_layer=cls._channel_layer).send(data)

    def on_connect(self, message, **kwargs):
        super(ModelSubscribeConsumers, self).on_connect(message, **kwargs)
        self.get_group().add(self.reply_channel)

    def on_disconnect(self, message, **kwargs):
        super(ModelSubscribeConsumers, self).on_disconnect(message, **kwargs)
        self.get_group().discard(self.reply_channel)


class CreateMixin(object):
    """
    Mixin - Adds the consumer that create object.
    Using with SerializerMixin and SingleObjectMixin
    """

    @consumer(action='create', data='.+')
    def create(self, message):
        serializer = self.get_serializer(data=message.content['data'])
        if serializer.is_valid():
            self.get_queryset().model._default_manager.create(**serializer.validated_data)
        self.reply_channel.send({'response': 'ok'})


class GetMixin(object):
    """
    Mixin - Adds the consumer that send to reply channel serializing object data.
    Using with SerializerMixin and SingleObjectMixin
    """

    @consumer(action='get')
    def get(self, message):
        self.reply_channel.send({'response': self.get_serializer(instance=self.instance).data})


class UpdateMixin(object):
    """
    Mixin - Adds the consumer that update object.
    Using with SerializerMixin and SingleObjectMixin
    """

    @consumer(action='update', data='.+')
    def update(self, message):
        serializer = self.get_serializer(instance=self.instance, data=message.content['data'])
        if serializer.is_valid():
            instance = self.instance
            for field, value in serializer.validated_data.items():
                setattr(instance, field, value)
            instance.save()
            self.reply_channel.send({'response': 'ok'})


class DeleteMixin(object):
    """
    Mixin - Adds consumer that delete object.
    Using with SerializerMixin and SingleObjectMixin
    """

    @consumer(action='delete')
    def delete(self, message):
        self.instance.delete()
        self.reply_channel.send({'response': 'ok'})


class CRUDConsumers(CreateMixin, GetMixin, UpdateMixin, DeleteMixin,
                    SerializerMixin, SingleObjectMixin, WebsocketConsumers):
    """
    Consumers collection - Provides base methods for object manipulations Create, Read, Update and Delete
    """


class ReadOnlyConsumers(GetMixin, SerializerMixin, SingleObjectMixin, WebsocketConsumers):
    pass


class CreateConsumers(CreateMixin, SerializerMixin, SingleObjectMixin, WebsocketConsumers):
    pass


class DeleteConsumers(DeleteMixin, SerializerMixin, SingleObjectMixin, WebsocketConsumers):
    pass


class UpdateConsumers(UpdateMixin, SerializerMixin, SingleObjectMixin, WebsocketConsumers):
    pass
