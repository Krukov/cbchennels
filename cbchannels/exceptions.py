

class ConsumerError(Exception):
    """
    Error that cached at the top level at consumer processed
    and sent exception message to the reply channel
    """