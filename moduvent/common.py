from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, Dict, Generic, List, NoReturn, Tuple, Type, TypeVar

from loguru import logger

from .descriptors import EventInheritor, EventInstance, WeakReference
from .events import E, Event
from .utils import (
    SUBSCRIPTION_STRATEGY,
    FunctionTypes,
    check_function_type,
    get_subscription_strategy,
    is_class_and_subclass,
    is_instance_and_subclass,
)

common_logger = logger.bind(source="moduvent_common")


# =============================================================================
# Custom Exceptions
# =============================================================================


class DuplicateResultKeyError(Exception):
    """Raised when multiple callbacks return the same result key."""

    def __init__(self, key: str, callback1: str, callback2: str):
        self.key = key
        self.callback1 = callback1
        self.callback2 = callback2
        super().__init__(
            f"Duplicate result key '{key}' returned by callbacks: "
            f"'{callback1}' and '{callback2}'"
        )


class InvalidCallbackReturnError(TypeError):
    """Raised when a callback returns an invalid type (not None or dict[str, Any])."""

    def __init__(self, callback_name: str, return_type: type):
        self.callback_name = callback_name
        self.return_type = return_type
        super().__init__(
            f"Callback '{callback_name}' returned invalid type '{return_type.__name__}'. "
            f"Expected None or dict[str, Any]."
        )


class InvalidCallbackRegistryError(TypeError):
    """Raised when registering a callback with wrong type (sync vs async mismatch)."""

    def __init__(self, callback_name: str, expected: str, got: str):
        self.callback_name = callback_name
        self.expected = expected
        self.got = got
        super().__init__(
            f"Cannot register '{callback_name}': expected {expected} callback, "
            f"got {got} callback."
        )


class CallbackExpiredError(RuntimeError):
    """Raised when a callback's weak reference has expired (been garbage collected).

    This typically happens when:
    1. A local function was registered as a callback but went out of scope
    2. An object with a bound method callback was deleted without unsubscribing

    To fix this:
    - Keep a reference to the callback function/object alive
    - Or call unsubscribe() before the callback goes out of scope
    """

    def __init__(self, event_type: type, callback_info: str):
        self.event_type = event_type
        self.callback_info = callback_info
        super().__init__(
            f"Callback expired for event '{event_type.__name__}': {callback_info}. "
            f"The callback was garbage collected before being unsubscribed. "
            f"Keep a reference to the callback or unsubscribe before it goes out of scope."
        )


# =============================================================================
# Result Validation and Merging Utilities
# =============================================================================


def validate_callback_result(result: Any, callback_name: str) -> Dict[str, Any] | None:
    """Validate and normalize callback return value.

    Args:
        result: The return value from callback
        callback_name: Name of the callback for error messages

    Returns:
        None if result is None, otherwise the validated dict

    Raises:
        InvalidCallbackReturnError: If result is not None or dict[str, Any]
    """
    if result is None:
        return None
    if not isinstance(result, dict):
        raise InvalidCallbackReturnError(callback_name, type(result))
    # Validate all keys are strings
    for key in result.keys():
        if not isinstance(key, str):
            raise InvalidCallbackReturnError(callback_name, type(result))
    return result


def merge_callback_results(
    accumulated: Dict[str, Any],
    new_result: Dict[str, Any] | None,
    callback_name: str,
    result_sources: Dict[str, str],
) -> None:
    """Merge callback result into accumulated results dict.

    Args:
        accumulated: The dict to merge into (mutated in place)
        new_result: The result dict to merge (or None)
        callback_name: Name of the callback for error messages
        result_sources: Dict tracking which callback produced each key

    Raises:
        DuplicateResultKeyError: If a key already exists in accumulated
    """
    if new_result is None:
        return
    for key, value in new_result.items():
        if key in accumulated:
            raise DuplicateResultKeyError(key, result_sources[key], callback_name)
        accumulated[key] = value
        result_sources[key] = callback_name


class BaseCallbackRegistry(ABC, Generic[E]):
    func: WeakReference = WeakReference()
    event_type: EventInheritor = EventInheritor()

    def __init__(
        self,
        func: Callable[[E], Any | Awaitable],
        event_type: Type[E],
        conditions: Tuple[Callable[[E], bool], ...] = (),
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

    def _check_conditions(self, event: E):
        for condition in self.conditions:
            if not condition(event):
                common_logger.debug(f"Condition {condition} failed, skipping.")
                return False
        return True

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


class PostCallbackRegistry(BaseCallbackRegistry[E], Generic[E]):
    func: WeakReference = WeakReference()
    event_type: EventInheritor = EventInheritor()

    def __init__(
        self,
        func: Callable[[E], Any | Awaitable] | Callable[[Any, E], Any | Awaitable],
        event_type: Type[E],
        conditions: Tuple[Callable[[E], bool], ...] = (),
    ) -> None:
        self.func_type = (
            FunctionTypes.UNKNOWN
        )  # we first set func_type since the setter of self.func may use it
        self.func: WeakReference = func
        self.event_type: EventInheritor = event_type
        self.conditions = conditions or ()

        self.func_type = check_function_type(func)

    def __eq__(self, value):
        if isinstance(value, PostCallbackRegistry):
            return super()._compare_attributes(value)
        return super().__eq__(value)


class BaseCallbackProcessing(BaseCallbackRegistry, ABC, Generic[E]):
    func: WeakReference = WeakReference()
    event: EventInstance = EventInstance()

    def __init__(
        self,
        func: Callable[[E], Any],
        event: E,
        conditions: Tuple[Callable[[Event], bool], ...] | None = None,
    ):
        self.func_type = (
            FunctionTypes.UNKNOWN
        )  # we first set func_type since the setter of self.func may use it
        self.func: WeakReference = func
        self.event: EventInstance = event
        self.conditions = conditions or []

        self.func_type = check_function_type(func)

    def is_callable(self) -> bool | NoReturn:
        """Check if conditions are met. Otherwise raise an error."""
        if not self._func_type_valid():
            self._report_function()
        return bool(self._check_conditions(self.event))

    @abstractmethod
    def call(self) -> Dict[str, Any] | None: ...


BCR = TypeVar("BCR", bound=BaseCallbackRegistry)
BCP = TypeVar("BCP", bound=BaseCallbackProcessing)


class BaseEventManager(ABC, Generic[BCR, BCP, E]):
    _subscriptions: Dict[Type[E], List[BCR]] = defaultdict(list)
    _callqueue = None
    _subscription_lock = None
    _callqueue_lock = None
    halted = False

    @property
    @abstractmethod
    def registry_class(cls) -> Type[BCR]: ...

    @property
    @abstractmethod
    def processing_class(cls) -> Type[BCP]: ...

    @abstractmethod
    def _set_subscriptions(self, subscriptions: Dict[Type[E], List[BCR]]):
        """Wrap this function with lock in subclass"""
        self._subscriptions = subscriptions

    @abstractmethod
    def _append_to_callqueue(self, callback: BCP): ...

    @abstractmethod
    def _get_callqueue_length(self) -> int:
        """Since the async version getting the length of callqueue may differ, we have this helper function to abstract the logic."""
        ...

    @abstractmethod
    def reset(self):
        """Reset the subscriptions."""
        ...

    def halt(self):
        """Halt the event manager by setting self.halted to True."""
        self.halted = True

    def _remove_subscriptions(self, filter_func: Callable[[Type[E], BCR], bool]):
        new_subscriptions = defaultdict(list)
        for event_type, callbacks in self._subscriptions.items():
            for cb in callbacks:
                if not filter_func(event_type, cb):
                    new_subscriptions[event_type].append(cb)
                else:
                    common_logger.debug(f"Removing subscription: {cb}")

        self._set_subscriptions(new_subscriptions)

    def _unsubscribe_check_args(
        self, func: Callable[[E], Any] | None, event_type: Type[E] | None
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
        self, func: Callable[[E], Any] | None, event_type: Type[E] | None
    ):
        if func and event_type:
            if event_type not in self._subscriptions:
                common_logger.debug(
                    f"No subscriptions for {event_type} found, skipping."
                )
                return
            self._remove_subscriptions(lambda e, c: e == event_type and c == func)
            common_logger.debug(f"Removed subscription for {event_type} and {func}")
        elif func:
            self._remove_subscriptions(lambda e, c: c == func)
            common_logger.debug(f"Removed all callbacks for {func}")
        elif event_type:
            if event_type in self._subscriptions:
                self._remove_subscriptions(lambda e, c: e == event_type)
                common_logger.debug(f"Cleared all subscriptions for {event_type}")

    @abstractmethod
    def _process_callqueue(self) -> Dict[str, Any]: ...

    @abstractmethod
    def register(
        self,
        func: Callable[[E], Any],
        event_type: Type[E],
        *conditions: Callable[[E], bool],
    ):
        """Wrap this function with lock in subclass"""
        callback: BCR = self.registry_class(
            func=func,
            event_type=event_type,
            conditions=conditions,
        )
        self._subscriptions[callback.event_type].append(callback)
        common_logger.debug(f"Registered {callback}")

    def unsubscribe(
        self,
        func: Callable[[E], Any] | None = None,
        event_type: Type[E] | None = None,
    ):
        self._unsubscribe_check_args(func, event_type)
        self._unsubscribe_process_logic(func, event_type)

    def _emit_check(self, event: E):
        if self.halted:
            common_logger.debug("Event manager is halted, skipping.")
            return False, event
        if not is_instance_and_subclass(event):
            common_logger.warning(f"Skipping non-instance event: {event}")
            return False, event
        event_type = type(event)
        if not event_type.enabled:
            common_logger.debug(f"Skipping disabled event {event_type.__qualname__}")
            return False, event_type
        return True, event_type

    def emit(self, event: E) -> Dict[str, Any]:
        valid, event_type = self._emit_check(event)
        if not valid:
            return {}
        common_logger.debug(f"Emitting {event}")
        expired_callbacks: List[BCR] = []
        if event_type in self._subscriptions:
            callbacks = self._subscriptions[event_type]
            common_logger.debug(
                f"Processing {event_type.__qualname__} ({len(callbacks)} callbacks)"
            )
            for callback in callbacks:
                # Check if the weak reference has expired
                if callback.func is None:
                    common_logger.warning(
                        f"Callback expired for event '{event_type.__name__}': {callback}. "
                        f"The callback was garbage collected before being unsubscribed."
                    )
                    expired_callbacks.append(callback)
                    continue
                if not callback._check_conditions(event):
                    common_logger.debug(
                        f"Skipping {callback} due to conditions not met."
                    )
                    continue
                self._append_to_callqueue(
                    self.processing_class(
                        func=callback.func,
                        event=event,
                        conditions=callback.conditions,
                    )
                )

        # Clean up expired callbacks
        if expired_callbacks:
            self._cleanup_expired_callbacks(event_type, expired_callbacks)

        return self._process_callqueue()

    def _cleanup_expired_callbacks(
        self, event_type: Type[E], expired_callbacks: List[BCR]
    ):
        """Remove expired callbacks from subscriptions."""
        for expired in expired_callbacks:
            if event_type in self._subscriptions:
                try:
                    self._subscriptions[event_type].remove(expired)
                    common_logger.debug(f"Removed expired callback: {expired}")
                except ValueError:
                    pass  # Already removed


def subscribe_method(*args, **kwargs):
    """subscribe dispatcher decorator.
    The first argument must be an event type.
    If the second argument is a function, then functions after that will be registered as conditions.
    If the second argument is another event, then events after that will be registered as multi-callbacks.
    If arguments after the second argument is not same, then it will raise a ValueError.
    """
    strategy = get_subscription_strategy(*args, **kwargs)
    if strategy == SUBSCRIPTION_STRATEGY.EVENTS:

        def events_decorator(func: Callable[[E], Any] | Callable[[Any, E], Any]):
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

        def conditions_decorator(func: Callable[[E], Any] | Callable[[Any, E], Any]):
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
