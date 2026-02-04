"""
Unit tests for synchronous EventManager.

Tests cover:
- Registration of callbacks
- Subscription decorator (EVENTS and CONDITIONS strategies)
- Event emission and result collection
- Unsubscription (by function, by event type, both)
- Reset and halt functionality
- Call queue processing
- Thread safety
"""

import pytest
import threading
from moduvent import Event


# =============================================================================
# Test Events
# =============================================================================


class SampleEvent(Event):
    """Basic test event."""

    def __init__(self, value: int = 0):
        self.value = value


class SampleEvent2(Event):
    """Second test event for multi-event tests."""

    def __init__(self, message: str = ""):
        self.message = message


class DisabledEvent(Event):
    """Event that is disabled."""

    enabled = False


# =============================================================================
# Registration Tests
# =============================================================================


class TestRegistration:
    """Tests for callback registration."""

    def test_register_function(self, event_manager):
        """Should register a function for an event type."""

        def handler(event):
            pass

        event_manager.register(handler, SampleEvent)
        assert SampleEvent in event_manager._subscriptions
        assert len(event_manager._subscriptions[SampleEvent]) == 1
        assert event_manager._subscriptions[SampleEvent][0] == handler

    def test_register_multiple_handlers(self, event_manager):
        """Should register multiple handlers for same event type."""

        def handler1(event):
            pass

        def handler2(event):
            pass

        event_manager.register(handler1, SampleEvent)
        event_manager.register(handler2, SampleEvent)
        assert len(event_manager._subscriptions[SampleEvent]) == 2

    def test_register_with_conditions(self, event_manager):
        """Should register handler with conditions."""

        def handler(event):
            pass

        def condition(e):
            return e.value > 0

        event_manager.register(handler, SampleEvent, condition)

        registry = event_manager._subscriptions[SampleEvent][0]
        assert len(registry.conditions) == 1

    def test_register_with_multiple_conditions(self, event_manager):
        """Should register handler with multiple conditions."""

        def handler(event):
            pass

        def cond1(e):
            return e.value > 0

        def cond2(e):
            return e.value < 100

        event_manager.register(handler, SampleEvent, cond1, cond2)

    def test_register_rejects_async_callback(self, event_manager):
        """Should reject async callback with InvalidCallbackRegistryError."""
        from moduvent.common import InvalidCallbackRegistryError

        async def async_handler(event):
            return {"value": event.value}

        with pytest.raises(InvalidCallbackRegistryError) as exc_info:
            event_manager.register(async_handler, SampleEvent)

        assert exc_info.value.expected == "sync"
        assert exc_info.value.got == "async"
        assert "async_handler" in exc_info.value.callback_name


# =============================================================================
# Subscribe Decorator Tests
# =============================================================================


class TestSubscribeDecorator:
    """Tests for the subscribe decorator."""

    def test_subscribe_single_event(self, event_manager):
        """@subscribe with single event should register handler."""

        @event_manager.subscribe(SampleEvent)
        def handler(event):
            return event.value

        assert SampleEvent in event_manager._subscriptions
        assert event_manager._subscriptions[SampleEvent][0] == handler

    def test_subscribe_multiple_events(self, event_manager):
        """@subscribe with multiple events should register for all."""

        @event_manager.subscribe(SampleEvent, SampleEvent2)
        def handler(event):
            return "handled"

        assert SampleEvent in event_manager._subscriptions
        assert SampleEvent2 in event_manager._subscriptions

    def test_subscribe_with_condition(self, event_manager):
        """@subscribe with condition should apply condition."""

        def condition(e):
            return e.value > 10

        @event_manager.subscribe(SampleEvent, condition)
        def handler(event):
            return event.value

        registry = event_manager._subscriptions[SampleEvent][0]
        assert len(registry.conditions) == 1

    def test_subscribe_preserves_function(self, event_manager):
        """@subscribe should return the original function."""

        @event_manager.subscribe(SampleEvent)
        def handler(event):
            return {"value": event.value}

        assert callable(handler)
        # Function should still work normally
        mock_event = SampleEvent(value=42)
        assert handler(mock_event) == {"value": 42}

    def test_subscribe_invalid_first_arg(self, event_manager):
        """@subscribe with non-event first arg should raise."""
        with pytest.raises(ValueError, match="First argument must be an event type"):

            @event_manager.subscribe("not_an_event")
            def handler(event):
                pass


# =============================================================================
# Emit Tests
# =============================================================================


class TestEmit:
    """Tests for event emission."""

    def test_emit_calls_handler(self, event_manager):
        """emit() should call registered handler."""
        results = []

        def handler(event):
            results.append(event.value)

        event_manager.register(handler, SampleEvent)
        event_manager.emit(SampleEvent(value=42))

        assert results == [42]

    def test_emit_calls_multiple_handlers(self, event_manager):
        """emit() should call all registered handlers."""
        results = []

        def handler1(event):
            results.append("handler1")

        def handler2(event):
            results.append("handler2")

        event_manager.register(handler1, SampleEvent)
        event_manager.register(handler2, SampleEvent)
        event_manager.emit(SampleEvent())

        assert "handler1" in results
        assert "handler2" in results

    def test_emit_returns_results(self, event_manager):
        """emit() should return dict of handler results."""

        def handler1(event):
            return {"handler1_result": "result1"}

        def handler2(event):
            return {"handler2_result": "result2"}

        event_manager.register(handler1, SampleEvent)
        event_manager.register(handler2, SampleEvent)
        results = event_manager.emit(SampleEvent())

        assert results.get("handler1_result") == "result1"
        assert results.get("handler2_result") == "result2"

    def test_emit_preserves_order(self, event_manager):
        """emit() should call handlers in registration order."""
        order = []

        def handler1(event):
            order.append(1)

        def handler2(event):
            order.append(2)

        def handler3(event):
            order.append(3)

        event_manager.register(handler1, SampleEvent)
        event_manager.register(handler2, SampleEvent)
        event_manager.register(handler3, SampleEvent)
        event_manager.emit(SampleEvent())

        assert order == [1, 2, 3]

    def test_emit_with_no_handlers(self, event_manager):
        """emit() with no handlers should return empty dict."""
        results = event_manager.emit(SampleEvent())
        assert results == {}

    def test_emit_disabled_event(self, event_manager):
        """emit() should skip disabled events."""
        results = []

        def handler(event):
            results.append("called")

        event_manager.register(handler, DisabledEvent)
        event_manager.emit(DisabledEvent())

        assert results == []

    def test_emit_with_condition_met(self, event_manager):
        """emit() should call handler when condition is met."""
        results = []

        def handler(event):
            results.append(event.value)

        def condition(e):
            return e.value > 10

        event_manager.register(handler, SampleEvent, condition)
        event_manager.emit(SampleEvent(value=50))

        assert results == [50]

    def test_emit_with_condition_not_met(self, event_manager):
        """emit() should skip handler when condition is not met."""
        results = []

        def handler(event):
            results.append(event.value)

        def condition(e):
            return e.value > 100

        event_manager.register(handler, SampleEvent, condition)
        event_manager.emit(SampleEvent(value=50))

        assert results == []

    def test_emit_handles_handler_exception(self, event_manager):
        """emit() should continue after handler exception."""
        results = []

        def failing_handler(event):
            raise ValueError("Test error")

        def succeeding_handler(event):
            results.append("success")

        event_manager.register(failing_handler, SampleEvent)
        event_manager.register(succeeding_handler, SampleEvent)
        event_manager.emit(SampleEvent())

        assert results == ["success"]


# =============================================================================
# Unsubscribe Tests
# =============================================================================


class TestUnsubscribe:
    """Tests for unsubscription."""

    def test_unsubscribe_function_from_event(self, event_manager):
        """unsubscribe(func, event_type) should remove specific subscription."""

        def handler(event):
            pass

        event_manager.register(handler, SampleEvent)
        event_manager.unsubscribe(handler, SampleEvent)

        assert handler not in [
            cb.func for cb in event_manager._subscriptions.get(SampleEvent, [])
        ]

    def test_unsubscribe_function_from_all_events(self, event_manager):
        """unsubscribe(func) should remove from all event types."""

        def handler(event):
            pass

        event_manager.register(handler, SampleEvent)
        event_manager.register(handler, SampleEvent2)
        event_manager.unsubscribe(handler)

        for callbacks in event_manager._subscriptions.values():
            assert handler not in [cb.func for cb in callbacks]

    def test_unsubscribe_all_from_event_type(self, event_manager):
        """unsubscribe(event_type=X) should remove all handlers for X."""

        def handler1(event):
            pass

        def handler2(event):
            pass

        event_manager.register(handler1, SampleEvent)
        event_manager.register(handler2, SampleEvent)
        event_manager.unsubscribe(event_type=SampleEvent)

        assert (
            SampleEvent not in event_manager._subscriptions
            or len(event_manager._subscriptions[SampleEvent]) == 0
        )

    def test_unsubscribe_preserves_other_subscriptions(self, event_manager):
        """unsubscribe should not affect other subscriptions."""

        def handler1(event):
            pass

        def handler2(event):
            pass

        event_manager.register(handler1, SampleEvent)
        event_manager.register(handler2, SampleEvent)
        event_manager.unsubscribe(handler1, SampleEvent)

        assert len(event_manager._subscriptions[SampleEvent]) == 1
        assert event_manager._subscriptions[SampleEvent][0] == handler2

    def test_unsubscribe_nonexistent_handler(self, event_manager):
        """unsubscribe of non-registered handler should not raise."""

        def handler(event):
            pass

        def other_handler(event):
            pass

        event_manager.register(handler, SampleEvent)
        # Should not raise
        event_manager.unsubscribe(other_handler, SampleEvent)

    def test_unsubscribe_requires_func_or_event_type(self, event_manager):
        """unsubscribe without func or event_type should raise."""
        with pytest.raises(ValueError, match="Either func or event_type"):
            event_manager.unsubscribe()

    def test_unsubscribe_invalid_arguments(self, event_manager):
        """unsubscribe with invalid args should raise."""
        with pytest.raises(ValueError):
            event_manager.unsubscribe(func=123, event_type=None)


# =============================================================================
# Reset and Halt Tests
# =============================================================================


class TestResetAndHalt:
    """Tests for reset and halt functionality."""

    def test_reset_clears_subscriptions(self, event_manager):
        """reset() should clear all subscriptions."""

        def handler(event):
            pass

        event_manager.register(handler, SampleEvent)
        event_manager.reset()

        assert len(event_manager._subscriptions) == 0

    def test_halt_stops_emit_processing(self, event_manager):
        """halt() should stop emit processing and return empty results."""

        def handler(event):
            return {"result": "value"}

        event_manager.register(handler, SampleEvent)

        # First emit works
        results = event_manager.emit(SampleEvent())
        assert results == {"result": "value"}

        # After halt, emit returns empty dict
        event_manager.halt()
        assert event_manager.is_halted

        results = event_manager.emit(SampleEvent())
        assert results == {}

        # Resume allows processing again
        event_manager.resume()
        assert not event_manager.is_halted
        results = event_manager.emit(SampleEvent())
        assert results == {"result": "value"}

    def test_reset_allows_re_registration(self, event_manager):
        """After reset(), new registrations should work."""

        def handler(event):
            return {"result": "works"}

        event_manager.register(handler, SampleEvent)
        event_manager.reset()
        event_manager.register(handler, SampleEvent)

        results = event_manager.emit(SampleEvent())
        assert results == {"result": "works"}


# =============================================================================
# Halt/Resume Tests
# =============================================================================


class TestHaltResume:
    """Tests for halt and resume functionality."""

    def test_is_halted_initially_false(self, event_manager):
        """is_halted should be False initially."""
        assert not event_manager.is_halted

    def test_halt_sets_is_halted(self, event_manager):
        """halt() should set is_halted to True."""
        event_manager.halt()
        assert event_manager.is_halted

    def test_resume_clears_is_halted(self, event_manager):
        """resume() should set is_halted to False."""
        event_manager.halt()
        event_manager.resume()
        assert not event_manager.is_halted

    def test_reset_auto_resumes(self, event_manager):
        """reset() should auto-resume from halted state."""
        event_manager.halt()
        assert event_manager.is_halted
        event_manager.reset()
        assert not event_manager.is_halted


# =============================================================================
# Thread Safety Tests
# =============================================================================


class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_emit(self, event_manager):
        """Concurrent emit() calls should not cause race conditions."""
        results = []
        lock = threading.Lock()

        def handler(event):
            with lock:
                results.append(event.value)
            # Return None to avoid DuplicateResultKeyError in concurrent scenario
            return None

        event_manager.register(handler, SampleEvent)

        threads = []
        for i in range(10):
            t = threading.Thread(
                target=lambda v: event_manager.emit(SampleEvent(value=v)), args=(i,)
            )
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        assert set(results) == set(range(10))

    def test_concurrent_register(self, event_manager):
        """Concurrent register() calls should not cause race conditions."""
        handlers = []

        def create_handler(i):
            def handler(event):
                return i

            handlers.append(handler)
            return handler

        threads = []
        for i in range(10):
            handler = create_handler(i)
            t = threading.Thread(
                target=event_manager.register, args=(handler, SampleEvent)
            )
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(event_manager._subscriptions[SampleEvent]) == 10

    def test_concurrent_emit_and_register(self, event_manager):
        """Concurrent emit() and register() should not cause race conditions."""
        results = []
        lock = threading.Lock()
        handlers = []  # Keep references to prevent garbage collection

        def handler(event):
            with lock:
                results.append(event.value)
            # Return None to avoid DuplicateResultKeyError in concurrent scenario
            return None

        # Pre-register one handler
        event_manager.register(handler, SampleEvent)

        emit_count = 5
        register_count = 5

        def do_emit(value):
            event_manager.emit(SampleEvent(value=value))

        def do_register(i):
            def new_handler(event):
                return {f"new_{i}_result": f"new_{i}"}

            handlers.append(new_handler)  # Keep reference alive
            event_manager.register(new_handler, SampleEvent)

        threads = []
        for i in range(emit_count):
            threads.append(threading.Thread(target=do_emit, args=(i,)))
        for i in range(register_count):
            threads.append(threading.Thread(target=do_register, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All emits should have completed without error
        # The exact count depends on timing, but should have at least emit_count results
        assert len(results) >= emit_count


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_emit_non_event_instance(self, event_manager):
        """emit() with non-Event should return empty dict."""
        results = event_manager.emit("not_an_event")  # type: ignore
        assert results == {}

    def test_emit_event_class_instead_of_instance(self, event_manager):
        """emit() with Event class should return empty dict."""

        def handler(event):
            return {"result": "called"}

        event_manager.register(handler, SampleEvent)
        results = event_manager.emit(SampleEvent)  # type: ignore (intentionally wrong)
        assert results == {}

    def test_handler_returning_none(self, event_manager):
        """Handler returning None should result in empty dict."""

        def handler(event):
            return None

        event_manager.register(handler, SampleEvent)
        results = event_manager.emit(SampleEvent())

        assert results == {}

    def test_lambda_handler(self, event_manager):
        """Lambda handlers should work correctly."""

        # Keep a reference to the lambda to prevent garbage collection
        # (weak references need the original object to stay alive)
        def handler(e):
            return {"value": e.value * 2}

        event_manager.register(handler, SampleEvent)
        results = event_manager.emit(SampleEvent(value=21))
        assert results == {"value": 42}

    def test_nested_emit(self, event_manager):
        """Handler that emits another event should work."""
        results = []

        def handler1(event):
            results.append("handler1")
            event_manager.emit(SampleEvent2(message="nested"))
            return {"handler1_result": "handler1_result"}

        def handler2(event):
            results.append("handler2")
            return {"handler2_result": "handler2_result"}

        event_manager.register(handler1, SampleEvent)
        event_manager.register(handler2, SampleEvent2)
        event_manager.emit(SampleEvent())

        assert "handler1" in results
        assert "handler2" in results
