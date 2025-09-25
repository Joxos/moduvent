from io import StringIO

from moduvent import (
    Event,
    clear_event_type,
    emit,
    event_manager,
    register,
    signal,
    subscribe,
)

output = StringIO()


def convert_output():
    global output
    result = output.getvalue().split("\n")
    output.close()
    output = StringIO()
    return result[:-1]  # remove the last empty line


def test_decoupling_with_named_signals():
    # The blinker uses "is" to compare signals, which it claims to allow "unconnected parts of code to all use the same signal without requiring any code shareing or special imports"
    # However, this doesn't support diverse customized functions (like __str__), could cause problems of typo and cannot be checked by the IDE.
    # Moreover, a signal can only take limited information, so moduvent uses Event class instead.
    # Even though, moduvent still provides a signal function for convenience, which returns a subclass of Event and takes only a name as an argument.
    initialized = signal("initialized")
    assert initialized is signal("initialized")


def test_subscribing_to_signals():
    def subscriber(signal: Event):
        print(f"Got another signal sent by {signal.sender!r}")

    ready = signal("ready")
    register(subscriber, ready)
    assert event_manager._subscriptions[ready] == [subscriber]
    clear_event_type(ready)
    assert ready not in event_manager._subscriptions

    # In moduvent, you can also use a modern way to subscribe a function to a signal:
    @subscribe(ready)
    def modern_subscriber(signal: Event):
        print(f"Got another signal sent by {signal.sender!r}", file=output)

    assert event_manager._subscriptions[ready] == [modern_subscriber]

    # test_emitting_signals
    class Processor:
        def __init__(self, name):
            self.name = name

        def go(self):
            ready = signal("ready")
            emit(ready(self))
            print("Processing.", file=output)
            complete = signal("complete")
            emit(complete(self))

        def __repr__(self):
            return f"<Processor {self.name}>"

    processor_a = Processor("a")
    processor_a.go()
    assert convert_output() == [
        "Got another signal sent by <Processor a>",
        "Processing.",
    ]
