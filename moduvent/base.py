from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, Dict, Generic, List, NoReturn, Tuple, Type, TypeVar

from loguru import logger


from .descriptors import EventInheritor, EventInstance, WeakReference
from .events import E
from .utils import (
    SUBSCRIPTION_STRATEGY,
    FunctionTypes,
    check_function_type,
    get_subscription_strategy,
    is_class_and_subclass,
    is_instance_and_subclass,
)

common_logger = logger.bind(source="moduvent_common")

callback_type = Callable[[E], dict | Awaitable]
checker_type = Callable[[E], bool]


class BaseCallbackRegistry(ABC, Generic[E]):
    func: WeakReference = WeakReference()
    event_type: EventInheritor = EventInheritor()

    def __init__(
        self,
        func: callback_type,
        event_type: Type[E],
        conditions: Tuple[checker_type, ...] = (),
    ) -> None:
        self.func: WeakReference = func
        self.event_type: EventInheritor = event_type
        self.conditions = conditions or ()

        self.func_type = check_function_type(func)

    def _compare_attributes(self, value: "BaseCallbackRegistry"):
        return (
            self.func == value.func
            and self.event_type == value.event_type
            and self.conditions == value.conditions
        )

    def _check_conditions(self, event: E):
        for condition in self.conditions:
            if not condition(event):
                common_logger.debug(f"Condition {condition} failed, skipping.")
                return False
        return True

    def __str__(self):
        instance_string = str(getattr(self.func, "__self__", "None"))
        func_string = self.func.__qualname__ if self.func else self.func
        return f"Callback: {self.event_type} -> {func_string} ({instance_string}:{self.func_type})"

    def __eq__(self, value):
        if isinstance(value, self.__class__):
            return self._compare_attributes(value)
        return False


class PostCallbackRegistry(BaseCallbackRegistry[E], Generic[E]):
    func: WeakReference = WeakReference()
    event_type: EventInheritor = EventInheritor()

    def __init__(
        self,
        func: callback_type,
        event_type: Type[E],
        conditions: Tuple[checker_type, ...] = (),
    ) -> None:
        super().__init__(func, event_type, conditions)


class BaseCallbackProcessing(BaseCallbackRegistry, ABC, Generic[E]):
    func: WeakReference = WeakReference()
    event: EventInstance = EventInstance()

    def __init__(
        self,
        func: callback_type,
        event: E,
        conditions: Tuple[checker_type, ...] | None = None,
    ):
        super().__init__(func, type(event), conditions or ())
        self.event: EventInstance = event

    def is_callable(self) -> bool | NoReturn:
        """Check if conditions are met. Otherwise raise an error."""
        if self.func_type not in [
            FunctionTypes.BOUND_METHOD,
            FunctionTypes.FUNCTION,
            FunctionTypes.STATICMETHOD,
        ]:
            qualname = getattr(self.func, "__qualname__", self.func)
            raise TypeError(f"Unknown function type for {qualname}")

        return bool(self._check_conditions(self.event))

    @abstractmethod
    def call(self) -> Dict[str, Any] | None: ...


BCR = TypeVar("BCR", bound=BaseCallbackRegistry)
BCP = TypeVar("BCP", bound=BaseCallbackProcessing)


class BaseEventManager(ABC, Generic[BCR, BCP, E]):
    """Abstract base class for event managers.

    Subclasses must implement:
    - registry_class: property returning the callback registry class
    - processing_class: property returning the callback processing class
    - emit(): emit an event to all registered callbacks
    - register(): register a callback for an event type
    - unsubscribe(): unsubscribe callbacks
    - reset(): reset all subscriptions
    """

    _subscriptions: Dict[Type[E], List[BCR]]
    _halted: bool = False

    @property
    def is_halted(self) -> bool:
        """Check if the event manager is halted."""
        return self._halted

    @property
    @abstractmethod
    def registry_class(cls) -> Type[BCR]: ...

    @property
    @abstractmethod
    def processing_class(cls) -> Type[BCP]: ...

    @abstractmethod
    def reset(self):
        """Reset the subscriptions and resume from halted state."""
        ...

    def halt(self):
        """Halt the event manager. All ongoing and future emit() calls will return empty results."""
        self._halted = True

    def resume(self):
        """Resume the event manager from halted state."""
        self._halted = False

    def _emit_check(self, event: E):
        """Validate event before emitting. Returns (is_valid, event_type)."""
        if self._halted:
            common_logger.debug("Event manager is halted, skipping.")
            return False, None
        if not is_instance_and_subclass(event):
            common_logger.warning(f"Skipping non-instance event: {event}")
            return False, None
        event_type = type(event)
        if not event_type.enabled:
            common_logger.debug(f"Skipping disabled event {event_type.__qualname__}")
            return False, None
        return True, event_type

    def _unsubscribe_check_args(
        self, func: callback_type | None, event_type: Type[E] | None
    ):
        """Validate unsubscribe arguments."""
        if not func and not event_type:
            raise ValueError(
                f"Either func or event_type must be provided (got func={func}, event_type={event_type})."
            )
        if not callable(func) and not is_class_and_subclass(event_type):
            raise ValueError(
                f"Invalid argument type (func={func}, event_type={event_type})."
            )

    @abstractmethod
    def emit(self, event: E) -> Dict[str, Any]:
        """Emit an event to all registered callbacks."""
        ...

    @abstractmethod
    def register(
        self,
        func: callback_type,
        event_type: Type[E],
        *conditions: checker_type,
    ):
        """Register a callback for an event type."""
        ...

    @abstractmethod
    def unsubscribe(
        self,
        func: callback_type | None = None,
        event_type: Type[E] | None = None,
    ):
        """Unsubscribe a callback from an event type."""
        ...


def subscribe_method(*args, **kwargs):
    """subscribe dispatcher decorator.
    The first argument must be an event type.
    If the second argument is a function, then functions after that will be registered as conditions.
    If the second argument is another event, then events after that will be registered as multi-callbacks.
    If arguments after the second argument is not same, then it will raise a ValueError.
    """
    strategy = get_subscription_strategy(*args, **kwargs)
    if strategy == SUBSCRIPTION_STRATEGY.EVENTS:

        def events_decorator(func: callback_type):
            if not hasattr(func, "_subscriptions"):
                func._subscriptions = defaultdict(list)  # pyright: ignore[reportFunctionMemberAccess] (function attribute does not support type hint)
            for event_type in args:
                func._subscriptions[event_type].append(  # pyright: ignore[reportFunctionMemberAccess] (function attribute does not support type hint)
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

        def conditions_decorator(func: callback_type):
            if not hasattr(func, "_subscriptions"):
                func._subscriptions = {}  # pyright: ignore[reportFunctionMemberAccess] (function attribute does not support type hint)
            if event_type not in func._subscriptions:  # pyright: ignore[reportFunctionMemberAccess]
                func._subscriptions[event_type] = []  # pyright: ignore[reportFunctionMemberAccess]
            func._subscriptions[event_type].append(  # pyright: ignore[reportFunctionMemberAccess] (function attribute does not support type hint)
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
