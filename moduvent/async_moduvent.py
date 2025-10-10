import asyncio
from abc import abstractmethod
from collections.abc import Callable
from threading import RLock
from typing import Any, Awaitable, Dict, Generic, List, Tuple, Type

from loguru import logger

from .common import (
    BaseCallbackProcessing,
    BaseCallbackRegistry,
    BaseEventManager,
    PostCallbackRegistry,
)
from .events import E, EventMeta
from .utils import SUBSCRIPTION_STRATEGY, get_subscription_strategy

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
    async def call(self):  # pyright: ignore[reportIncompatibleMethodOverride] (async version)
        if super().callable():
            try:
                await self.func(self.event)
            except Exception as e:
                async_moduvent_logger.exception(f"Error while calling {self}: {e}")


# We say that a subscription is the information that a method wants to be called back
# and a registration is the process of adding a method to the list of callbacks for a particular event.
class AsyncEventManager(
    BaseEventManager[AsyncCallbackRegistry, AsyncCallbackProcessing, E]
):
    def __init__(self):
        self._subscriptions: Dict[Type[E], List[AsyncCallbackRegistry]] = {}
        self._post_subscriptions: Dict[Type[E], List[PostCallbackRegistry]] = {}
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

    async def _process_callqueue(self):  # pyright: ignore[reportIncompatibleMethodOverride] (async version)
        # note that asyncio.Queue is not iterable
        async_moduvent_logger.debug(f"Callqueue ({self._get_callqueue_length()}):")
        # for i in range(self._get_callqueue_length()):
        #     callback = self._callqueue.get_nowait()
        #     async_moduvent_logger.debug(f"\t{callable}")
        #     self._callqueue.put_nowait(callback)
        async_moduvent_logger.debug("Processing callqueue...")
        # The asyncio.Queue is naturally corotine-safe
        async with asyncio.TaskGroup() as group:
            while not self._callqueue.empty():
                callback = await self._callqueue.get()
                async_moduvent_logger.debug(f"Calling {callback}...")
                try:
                    group.create_task(callback.call())
                    self._callqueue.task_done()
                except Exception as e:
                    async_moduvent_logger.exception(
                        f"Error while processing callback: {e}"
                    )
                    continue
            await self._callqueue.join()
        async_moduvent_logger.debug("End processing callqueue.")

    async def register(  # pyright: ignore[reportIncompatibleMethodOverride] (async version)
        self,
        func: Callable[[E], None],
        event_type: Type[E],
        *conditions: Callable[[E], bool],
    ):
        async with self._subscription_lock:
            super().register(func, event_type, *conditions)

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
                    self._post_subscriptions.setdefault(event_type, []).append(
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
                self._post_subscriptions.setdefault(event_type, []).append(
                    PostCallbackRegistry(
                        func=func, event_type=event_type, conditions=conditions
                    )
                )
                return func

            return conditions_decorator
        else:
            raise ValueError(f"Invalid subscription strategy: {strategy}")

    async def emit(self, event: E):  # pyright: ignore[reportIncompatibleMethodOverride] (async version)
        valid, event_type = self._emit_check(event)
        if not valid:
            return
        async_moduvent_logger.debug(f"Emitting {event}")
        if event_type in self._subscriptions:
            logger.debug(f"Processing {event_type.__qualname__} subscriptions...")
            callbacks = self._subscriptions[event_type]
            async_moduvent_logger.debug(
                f"Processing {event_type.__qualname__} ({len(callbacks)} callbacks)"
            )
            for callback in callbacks:
                logger.debug(f"Adding {callback} to callqueue...")
                await self._append_to_callqueue(
                    self.processing_class(
                        func=callback.func,
                        event=event,
                        conditions=callback.conditions,
                    )
                )

        await self._process_callqueue()


class AsyncEventAwareBase(Generic[E], metaclass=EventMeta):
    """The base class that utilize the metaclass."""

    event_manager: AsyncEventManager
    _subscriptions: Dict[Type[E], List[PostCallbackRegistry]] = {}

    def __init__(self, event_manager=None):
        if event_manager:
            self.event_manager: AsyncEventManager = event_manager

    @classmethod
    @abstractmethod
    async def create(cls, event_manager):
        instance = cls(event_manager)
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
