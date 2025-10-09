import asyncio
import sys
import tracemalloc

import pytest
from loguru import logger

from moduvent import (
    DataEvent,
    Signal,
    aemit,
    asubscribe,
    data_event,
    emit,
    event_manager,
    initialize,
    register,
    signal,
    subscribe,
)


def test_decoupling_with_named_signals():
    # The blinker uses "is" to compare signals, which it claims to allow "unconnected parts of code to all use the same signal without requiring any code shareing or special imports"
    # However, this doesn't support diverse customized functions (like __str__), could cause problems of typo and cannot be checked by the IDE.
    # Moreover, a signal can only take limited information, so moduvent uses Event class instead.
    # Even though, moduvent still provides a signal function for convenience, which returns a subclass of Event and takes only a name as an argument.
    initialized = signal("initialized")
    assert initialized is signal("initialized")


def test_subscribing_to_signals(capsys):
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
    captured = capsys.readouterr()
    assert captured.out.split("\n")[:-1] == [
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
    captured = capsys.readouterr()
    assert captured.out.split("\n")[:-1] == [
        "Got a signal sent by <Processor a>",
        "Processing.",
    ]
    processor_b.go()
    captured = capsys.readouterr()
    assert captured.out.split("\n")[:-1] == [
        "Got a signal sent by <Processor b>",
        "Caught signal from processor_b.",
        "Processing.",
    ]


def test_sending_and_receiving_data_through_signals(capsys):
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
    captured = capsys.readouterr()
    assert captured.out.split("\n")[:-1] == [
        "Caught signal from None, data {'abc': 123}",
        "Caught signal from receive_data, data received!",
    ]


def test_muting_signals(capsys):
    sig = signal("send-data")

    @subscribe(sig)
    def receive_data(event: Signal):
        print(f"Caught signal from {event.sender!r}")

    with sig.muted():
        emit(sig("muted"))
    emit(sig("not muted"))
    captured = capsys.readouterr()
    assert captured.out == "Caught signal from 'not muted'\n"


def test_anonymous_signals(capsys):
    class AltProcessor:
        on_ready = signal()
        on_complete = signal()

        def __init__(self, name):
            self.name = name

        def go(self):
            emit(self.on_ready(self))
            print("Alternate processing.")
            emit(self.on_complete(self))

        def __repr__(self):
            return f"<AltProcessor {self.name}>"

    # test_connect_as_a_decorator
    apc = AltProcessor("c")

    @subscribe(apc.on_complete)
    def completed(event: Signal):
        print(f"AltProcessor {event.sender.name} completed!")

    apc.go()
    captured = capsys.readouterr()
    assert captured.out.split("\n")[:-1] == [
        "Alternate processing.",
        "AltProcessor c completed!",
    ]

    # The form of `connect` decorator in blinker unfortunately does not allow extra arguments and it uses `connect_via` instead.
    # Luckily, you don't need to do this in moduvent since moduvent pass an Event object to the callback, which can be customized with extra attributes.
    dice_roll = signal("dice_roll")

    @subscribe(dice_roll)
    def roll_dice(event: Signal):
        print(f"Observed dice roll {event.sender}")

    emit(dice_roll(3))
    captured = capsys.readouterr()
    assert captured.out == "Observed dice roll 3\n"


def test_optimizing_signal_sending(capsys):
    # In blinker, you can check if a signal is connected before sending it, which can improve performance.
    # However, in moduvent, it is reguarded as poor-designed that the developers don't know whether they should create a signal or not.
    # So, moduvent does not have any plan to implement specific helpers about this at least for now.
    # However, you can do this anyway by checking some_signal in event_manager._subscriptions and event_manager._subscriptions[signal("some_signal")]
    # We skip this test for now.
    ...


def test_documenting_signals():
    # TODO
    ...


@pytest.mark.asyncio
async def test_async_receivers(capsys):
    sig = signal()

    @asubscribe(sig)
    async def receiver(event: Signal):
        print(f"Caught signal from {event.sender!r}")

    # blinder does not seem to check whether a subscriber in main async loop or not.
    # In moduvent however, we require you to initialize the async event manager explicitly with initialize()
    # Note that the realization is likely to be buggy if in multi-threaded environment.
    await initialize()
    await aemit(sig("async"))
    captured = capsys.readouterr()
    assert captured.out == "Caught signal from 'async'\n"
    # blinker allows you to wrap a coroutine into a synchronous function which directly calls asyncio.run()
    # We reguard this a wierd design and skip this.


def test_call_receivers_in_order_of_registration(capsys):
    # In synchronous version of moduvent this is originally supported.
    # No need extra component.
    sig = signal()

    @subscribe(sig)
    def receiver1(event: Signal):
        print(f"Caught signal from {event.sender!r} (receiver1)")

    @subscribe(sig)
    def receiver2(event: Signal):
        print(f"Caught signal from {event.sender!r} (receiver2)")

    emit(sig("order"))
    captured = capsys.readouterr()
    assert captured.out.split("\n")[:-1] == [
        "Caught signal from 'order' (receiver1)",
        "Caught signal from 'order' (receiver2)",
    ]


async def main():
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")
    tracemalloc.start()
    await test_async_receivers()


if __name__ == "__main__":
    asyncio.run(main())
