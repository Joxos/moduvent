from enum import Enum, auto

from .events import Event


def is_class_and_subclass(obj):
    return isinstance(obj, type) and issubclass(obj, Event)


def is_instance_and_subclass(obj):
    return is_class_and_subclass(type(obj))


class FunctionTypes(Enum):
    """
    BOUND_METHOD: instance is the instance (BOUND_METHOD) or class (CLASSMETHOD)
    UNBOUND_METHOD: instance isn't set yet since the class hasn't been initialized
    FUNCTION/STATICMETHOD: instance is None
    """

    STATICMETHOD = auto()
    BOUND_METHOD = auto()
    UNBOUND_METHOD = auto()  # this occurs when a class method (both classmethod and instance method) is defined but the class is not initialized
    FUNCTION = auto()
    CALLBACK = auto()
    UNKNOWN = auto()


def check_function_type(func):
    type_name = func.__class__.__name__
    if type_name == "staticmethod":
        return FunctionTypes.STATICMETHOD
    elif type_name == "method":
        return FunctionTypes.BOUND_METHOD
    elif type_name == "function":
        if hasattr(func, "_subscriptions"):
            return FunctionTypes.UNBOUND_METHOD
        else:
            return FunctionTypes.FUNCTION
    else:
        return FunctionTypes.UNKNOWN


class SUBSCRIPTION_STRATEGY(Enum):
    EVENTS = auto()
    CONDITIONS = auto()


def _get_subscription_strategy(*args, **kwargs):
    """
    The first argument must be an event type.
    If the second argument is a function, then functions after that will be registered as conditions.
    If the second argument is another event, then events after that will be registered as multi-callbacks.
    If arguments after the second argument is not same, then it will raise a ValueError.
    """
    # handle invalid subscriptions
    if not args:
        raise ValueError("At least one event type must be provided")
    if not is_class_and_subclass(args[0]):
        raise ValueError("First argument must be an event type")

    if len(args) == 1 and is_class_and_subclass(args[0]):
        return SUBSCRIPTION_STRATEGY.EVENTS
    all_events = is_class_and_subclass(args[1])  # pyright: ignore[reportGeneralTypeIssues] (surpress because of the check above)
    for arg in args:
        if all_events and not is_class_and_subclass(arg):
            raise ValueError(
                f"Got {arg} among events (expect an inheritor of Event)"
            )
        elif not all_events and not callable(arg):
            raise ValueError(
                f"Got {arg} among conditions (expect a callable function to be the condition)"
            )
    return (
        SUBSCRIPTION_STRATEGY.EVENTS
        if all_events
        else SUBSCRIPTION_STRATEGY.CONDITIONS
    )