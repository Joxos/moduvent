import asyncio
from abc import abstractmethod
from typing import Callable, Dict, List, Type

from loguru import logger

from .common import (
    BaseCallbackProcessing,
    BaseCallbackRegistry,
    BaseEventManager,
    EventMeta,
)
from .events import Event

async_moduvent_logger = logger.bind(source="moduvent_async")


class AsyncCallbackRegistry(BaseCallbackRegistry):
    def __eq__(self, value):
        if isinstance(value, AsyncCallbackRegistry):
            return self._compare_attributes(value)
        return super().__eq__(value)


class AsyncCallbackProcessing(BaseCallbackProcessing, AsyncCallbackRegistry):
    async def call(self):
        if super().call():
            await self.func.call(self.event)


# We say that a subscription is the information that a method wants to be called back
# and a registration is the process of adding a method to the list of callbacks for a particular event.
class AsyncEventManager(BaseEventManager):
    def __init__(self):
        self._subscriptions: Dict[Type[Event], List[AsyncCallbackRegistry]] = {}
        self._callqueue: asyncio.Queue[AsyncCallbackRegistry] = asyncio.Queue()
        self._subscription_lock = asyncio.Lock()
        self._callqueue_lock = asyncio.Lock()

        self.registry_class = AsyncCallbackRegistry
        self.processing_class = AsyncCallbackProcessing

    async def _set_subscriptions(
        self, subscriptions: Dict[Type[Event], List[AsyncCallbackRegistry]]
    ):
        async with self._subscription_lock:
            return super()._set_subscriptions(subscriptions)

    async def _append_to_callqueue(self, callback: AsyncCallbackRegistry):
        async with self._callqueue_lock:
            await self._callqueue.put(callback)

    async def _get_callqueue_length(self) -> int:
        return self._callqueue.qsize()

    async def _post_emit(self):
        self._verbose_callqueue()
        await self._process_callqueue()

    async def _process_callqueue(self):
        async_moduvent_logger.debug("Processing callqueue...")
        async with self._callqueue_lock:
            while self._callqueue:
                callback = await self._callqueue.get()
                async_moduvent_logger.debug(f"Calling {callback}")
                try:
                    await callback.call()
                except Exception as e:
                    async_moduvent_logger.exception(
                        f"Error while processing callback: {e}"
                    )
                    continue
        async_moduvent_logger.debug("End processing callqueue.")

    async def register(
        self,
        func: Callable[[Event], None],
        event_type: Type[Event],
        *conditions: list[Callable[[Event], bool]],
    ):
        async with self._subscription_lock:
            super().register(func=func, event_type=event_type, conditions=conditions)

    def subscribe(self, *args, **kwargs):
        strategy = self._get_subscription_strategy(*args, **kwargs)
        if strategy == self.SUBSCRIPTION_STRATEGY.EVENTS:

            async def decorator(func: Callable[[Event], None]):
                async with asyncio.TaskGroup() as tg:
                    for event_type in args:
                        tg.create_task(self.register(func=func, event_type=event_type))
                return func

            return decorator
        elif strategy == self.SUBSCRIPTION_STRATEGY.CONDITIONS:
            event_type = args[0]
            conditions = args[1:]

            async def decorator(func: Callable[[Event], None]):
                await self.register(
                    func=func, event_type=event_type, conditions=conditions
                )
                return func

            return decorator
        else:
            raise ValueError(f"Invalid subscription strategy: {strategy}")

    async def unsubscribe(
        self, func: Callable[[Event], None] = None, event_type: Type[Event] = None
    ):
        super().unsubscribe(func=func, event_type=event_type)

    async def emit(self, event: Event):
        super().emit(event)


class AsyncEventAwareBase(metaclass=EventMeta):
    """The base class that utilize the metaclass."""

    def __init__(self, event_manager):
        self.event_manager: AsyncEventManager = event_manager

    @classmethod
    @abstractmethod
    async def create(cls, event_manager):
        instance = cls(event_manager)
        await instance._register()
        return instance

    async def _register(self):
        async_moduvent_logger.debug(f"Registering callbacks of {self}...")
        for event_type, funcs in self._subscriptions.items():
            for func in funcs:
                callback = AsyncCallbackRegistry(
                    func=getattr(self, func.__name__), event=event_type
                )
                await self.event_manager.register(callback)
