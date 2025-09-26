class Event:
    """Base event class"""

    def __str__(self):
        # get all attributes without the ones starting with __
        attrs = [f"{k}={v}" for k, v in self.__dict__.items() if not k.startswith("__")]
        return f"{type(self).__qualname__}({', '.join(attrs)})"


class Signal(Event):
    def __init__(self, sender: object = None):
        self.sender = sender

    def __str__(self):
        return f"Signal({self.__class__.__name__})"


class SignalDict(dict[str, Event]):
    """A dict mapping names to signals."""

    def signal(self, name: str) -> Signal:
        if name not in self:
            self[name] = type(name, (Signal,), {})

        return self[name]


class EventWithData(Signal):
    def __init__(self, data, sender: object = None):
        self.data = data
        self.sender = sender
