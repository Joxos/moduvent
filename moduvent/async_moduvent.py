import asyncio
from collections import defaultdict
from collections.abc import Callable
from threading import RLock
from typing import Any, Awaitable, Dict, Generic, List, Tuple, Type

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

async_moduvent_logger = logger.bind(source="moduvent_async")


class AsyncPostCallbackRegistry(PostCallbackRegistry[E]):
    def __init__(
        self,
        func: Callable[[E], Awaitable],
        event_type: Type[E],
        conditions: Tuple[Callable[[E], bool], ...] = (),
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
        self._callqueue: asyncio.Queue[AsyncCallbackProcessing] = asyncio.Queue()
        self._subscription_lock = asyncio.Lock()
        self._post_subscription_lock = RLock()

        self.worker_count = 10

    @property
    def registry_class(cls) -> Type[AsyncCallbackRegistry]:
        return AsyncCallbackRegistry

    @property
    def processing_class(cls) -> Type[AsyncCallbackProcessing]:
        return AsyncCallbackProcessing

    async def _set_subscriptions(  # pyright: ignore[reportIncompatibleMethodOverride] (async version)
        self, subscriptions: Dict[Type[E], List[AsyncCallbackRegistry]]
    ):
        async with self._subscription_lock:
            return super()._set_subscriptions(subscriptions)

    async def _append_to_callqueue(self, callback: AsyncCallbackProcessing):  # pyright: ignore[reportIncompatibleMethodOverride] (async version)
        await self._callqueue.put(callback)

    def _get_callqueue_length(self) -> int:
        return self._callqueue.qsize()

    async def reset(self):  # pyright: ignore[reportIncompatibleMethodOverride] (async version)
        async with self._subscription_lock:
            self._subscriptions.clear()

    async def halt(self):  # pyright: ignore[reportIncompatibleMethodOverride] (async version)
        async with self._subscription_lock:
            self._subscriptions.clear()

    async def _process_callqueue(self) -> Dict[str, Any]:  # pyright: ignore[reportIncompatibleMethodOverride] (async version)
        if self.halted:
            return {}
        # note that asyncio.Queue is not iterable
        async_moduvent_logger.debug(f"Callqueue ({self._get_callqueue_length()}):")
        # for i in range(self._get_callqueue_length()):
        #     callback = self._callqueue.get_nowait()
        #     async_moduvent_logger.debug(f"\t{callable}")
        #     self._callqueue.put_nowait(callback)
        async_moduvent_logger.debug("Processing callqueue...")
        # The asyncio.Queue is naturally corotine-safe
        # Note: Async emit does NOT guarantee callback execution order
        tasks: list[tuple[asyncio.Task, str]] = []  # (task, callback_name)
        async with asyncio.TaskGroup() as group:
            while not self._callqueue.empty():
                callback = await self._callqueue.get()
                async_moduvent_logger.debug(f"Calling {callback}...")
                try:
                    callback_name = getattr(
                        callback.func, "__qualname__", str(callback.func)
                    )
                    task = group.create_task(callback.call())
                    tasks.append((task, callback_name))
                    self._callqueue.task_done()
                except Exception as e:
                    async_moduvent_logger.exception(
                        f"Error while processing callback: {e}"
                    )
                    continue
            await self._callqueue.join()
        async_moduvent_logger.debug("End processing callqueue.")

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

    async def register(  # pyright: ignore[reportIncompatibleMethodOverride] (async version)
        self,
        func: Callable[[E], None],
        event_type: Type[E],
        *conditions: Callable[[E], bool],
    ):
        # Validate that the callback is async
        callback_name = getattr(func, "__qualname__", str(func))
        if not is_coroutine_function(func):
            raise InvalidCallbackRegistryError(
                callback_name, expected="async", got="sync"
            )
        async with self._subscription_lock:
            super().register(func, event_type, *conditions)

    async def unsubscribe(  # pyright: ignore[reportIncompatibleMethodOverride] (async version)
        self,
        func: Callable[[E], Any] | None = None,
        event_type: Type[E] | None = None,
    ):
        """Async version of unsubscribe that properly awaits _set_subscriptions."""
        self._unsubscribe_check_args(func, event_type)
        # We need to reimplement _unsubscribe_process_logic here because
        # _remove_subscriptions calls _set_subscriptions which is async
        if func and event_type:
            if event_type not in self._subscriptions:
                async_moduvent_logger.debug(
                    f"No subscriptions for {event_type} found, skipping."
                )
                return
            await self._async_remove_subscriptions(
                lambda e, c: e == event_type and c == func
            )
            async_moduvent_logger.debug(
                f"Removed subscription for {event_type} and {func}"
            )
        elif func:
            await self._async_remove_subscriptions(lambda e, c: c == func)
            async_moduvent_logger.debug(f"Removed all callbacks for {func}")
        elif event_type:
            if event_type in self._subscriptions:
                await self._async_remove_subscriptions(lambda e, c: e == event_type)
                async_moduvent_logger.debug(
                    f"Cleared all subscriptions for {event_type}"
                )

    async def _async_remove_subscriptions(
        self, filter_func: Callable[[Type[E], AsyncCallbackRegistry], bool]
    ):
        """Async version of _remove_subscriptions."""
        from collections import defaultdict

        new_subscriptions = defaultdict(list)
        for event_type, callbacks in self._subscriptions.items():
            for cb in callbacks:
                if not filter_func(event_type, cb):
                    new_subscriptions[event_type].append(cb)
                else:
                    async_moduvent_logger.debug(f"Removing subscription: {cb}")

        await self._set_subscriptions(new_subscriptions)

    async def initialize(self):
        """Call this in main event loop to register post-subscriptions."""
        async_moduvent_logger.debug("Initializing event manager...")
        # we do not acquire async lock here since it will cause deadlock with register()
        # this might be a PROBLEM in occasions where we initialize() along with subscribe()
        # for now we assume that subscribe() will be called before initialize()
        with self._post_subscription_lock:
            async with asyncio.TaskGroup() as group:
                for event_type, callbacks in self._post_subscriptions.items():
                    for callback in callbacks:
                        group.create_task(self.register(callback.func, event_type))
        self._post_subscriptions.clear()

    def subscribe(self, *args, **kwargs):
        strategy = get_subscription_strategy(*args, **kwargs)
        if strategy == SUBSCRIPTION_STRATEGY.EVENTS:

            def events_decorator(
                func: Callable[[E], Awaitable] | Callable[[Any, E], Awaitable],
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
                func: Callable[[E], Awaitable] | Callable[[Any, E], Awaitable],
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

    async def emit(self, event: E) -> Dict[str, Any]:  # pyright: ignore[reportIncompatibleMethodOverride] (async version)
        valid, event_type = self._emit_check(event)
        if not valid:
            return {}
        async_moduvent_logger.debug(f"Emitting {event}")
        expired_callbacks = []
        if event_type in self._subscriptions:
            logger.debug(f"Processing {event_type.__qualname__} subscriptions...")
            callbacks = self._subscriptions[event_type]
            async_moduvent_logger.debug(
                f"Processing {event_type.__qualname__} ({len(callbacks)} callbacks)"
            )
            for callback in callbacks:
                # Check if the weak reference has expired
                if callback.func is None:
                    async_moduvent_logger.warning(
                        f"Callback expired for event '{event_type.__name__}': {callback}. "
                        f"The callback was garbage collected before being unsubscribed."
                    )
                    expired_callbacks.append(callback)
                    continue
                logger.debug(f"Adding {callback} to callqueue...")
                await self._append_to_callqueue(
                    self.processing_class(
                        func=callback.func,
                        event=event,
                        conditions=callback.conditions,
                    )
                )

        # Clean up expired callbacks
        if expired_callbacks:
            await self._async_cleanup_expired_callbacks(event_type, expired_callbacks)

        return await self._process_callqueue()

    async def _async_cleanup_expired_callbacks(self, event_type, expired_callbacks):
        """Remove expired callbacks from subscriptions (async version)."""
        for expired in expired_callbacks:
            if event_type in self._subscriptions:
                try:
                    self._subscriptions[event_type].remove(expired)
                    async_moduvent_logger.debug(f"Removed expired callback: {expired}")
                except ValueError:
                    pass  # Already removed


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
