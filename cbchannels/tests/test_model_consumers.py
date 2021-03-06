from __future__ import unicode_literals

import json
from channels.tests import ChannelTestCase, HttpClient, apply_routes

from django.contrib.auth.models import User

from cbchannels.generic.models import (ObjectSubscribeConsumers, ModelSubscribeConsumers, ReadOnlyConsumers,
                                       CreateConsumers, DeleteConsumers, UpdateConsumers, ListConsumers, CRUDConsumers)
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
            res = json.loads(client.receive()['text'])
            self.assertEqual(res['action'], 'updated')
            self.assertEqual(res['data']['username'], 'sub_object')
            self.assertEqual(res['data']['email'], 'new@email.com')
            self.assertEqual(res['data']['is_staff'], False)

            # change second object
            just_object.email = 'test@new.mail'
            just_object.save()

            # check that nothing happened
            self.assertIsNone(client.receive())

            # delete
            sub_object.delete()
            just_object.delete()
            res = json.loads(client.receive()['text'])
            self.assertEqual(res['action'], 'deleted')
            self.assertEqual(res['data']['username'], 'sub_object')
            self.assertEqual(res['data']['email'], 'new@email.com')
            self.assertEqual(res['data']['is_staff'], False)

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

            res = json.loads(client.receive()['text'])['data']
            self.assertEqual(res['username'], 'sub_object')
            self.assertEqual(res['is_active'], True)
            self.assertNotIn('email', res)
            self.assertNotIn('is_staff', res)

            sub_object.username = 'test'
            sub_object.is_active = False
            sub_object.save()

            res = json.loads(client.receive()['text'])
            self.assertEqual(res['action'], 'updated')
            self.assertNotIn('email', res['data'])
            self.assertNotIn('is_staff', res['data'])

            self.assertEqual(res['data']['username'], 'test')
            self.assertEqual(res['data']['is_active'], False)

            sub_object.username = 'test_new'
            sub_object.save(update_fields=['username'])

            res = json.loads(client.receive()['text'])
            self.assertEqual(res['action'], 'updated')
            self.assertEqual(res['data']['username'], 'test_new')
            self.assertNotIn('is_active', res['data'])
            self.assertNotIn('is_staff', res['data'])

            sub_object.email = 'new@email.com'
            sub_object.save(update_fields=['email'])

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
            res = json.loads(client.receive()['text'])
            self.assertTrue('data' in res.keys())
            self.assertTrue('action' in res.keys())
            self.assertTrue(res['action'] == 'created')
            data = res['data']
            self.assertEqual(data['username'], 'test')
            self.assertEqual(data['is_active'], True)
            self.assertEqual(data['email'], 't@t.tt')
            self.assertEqual(data['is_staff'], False)

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

            res = json.loads(client.receive()['text'])
            self.assertEqual(res['action'], 'updated')
            self.assertEqual(res['data']['username'], 'new username')
            self.assertEqual(res['data']['email'], 't@t.tt')

            # create new one
            to_del = User.objects.create_user(username='test2', email='t2@t.tt')
            res = json.loads(client.receive()['text'])
            self.assertEqual(res['action'], 'created')
            self.assertEqual(res['data']['username'], 'test2')
            self.assertEqual(res['data']['email'], 't2@t.tt')

            # delete
            to_del.delete()
            res = json.loads(client.receive()['text'])
            self.assertEqual(res['action'], 'deleted')
            self.assertEqual(res['data']['username'], 'test2')
            self.assertEqual(res['data']['email'], 't2@t.tt')

    def test_model_sub_with_fields(self):
        # define consumers
        routes = ModelSubscribeConsumers.as_routes(model=User,
                                                   serializer_kwargs={'fields': ['username']})
        # create client
        client = HttpClient()

        with apply_routes([routes]):
            # subscribe for Models changes
            client.send_and_consume(u'websocket.connect')

            # create object
            User.objects.create_user(username='test', email='t@t.tt')

            res = json.loads(client.receive()['text'])
            self.assertEqual(res['action'], 'created')
            self.assertEqual(res['data']['username'], 'test')
            self.assertNotIn('is_active', res['data'])
            self.assertNotIn('email', res['data'])

    def test_get_mixin(self):
        # create object
        obj = User.objects.create_user(username='test', email='t@t.tt')
        # create client
        client = HttpClient()

        with apply_routes([ReadOnlyConsumers.as_routes(model=User, path='/(?P<pk>\d+)/?', channel_name='test')]):

            client.send_and_consume(u'websocket.connect', {'path': '/{}'.format(obj.pk)})
            client.send_and_consume(u'websocket.receive', {'path': '/{}'.format(obj.pk), 'action': 'get'})
            client.consume('test')
            res = json.loads(json.loads(client.receive()['text'])['response'])

            self.assertEqual(res['username'], 'test')
            self.assertEqual(res['email'], 't@t.tt')
            self.assertEqual(res['is_active'], True)

    def test_create_mixin(self):
        # create client
        client = HttpClient()
        data = {'username': 'test', 'email': 't@t.tt'}

        with apply_routes([CreateConsumers.as_routes(model=User, path='/', channel_name='test')]):
            client.send_and_consume(u'websocket.connect', {'path': '/'})
            client.send_and_consume(u'websocket.receive', {'path': '/', 'action': 'create',
                                                           'data': json.dumps(data)})
            client.consume(u'test')

        self.assertTrue(User.objects.filter(username='test', email='t@t.tt').exists())

    def test_update_mixin(self):
        # create object
        obj = User.objects.create_user(username='test', email='t@t.tt')
        # create client
        client = HttpClient()

        data = {'username': 'new_name'}
        with apply_routes([UpdateConsumers.as_routes(model=User, path='/(?P<pk>\d+)/?', channel_name='test')]):

            client.send_and_consume('websocket.connect', {'path': '/{}'.format(obj.pk)})
            client.send_and_consume('websocket.receive', {'path': '/{}'.format(obj.pk), 'action': 'update',
                                                          'data': json.dumps(data)})
            client.consume('test')

        user = User.objects.filter(pk=obj.pk).first()
        self.assertTrue(user)
        self.assertEqual(user.username, 'new_name')

    def test_delete_mixin(self):
        # create object
        obj = User.objects.create_user(username='test', email='t@t.tt')
        # create client
        client = HttpClient()

        with apply_routes([DeleteConsumers.as_routes(model=User, path='/(?P<pk>\d+)/?', channel_name='test')]):
            client.send_and_consume(u'websocket.connect', {'path': '/{}'.format(obj.pk)})
            client.send_and_consume(u'websocket.receive', {'path': '/{}'.format(obj.pk), 'action': 'delete'})
            client.consume('test')

        self.assertFalse(User.objects.filter(pk=obj.pk).exists())

    def test_list_consumers(self):
        # create object
        for i in range(20):
            User.objects.create_user(username='test' + str(i), email='t@t.tt')
        # create client
        client = HttpClient()

        with apply_routes([ListConsumers.as_routes(model=User, path='/', channel_name='test', paginate_by=10)]):
            client.send_and_consume(u'websocket.connect', {'path': '/'})
            client.send_and_consume(u'websocket.receive', {'path': '/', 'action': 'list', 'page': 2})
            client.consume('test')
            rec = client.receive()
            res = json.loads(json.loads(rec['text'])['response'])

        self.assertEqual(len(res), 10)
        self.assertEqual(res[0]['username'], 'test10')
        self.assertEqual(res[0]['email'], 't@t.tt')
        self.assertEqual(res[0]['is_active'], True)

    def test_crud_consumers(self):
        # create object
        for i in range(20):
            User.objects.create_user(username='test' + str(i), email='t@t.tt')
        # create client
        client = HttpClient()

        with apply_routes([CRUDConsumers.as_routes(model=User, path='/', channel_name='test', paginate_by=10)]):
            client.send_and_consume(u'websocket.connect', {'path': '/'})
            client.send_and_consume(u'websocket.receive', {'path': '/', 'action': 'list', 'page': 2})
            client.consume('test')
            rec = client.receive()
            res = json.loads(json.loads(rec['text'])['response'])

            self.assertEqual(len(res), 10)
            self.assertEqual(res[0]['username'], 'test10')
            self.assertEqual(res[0]['email'], 't@t.tt')
            self.assertEqual(res[0]['is_active'], True)

            client.send_and_consume(u'websocket.connect', {'path': '/{}'.format(10)})
            client.send_and_consume(u'websocket.receive', {'path': '/{}'.format(10), 'action': 'delete'})
            client.consume('test')

            self.assertFalse(User.objects.filter(pk=10).exists())

            data = {'username': 'new_name'}
            client.send_and_consume('websocket.connect', {'path': '/{}'.format(11)})
            client.send_and_consume('websocket.receive', {'path': '/{}'.format(11), 'action': 'update',
                                                          'data': json.dumps(data)})
            client.consume('test')

            user = User.objects.filter(pk=11).first()
            self.assertTrue(user)
            self.assertEqual(user.username, 'new_name')
