from .exceptions import ClientError


def catch_client_error(func):
    """
    Decorator to catch the ClientError exception and translate it into a reply.
    """
    def inner(message):
        try:
            return func(message)
        except ClientError as e:
            # If we catch a client error, tell it to send an error string
            # back to the client on their reply channel
            e.send_to(message.reply_channel)
    return inner

