import asyncio
import contextlib
from collections import defaultdict
from threading import RLock
from typing import Any, Dict, Generic, List, Tuple, Type
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

async_moduvent_logger = logger.bind(source="moduvent_async")


class AsyncPostCallbackRegistry(PostCallbackRegistry[E]):
    def __init__(
        self,
        func: callback_type,
        event_type: Type[E],
        conditions: Tuple[checker_type, ...] = (),
    ) -> None:
        super().__init__(func, event_type, conditions)

    def __eq__(self, value):
        if isinstance(value, AsyncPostCallbackRegistry):
            return self._compare_attributes(value)
        return super().__eq__(value)


class AsyncCallbackRegistry(BaseCallbackRegistry[E]):
    def __eq__(self, value):
        if isinstance(value, AsyncCallbackRegistry):
            return self._compare_attributes(value)
        return super().__eq__(value)


class AsyncCallbackProcessing(BaseCallbackProcessing[E], AsyncCallbackRegistry):
    async def call(self) -> Dict[str, Any] | None:  # pyright: ignore[reportIncompatibleMethodOverride] (async version)
        if super().is_callable():
            try:
                result = await self.func(self.event)
                callback_name = getattr(self.func, "__qualname__", str(self.func))
                return validate_callback_result(result, callback_name)
            except (InvalidCallbackReturnError, DuplicateResultKeyError):
                raise
            except Exception as e:
                async_moduvent_logger.exception(f"Error while calling {self}: {e}")
                return None
        return None


# We say that a subscription is the information that a method wants to be called back
# and a registration is the process of adding a method to the list of callbacks for a particular event.
class AsyncEventManager(
    BaseEventManager[AsyncCallbackRegistry, AsyncCallbackProcessing, E]
):
    def __init__(self):
        self._subscriptions: Dict[Type[E], List[AsyncCallbackRegistry]] = defaultdict(
            list
        )
        self._post_subscriptions: Dict[Type[E], List[PostCallbackRegistry]] = (
            defaultdict(list)
        )
        self._subscription_lock = asyncio.Lock()
        self._post_subscription_lock = RLock()
        self._halted = False

    @property
    def registry_class(cls) -> Type[AsyncCallbackRegistry]:
        return AsyncCallbackRegistry

    @property
    def processing_class(cls) -> Type[AsyncCallbackProcessing]:
        return AsyncCallbackProcessing

    async def reset(self):
        """Reset subscriptions and resume from halted state."""
        async with self._subscription_lock:
            self._subscriptions.clear()
        self._halted = False  # Auto-resume

    async def register(
        self,
        func: callback_type,
        event_type: Type[E],
        *conditions: checker_type,
    ):
        """Register an async callback for an event type."""
        callback_name = getattr(func, "__qualname__", str(func))
        if not iscoroutinefunction(func):
            raise InvalidCallbackRegistryError(
                callback_name, expected="async", got="sync"
            )
        callback = self.registry_class(
            func=func,
            event_type=event_type,
            conditions=conditions,
        )
        async with self._subscription_lock:
            self._subscriptions[callback.event_type].append(callback)
        async_moduvent_logger.debug(f"Registered {callback}")

    async def unsubscribe(
        self,
        func: callback_type | None = None,
        event_type: Type[E] | None = None,
    ):
        """Unsubscribe a callback from an event type."""
        self._unsubscribe_check_args(func, event_type)
        async with self._subscription_lock:
            if func and event_type:
                if event_type not in self._subscriptions:
                    async_moduvent_logger.debug(
                        f"No subscriptions for {event_type} found, skipping."
                    )
                    return
                self._subscriptions[event_type] = [
                    cb for cb in self._subscriptions[event_type] if cb.func != func
                ]
                async_moduvent_logger.debug(
                    f"Removed subscription for {event_type} and {func}"
                )
            elif func:
                for et in list(self._subscriptions.keys()):
                    self._subscriptions[et] = [
                        cb for cb in self._subscriptions[et] if cb.func != func
                    ]
                async_moduvent_logger.debug(f"Removed all callbacks for {func}")
            elif event_type:
                if event_type in self._subscriptions:
                    del self._subscriptions[event_type]
                    async_moduvent_logger.debug(
                        f"Cleared all subscriptions for {event_type}"
                    )

    async def emit(self, event: E) -> Dict[str, Any]:
        """Emit an event to all registered callbacks.

        Uses a local queue to ensure thread safety. Each emit() call
        operates independently without interfering with concurrent emit() calls.
        """
        valid, event_type = self._emit_check(event)
        if not valid:
            return {}

        async_moduvent_logger.debug(f"Emitting {event}")

        # Get a snapshot of callbacks (with lock)
        async with self._subscription_lock:
            if event_type not in self._subscriptions:
                return {}
            callbacks = list(self._subscriptions[event_type])

        if not callbacks:
            return {}

        async_moduvent_logger.debug(
            f"Processing {event_type.__qualname__} ({len(callbacks)} callbacks)"
        )

        # Build local queue for this emit call
        local_queue: List[AsyncCallbackProcessing] = []
        expired_callbacks: List[AsyncCallbackRegistry] = []

        for callback in callbacks:
            if self._halted:
                async_moduvent_logger.debug(
                    "Event manager halted during emit, stopping."
                )
                return {}

            if callback.func is None:
                async_moduvent_logger.warning(
                    f"Callback expired for event '{event_type.__name__}': {callback}. "
                    f"The callback was garbage collected before being unsubscribed."
                )
                expired_callbacks.append(callback)
                continue

            if not callback._check_conditions(event):
                async_moduvent_logger.debug(
                    f"Skipping {callback} due to conditions not met."
                )
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
            async with self._subscription_lock:
                for expired in expired_callbacks:
                    if event_type in self._subscriptions:
                        with contextlib.suppress(ValueError):
                            self._subscriptions[event_type].remove(expired)
                            async_moduvent_logger.debug(
                                f"Removed expired callback: {expired}"
                            )
        # Process the local queue
        return await self._process_local_queue(local_queue)

    async def _process_local_queue(
        self, queue: List[AsyncCallbackProcessing]
    ) -> Dict[str, Any]:
        """Process a local callback queue and return merged results."""
        if self._halted:
            return {}

        async_moduvent_logger.debug(
            f"Processing local queue ({len(queue)} callbacks)..."
        )

        # Note: Async emit does NOT guarantee callback execution order
        tasks: list[tuple[asyncio.Task, str]] = []  # (task, callback_name)
        async with asyncio.TaskGroup() as group:
            for callback in queue:
                if self._halted:
                    async_moduvent_logger.debug(
                        "Event manager halted during processing, stopping."
                    )
                    break

                async_moduvent_logger.debug(f"Calling {callback}...")
                try:
                    callback_name = getattr(
                        callback.func, "__qualname__", str(callback.func)
                    )
                    task = group.create_task(callback.call())
                    tasks.append((task, callback_name))
                except Exception as e:
                    async_moduvent_logger.exception(
                        f"Error while processing callback: {e}"
                    )
                    continue

        async_moduvent_logger.debug("End processing local queue.")

        # Merge results from all tasks
        results: Dict[str, Any] = {}
        result_sources: Dict[str, str] = {}
        for task, callback_name in tasks:
            try:
                result = task.result()
                merge_callback_results(results, result, callback_name, result_sources)
            except (InvalidCallbackReturnError, DuplicateResultKeyError):
                raise
            except Exception as e:
                async_moduvent_logger.exception(
                    f"Error getting result from callback {callback_name}: {e}"
                )
        return results

    async def initialize(self):
        """Call this in main event loop to register post-subscriptions."""
        async_moduvent_logger.debug("Initializing event manager...")
        with self._post_subscription_lock:
            async with asyncio.TaskGroup() as group:
                for event_type, callbacks in self._post_subscriptions.items():
                    for callback in callbacks:
                        group.create_task(self.register(callback.func, event_type))
        self._post_subscriptions.clear()

    def subscribe(self, *args, **kwargs):
        """Subscribe decorator for registering async callbacks.

        The first argument must be an event type.
        If the second argument is a function, then functions after that will be registered as conditions.
        If the second argument is another event, then events after that will be registered as multi-callbacks.
        """
        strategy = get_subscription_strategy(*args, **kwargs)
        if strategy == SUBSCRIPTION_STRATEGY.EVENTS:

            def events_decorator(
                func: callback_type,
            ):
                for event_type in args:
                    self._post_subscriptions[event_type].append(
                        PostCallbackRegistry(func=func, event_type=event_type)
                    )
                return func

            return events_decorator
        elif strategy == SUBSCRIPTION_STRATEGY.CONDITIONS:
            event_type = args[0]
            conditions = args[1:]

            def conditions_decorator(
                func: callback_type,
            ):
                self._post_subscriptions[event_type].append(
                    PostCallbackRegistry(
                        func=func, event_type=event_type, conditions=conditions
                    )
                )
                return func

            return conditions_decorator
        else:
            raise ValueError(f"Invalid subscription strategy: {strategy}")


class AsyncEventAwareBase(Generic[E], metaclass=EventMeta):
    """Base class for classes that want to use @subscribe_method decorator with async handlers.

    This class provides automatic registration of async methods decorated with
    @subscribe_method. Since registration is async, use the create() class method
    to instantiate.

    Usage:
        class MyAsyncHandler(AsyncEventAwareBase):
            @subscribe_method(MyEvent)
            async def handle_event(self, event: MyEvent):
                return {"result": "handled"}

        # Option 1: Use class-level event_manager
        MyAsyncHandler.event_manager = my_async_manager
        handler = await MyAsyncHandler.create()

        # Option 2: Pass event_manager to create()
        handler = await MyAsyncHandler.create(event_manager=my_async_manager)
    """

    event_manager: AsyncEventManager
    _subscriptions: Dict[Type[E], List[PostCallbackRegistry]] = {}

    def __init__(self, event_manager: AsyncEventManager | None = None):
        """Initialize the instance (but does not register handlers).

        Note: Use create() class method instead of __init__ directly,
        as registration requires async operations.

        Args:
            event_manager: Optional AsyncEventManager instance. If provided, it will
                be used instead of the class-level event_manager attribute.
        """
        if event_manager is not None:
            self.event_manager = event_manager

    @classmethod
    async def create(
        cls, event_manager: AsyncEventManager | None = None, **kwargs
    ) -> "AsyncEventAwareBase":
        """Create and initialize an instance with all handlers registered.

        This is the recommended way to instantiate AsyncEventAwareBase subclasses.

        Args:
            event_manager: Optional AsyncEventManager instance. If provided, it will
                be used instead of the class-level event_manager attribute.
            **kwargs: Additional keyword arguments passed to __init__.

        Returns:
            A fully initialized instance with all handlers registered.

        Example:
            handler = await MyAsyncHandler.create(event_manager=manager)
        """
        instance = cls(event_manager=event_manager, **kwargs)
        await instance._register()
        return instance

    async def _register(self):
        async_moduvent_logger.debug(f"Registering callbacks of {self}...")
        for event_type, callbacks in self._subscriptions.items():
            for callback in callbacks:
                await self.event_manager.register(
                    getattr(self, callback.func.__name__),
                    event_type,
                    *callback.conditions,
                )
