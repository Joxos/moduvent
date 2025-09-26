import types
from uuid import uuid4 as uuid


class MutedContext:
    """A context manager to temporarily mute events"""

    def __init__(self, event: "Event"):
        self.event = event

    def __enter__(self):
        self.event.enabled = False

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.event.enabled = True


class Event:
    """Base event class"""

    enabled: bool = True

    @classmethod
    def muted(self):
        """Return a context manager to temporarily mute the event"""
        return MutedContext(self)

    def __str__(self):
        # get all attributes without the ones starting with __
        attrs = [f"{k}={v}" for k, v in self.__dict__.items() if not k.startswith("__")]
        return f"{type(self).__qualname__}({', '.join(attrs)})"


class EventFactory[T](dict[str, T]):
    """A factory to create new event classes inheriting from given base class but with customized name."""

    base_class: type[Event] = Event

    @classmethod
    def create(cls, base_class: type[Event]) -> "EventFactory[T]":
        instance = cls[T]()
        instance.base_class = base_class
        return instance

    def new(self, name: str = None):
        if not name:
            name = f"{self.base_class.__name__}_{str(uuid())}"
        if name not in self:
            self[name] = types.new_class(name, (self.base_class,), {})

        return self[name]


class Signal(Event):
    """Signal is an event with only a sender"""

    def __init__(self, sender: object = None):
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
