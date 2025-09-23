from asyncio import Lock, Queue
from typing import Callable, Dict, List, Type

from .common import (BaseCallback, Event, FunctionTypes, check_function_type,
                     logger)

logger.add(enqueue=True)


class AsyncCallback(BaseCallback):
    async def call(self):
        if self.func_type in [
            FunctionTypes.BOUND_METHOD,
            FunctionTypes.FUNCTION,
            FunctionTypes.STATICMETHOD,
        ]:
            await self.func(self.event)
        else:
            logger.exception(f"Unknown function type for {self.func.__qualname__}")

    def copy(self):
        # shallow copy
        return AsyncCallback(func=self.func, event=self.event)

    def __eq__(self, value):
        if isinstance(value, AsyncCallback):
            return self.func == value.func and self.event == value.event
        return super().__eq__(value)


# We say that a subscription is the information that a method wants to be called back
# and a registration is the process of adding a method to the list of callbacks for a particular event.
class AsyncEventManager:
    def __init__(self):
        self._subscriptions: Dict[Type[Event], List[AsyncCallback]] = {}
        self._callqueue: Queue[AsyncCallback] = Queue()
        self._subscription_lock = Lock()
        self._callqueue_lock = Lock()

    def _verbose_callqueue(self):
        logger.debug(f"Callqueue ({len(self._callqueue)}):")
        for callback in self._callqueue:
            logger.debug(f"{callback}")

    async def _process_callqueue(self):
        logger.debug("Processing callqueue...")
        async with self._callqueue_lock:
            while self._callqueue:
                callback = await self._callqueue.get()
                logger.debug(f"Calling {callback}")
                try:
                    await callback.call()
                except Exception as e:
                    logger.exception(f"Error while processing callback: {e}")
                    continue
        logger.debug("End processing callqueue.")

    async def _register_callback(self, callback: AsyncCallback):
        async with self._subscription_lock:
            self._subscriptions.setdefault(callback.event, []).append(callback)

    async def register(self, func: Callable[[Event], None], event_type: Type[Event]):
        callback = AsyncCallback(func=func, event=event_type)
        await self._register_callback(callback)
        logger.debug(f"Registered {callback}")

    def subscribe(self, *event_types: Type[Event]):
        """This is used as a decorator to register a simple function."""

        async def decorator(func: Callable[[Event], None]):
            for event_type in event_types:
                await self.register(func=func, event_type=event_type)
            return func

        return decorator

    async def remove_callback(
        self, func: Callable[[Event], None], event_type: Type[Event]
    ):
        """Remove a callback from the list of subscriptions."""
        if event_type not in self._subscriptions:
            return
        async with self._subscription_lock:
            for callback in self._subscriptions.get(event_type, []):
                if callback.func == func:
                    self._subscriptions[event_type].remove(callback)
                    logger.debug(f"Removed {callback} ({event_type})")

    async def remove_function(self, func: Callable[[Event], None]):
        """Remove all callbacks for a function."""
        async with self._subscription_lock:
            for callbacks in self._subscriptions.values():
                for callback in callbacks:
                    if callback == func:
                        callbacks.remove(callback)
        logger.debug(f"Removed all callbacks for {func}")

    async def clear_event_type(self, event_type: Type[Event]):
        async with self._subscription_lock:
            if event_type in self._subscriptions:
                del self._subscriptions[event_type]
                logger.debug(f"Cleared all subscriptions for {event_type}")

    async def emit(self, event: Event):
        event_type = type(event)
        logger.debug(f"Emitting {event}")

        if event_type in self._subscriptions:
            callbacks = self._subscriptions[event_type]
            logger.debug(
                f"Processing {event_type.__qualname__} ({len(callbacks)} callbacks)"
            )
            for callback in callbacks:
                callback_copy = callback.copy()
                callback_copy.event = event
                await self._callqueue.put(callback_copy)

            self._verbose_callqueue()
            await self._process_callqueue()


class AsyncEventMeta(type):
    """Define a new class with events info gathered after class creation."""

    def __new__(cls, name, bases, attrs):
        new_class = super().__new__(cls, name, bases, attrs)

        _subscriptions: Dict[Type[Event], List[AsyncCallback]] = {}
        for attr_name, attr_value in attrs.items():
            # find all subscriptions of methods
            if hasattr(attr_value, "_subscriptions"):
                for event_type in attr_value._subscriptions:
                    _subscriptions.setdefault(event_type, []).append(attr_value)

        new_class._subscriptions = _subscriptions
        return new_class


class AsyncEventAwareBase(metaclass=AsyncEventMeta):
    """The base class that utilize the metaclass."""

    async def __init__(self, event_manager):
        self.event_manager: AsyncEventManager = event_manager
        # trigger registrations
        await self._register()

    async def _register(self):
        logger.debug(f"Registering callbacks of {self}...")
        for event_type, funcs in self._subscriptions.items():
            for func in funcs:
                func_type = check_function_type(func)
                callback = AsyncCallback(
                    func=getattr(self, func.__name__), event=event_type
                )
                logger.debug(f"Registered {func.__qualname__} ({func_type})")
                await self.event_manager._register_callback(callback)
