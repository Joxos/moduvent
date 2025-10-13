from collections import defaultdict
from types import new_class
from typing import Any, Type, TypeVar
from uuid import uuid4 as uuid


class MutedContext:
    """A context manager to temporarily mute events"""

    def __init__(self, event: Type["Event"]) -> None:
        self.event = event

    def __enter__(self) -> None:
        self.event.enabled = False

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.event.enabled = True


class Event:
    """Base event class"""

    enabled: bool = True

    @classmethod
    def muted(cls) -> MutedContext:
        """Return a context manager to temporarily mute the event"""
        return MutedContext(cls)

    def __str__(self) -> str:
        # get all attributes without the ones starting with __
        attrs = [f"{k}={v}" for k, v in self.__dict__.items() if not k.startswith("__")]
        return f"{type(self).__qualname__}({', '.join(attrs)})"


E = TypeVar("E", bound=Event)


class EventFactory(dict[str, Type[E]]):
    """A factory to create new event classes inheriting from given base class but with customized name."""

    base_class: Type[E]

    @classmethod
    def create(cls, base_class: Type[E] = Event) -> "EventFactory":
        if not issubclass(base_class, Event):
            raise TypeError("base_class must be a subclass of Event")
        instance = cls()
        instance.base_class = base_class
        return instance

    def new(self, name: str = "") -> Type[E]:
        if not name:
            name = f"{self.base_class.__name__}_{str(uuid())}"
        if name not in self:
            self[name] = new_class(name, (self.base_class,))

        return self[name]


class Signal(Event):
    """Signal is an event with only a sender"""

    def __init__(self, sender: Any = None):
        self.sender = sender

    def __str__(self):
        return f"Signal({self.__class__.__name__}, sender={self.sender})"


SignalFactory = EventFactory.create(Signal)


class DataEvent(Signal):
    """An event with data and a sender"""

    def __init__(self, data, sender: object = None):
        self.data = data
        self.sender = sender


DataEventFactory = EventFactory.create(DataEvent)


class EventMeta(type):
    """Define a new class with events info gathered after class creation."""

    def __new__(cls, name, bases, attrs):
        new_class = super().__new__(cls, name, bases, attrs)

        _subscriptions = defaultdict(list)
        for attr_name, attr_value in attrs.items():
            # find all subscriptions of methods
            if hasattr(attr_value, "_subscriptions"):
                for event_type in attr_value._subscriptions:
                    _subscriptions[event_type].extend(
                        attr_value._subscriptions[event_type]
                    )

        new_class._subscriptions = _subscriptions  # pyright: ignore[reportAttributeAccessIssue] (surpress because it's metaclass)
        return new_class
