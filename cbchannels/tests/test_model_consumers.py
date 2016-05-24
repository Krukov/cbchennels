
import json
from channels.tests import ChannelTestCase

try:
    from channels.tests import HttpClient, apply_routes
except ImportError:
    # remove it soon
    from .features import apply_routes, HttpClient

from django.contrib.auth.models import User

from cbchannels.generic.models import ObjectSubscribeConsumers, ModelSubscribeConsumers
from cbchannels.generic.serializers import SimpleSerializer


class ModelsTestCase(ChannelTestCase):

    def test_serializer(self):
        obj = User.objects.create_user(username='test', email='t@t.tt')
        self.assertDictEqual(json.loads(SimpleSerializer(obj, fields=['username', 'email']).data),
                             {'email': 't@t.tt', 'username': 'test'})

        self.assertEqual(json.loads(SimpleSerializer(obj).data)['username'], 'test')
        self.assertEqual(json.loads(SimpleSerializer(obj).data)['email'], 't@t.tt')
        self.assertEqual(json.loads(SimpleSerializer(obj).data)['is_active'], True)

    def test_object_sub(self):

        # create object for subscribe
        sub_object = User.objects.create_user(username='test', email='t@t.tt')

        # create object without subscribers
        just_object = User.objects.create_user(username='test2', email='t2@t.tt')

        # define consumers
        routes = ObjectSubscribeConsumers.as_routes(path='/(?P<pk>\d+)/?', model=User)

        # create client
        client = HttpClient()
        with apply_routes([routes]):
            # subscribe for object changes
            client.send_and_consume(u'websocket.connect', content={'path': '/{}'.format(sub_object.pk)})

            # change sub object
            sub_object.username = 'sub_object'
            sub_object.email = 'new@email.com'
            sub_object.save()
            res = json.loads(client.receive()['updated'])
            self.assertEqual(res['username'], 'sub_object')
            self.assertEqual(res['email'], 'new@email.com')
            self.assertEqual(res['is_staff'], False)

            # change second object
            just_object.email = 'test@new.mail'
            just_object.save()

            # check that nothing happened
            self.assertIsNone(client.receive())

    def test_object_sub_with_fields(self):
        # create object for subscribe
        sub_object = User.objects.create_user(username='test', email='t@t.tt')

        # define consumers
        routes = ObjectSubscribeConsumers.as_routes(path='/(?P<pk>\d+)/?', model=User,
                                                    serializer_kwargs={'fields': ['username', 'is_active']})

        # create client
        client = HttpClient()
        with apply_routes([routes]):
            # subscribe for object changes
            client.send_and_consume(u'websocket.connect', content={'path': '/{}'.format(sub_object.pk)})

            # change sub object
            sub_object.username = 'sub_object'
            sub_object.email = 'new@email.com'
            sub_object.save()

            res = json.loads(client.receive()['updated'])
            self.assertEqual(res['username'], 'sub_object')
            self.assertEqual(res['is_active'], True)
            self.assertNotIn('email', res)
            self.assertNotIn('is_staff', res)

            sub_object.username = 'test'
            sub_object.is_active = False
            sub_object.save()

            res = json.loads(client.receive()['updated'])
            self.assertNotIn('email', res)
            self.assertNotIn('is_staff', res)

            self.assertEqual(res['username'], 'test')
            self.assertEqual(res['is_active'], False)

            sub_object.email = 'new@email.com'
            sub_object.save()

            res = json.loads(client.receive()['updated'])
            self.assertEqual(res['username'], 'test')
            self.assertEqual(res['is_active'], False)

            # check that nothing happened
            self.assertIsNone(client.receive())

    def test_object_sub_with_subs_first(self):
        # define consumers
        routes = ObjectSubscribeConsumers.as_routes(path='/(?P<pk>\d+)/?', model=User)
        # create client
        client = HttpClient()
        with apply_routes([routes]):
            # subscribe for object changes
            client.send_and_consume(u'websocket.connect', content={'path': '/{}'.format('1')})

            # create object
            User.objects.create_user(username='test', email='t@t.tt')
            res = json.loads(client.receive()['created'])
            self.assertEqual(res['username'], 'test')
            self.assertEqual(res['is_active'], True)
            self.assertEqual(res['email'], 't@t.tt')
            self.assertEqual(res['is_staff'], False)

            # check that nothing happened
            self.assertIsNone(client.receive())

    def test_model_sub(self):
        # define consumers
        routes = ModelSubscribeConsumers.as_routes(model=User)
        # create client
        client = HttpClient()

        # create object
        user = User.objects.create_user(username='test', email='t@t.tt')

        with apply_routes([routes]):
            # subscribe for Models changes
            client.send_and_consume(u'websocket.connect')

            # change object
            user.username = 'new username'
            user.save()

            res = json.loads(client.receive()['updated'])
            self.assertEqual(res['username'], 'new username')
            self.assertEqual(res['email'], 't@t.tt')

            # create new one
            User.objects.create_user(username='test2', email='t2@t.tt')
            res = json.loads(client.receive()['created'])
            self.assertEqual(res['username'], 'test2')
            self.assertEqual(res['email'], 't2@t.tt')

    def test_get_mixin(self):
        pass

    def test_create_mixin(self):
        pass

    def test_update_mixin(self):
        pass

    def test_delete_mixin(self):
        pass
