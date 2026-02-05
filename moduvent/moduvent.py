import contextlib
from collections import defaultdict
from threading import RLock
from typing import Any, Dict, Generic, List, Type
from inspect import iscoroutinefunction

from loguru import logger

from .exceptions import (
    DuplicateResultKeyError,
    InvalidCallbackRegistryError,
    InvalidCallbackReturnError,
)

from .base import (
    BaseCallbackProcessing,
    BaseCallbackRegistry,
    BaseEventManager,
    PostCallbackRegistry,
    callback_type,
    checker_type,
)
from .events import E, EventMeta
from .utils import (
    SUBSCRIPTION_STRATEGY,
    get_subscription_strategy,
    merge_callback_results,
    validate_callback_result,
)

moduvent_logger = logger.bind(source="moduvent_sync")


class CallbackRegistry(BaseCallbackRegistry[E]):
    def __eq__(self, value):
        return (
            self._compare_attributes(value)
            if isinstance(value, CallbackRegistry)
            else False
        )


class CallbackProcessing(BaseCallbackProcessing[E], CallbackRegistry):
    def call(self) -> Dict[str, Any] | None:
        if super().is_callable():
            try:
                result = self.func(self.event)
                callback_name = getattr(self.func, "__qualname__", str(self.func))
                return validate_callback_result(result, callback_name)
            except (InvalidCallbackReturnError, DuplicateResultKeyError):
                raise
            except Exception as e:
                moduvent_logger.exception(f"Error while processing {self}: {e}")
                return None
        return None


# We say that a subscription is the information that a method wants to be called back
# and a registration is the process of adding a method to the list of callbacks for a particular event.
class EventManager(BaseEventManager[CallbackRegistry, CallbackProcessing, E]):
    def __init__(self):
        self._subscriptions: Dict[Type[E], List[CallbackRegistry]] = defaultdict(list)
        self._subscription_lock = RLock()
        self._halted = False

    @property
    def registry_class(cls) -> Type[CallbackRegistry]:
        return CallbackRegistry

    @property
    def processing_class(cls) -> Type[CallbackProcessing]:
        return CallbackProcessing

    def reset(self):
        """Reset subscriptions and resume from halted state."""
        with self._subscription_lock:
            self._subscriptions.clear()
        self._halted = False  # Auto-resume

    def register(
        self,
        func: callback_type,
        event_type: Type[E],
        *conditions: checker_type,
    ):
        """Register a callback for an event type."""
        callback_name = getattr(func, "__qualname__", str(func))
        if iscoroutinefunction(func):
            raise InvalidCallbackRegistryError(
                callback_name, expected="sync", got="async"
            )
        callback = self.registry_class(
            func=func,
            event_type=event_type,
            conditions=conditions,
        )
        with self._subscription_lock:
            self._subscriptions[callback.event_type].append(callback)
        moduvent_logger.debug(f"Registered {callback}")

    def unsubscribe(
        self,
        func: callback_type | None = None,
        event_type: Type[E] | None = None,
    ):
        """Unsubscribe a callback from an event type."""
        self._unsubscribe_check_args(func, event_type)
        with self._subscription_lock:
            if func and event_type:
                if event_type not in self._subscriptions:
                    moduvent_logger.debug(
                        f"No subscriptions for {event_type} found, skipping."
                    )
                    return
                self._subscriptions[event_type] = [
                    cb for cb in self._subscriptions[event_type] if cb.func != func
                ]
                moduvent_logger.debug(
                    f"Removed subscription for {event_type} and {func}"
                )
            elif func:
                for et in list(self._subscriptions.keys()):
                    self._subscriptions[et] = [
                        cb for cb in self._subscriptions[et] if cb.func != func
                    ]
                moduvent_logger.debug(f"Removed all callbacks for {func}")
            elif event_type:
                if event_type in self._subscriptions:
                    del self._subscriptions[event_type]
                    moduvent_logger.debug(f"Cleared all subscriptions for {event_type}")

    def emit(self, event: E) -> Dict[str, Any]:
        """Emit an event to all registered callbacks.

        Uses a local queue to ensure thread safety. Each emit() call
        operates independently without interfering with concurrent emit() calls.
        """
        valid, event_type = self._emit_check(event)
        if not valid:
            return {}

        moduvent_logger.debug(f"Emitting {event}")

        # Get a thread-safe snapshot of callbacks
        with self._subscription_lock:
            if event_type not in self._subscriptions:
                return {}
            callbacks = list(self._subscriptions[event_type])

        if not callbacks:
            return {}

        moduvent_logger.debug(
            f"Processing {event_type.__qualname__} ({len(callbacks)} callbacks)"
        )

        # Build local queue for this emit call
        local_queue: List[CallbackProcessing] = []
        expired_callbacks: List[CallbackRegistry] = []

        for callback in callbacks:
            if self._halted:
                moduvent_logger.debug("Event manager halted during emit, stopping.")
                return {}

            if callback.func is None:
                moduvent_logger.warning(
                    f"Callback expired for event '{event_type.__name__}': {callback}. "
                    f"The callback was garbage collected before being unsubscribed."
                )
                expired_callbacks.append(callback)
                continue

            if not callback._check_conditions(event):
                moduvent_logger.debug(f"Skipping {callback} due to conditions not met.")
                continue

            local_queue.append(
                self.processing_class(
                    func=callback.func,
                    event=event,
                    conditions=callback.conditions,
                )
            )

        # Clean up expired callbacks
        if expired_callbacks:
            with self._subscription_lock:
                for expired in expired_callbacks:
                    if event_type in self._subscriptions:
                        with contextlib.suppress(ValueError):
                            self._subscriptions[event_type].remove(expired)
                            moduvent_logger.debug(
                                f"Removed expired callback: {expired}"
                            )
        # Process the local queue
        return self._process_local_queue(local_queue)

    def _process_local_queue(self, queue: List[CallbackProcessing]) -> Dict[str, Any]:
        """Process a local callback queue and return merged results."""
        if self._halted:
            return {}

        moduvent_logger.debug(f"Processing local queue ({len(queue)} callbacks)...")
        results: Dict[str, Any] = {}
        result_sources: Dict[str, str] = {}

        for callback in queue:
            if self._halted:
                moduvent_logger.debug(
                    "Event manager halted during processing, stopping."
                )
                return results

            moduvent_logger.debug(f"Calling {callback}")
            try:
                result = callback.call()
                callback_name = getattr(
                    callback.func, "__qualname__", str(callback.func)
                )
                merge_callback_results(results, result, callback_name, result_sources)
            except (InvalidCallbackReturnError, DuplicateResultKeyError):
                raise
            except Exception as e:
                moduvent_logger.exception(f"Error while processing callback: {e}")
                continue

        moduvent_logger.debug("End processing local queue.")
        return results

    def subscribe(self, *args, **kwargs):
        """Subscribe decorator for registering callbacks.

        The first argument must be an event type.
        If the second argument is a function, then functions after that will be registered as conditions.
        If the second argument is another event, then events after that will be registered as multi-callbacks.
        """
        strategy = get_subscription_strategy(*args, **kwargs)
        if strategy == SUBSCRIPTION_STRATEGY.EVENTS:

            def events_decorator(func: callback_type):
                for event_type in args:
                    self.register(func=func, event_type=event_type)
                return func

            return events_decorator
        elif strategy == SUBSCRIPTION_STRATEGY.CONDITIONS:
            event_type = args[0]
            conditions = args[1:]

            def conditions_decorator(func: callback_type):
                self.register(func, event_type, *conditions)
                return func

            return conditions_decorator
        else:
            raise ValueError(f"Invalid subscription strategy {strategy}")


class EventAwareBase(Generic[E], metaclass=EventMeta):
    """Base class for classes that want to use @subscribe_method decorator.

    This class provides automatic registration of methods decorated with
    @subscribe_method when an instance is created.

    Usage:
        class MyHandler(EventAwareBase):
            @subscribe_method(MyEvent)
            def handle_event(self, event: MyEvent):
                return {"result": "handled"}

        # Option 1: Use class-level event_manager
        MyHandler.event_manager = my_manager
        handler = MyHandler()

        # Option 2: Pass event_manager to constructor
        handler = MyHandler(event_manager=my_manager)
    """

    event_manager: EventManager
    _subscriptions: Dict[Type[E], List[PostCallbackRegistry]] = {}

    def __init__(self, event_manager: EventManager | None = None):
        """Initialize and register all subscribed methods.

        Args:
            event_manager: Optional EventManager instance. If provided, it will
                be used instead of the class-level event_manager attribute.
        """
        if event_manager is not None:
            self.event_manager = event_manager
        # trigger registrations
        self._register()

    def _register(self):
        moduvent_logger.debug(f"Registering callbacks of {self}...")
        for event_type, callbacks in self._subscriptions.items():
            for callback in callbacks:
                self.event_manager.register(
                    getattr(self, callback.func.__name__),
                    event_type,
                    *callback.conditions,
                )
