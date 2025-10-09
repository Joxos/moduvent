import importlib
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import (
    Concatenate,
    Dict,
    Generic,
    List,
    Literal,
    NoReturn,
    ParamSpec,
    Tuple,
    Type,
    TypeVar,
)

from loguru import logger

from .descriptors import EventInheritor, EventInstance, WeakReference
from .events import Event
from .utils import (
    SUBSCRIPTION_STRATEGY,
    FunctionTypes,
    _get_subscription_strategy,
    check_function_type,
    is_class_and_subclass,
    is_instance_and_subclass,
)

common_logger = logger.bind(source="moduvent_common")


class BaseCallbackRegistry(ABC):
    func: WeakReference = WeakReference()
    event_type: EventInheritor = EventInheritor()

    def __init__(
        self,
        func: Callable[[Event], None],
        event_type: Type[Event],
        conditions: Tuple[Callable[[Event], bool], ...] = (),
    ) -> None:
        self.func_type = (
            FunctionTypes.UNKNOWN
        )  # we first set func_type since the setter of self.func may use it
        self.func: WeakReference = func
        self.event_type: EventInheritor = event_type
        self.conditions = conditions or ()

        self.func_type = check_function_type(func)

    def _report_function(self) -> NoReturn:
        qualname = getattr(self.func, "__qualname__", self.func)
        raise TypeError(f"Unknown function type for {qualname}")

    def _func_type_valid(self) -> bool:
        return self.func_type in [
            FunctionTypes.BOUND_METHOD,
            FunctionTypes.FUNCTION,
            FunctionTypes.STATICMETHOD,
        ]

    def _shallow_copy(
        self, subclass: Type["BaseCallbackRegistry"]
    ) -> "BaseCallbackRegistry|None":
        if self.func:
            return subclass(
                func=self.func,  # the weakref is valid or not is checked by the setter of subclass
                event_type=self.event_type,
                conditions=self.conditions,
            )
        return None

    def _compare_attributes(self, value: "BaseCallbackRegistry"):
        return (
            self.func == value.func
            and self.event_type == value.event_type
            and self.conditions == value.conditions
        )

    @abstractmethod
    def __eq__(self, value):
        return (
            self.func == value
            if check_function_type(value)
            in [
                FunctionTypes.BOUND_METHOD,
                FunctionTypes.UNBOUND_METHOD,
                FunctionTypes.FUNCTION,
                FunctionTypes.STATICMETHOD,
            ]
            else False
        )

    def __str__(self):
        instance_string = str(getattr(self.func, "__self__", "None"))
        func_string = self.func.__qualname__ if self.func else self.func
        return f"Callback: {self.event_type} -> {func_string} ({instance_string}:{self.func_type})"


class PostCallbackRegistry(BaseCallbackRegistry):
    func: WeakReference = WeakReference()

    def __eq__(self, value):
        if isinstance(value, PostCallbackRegistry):
            return super()._compare_attributes(value)
        return super().__eq__(value)


class BaseCallbackProcessing(BaseCallbackRegistry, ABC):
    func: WeakReference = WeakReference()
    event: EventInstance = EventInstance()

    def __init__(
        self,
        func: Callable[[Event], None],
        event: Event,
        conditions: Tuple[Callable[[Event], bool], ...] | None = None,
    ):
        self.func_type = (
            FunctionTypes.UNKNOWN
        )  # we first set func_type since the setter of self.func may use it
        self.func: WeakReference = func
        self.event: EventInstance = event
        self.conditions = conditions or []

        self.func_type = check_function_type(func)

    def _check_conditions(self):
        for condition in self.conditions:
            if not condition(self.event):
                common_logger.debug(f"Condition {condition} failed, skipping.")
                return False
        return True

    def callable(self) -> Literal[True] | NoReturn:
        """Check if conditions are met. Otherwise raise an error."""
        return (
            True
            if self.func and self._func_type_valid() and self._check_conditions()
            else self._report_function()
        )

    @abstractmethod
    def call(self): ...


BCR = TypeVar("BCR", bound=BaseCallbackRegistry)
BCP = TypeVar("BCP", bound=BaseCallbackProcessing)


class BaseEventManager(ABC, Generic[BCR, BCP]):
    _subscriptions: Dict[Type[Event], List[BCR]] = {}
    _callqueue = None
    _subscription_lock = None
    _callqueue_lock = None

    @property
    @abstractmethod
    def registry_class(cls) -> Type[BCR]: ...

    @property
    @abstractmethod
    def processing_class(cls) -> Type[BCP]: ...

    @abstractmethod
    def __init__(self):
        """Note that the correct registry_class and processing_class should be set in the subclass here."""
        ...

    @abstractmethod
    def _set_subscriptions(self, subscriptions: Dict[Type[Event], List[BCR]]):
        """Wrap this function with lock in subclass"""
        self._subscriptions = subscriptions

    @abstractmethod
    def _append_to_callqueue(self, callback: BCP): ...

    @abstractmethod
    def _get_callqueue_length(self) -> int:
        """Since the async version getting the length of callqueue may differ, we have this helper function to abstract the logic."""
        ...

    @abstractmethod
    def reset(self): ...

    def _remove_subscriptions(self, filter_func: Callable[[Type[Event], BCR], bool]):
        new_subscriptions = {}
        for event_type, callbacks in list(self._subscriptions.items()):
            for cb in callbacks:
                if not filter_func(event_type, cb):
                    new_subscriptions.setdefault(event_type, []).append(cb)
                else:
                    common_logger.debug(f"Removing subscription: {cb}")

        self._set_subscriptions(new_subscriptions)

    def _unsubscribe_check_args(
        self, func: Callable[[Event], None] | None, event_type: Type[Event] | None
    ):
        if not func and not event_type:
            raise ValueError(
                f"Either func or event_type must be provided (got func={func}, event_type={event_type})."
            )
        if not callable(func) and not is_class_and_subclass(event_type):
            raise ValueError(
                f"Invalid argument type (func={func}, event_type={event_type})."
            )

    def _unsubscribe_process_logic(
        self, func: Callable[[Event], None] | None, event_type: Type[Event] | None
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
                self._remove_subscriptions(lambda e, c: e == event_type)
                common_logger.debug(f"Cleared all subscriptions for {event_type}")

    @abstractmethod
    def _process_callqueue(self): ...

    @abstractmethod
    def register(
        self,
        func: Callable[[Event], None],
        event_type: Type[Event],
        *conditions: Callable[[Event], bool],
    ):
        """Wrap this function with lock in subclass"""
        callback: BCR = self.registry_class(
            func=func,
            event_type=event_type,
            conditions=conditions,
        )
        self._subscriptions.setdefault(callback.event_type, []).append(callback)
        common_logger.debug(f"Registered {callback}")

    def verbose_subscriptions(self):
        common_logger.debug("Subscriptions:")
        for event_type, callbacks in self._subscriptions.items():
            common_logger.debug(f"\t{event_type.__qualname__} ({len(callbacks)}):")
            for callback in callbacks:
                common_logger.debug(f"\t\t{callback}")

    def unsubscribe(
        self,
        func: Callable[[Event], None] | None = None,
        event_type: Type[Event] | None = None,
    ):
        self._unsubscribe_check_args(func, event_type)
        self._unsubscribe_process_logic(func, event_type)

    def _emit_check(self, event: Event):
        if not is_instance_and_subclass(event):
            common_logger.warning(f"Skipping non-instance event: {event}")
            return False, event
        event_type = type(event)
        if not event_type.enabled:
            common_logger.debug(f"Skipping disabled event {event_type.__qualname__}")
            return False, event_type
        return True, event_type

    def emit(self, event: Event):
        valid, event_type = self._emit_check(event)
        if not valid:
            return
        common_logger.debug(f"Emitting {event}")
        if event_type in self._subscriptions:
            callbacks = self._subscriptions[event_type]
            common_logger.debug(
                f"Processing {event_type.__qualname__} ({len(callbacks)} callbacks)"
            )
            for callback in callbacks:
                self._append_to_callqueue(
                    self.processing_class(
                        func=callback.func,
                        event=event,
                        conditions=callback.conditions,
                    )
                )

        self._process_callqueue()


def subscribe_method(*args, **kwargs):
    """subscribe dispatcher decorator.
    The first argument must be an event type.
    If the second argument is a function, then functions after that will be registered as conditions.
    If the second argument is another event, then events after that will be registered as multi-callbacks.
    If arguments after the second argument is not same, then it will raise a ValueError.
    """
    strategy = _get_subscription_strategy(*args, **kwargs)
    P = ParamSpec("P")
    if strategy == SUBSCRIPTION_STRATEGY.EVENTS:

        def events_decorator(func: Callable[Concatenate[Event, P], None]):
            if not hasattr(func, "_subscriptions"):
                func._subscriptions = {}  # pyright: ignore[reportFunctionMemberAccess] (function attribute does not support type hint)
            for event_type in args:
                func._subscriptions.setdefault(event_type, []).append(  # pyright: ignore[reportFunctionMemberAccess] (function attribute does not support type hint)
                    PostCallbackRegistry(func=func, event_type=event_type)
                )
                common_logger.debug(
                    f"{func.__qualname__}._subscriptions[{event_type}] is set."
                )
            return func

        return events_decorator
    elif strategy == SUBSCRIPTION_STRATEGY.CONDITIONS:
        event_type = args[0]
        conditions = args[1:]

        def conditions_decorator(func: Callable[Concatenate[Event, P], None]):
            if not hasattr(func, "_subscriptions"):
                func._subscriptions = {}  # pyright: ignore[reportFunctionMemberAccess] (function attribute does not support type hint)
            func._subscriptions.setdefault(event_type, []).append(  # pyright: ignore[reportFunctionMemberAccess] (function attribute does not support type hint)
                PostCallbackRegistry(
                    func=func, event_type=event_type, conditions=conditions
                )
            )
            common_logger.debug(
                f"{func.__qualname__}._subscriptions[{event_type}] = {conditions}"
            )
            return func

        return conditions_decorator
    else:
        raise ValueError(f"Invalid subscription strategy {strategy}")


class EventMeta(type):
    """Define a new class with events info gathered after class creation."""

    def __new__(cls, name, bases, attrs):
        new_class = super().__new__(cls, name, bases, attrs)

        _subscriptions: Dict[Type[Event], List[PostCallbackRegistry]] = {}
        for attr_name, attr_value in attrs.items():
            # find all subscriptions of methods
            if hasattr(attr_value, "_subscriptions"):
                for event_type in attr_value._subscriptions:
                    _subscriptions.setdefault(event_type, []).extend(
                        attr_value._subscriptions[event_type]
                    )

        new_class._subscriptions = _subscriptions  # pyright: ignore[reportAttributeAccessIssue] (surpress because it's metaclass)
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
