from moduvent import (
    Signal,
    emit,
    event_manager,
    register,
    signal,
    subscribe,
    DataEvent,
    data_event,
)
from utils import CaptureOutput
from loguru import logger
import sys



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
            print(f"Got a signal sent by {signal.sender!r}")

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
            "Got a signal sent by <Processor a>",
            "Processing.",
        ]

        # test_subscribing_to_specific_senders
        # moduvent does not encorage you to subscribe to specific senders.
        # This is because complex conditions are hard to represent, error-prone and will slow down the system.
        def b_subscriber(signal: Signal):
            print("Caught signal from processor_b.")

        processor_b = Processor("b")
        # function register accept zero or multiple conditions after the two common subscription arguments.
        register(b_subscriber, ready, lambda s: s.sender is processor_b)
        processor_a.go()
        assert output.getlines() == [
            "Got a signal sent by <Processor a>",
            "Processing.",
        ]
        processor_b.go()
        assert output.getlines() == [
            "Got a signal sent by <Processor b>",
            "Caught signal from processor_b.",
            "Processing.",
        ]

def test_sending_and_receiving_data_through_signals():
    with CaptureOutput() as output:
        # In blinker, data is sent nonstandardly through a accompanied dict, which is not recommended by moduvent.
        # You should always define your own class for data, which is more flexible and can be checked by the IDE.
        # Even though, moduvent still provides a data_event function for convenience, which you can pass any data as an argument.
        send_data_event = data_event("send-data")
        receive_data_event = data_event("receive-data")

        # In blinker, signals are connected through @send_data.connect
        # In moduvent, you should use @subscribe(send_data_event) instead.
        # This is more flexible when you need to subscribe to multiple signals.
        @subscribe(send_data_event)
        def receive_data(event: DataEvent):
            print(f"Caught signal from None, data {event.data}")
            emit(receive_data_event("received!", receive_data))

        # blinker returns the result directly from an event.
        # However, an event may provoke a chain of events to achieve a complex functionality in moduvent.
        # So, moduvent does not return the result directly when emitting an event.
        # Instead, a callback may be used to capture the specific result you need.
        @subscribe(receive_data_event)
        def capture_result(event: DataEvent):
            print(f"Caught signal from receive_data, data {event.data}")
            assert event.sender is receive_data
            assert event.data == "received!"

        emit(send_data_event({"abc": 123}))
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
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")
    test_decoupling_with_named_signals()
    test_subscribing_to_signals()
    test_sending_and_receiving_data_through_signals()
