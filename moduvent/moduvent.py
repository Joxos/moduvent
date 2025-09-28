from collections import deque
from threading import RLock
from typing import Callable, Deque, Dict, List, Type

from loguru import logger

from .common import (
    BaseCallbackProcessing,
    BaseCallbackRegistry,
    BaseEventManager,
    EventMeta,
)
from .events import Event

moduvent_logger = logger.bind(source="moduvent_sync")


class CallbackRegistry(BaseCallbackRegistry):
    def __eq__(self, value):
        if isinstance(value, CallbackRegistry):
            return self._compare_attributes(value)
        return super().__eq__(value)


class CallbackProcessing(BaseCallbackProcessing, CallbackRegistry):
    def call(self):
        if super().call():
            try:
                self.func(self.event)
            except Exception as e:
                moduvent_logger.exception(f"Error while processing callback: {e}")


# We say that a subscription is the information that a method wants to be called back
# and a registration is the process of adding a method to the list of callbacks for a particular event.
class EventManager(BaseEventManager):
    def __init__(self):
        self._subscriptions: Dict[Type[Event], List[CallbackRegistry]] = {}
        self._callqueue: Deque[CallbackRegistry] = deque()
        self._subscription_lock = RLock()
        self._callqueue_lock = RLock()

        self.registry_class = CallbackRegistry
        self.processing_class = CallbackProcessing

    def _set_subscriptions(
        self, subscriptions: Dict[Type[Event], List[CallbackRegistry]]
    ):
        with self._subscription_lock:
            return super()._set_subscriptions(subscriptions)

    def _append_to_callqueue(self, callback):
        with self._callqueue_lock:
            super()._append_to_callqueue(callback)

    def _get_callqueue_length(self):
        return len(self._callqueue)

    def _process_callqueue(self):
        moduvent_logger.debug("Processing callqueue...")
        with self._callqueue_lock:
            while self._callqueue:
                callback = self._callqueue.popleft()
                moduvent_logger.debug(f"Calling {callback}")
                try:
                    callback.call()
                except Exception as e:
                    moduvent_logger.exception(f"Error while processing callback: {e}")
                    continue
        moduvent_logger.debug("End processing callqueue.")

    def register(
        self,
        func: Callable[[Event], None],
        event_type: Type[Event],
        *conditions: list[Callable[[Event], bool]],
    ):
        with self._subscription_lock:
            super().register(func=func, event_type=event_type, conditions=conditions)

    def subscribe(self, *args, **kwargs):
        """subscribe dispatcher decorator.
        The first argument must be an event type.
        If the second argument is a function, then functions after that will be registered as conditions.
        If the second argument is another event, then events after that will be registered as multi-callbacks.
        If arguments after the second argument is not same, then it will raise a ValueError.
        """
        strategy = self._get_subscription_strategy(*args, **kwargs)
        if strategy == self.SUBSCRIPTION_STRATEGY.EVENTS:

            def decorator(func: Callable[[Event], None]):
                for event_type in args:
                    self.register(func=func, event_type=event_type)
                return func

            return decorator
        elif strategy == self.SUBSCRIPTION_STRATEGY.CONDITIONS:
            event_type = args[0]
            conditions = args[1:]

            def decorator(func: Callable[[Event], None]):
                self.register(func=func, event_type=event_type, conditions=conditions)
                return func

            return decorator
        else:
            raise ValueError(f"Invalid subscription strategy {strategy}")


class EventAwareBase(metaclass=EventMeta):
    """The base class that utilize the metaclass."""

    def __init__(self, event_manager):
        self.event_manager: EventManager = event_manager
        # trigger registrations
        self._register()

    def _register(self):
        moduvent_logger.debug(f"Registering callbacks of {self}...")
        for event_type, funcs in self._subscriptions.items():
            for func in funcs:
                callback = CallbackRegistry(
                    func=getattr(self, func.__name__), event=event_type
                )
                self.event_manager.register(callback)
