from moduvent import (
    Signal,
    emit,
    event_manager,
    register,
    signal,
    subscribe,
    EventWithData,
)
from utils import CaptureOutput


def test_decoupling_with_named_signals():
    # The blinker uses "is" to compare signals, which it claims to allow "unconnected parts of code to all use the same signal without requiring any code shareing or special imports"
    # However, this doesn't support diverse customized functions (like __str__), could cause problems of typo and cannot be checked by the IDE.
    # Moreover, a signal can only take limited information, so moduvent uses Event class instead.
    # Even though, moduvent still provides a signal function for convenience, which returns a subclass of Event and takes only a name as an argument.
    initialized = signal("initialized")
    assert initialized is signal("initialized")


def test_subscribing_to_signals():
    with CaptureOutput() as output:

        def subscriber(signal: Signal):
            print(f"Got another signal sent by {signal.sender!r}")

        ready = signal("ready")
        register(subscriber, ready)
        assert event_manager._subscriptions[ready] == [subscriber]

        # test_emitting_signals
        class Processor:
            def __init__(self, name):
                self.name = name

            def go(self):
                ready = signal("ready")
                emit(ready(self))
                print("Processing.")
                complete = signal("complete")
                emit(complete(self))

            def __repr__(self):
                return f"<Processor {self.name}>"

        processor_a = Processor("a")
        processor_a.go()
        assert output.getlines() == [
            "Got another signal sent by <Processor a>",
            "Processing.",
        ]

        # test_subscribing_to_specific_senders
        # TODO: implement event filtering


def test_sending_and_receiving_data_through_signals():
    with CaptureOutput() as output:

        @subscribe(EventWithData)
        def receive_data(event: EventWithData):
            if event.sender is None:
                print(f"Caught signal from None, data {event.data}")
                emit(EventWithData("received!", receive_data))

        @subscribe(EventWithData)
        def capture_result(event: EventWithData):
            if event.sender is receive_data:
                print(f"Caught signal from receive_data, data {event.data}")
                assert event.sender is receive_data
                assert event.data == "received!"

        emit(EventWithData({"abc": 123}))
        assert output.getlines() == [
            "Caught signal from None, data {'abc': 123}",
            "Caught signal from receive_data, data received!",
        ]


def test_muting_signals():
    # TODO: implement signal muting
    pass


def test_anonymous_signals():
    # TODO: implement anonymous signals
    pass


if __name__ == "__main__":
    test_sending_and_receiving_data_through_signals()
