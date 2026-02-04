"""
Integration tests comparing moduvent features to Blinker library patterns.

This module documents how moduvent handles patterns that are common in Blinker,
while providing moduvent's own idiomatic solutions. These tests serve as both
documentation and verification that moduvent can handle Blinker-like use cases.

Tests cover:
- Named signals (Blinker: signal by name, moduvent: signal() factory)
- Subscribing to signals (Blinker: @signal.connect, moduvent: @subscribe)
- Emitting signals (Blinker: signal.send(), moduvent: emit())
- Subscribing to specific senders (moduvent: conditions)
- Data events (Blinker: signal with data dict, moduvent: DataEvent)
- Muting signals (both support)
- Anonymous signals (class attributes)
- Async receivers (Blinker: @signal.connect, moduvent: @asubscribe + initialize)
- Receiver call order (both maintain registration order)
"""

import pytest

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


# =============================================================================
# Named Signal Tests
# =============================================================================


class TestNamedSignals:
    """Tests for named signal creation and identity.

    Blinker uses string names to identify signals, where the same name
    always returns the same signal object (identity comparison with 'is').

    Moduvent's signal() factory provides similar functionality while
    supporting customization through Event class inheritance.
    """

    def test_decoupling_with_named_signals(self):
        """Named signals should return the same class for the same name.

        Blinker pattern:
            from blinker import signal
            ready = signal('ready')
            ready is signal('ready')  # True

        Moduvent pattern:
            from moduvent import signal
            initialized = signal("initialized")
            initialized is signal("initialized")  # True
        """
        initialized = signal("initialized")
        assert initialized is signal("initialized")

    def test_different_names_different_signals(self):
        """Different names should produce different signal classes."""
        signal_a = signal("signal_a")
        signal_b = signal("signal_b")
        assert signal_a is not signal_b

    def test_named_signal_is_event_subclass(self):
        """Named signals should be Event subclasses."""
        my_signal = signal("my_signal")
        assert issubclass(my_signal, Signal)


# =============================================================================
# Signal Subscription Tests
# =============================================================================


class TestSignalSubscription:
    """Tests for subscribing to signals.

    Blinker uses @signal.connect decorator.
    Moduvent uses @subscribe(signal) decorator or register() function.
    """

    def test_subscribing_to_signals(self, capsys):
        """Subscribe to a signal and receive events.

        Blinker pattern:
            @ready.connect
            def subscriber(sender):
                print(f"Got signal from {sender}")

        Moduvent pattern:
            @subscribe(ready)
            def subscriber(signal):
                print(f"Got signal from {signal.sender}")
        """

        def subscriber(signal: Signal):
            print(f"Got a signal sent by {signal.sender!r}")

        ready = signal("ready_test")
        register(subscriber, ready)
        assert event_manager._subscriptions[ready] == [subscriber]

        # Clean up
        event_manager.unsubscribe(subscriber, ready)

    def test_subscribe_decorator_pattern(self, capsys):
        """Use @subscribe decorator for cleaner syntax."""
        notification = signal("notification_test")

        @subscribe(notification)
        def handler(event: Signal):
            print(f"Notification from {event.sender}")

        emit(notification("test_source"))
        captured = capsys.readouterr()
        assert "Notification from test_source" in captured.out

        # Clean up
        event_manager.unsubscribe(handler, notification)


# =============================================================================
# Signal Emission Tests
# =============================================================================


class TestSignalEmission:
    """Tests for emitting signals.

    Blinker uses signal.send(sender).
    Moduvent uses emit(signal_class(sender)).
    """

    def test_emitting_signals(self, capsys):
        """Emit signals and verify handler invocation.

        Blinker pattern:
            ready.send(self)

        Moduvent pattern:
            emit(ready(self))
        """
        ready = signal("emit_test_ready")
        complete = signal("emit_test_complete")

        def subscriber(signal: Signal):
            print(f"Got a signal sent by {signal.sender!r}")

        register(subscriber, ready)

        class Processor:
            def __init__(self, name):
                self.name = name

            def go(self):
                emit(ready(self))
                print("Processing.")
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

        # Clean up
        event_manager.unsubscribe(subscriber, ready)


# =============================================================================
# Conditional Subscription Tests
# =============================================================================


class TestConditionalSubscription:
    """Tests for subscribing with conditions (sender filtering).

    Blinker uses @signal.connect_via(sender) decorator.
    Moduvent uses condition functions passed to register().

    Note: Moduvent discourages sender-specific subscriptions as they
    can be error-prone with complex conditions. Instead, handlers should
    check conditions internally when needed.
    """

    def test_subscribing_to_specific_senders(self, capsys):
        """Filter events by sender using conditions.

        Blinker pattern:
            @ready.connect_via(processor_b)
            def b_subscriber(sender):
                print("Caught from processor_b")

        Moduvent pattern:
            register(b_subscriber, ready, lambda s: s.sender is processor_b)
        """
        ready = signal("sender_filter_ready")

        def subscriber(signal: Signal):
            print(f"Got a signal sent by {signal.sender!r}")

        class Processor:
            def __init__(self, name):
                self.name = name

            def go(self):
                emit(ready(self))
                print("Processing.")

            def __repr__(self):
                return f"<Processor {self.name}>"

        register(subscriber, ready)

        processor_a = Processor("a")
        processor_b = Processor("b")

        # Subscribe specifically to processor_b
        def b_subscriber(signal: Signal):
            print("Caught signal from processor_b.")

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

        # Clean up
        event_manager.unsubscribe(subscriber, ready)
        event_manager.unsubscribe(b_subscriber, ready)


# =============================================================================
# DataEvent Tests
# =============================================================================


class TestDataEvents:
    """Tests for sending data with events.

    Blinker sends data through keyword arguments.
    Moduvent uses DataEvent class with explicit data attribute.

    Moduvent encourages defining custom Event classes for structured data,
    but provides DataEvent for simple cases.
    """

    def test_sending_and_receiving_data_through_signals(self, capsys):
        """Send and receive data through events.

        Blinker pattern:
            send_data.send(sender, data={'key': 'value'})

        Moduvent pattern:
            emit(send_data_event({'key': 'value'}))
        """
        send_data_event = data_event("data_send_test")
        receive_data_event = data_event("data_receive_test")

        @subscribe(send_data_event)
        def receive_data(event: DataEvent):
            print(f"Caught signal from None, data {event.data}")
            emit(receive_data_event("received!", receive_data))

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

        # Clean up
        event_manager.unsubscribe(receive_data, send_data_event)
        event_manager.unsubscribe(capture_result, receive_data_event)


# =============================================================================
# Signal Muting Tests
# =============================================================================


class TestSignalMuting:
    """Tests for temporarily muting signals.

    Both Blinker and moduvent support context managers for muting.
    """

    def test_muting_signals(self, capsys):
        """Muted signals should not trigger handlers.

        Blinker pattern:
            with sig.muted():
                sig.send(sender)  # Handlers not called

        Moduvent pattern:
            with sig.muted():
                emit(sig("muted"))  # Handlers not called
        """
        sig = signal("mute_test_signal")

        @subscribe(sig)
        def receive_data(event: Signal):
            print(f"Caught signal from {event.sender!r}")

        with sig.muted():
            emit(sig("muted"))

        emit(sig("not muted"))
        captured = capsys.readouterr()
        assert captured.out == "Caught signal from 'not muted'\n"

        # Clean up
        event_manager.unsubscribe(receive_data, sig)


# =============================================================================
# Anonymous Signal Tests
# =============================================================================


class TestAnonymousSignals:
    """Tests for anonymous signals (class attributes).

    Both Blinker and moduvent support signals as class attributes
    without explicit names.
    """

    def test_anonymous_signals(self, capsys):
        """Signals can be used as class attributes without names.

        Blinker pattern:
            class AltProcessor:
                on_ready = signal()
                on_complete = signal()

        Moduvent pattern:
            class AltProcessor:
                on_ready = signal()
                on_complete = signal()
        """

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

        # Clean up
        event_manager.unsubscribe(completed, apc.on_complete)

    def test_signal_with_arbitrary_sender(self, capsys):
        """Signals can have any object as sender.

        Blinker pattern:
            @connect_via(3)
            def roll_dice(sender):
                ...

        Moduvent pattern:
            emit(dice_roll(3))  # Sender can be any value
        """
        dice_roll = signal("dice_roll_test")

        @subscribe(dice_roll)
        def roll_dice(event: Signal):
            print(f"Observed dice roll {event.sender}")

        emit(dice_roll(3))
        captured = capsys.readouterr()
        assert captured.out == "Observed dice roll 3\n"

        # Clean up
        event_manager.unsubscribe(roll_dice, dice_roll)


# =============================================================================
# Async Receiver Tests
# =============================================================================


class TestAsyncReceivers:
    """Tests for async event handlers.

    Blinker supports async receivers with @signal.connect.
    Moduvent requires explicit @asubscribe and initialize() for async.
    """

    @pytest.mark.asyncio
    async def test_async_receivers(self, capsys):
        """Async handlers should work with async emit.

        Blinker pattern:
            @signal.connect
            async def receiver(sender):
                ...
            await signal.send_async(sender)

        Moduvent pattern:
            @asubscribe(sig)
            async def receiver(event):
                ...
            await initialize()
            await aemit(sig("sender"))
        """
        sig = signal()

        @asubscribe(sig)
        async def receiver(event: Signal):
            print(f"Caught signal from {event.sender!r}")

        await initialize()
        await aemit(sig("async"))
        captured = capsys.readouterr()
        assert captured.out == "Caught signal from 'async'\n"


# =============================================================================
# Handler Order Tests
# =============================================================================


class TestHandlerOrder:
    """Tests for handler invocation order.

    Both Blinker and moduvent maintain registration order by default.
    """

    def test_call_receivers_in_order_of_registration(self, capsys):
        """Handlers should be called in registration order.

        Both Blinker and moduvent call handlers in the order
        they were registered.
        """
        sig = signal("order_test")

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

        # Clean up
        event_manager.unsubscribe(receiver1, sig)
        event_manager.unsubscribe(receiver2, sig)


# =============================================================================
# Design Philosophy Notes
# =============================================================================


class TestDesignPhilosophy:
    """Documentation tests explaining moduvent's design choices vs Blinker.

    These tests document why moduvent makes certain design decisions
    differently from Blinker.
    """

    def test_optimizing_signal_sending(self):
        """Document approach to checking if signals have receivers.

        Blinker provides signal.receivers property to check if anyone
        is listening before sending, for optimization.

        Moduvent philosophy: Developers should know their event flow.
        If you need to check receivers, you can inspect:
        - event_manager._subscriptions
        - signal in event_manager._subscriptions

        This is considered a code smell in moduvent as it indicates
        unclear event architecture.
        """
        # This is intentionally a documentation-only test
        my_signal = signal("optimization_test")

        # You CAN check if there are subscribers:
        has_subscribers = (
            my_signal in event_manager._subscriptions
            and len(event_manager._subscriptions[my_signal]) > 0
        )

        assert not has_subscribers  # No subscribers registered

    def test_documenting_signals(self):
        """Document approach to signal documentation.

        Blinker uses signal.doc attribute.

        Moduvent encourages using Event class docstrings and type hints
        for documentation, which provides better IDE support.
        """
        from moduvent import Event

        class UserCreatedEvent(Event):
            """Emitted when a new user is created in the system.

            Attributes:
                user_id: The ID of the newly created user.
                username: The username of the new user.
            """

            def __init__(self, user_id: int, username: str):
                self.user_id = user_id
                self.username = username

        # The docstring is accessible and provides better documentation
        # than Blinker's signal.doc approach
        assert "Emitted when a new user" in UserCreatedEvent.__doc__
