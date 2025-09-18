import importlib
from collections import deque
from pathlib import Path
from threading import RLock
from typing import Callable, Deque, Dict, List, Type

from .log import logger


class Event:
    """Base event class"""

    pass


class Callback:
    def __init__(
        self,
        func: Callable[[Event], None],
        event: Event,
        instance: type = None,
    ):
        self.func: Callable[[Event], None] = func
        self.event: Event | Type[Event] = event
        self.instance: type = instance

    def call(self):
        if self.instance:
            self.func(self.instance, self.event)
        else:
            self.func(self.event)

    def copy(self):
        return Callback(self.func, self.event, self.instance)


class EventManager:
    def __init__(self):
        self._subscriptions: Dict[Type[Event], List[Callback]] = {}
        self._callqueue: Deque[Callback] = deque()
        self._lock = RLock()

    def _subscribe(self, event_type: Type[Event], callback: Callback):
        with self._lock:
            self._subscriptions.setdefault(event_type, []).append(callback)

    def subscribe(self, *event_types: Type[Event]):
        def decorator(func: Callable[[Event], None]):
            for event_type in event_types:
                callback = Callback(func, event_type)
                self._subscribe(event_type, callback)
                logger.debug(
                    f"Subscribed function {func.__name__} to {event_type.__name__}"
                )
            return func

        return decorator

    def _callback_matches(
        self, callback: Callback, func: Callable, instance: object = None
    ) -> bool:
        if hasattr(func, "__func__") and hasattr(func, "__self__"):
            return callback.func == func.__func__ and callback.instance == func.__self__

        return callback.func == func and callback.instance == instance

    def unsubscribe(self, func: Callable[[Event], None], event_type: Type[Event]):
        if event_type not in self._subscriptions:
            return

        with self._lock:
            instance = None
            if hasattr(func, "__self__"):
                instance = func.__self__

            self._subscriptions[event_type] = [
                cb
                for cb in self._subscriptions[event_type]
                if not self._callback_matches(cb, func, instance)
            ]

    def unsubscribe_instance(self, instance: object):
        with self._lock:
            for event_type in self._subscriptions:
                self._subscriptions[event_type] = [
                    cb
                    for cb in self._subscriptions[event_type]
                    if cb.instance != instance
                ]

    def remove_function(self, func: Callable[[Event], None]):
        with self._lock:
            instance = None
            if hasattr(func, "__self__"):
                instance = func.__self__

            for event_type in self._subscriptions:
                self._subscriptions[event_type] = [
                    cb
                    for cb in self._subscriptions[event_type]
                    if not self._callback_matches(cb, func, instance)
                ]

    def clear_event_type(self, event_type: Type[Event]):
        with self._lock:
            if event_type in self._subscriptions:
                del self._subscriptions[event_type]

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

            # trigger parent class events using callqueue
            # for cls in event_type.__mro__[1:]:  # skip self
            #     if cls in self._callbacks and cls != Event:
            #         logger.info(f"Triggering parent class callbacks for: {cls.__name__}")
            #         for callback in self._callbacks[cls]:
            #             callback_copy = Callback(callback.func, event)
            #             self._callqueue.append(callback_copy)

            self._verbose_callqueue()
            self._process_callqueue()

    def _process_callqueue(self):
        while self._callqueue:
            callback = self._callqueue.popleft()
            logger.debug(f"Processing callqueue callback: {callback.func.__name__}")

            @logger.catch
            def wrapper():
                callback.call()

            wrapper()

    def _verbose_callqueue(self):
        for callback in self._callqueue:
            logger.debug(f"Callback in callqueue: {callback.func.__name__}")


# We say that a subscription is the information that a method wants to be called back
# and a registration is the process of adding a method to the list of callbacks for a particular event.
def subscribe_classmethod(*event_types: List[Type[Event]]):
    """Tag the method with subscription info."""

    def decorator(func):
        if not hasattr(func, "_subscriptions"):
            func._subscriptions = []  # note that function member does not support type hint
        func._subscriptions.extend(event_types)
        return func

    return decorator


class EventMeta(type):
    """Define a new class with events info held."""

    def __new__(cls, name, bases, attrs):
        new_class = super().__new__(cls, name, bases, attrs)

        subscriptions: Dict[Type[Event], List[Callback]] = {}
        for attr_name, attr_value in attrs.items():
            # find all subscriptions of methods
            if callable(attr_value) and hasattr(attr_value, "_subscriptions"):
                for event_type in attr_value._subscriptions:
                    if event_type not in subscriptions:
                        subscriptions[event_type] = []
                    callback = Callback(attr_value, event_type)
                    subscriptions[event_type].append(callback)

        new_class.subscriptions = subscriptions
        return new_class


class EventAwareBase(metaclass=EventMeta):
    """The base class that utilize the metaclass."""

    def __init__(self, event_manager):
        self.event_manager = event_manager
        # trigger registrations
        self._register()

    def _register(self):
        for event_type, callbacks in self.subscriptions.items():
            for callback in callbacks:
                callback.instance = self
                self.event_manager._subscribe(event_type, callback)


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
            logger.info(f"Successfully loaded module: {module_name}")

        except ImportError as e:
            logger.error(f"Failed to import module {module_name}: {e}")
            raise
