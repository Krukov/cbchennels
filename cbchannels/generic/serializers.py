import json

from django.core import serializers
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import model_to_dict


class SimpleSerializer(object):

    def __init__(self, instance=None, data=None, **kwargs):
        self.instance = instance
        self._data = data
        self._validated_data = None
        self.kwargs = kwargs

    @property
    def data(self):
        if not self._data:
            data = model_to_dict(self.instance, **self.kwargs)
            if data:
                self._data = json.dumps(data, cls=DjangoJSONEncoder)
        return self._data

    def is_valid(self):
        self._validated_data = json.loads(self.data)
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
