import importlib
from collections import deque
from pathlib import Path
from threading import RLock
from types import FunctionType, MethodType
from typing import Callable, Deque, Dict, List, Type

from .log import logger


class Event:
    """Base event class"""

    def __str__(self):
        return f"{type(self).__name__}"


class Callback:
    def __init__(
        self,
        func: Callable[[Event], None],
        event: Type[Event] | Event,
        instance=None,
    ):
        self.func: Callable[[Event], None] = func
        self.event: Event | Type[Event] = event
        self.instance = instance

    def call(self):
        if self.instance:
            self.func(self.instance, self.event)
        else:
            self.func(self.event)

    def copy(self):
        # shallow copy
        return Callback(self.func, self.event, self.instance)

    def __eq__(self, value):
        if isinstance(value, Callback):
            return self.func is value.func and self.event is value.event
        elif isinstance(value, FunctionType):
            return self.func == value
        elif isinstance(value, MethodType):
            if self.instance is None:
                return False
            return getattr(self.instance, self.func.__name__) == value
        return False

    def __str__(self):
        instance_string = "None" if self.instance is None else f"{self.instance}"
        return f"Callback {self.func.__name__} ({instance_string}) for {self.event}"


# We say that a subscription is the information that a method wants to be called back
# and a registration is the process of adding a method to the list of callbacks for a particular event.
class EventManager:
    def __init__(self):
        self._subscriptions: Dict[Type[Event], List[Callback]] = {}
        self._callqueue: Deque[Callback] = deque()
        self._subscription_lock = RLock()
        self._callqueue_lock = RLock()

    def _verbose_callqueue(self):
        logger.debug(f"Callqueue ({len(self._callqueue)}):")
        for callback in self._callqueue:
            logger.debug(f"{callback}")

    def _process_callqueue(self):
        logger.debug("Processing callqueue:")
        with self._callqueue_lock:
            while self._callqueue:
                callback = self._callqueue.popleft()
                instance_string = ""
                if callback.instance:
                    instance_string = f"{callback.instance}"
                logger.debug(
                    f"Processing callqueue callback: {callback.func.__name__} {instance_string}"
                )
                callback.call()

    def register(
        self, func: Callable[[Event], None], event_type: Type[Event], instance=None
    ):
        if hasattr(func, "__self__"):
            instance = None  # instance is already set in the method
        callback = Callback(func=func, event=event_type, instance=instance)
        with self._subscription_lock:
            self._subscriptions.setdefault(event_type, []).append(callback)
        logger.debug(f"Registered {callback}")

    def subscribe(self, *event_types: Type[Event]):
        def decorator(func: Callable[[Event], None]):
            for event_type in event_types:
                self.register(func=func, event_type=event_type)
            return func

        return decorator

    def remove_callback(self, func: Callable[[Event], None], event_type: Type[Event]):
        """Remove a callback from the list of subscriptions."""
        if event_type not in self._subscriptions:
            return
        for callback in self._subscriptions.get(event_type, []):
            if callback == func:
                with self._subscription_lock:
                    self._subscriptions[event_type].remove(callback)
                logger.debug(f"Removed {callback} ({event_type})")

    def remove_function(self, func: Callable[[Event], None]):
        """Remove all callbacks for a function."""
        for callbacks in self._subscriptions.values():
            for callback in callbacks:
                if callback == func:
                    with self._subscription_lock:
                        callbacks.remove(callback)
        logger.debug(f"Removed all callbacks for {func}")

    def clear_event_type(self, event_type: Type[Event]):
        if event_type in self._subscriptions:
            with self._subscription_lock:
                del self._subscriptions[event_type]
            logger.debug(f"Cleared all subscriptions for {event_type}")

    def emit(self, event: Event):
        event_type = type(event)
        logger.debug(f"Emitting event: {event_type.__name__}")

        if event_type in self._subscriptions:
            logger.debug(
                f"Found {len(self._subscriptions[event_type])} callbacks for event type: {event_type.__name__}"
            )
            for callback in self._subscriptions[event_type]:
                callback_copy = callback.copy()
                callback_copy.event = event
                self._callqueue.append(callback_copy)

            # trigger parent class
            # for cls in event_type.__mro__[1:]:  # skip self
            #     if cls in self._callbacks and cls != Event:
            #         logger.info(f"Triggering parent class callbacks for: {cls.__name__}")
            #         for callback in self._callbacks[cls]:
            #             callback_copy = Callback(callback, event)
            #             self._callqueue.append(callback_copy)

            self._verbose_callqueue()
            self._process_callqueue()


def subscribe_classmethod(*event_types: List[Type[Event]]):
    """Tag the method with subscription info."""

    def decorator(func):
        if not hasattr(func, "_subscriptions"):
            func._subscriptions = []  # note that function member does not support type hint
        func._subscriptions.extend(event_types)
        logger.debug(f"Tag subscription info for {func.__name__} {event_types}")
        return func

    return decorator


class EventMeta(type):
    """Define a new class with events info gathered after class creation."""

    def __new__(cls, name, bases, attrs):
        new_class = super().__new__(cls, name, bases, attrs)

        _subscriptions: Dict[Type[Event], List[Callable]] = {}
        for attr_name, attr_value in attrs.items():
            # find all subscriptions of methods
            if callable(attr_value) and hasattr(attr_value, "_subscriptions"):
                for event_type in attr_value._subscriptions:
                    _subscriptions.setdefault(event_type, []).append(attr_value)

        new_class._subscriptions = _subscriptions
        return new_class


class EventAwareBase(metaclass=EventMeta):
    """The base class that utilize the metaclass."""

    def __init__(self, event_manager):
        self.event_manager: EventManager = event_manager
        # trigger registrations
        self._register()

    def _register(self):
        for event_type, funcs in self._subscriptions.items():
            for func in funcs:
                self.event_manager.register(
                    func=func, event_type=event_type, instance=self
                )


class ModuleLoader:
    def __init__(self, event_manager: EventManager):
        self.event_manager = event_manager
        self.loaded_modules = set()

    def discover_modules(self, modules_dir: str = "modules"):
        modules_path = Path(modules_dir)

        if not modules_path.exists():
            logger.warning(f"Module directory does not exist: {modules_dir}")
            return

        for item in modules_path.iterdir():
            if item.is_dir() and not item.name.startswith("__"):
                try:
                    module_name = f"{modules_dir}.{item.name}"
                    self.load_module(module_name)
                    logger.debug(f"Discovered module: {module_name}")
                except ImportError as e:
                    logger.error(f"Failed to load module {item.name}: {e}")
                except Exception as ex:
                    logger.exception(
                        f"Unexpected error occurred while loading module {item.name}: {ex}"
                    )

    def load_module(self, module_name: str):
        if module_name in self.loaded_modules:
            logger.debug(f"Module already loaded: {module_name}")
            return

        try:
            importlib.import_module(module_name)
            self.loaded_modules.add(module_name)
            logger.debug(f"Successfully loaded module: {module_name}")

        except ImportError as e:
            logger.error(f"Failed to import module {module_name}: {e}")
            raise
