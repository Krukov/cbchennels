====================
Class based channels
====================

New Class based consumers for django channels that provides easy way to use channels

Goals
=====

Actually django-channels consist Base For class-based structure of channels,
but this is another way to use Class power with channels. At the current generics approach consider class as
group off consumers without paying attention for possible relations among them. Also default generic consumer
used class as handler, not an instance.
    This is the attempt to use classes in more familiar way, like django class-based views or viewsets in django-rest-framework.
That mean that you can create new consumers like this:

```python
ChatConsumers.as_routes(path='new', perms='private')
```

Also module contain usefully groups of consumers:
 * GroupConsumers
 * RoomConsumers
 * CRUDConsumers (for models)
 * ObjectSubscribeConsumers (for subscribe websocket for model/instance changes: new value of field or creating)
 * ModelSubscribeConsumers (for subscribe websocket for models changes)
 * ListConsumers (for models)
 * etс.

and Mixins:
 * SessionMixin
 * PermissionMixin
 * UserMixin
 * etс.


Base
====

There are `Consumers` class and `consumer` decorator at the core of CBChannels. Usually they works together:

```python
from cbchannels import Consumers, consumer

class MyConsumers(Consumers):
    channel_name = 'default'
    prefix = 'new'

    @consumer(page="(?P<page>\d+)")
    def handle_stats(self, message, page):
        PageView.objects.create(page=self.prefix + page)

```

You can use Consumers at routes by call `as_routes` class method with instance specific keywords, like this:

```python
routes = [
    MyConsumers.as_routes(channel_name='private', prefix='private'),
    MyConsumers.as_routes(),
]
```
Pretty simple. Is it?

Consumers has next properties and public methods:
* `channel_name` - see (Channels names)[#Channels names]
* `decorators` - property: iterable object of decorators for applying to each consumer
* `at_exception` - method that determine behavior at exception in consumer, takes cached exception
* `as_routes` - class method that transform Consumers classes in to channels `routes`, Takes initial kwargs
* `get_channels_name` - method that return default channel name of consumers. (see (Channels names)[#Channels names])
* `get_decorators` - method that determine `decorators` for applying to each consumer (see (Decorators)[#Decorators]
* `reply` - method that send to reply channel given content


Channels names
--------------

By default channels name for consumer determined by class property that can be overwrite by `channel_name`
at `as_routes` kwargs or at `consumer` decorator. Take a look at example:

```python
from cbchannels import Consumers, consumer

class MyConsumers(Consumers):
    channel_name = 'default'

    @consumer(page='info')
    def info(self, message):
        self.reply({'title': 'Info', 'text': 'Info content from ' + message.channel.name})

    @consumer(page='about')
    def about(self, message):
        self.reply({'title': 'About', 'text': 'About content from ' + message.channel.name})

    @consumer(channel_name='about')
    def about_new(self, message):
        self.reply({'title': 'About', 'text': 'About content from ' + message.channel.name})

### ROUTES
routes = [
    MyConsumers.as_routes(channel_name='private', path='/private/'),
    MyConsumers.as_routes(),
]
```
At this example created next routes:
|channel name|filters|method|
|private|path='info'|info|
|private|path='about'|about|
|about||about_new|
|default|path='info'|info|
|default|path='about'|about|
|about||about_new|

There are two routes for channel about without filters, but works only first of them.

Filters
=======

[Filters](http://channels.readthedocs.io/en/latest/routing.html?highlight=Filters#filters) for consumers determined at
`consumer` decorator kwargs. Using filters the same as in routes with next features:
* value of filter can be callable object (or classmethod/staticmethod) that takes Consumers class object
and initialized kwargs of `as_router` method
* captured keywords passed to the consumer itself and stored in `self.kwargs` variable

```python
class MyConsumers(Consumers):
    channel_name = 'example'
    gate = 'g-(?P<gate>\w+)'

    @classmethod
    def get_gate(cls, **kwargs):
        return kwargs.get('gate', cls.gate)

    @property
    def message_text(self):
        return self.kwargs.get('gate', 'no')

    @consumer(gate=get_gate)
    def notify(self, message, **kwargs):
        Channel(message.content['gate']).send({'text': self.message_text})
```

Decorators
==========

...

Generic
=======

The Real power is in generic. We will use some wordings:
`external channels` - channels that consumers used by external providers, like `websocket` channels
`internal channels` - channels that usually used for custom internal interaction or for more flexible architecture

So `Consumers` can define consumers for both of this groups or only for one (usually for both).

WebsocketConsumers
------------------

`WebsocketConsumers` already have ability to handle websocket channels in a right way.
`WebsocketConsumers` has `path` filter for external channels.
Methods:
* on_connect -
* on_disconnect
* on_receive
Be default all received messages transmitted to the internal channels definded at init kwargs or at class properties.


```python
# consumers.py
from cbchannels import WebsocketConsumers

class AnonymousChat(WebsocketConsumers):
    channel_name = 'anonymous'

    def on_connect(self, message, **kwargs):
        Group(self.get_channels_name()).add(self.reply_channel)

    def on_disconnect(self, message, **kwargs):
        Group(self.get_channels_name()).add(self.reply_channel)

    @consumer(command='send')
    def at_send(self, message, name=None):
        Group(self.get_channels_name()).send(message.content)

    @consumer(command='send_to_user', user='(?P<name>\w+)')
    def at_send_to_user(self, message, name=None):
        Group(name + self.get_channels_name()).send(message.content)

    @consumer(command='join_user', user='(?P<name>\w+)')
    def at_join_to_user(self, message, name):
        Group(name + self.get_channels_name()).add(self.reply_channel)


# routes.py

routes = [
    AnonymousChat(path='/a'),
    AnonymousChat(path='/myroom', channel_name='myanonymous'),
]
```

GroupConsumers
--------------
inherit `WebsocketConsumers`
GroupConsumers automatically adding connected websocket to the determined group and broadcast to the group on receive.
Group name determined flexible. You can use class property for it or overwrite get_group_name method..
If group name not determined channel name will use by group name. Group name (channel name) will formatting
with filters kwargs (self.kwargs), so croup name can be formatting style string:

```python
# routers.py
from cbchannels.generic import GroupConsumers

routes = [
    GroupConsumers(path='(?P<room>\w+)', group_name='room_{room}')
]
```


RoomConsumers
-------------
inherit `WebsocketConsumers`
For simple chat based on session use RoomConsumers:

```python
routes = [
    RoomConsumers(channel_name='rooms', path='/', auth=True)
]
```

Model Generic
=============

CRUDConsumers
-------------
It is like ModelView
```python
routes = [
    CRUDConsumers(path='/users', queryset=User.objects.filter(active=True), paginate_by=10),
]
```

ObjectSubscribeConsumers
------------------------

`ObjectSubscribeConsumers` allow you to create websocket that subscribe for the model record changes (creating or updating)

```python
routes = [
    ObjectSubscribeConsumers.as_routes(path='/(?P<pk>\d+)/?', model=User,
                                       serializer_kwargs={'fields': ['username', 'is_active']})
]
```
All sockets that connected to this channel will receive messages about changes of user with spicified pk.
Received messages look like this `{created: {username: 'John', is_active: true}}` (at create)
It is very useful if you need to create data binding.

ModelSubscribeConsumers
-----------------------

`ModelSubscribeConsumers` allow you to create websocket that subscribe for the model changes (creating or updating)

```python
routes = [
    ModelSubscribeConsumers.as_routes(path='/users/?', model=User,
                                      serializer_kwargs={'fields': ['username', 'is_active']})
]
```


Tests
=====



[Django Channels](http://channels.readthedocs.io/en/latest/index.html) 