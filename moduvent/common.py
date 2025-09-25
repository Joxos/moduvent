import importlib
import weakref
from abc import ABC, abstractmethod
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Type

from loguru import logger

logger.remove()
common_logger = logger.bind(source="moduvent_common")


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


class Event:
    """Base event class"""

    def __str__(self):
        # get all attributes without the ones starting with __
        attrs = [f"{k}={v}" for k, v in self.__dict__.items() if not k.startswith("__")]
        return f"{type(self).__qualname__}({', '.join(attrs)})"


class WeakReference:
    def __set__(self, obj, value):
        obj._func_ref = (
            weakref.WeakMethod(value)
            if check_function_type(value) == FunctionTypes.BOUND_METHOD
            else weakref.ref(value)
        )

    def __get__(self, obj, objtype=None):
        return obj._func_ref() if obj else None


class BaseCallback(ABC):
    func = WeakReference()

    def __init__(
        self,
        func: Callable[[Event], None],
        event: Type[Event] | Event,
    ):
        """
        BOUND_METHOD: instance is the instance (BOUND_METHOD) or class (CLASSMETHOD)
        UNBOUND_METHOD: instance isn't set yet since the class hasn't been initialized
        FUNCTION/STATICMETHOD: instance is None
        """
        self.func: weakref.ReferenceType[Callable[[Event], None]] = func
        self.event: Event | Type[Event] = event
        self.func_type = check_function_type(func)

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
        return f"Callback: {self.event} -> {self.func.__qualname__} ({instance_string}:{self.func_type})"


def subscribe_method(*event_types: Type[Event]):
    """Tag the method with subscription info."""
    # Validate that all event_types are subclasses of Event
    for event_type in event_types:
        if not isinstance(event_type, type) or not issubclass(event_type, Event):
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
