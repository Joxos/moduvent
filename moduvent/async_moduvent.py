import asyncio
from abc import abstractmethod
from typing import Callable, Dict, List, Type

from loguru import logger

from .common import BaseCallback, CommonEventManager, EventMeta
from .events import Event

async_moduvent_logger = logger.bind(source="moduvent_async")


class AsyncCallback(BaseCallback):
    async def call(self):
        if self._func_type_valid() and self._check_conditions():
            await self.func(self.event)
        else:
            self._report_function()

    def copy(self):
        return self._shallow_copy(AsyncCallback)

    def __eq__(self, value):
        if isinstance(value, AsyncCallback):
            return self._compare_attributes(value)
        return super().__eq__(value)


# We say that a subscription is the information that a method wants to be called back
# and a registration is the process of adding a method to the list of callbacks for a particular event.
class AsyncEventManager(CommonEventManager):
    def __init__(self):
        self._subscriptions: Dict[Type[Event], List[AsyncCallback]] = {}
        self._callqueue: asyncio.Queue[AsyncCallback] = asyncio.Queue()
        self._subscription_lock = asyncio.Lock()
        self._callqueue_lock = asyncio.Lock()

    def _verbose_callqueue(self):
        super()._verbose_callqueue(self._callqueue.qsize())

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

    async def _register_callback(self, callback: AsyncCallback):
        async with self._subscription_lock:
            self._subscriptions.setdefault(callback.event, []).append(callback)

    async def register(
        self,
        func: Callable[[Event], None],
        event_type: Type[Event],
        *conditions: list[Callable[[Event], bool]],
    ):
        callback = AsyncCallback(func=func, event=event_type, conditions=conditions)
        await self._register_callback(callback)
        async_moduvent_logger.debug(f"Registered {callback}")

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
        self._check_unregister_args(func, event_type)
        async with self._subscription_lock:
            self._process_unregister_logic(func, event_type)

    async def emit(self, event: Event):
        event_type = type(event)
        if not event_type.enabled:
            async_moduvent_logger.debug(
                f"Skipping disabled event {event_type.__qualname__}"
            )
            return
        async_moduvent_logger.debug(f"Emitting {event}")

        if event_type in self._subscriptions:
            callbacks = self._subscriptions[event_type]
            async_moduvent_logger.debug(
                f"Processing {event_type.__qualname__} ({len(callbacks)} callbacks)"
            )
            for callback in callbacks:
                callback_copy = callback.copy()
                if callback_copy:
                    callback_copy.event = event
                    self._callqueue.append(callback_copy)
                else:
                    # the callback is no longer valid
                    async with self._subscription_lock:
                        self._subscriptions[event_type].remove(callback)
                    async_moduvent_logger.warning(
                        f"Invalid callback {callback} has been removed before processing event."
                    )

            self._verbose_callqueue()
            await self._process_callqueue()


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
                callback = AsyncCallback(
                    func=getattr(self, func.__name__), event=event_type
                )
                await self.event_manager._register_callback(callback)
