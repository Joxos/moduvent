from collections import defaultdict, deque
from collections.abc import Callable
from threading import RLock
from typing import Any, Deque, Dict, Generic, List, Type

from loguru import logger

from .common import (
    BaseCallbackProcessing,
    BaseCallbackRegistry,
    BaseEventManager,
    DuplicateResultKeyError,
    InvalidCallbackRegistryError,
    InvalidCallbackReturnError,
    PostCallbackRegistry,
    merge_callback_results,
    validate_callback_result,
)
from .events import E, EventMeta
from .utils import (
    SUBSCRIPTION_STRATEGY,
    get_subscription_strategy,
    is_coroutine_function,
)

moduvent_logger = logger.bind(source="moduvent_sync")


class CallbackRegistry(BaseCallbackRegistry[E]):
    def __eq__(self, value):
        return (
            super()._compare_attributes(value)
            if isinstance(value, CallbackRegistry)
            else super().__eq__(value)
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
        self._callqueue: Deque[CallbackProcessing] = deque()
        self._subscription_lock = RLock()
        self._callqueue_lock = RLock()

    @property
    def registry_class(cls) -> Type[CallbackRegistry]:
        return CallbackRegistry

    @property
    def processing_class(cls) -> Type[CallbackProcessing]:
        return CallbackProcessing

    def _set_subscriptions(self, subscriptions: Dict[Type[E], List[CallbackRegistry]]):
        with self._subscription_lock:
            return super()._set_subscriptions(subscriptions)

    def _append_to_callqueue(self, callback: CallbackProcessing):
        with self._callqueue_lock:
            self._callqueue.append(callback)

    def _get_callqueue_length(self):
        return len(self._callqueue)

    def reset(self):
        with self._subscription_lock:
            self._subscriptions.clear()

    def halt(self):
        with self._callqueue_lock:
            self._callqueue.clear()

    def _process_callqueue(self) -> Dict[str, Any]:
        if self.halted:
            return {}
        moduvent_logger.debug(f"Callqueue ({self._get_callqueue_length()}):")
        moduvent_logger.debug("Processing callqueue...")
        results: Dict[str, Any] = {}
        result_sources: Dict[str, str] = {}
        with self._callqueue_lock:
            # Copy the queue for logging to avoid iteration issues
            queue_snapshot = list(self._callqueue)
            for callback in queue_snapshot:
                moduvent_logger.debug(f"\t{callback}")
            while self._callqueue:
                callback = self._callqueue.popleft()
                moduvent_logger.debug(f"Calling {callback}")
                try:
                    result = callback.call()
                    callback_name = getattr(
                        callback.func, "__qualname__", str(callback.func)
                    )
                    merge_callback_results(
                        results, result, callback_name, result_sources
                    )
                except (InvalidCallbackReturnError, DuplicateResultKeyError):
                    raise
                except Exception as e:
                    moduvent_logger.exception(f"Error while processing callback: {e}")
                    continue
        moduvent_logger.debug("End processing callqueue.")
        return results

    def register(
        self,
        func: Callable[[E], Any],
        event_type: Type[E],
        *conditions: Callable[[E], bool],
    ):
        # Validate that the callback is not async
        callback_name = getattr(func, "__qualname__", str(func))
        if is_coroutine_function(func):
            raise InvalidCallbackRegistryError(
                callback_name, expected="sync", got="async"
            )
        with self._subscription_lock:
            super().register(func, event_type, *conditions)

    def subscribe(self, *args, **kwargs):
        """subscribe dispatcher decorator.
        The first argument must be an event type.
        If the second argument is a function, then functions after that will be registered as conditions.
        If the second argument is another event, then events after that will be registered as multi-callbacks.
        If arguments after the second argument is not same, then it will raise a ValueError.
        """
        strategy = get_subscription_strategy(*args, **kwargs)
        if strategy == SUBSCRIPTION_STRATEGY.EVENTS:

            def events_decorator(func: Callable[[E], Any]):
                for event_type in args:
                    self.register(func=func, event_type=event_type)
                return func

            return events_decorator
        elif strategy == SUBSCRIPTION_STRATEGY.CONDITIONS:
            event_type = args[0]
            conditions = args[1:]

            def conditions_decorator(func: Callable[[E], Any]):
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
