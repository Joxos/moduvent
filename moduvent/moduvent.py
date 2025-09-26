from collections import deque
from threading import RLock
from typing import Callable, Deque, Dict, List, Type

from loguru import logger

from .common import BaseCallback, CommonEventManager, EventMeta
from .events import Event

moduvent_logger = logger.bind(source="moduvent_sync")


class Callback(BaseCallback):
    def call(self):
        if self._func_type_valid() and self._check_conditions():
            self.func(self.event)
        else:
            self._report_function()

    def copy(self):
        return self._shallow_copy(Callback)

    def __eq__(self, value):
        if isinstance(value, Callback):
            return self._compare_attributes(value)
        return super().__eq__(value)


# We say that a subscription is the information that a method wants to be called back
# and a registration is the process of adding a method to the list of callbacks for a particular event.
class EventManager(CommonEventManager):
    def __init__(self):
        self._subscriptions: Dict[Type[Event], List[Callback]] = {}
        self._callqueue: Deque[Callback] = deque()
        self._subscription_lock = RLock()
        self._callqueue_lock = RLock()

    def _verbose_callqueue(self):
        super()._verbose_callqueue(len(self._callqueue))

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

    def _register_callback(self, callback: Callback):
        with self._subscription_lock:
            self._subscriptions.setdefault(callback.event, []).append(callback)

    def register(
        self,
        func: Callable[[Event], None],
        event_type: Type[Event],
        *conditions: list[Callable[[Event], bool]],
    ):
        callback = Callback(func=func, event=event_type, conditions=conditions)
        self._register_callback(callback)
        moduvent_logger.debug(f"Registered {callback}")

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

    def unsubscribe(
        self, func: Callable[[Event], None] = None, event_type: Type[Event] = None
    ):
        self._check_unregister_args(func, event_type)
        with self._subscription_lock:
            self._process_unregister_logic(func, event_type)

    def emit(self, event: Event):
        event_type = type(event)
        if not event_type.enabled:
            moduvent_logger.debug(f"Skipping disabled event {event_type.__qualname__}")
            return
        moduvent_logger.debug(f"Emitting {event}")

        if event_type in self._subscriptions:
            callbacks = self._subscriptions[event_type]
            moduvent_logger.debug(
                f"Processing {event_type.__qualname__} ({len(callbacks)} callbacks)"
            )
            for callback in callbacks:
                callback_copy = callback.copy()
                if callback_copy:
                    callback_copy.event = event
                    self._callqueue.append(callback_copy)
                else:
                    # the callback is no longer valid
                    with self._subscription_lock:
                        self._subscriptions[event_type].remove(callback)
                    moduvent_logger.warning(
                        f"Invalid callback {callback} has been removed before processing event."
                    )

            self._verbose_callqueue()
            self._process_callqueue()


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
                callback = Callback(func=getattr(self, func.__name__), event=event_type)
                self.event_manager._register_callback(callback)
