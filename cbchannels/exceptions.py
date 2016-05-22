

class ConsumerError(Exception):
    """
    Error that catching at the top level at consumer processed
    and sent exception message to the reply channel
    """
