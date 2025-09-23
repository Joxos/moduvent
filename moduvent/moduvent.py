import importlib
import inspect
from collections import deque
from pathlib import Path
from threading import RLock
from typing import Callable, Deque, Dict, List, Type
from enum import Enum, auto

from .log import logger

class FunctionTypes(Enum):
    CLASSMETHOD = auto()
    STATICMETHOD = auto()
    BOUND_METHOD = auto()
    UNBOUND_METHOD = auto()  # this occurs when a class method is defined but the class is not initialized
    FUNCTION = auto()
    CALLBACK = auto()
    UNKNOWN = auto()

def check_function_type(func):
    if isinstance(func, Callback):
        return FunctionTypes.CALLBACK
    type_name = func.__class__.__name__
    if type_name == "classmethod":
        return FunctionTypes.CLASSMETHOD
    elif type_name == "staticmethod":
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

class Event:
    """Base event class"""

    def __str__(self):
        # get all attributes without the ones starting with __
        attrs = [
            f"{k}={v}"
            for k, v in self.__dict__.items()
            if not k.startswith("__")
        ]
        return f"{type(self).__qualname__}({', '.join(attrs)})"


class Callback:
    def __init__(
        self,
        func: Callable[[Event], None],
        event: Type[Event] | Event,
        instance: object | type=None,
    ):
        '''
        BOUND_METHOD: instance is the instance
        UNBOUND_METHOD: instance isn't set yet since the class hasn't been initialized
        CLASSMETHOD: instance is the class
        FUNCTION/STATICMETHOD: instance is None
        '''
        self.func: Callable[[Event], None] = func
        self.event: Event | Type[Event] = event
        self.instance = instance
        self.func_type = check_function_type(func)

    def call(self):
        if self.func_type in [FunctionTypes.CLASSMETHOD, FunctionTypes.BOUND_METHOD, FunctionTypes.FUNCTION, FunctionTypes.STATICMETHOD]:
            self.func(self.event)
        elif self.func_type == FunctionTypes.UNBOUND_METHOD:
            self.func(self.instance, self.event)
        else:
            logger.exception(f"Unknown function type for {self.func.__qualname__}")

    def copy(self):
        # shallow copy
        callback = Callback(self.func, self.event, self.instance)
        return callback

    def __eq__(self, value):
        func_type = check_function_type(value)
        if func_type == FunctionTypes.CALLBACK:
            return self.func == value.func and self.event == value.event
        elif func_type in [FunctionTypes.CLASSMETHOD, FunctionTypes.BOUND_METHOD, FunctionTypes.UNBOUND_METHOD, FunctionTypes.FUNCTION, FunctionTypes.STATICMETHOD]:
            return self.func == value
        else:
            return False

    def __str__(self):
        instance_string = "None" if self.instance is None else f"{self.instance}"
        return f"Callback: {self.event} -> {self.func.__qualname__} ({instance_string}:{self.func_type})"


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
        logger.debug("Processing callqueue...")
        with self._callqueue_lock:
            while self._callqueue:
                callback = self._callqueue.popleft()
                logger.debug(f"Calling {callback}")
                try:
                    callback.call()
                except Exception as e:
                    logger.exception(f"Error while processing callback: {e}")
                    continue
        logger.debug("End processing callqueue.")

    def _register_callback(self, callback: Callback):
        with self._subscription_lock:
            self._subscriptions.setdefault(callback.event, []).append(callback)

    def register(
        self, func: Callable[[Event], None], event_type: Type[Event]
    ):
        callback = Callback(func=func, event=event_type)
        self._register_callback(callback)
        logger.debug(f"Registered {callback}")

    def subscribe(self, *event_types: Type[Event]):
        '''This is used as a decorator to register a simple function.'''
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
        with self._subscription_lock:
            for callbacks in self._subscriptions.values():
                for callback in callbacks:
                    if callback == func:
                        callbacks.remove(callback)
        logger.debug(f"Removed all callbacks for {func}")

    def clear_event_type(self, event_type: Type[Event]):
        if event_type in self._subscriptions:
            with self._subscription_lock:
                del self._subscriptions[event_type]
            logger.debug(f"Cleared all subscriptions for {event_type}")

    def emit(self, event: Event):
        event_type = type(event)
        logger.debug(f"Emitting {event}")

        if event_type in self._subscriptions:
            callbacks = self._subscriptions[event_type]
            logger.debug(
                f"Processing {event_type.__qualname__} ({len(callbacks)} callbacks)"
            )
            for callback in callbacks:
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
        logger.debug(f"{func.__qualname__}._subscriptions = {event_types}")
        return func

    return decorator


class EventMeta(type):
    """Define a new class with events info gathered after class creation."""

    def __new__(cls, name, bases, attrs):
        new_class = super().__new__(cls, name, bases, attrs)

        _subscriptions: Dict[Type[Event], List[Callback]] = {}
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
        logger.debug(f"Registering callbacks of {self}...")
        for event_type, funcs in self._subscriptions.items():
            for func in funcs:
                func_type = check_function_type(func)
                callback = Callback(func=func, event=event_type)
                if func_type == FunctionTypes.CLASSMETHOD:
                    callback.instance = self.__class__
                elif func_type == FunctionTypes.UNBOUND_METHOD:
                    callback.instance = self
                elif func_type == FunctionTypes.STATICMETHOD or func_type == FunctionTypes.FUNCTION:
                    callback.instance = None
                else:
                    logger.exception(f"Unknown function type for {func.__qualname__} ({func_type})")
                    return
                logger.debug(f"callback.instance = {callback.instance} for {func_type} {func.__qualname__}")
                self.event_manager._register_callback(callback)


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
            logger.exception(f"Error while loading module {module_name}: {e}")
