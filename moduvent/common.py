import importlib
import weakref
from abc import ABC, abstractmethod
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Dict, List, Type

from loguru import logger

from .events import Event

common_logger = logger.bind(source="moduvent_common")

def is_class_and_subclass(obj, cls):
    return isinstance(obj, type) and issubclass(obj, cls)

class FunctionTypes(Enum):
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


class EventInheritor:
    def __set_name__(self, owner, name):
        self.public_name = name
        self.private_name = f"_{name}"
        setattr(owner, self.private_name, None)

    def __set__(self, obj, value):
        value_type = type(value)
        if is_class_and_subclass(value, Event):
            setattr(obj, self.private_name, value)
        else:
            setattr(obj, self.private_name, None)
            raise TypeError(
                f"{value} with {value_type} type is not an inheritor of base event class"
            )

    def __get__(self, obj, objtype=None):
        return getattr(obj, self.private_name)


class WeakReference:
    def __set__(self, obj, value):
        if obj and value:
            if check_function_type(value) == FunctionTypes.BOUND_METHOD:
                obj._func_ref = weakref.WeakMethod(value)
            else:
                obj._func_ref = weakref.ref(value)
        else:
            obj._func_ref = None
            raise ValueError(f"Cannot set weak reference of {value} to {obj}")

    def __get__(self, obj, objtype=None):
        ref = obj._func_ref
        if ref is None:
            return None
        return ref()


class BaseCallback(ABC):
    func: WeakReference = WeakReference()
    event: EventInheritor = EventInheritor()

    def __init__(
        self,
        func: Callable[[Event], None],
        event: Type[Event] | Event,
        conditions: list[Callable[[Event], bool]] = None,
    ):
        """
        BOUND_METHOD: instance is the instance (BOUND_METHOD) or class (CLASSMETHOD)
        UNBOUND_METHOD: instance isn't set yet since the class hasn't been initialized
        FUNCTION/STATICMETHOD: instance is None
        """
        self.func_type = (
            FunctionTypes.UNKNOWN
        )  # we first set func_type since the setter of self.func may use it
        self.func: weakref.ReferenceType[Callable[[Event], None]] = func
        self.event: Event | Type[Event] = event
        self.conditions = conditions if conditions else []

        self.func_type = check_function_type(func)

    def _report_function(self):
        qualname = getattr(self.func, "__qualname__", self.func)
        raise TypeError(f"Unknown function type for {qualname}")

    def _func_type_valid(self):
        if self.func_type in [
            FunctionTypes.BOUND_METHOD,
            FunctionTypes.FUNCTION,
            FunctionTypes.STATICMETHOD,
        ]:
            return True
        else:
            return False

    def _check_conditions(self):
        for condition in self.conditions:
            if not condition(self.event):
                common_logger.debug(f"Condition {condition} failed, skipping.")
                return False
        return True

    def _shallow_copy(self, subclass: Type["BaseCallback"]):
        if self.func and self.event:
            return subclass(
                func=self.func,
                event=self.event,
                conditions=self.conditions,
            )
        return None

    def _compare_attributes(self, value: "BaseCallback"):
        return (
            self.func == value.func
            and self.event == value.event
            and self.conditions == value.conditions
        )

    @abstractmethod
    def call(self):
        pass

    @abstractmethod
    def copy(self):
        pass

    @abstractmethod
    def __eq__(self, value):
        func_type = check_function_type(value)
        if func_type in [
            FunctionTypes.BOUND_METHOD,
            FunctionTypes.UNBOUND_METHOD,
            FunctionTypes.FUNCTION,
            FunctionTypes.STATICMETHOD,
        ]:
            return self.func == value
        else:
            return False

    def __str__(self):
        instance_string = (
            str(self.func.__self__) if hasattr(self.func, "__self__") else "None"
        )
        func_string = self.func.__qualname__ if self.func else self.func
        return f"Callback: {self.event} -> {func_string} ({instance_string}:{self.func_type})"


class CommonEventManager:
    class SUBSCRIPTION_STRATEGY(Enum):
        EVENTS = auto()
        CONDITIONS = auto()

    def _verbose_callqueue(self, size: int):
        common_logger.debug(f"Callqueue ({size}):")
        for callback in self._callqueue:
            common_logger.debug(f"\t{callback}")

    def _handle_invalid_subscriptions(self, *args, **kwargs):
        if not args:
            raise ValueError("At least one event type must be provided")

        if not is_class_and_subclass(args[0], Event):
            raise ValueError("First argument must be an event type")

    def _get_subscription_strategy(self, *args, **kwargs):
        """
        The first argument must be an event type.
        If the second argument is a function, then functions after that will be registered as conditions.
        If the second argument is another event, then events after that will be registered as multi-callbacks.
        If arguments after the second argument is not same, then it will raise a ValueError.
        """
        self._handle_invalid_subscriptions(*args, **kwargs)
        if len(args) == 1 and is_class_and_subclass(args[0], Event):
            return self.SUBSCRIPTION_STRATEGY.EVENTS
        all_events = is_class_and_subclass(args[1], Event)
        for arg in args:
            if all_events and not is_class_and_subclass(arg, Event):
                raise ValueError(
                    f"Got {arg} among events (expect a inheritor of Event)"
                )
            elif not all_events and not callable(arg):
                raise ValueError(
                    f"Got {arg} among conditions (expect a callable judger function)"
                )
        return (
            self.SUBSCRIPTION_STRATEGY.EVENTS
            if all_events
            else self.SUBSCRIPTION_STRATEGY.CONDITIONS
        )

    def _remove_subscriptions(self, filter_func: Callable[[Type[Event], None], bool]):
        """Note that using this function should attain the lock first."""
        for event_type, callbacks in list(self._subscriptions.items()):
            for cb in callbacks:
                if filter_func(event_type, cb):
                    common_logger.debug(f"Removing subscription: {cb}")
                    callbacks.remove(cb)

            # clean-up
            if not self._subscriptions[event_type]:
                common_logger.debug(f"Clean up empty event {event_type}")
                del self._subscriptions[event_type]

    def _check_unregister_args(
        self, func: Callable[[Event], None], event_type: Type[Event]
    ):
        if not func and not event_type:
            raise ValueError(
                f"Either func or event_type must be provided (got func={func}, event_type={event_type})."
            )
        if not callable(func) and not is_class_and_subclass(event_type, Event):
            raise ValueError(
                f"Invalid argument type (func={func}, event_type={event_type})."
            )

    def _process_unregister_logic(
        self, func: Callable[[Event], None], event_type: Type[Event]
    ):
        if func and event_type:
            if event_type not in self._subscriptions:
                common_logger.debug(
                    f"No subscriptions for {event_type} found, skipping."
                )
                return
            self._remove_subscriptions(lambda e, c: e == event_type and c == func)
        elif func:
            self._remove_subscriptions(lambda e, c: c == func)
            common_logger.debug(f"Removed all callbacks for {func}")
        elif event_type:
            if event_type in self._subscriptions:
                del self._subscriptions[event_type]
                common_logger.debug(f"Cleared all subscriptions for {event_type}")

    def verbose_subscriptions(self):
        common_logger.debug("Subscriptions:")
        for event_type, callbacks in self._subscriptions.items():
            common_logger.debug(f"\t{event_type.__qualname__} ({len(callbacks)}):")
            for callback in callbacks:
                common_logger.debug(f"\t\t{callback}")


def subscribe_method(*event_types: Type[Event]):
    """Tag the method with subscription info."""
    # Validate that all event_types are subclasses of Event
    for event_type in event_types:
        if not is_class_and_subclass(event_type, Event):
            raise TypeError(
                f"subscribe_method decorator expects Event subclasses, got {event_type!r}."
            )

    def decorator(func):
        if not hasattr(func, "_subscriptions"):
            func._subscriptions = []  # note that function member does not support type hint
        func._subscriptions.extend(event_types)
        common_logger.debug(f"{func.__qualname__}._subscriptions = {event_types}")
        return func

    return decorator


class EventMeta(type):
    """Define a new class with events info gathered after class creation."""

    def __new__(cls, name, bases, attrs):
        new_class = super().__new__(cls, name, bases, attrs)

        _subscriptions: Dict[Type[Event], List[Callable[[Event], None]]] = {}
        for attr_name, attr_value in attrs.items():
            # find all subscriptions of methods
            if hasattr(attr_value, "_subscriptions"):
                for event_type in attr_value._subscriptions:
                    _subscriptions.setdefault(event_type, []).append(attr_value)

        new_class._subscriptions = _subscriptions
        return new_class


class ModuleLoader:
    def __init__(self):
        self.loaded_modules = set()

    def discover_modules(self, modules_dir: str = "modules"):
        modules_path = Path(modules_dir)

        if not modules_path.exists():
            common_logger.warning(f"Module directory does not exist: {modules_dir}")
            return

        for item in modules_path.iterdir():
            if item.is_dir() and not item.name.startswith("__"):
                try:
                    module_name = f"{modules_dir}.{item.name}"
                    self.load_module(module_name)
                    common_logger.debug(f"Discovered module: {module_name}")
                except ImportError as e:
                    common_logger.error(f"Failed to load module {item.name}: {e}")
                except Exception as ex:
                    common_logger.exception(
                        f"Unexpected error occurred while loading module {item.name}: {ex}"
                    )

    def load_module(self, module_name: str):
        if module_name in self.loaded_modules:
            common_logger.debug(f"Module already loaded: {module_name}")
            return

        try:
            importlib.import_module(module_name)
            self.loaded_modules.add(module_name)
            common_logger.debug(f"Successfully loaded module: {module_name}")

        except ImportError as e:
            common_logger.exception(f"Error while loading module {module_name}: {e}")
