"""
Unit tests for asynchronous AsyncEventManager.

Tests cover:
- Async registration of callbacks
- Async subscription decorator
- Async event emission
- Initialize for deferred post-subscriptions
- Async reset and halt
- Async call queue processing with TaskGroup
- Async lock behavior
"""

import pytest
import asyncio
from moduvent.async_moduvent import AsyncEventManager
from moduvent.events import Event


# =============================================================================
# Test Events
# =============================================================================


class SampleEvent(Event):
    """Basic test event for async tests."""

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
# AsyncEventManager Fixture
# =============================================================================


@pytest.fixture
def async_manager():
    """Create a fresh AsyncEventManager for each test."""
    return AsyncEventManager()


# =============================================================================
# Registration Tests
# =============================================================================


class TestAsyncRegistration:
    """Tests for async callback registration."""

    @pytest.mark.asyncio
    async def test_register_async_function(self, async_manager):
        """Should register an async function for an event type."""

        async def handler(event):
            return event.value

        await async_manager.register(handler, SampleEvent)
        assert SampleEvent in async_manager._subscriptions
        assert len(async_manager._subscriptions[SampleEvent]) == 1

    @pytest.mark.asyncio
    async def test_register_multiple_handlers(self, async_manager):
        """Should register multiple async handlers for same event type."""

        async def handler1(event):
            return 1

        async def handler2(event):
            return 2

        await async_manager.register(handler1, SampleEvent)
        await async_manager.register(handler2, SampleEvent)
        assert len(async_manager._subscriptions[SampleEvent]) == 2

    @pytest.mark.asyncio
    async def test_register_with_conditions(self, async_manager):
        """Should register async handler with conditions."""

        async def handler(event):
            return event.value

        def condition(e):
            return e.value > 0

        await async_manager.register(handler, SampleEvent, condition)

        registry = async_manager._subscriptions[SampleEvent][0]
        assert len(registry.conditions) == 1

    @pytest.mark.asyncio
    async def test_register_rejects_sync_callback(self, async_manager):
        """Should reject sync callback with InvalidCallbackRegistryError."""
        from moduvent.exceptions import InvalidCallbackRegistryError

        def sync_handler(event):
            return {"value": event.value}

        with pytest.raises(InvalidCallbackRegistryError) as exc_info:
            await async_manager.register(sync_handler, SampleEvent)

        assert exc_info.value.expected == "async"
        assert exc_info.value.got == "sync"
        assert "sync_handler" in exc_info.value.callback_name


# =============================================================================
# Subscribe Decorator Tests
# =============================================================================


class TestAsyncSubscribeDecorator:
    """Tests for the async subscribe decorator."""

    @pytest.mark.asyncio
    async def test_subscribe_single_event(self, async_manager):
        """@asubscribe with single event should add to post_subscriptions."""

        @async_manager.subscribe(SampleEvent)
        async def handler(event):
            return event.value

        # Before initialize, should be in post_subscriptions
        assert SampleEvent in async_manager._post_subscriptions
        assert len(async_manager._post_subscriptions[SampleEvent]) == 1

    @pytest.mark.asyncio
    async def test_subscribe_multiple_events(self, async_manager):
        """@asubscribe with multiple events should add to all."""

        @async_manager.subscribe(SampleEvent, SampleEvent2)
        async def handler(event):
            return "handled"

        assert SampleEvent in async_manager._post_subscriptions
        assert SampleEvent2 in async_manager._post_subscriptions

    @pytest.mark.asyncio
    async def test_subscribe_with_condition(self, async_manager):
        """@asubscribe with condition should store condition."""

        def condition(e):
            return e.value > 10

        @async_manager.subscribe(SampleEvent, condition)
        async def handler(event):
            return event.value

        registry = async_manager._post_subscriptions[SampleEvent][0]
        assert len(registry.conditions) == 1

    @pytest.mark.asyncio
    async def test_subscribe_preserves_function(self, async_manager):
        """@asubscribe should return the original async function."""

        @async_manager.subscribe(SampleEvent)
        async def handler(event):
            return event.value

        # Function should still work normally
        mock_event = SampleEvent(value=42)
        result = await handler(mock_event)
        assert result == 42


# =============================================================================
# Initialize Tests
# =============================================================================


class TestInitialize:
    """Tests for initialize() which processes post_subscriptions."""

    @pytest.mark.asyncio
    async def test_initialize_moves_post_subscriptions(self, async_manager):
        """initialize() should move post_subscriptions to subscriptions."""

        @async_manager.subscribe(SampleEvent)
        async def handler(event):
            return event.value

        assert SampleEvent in async_manager._post_subscriptions

        await async_manager.initialize()

        # After initialize, should be in _subscriptions
        assert SampleEvent in async_manager._subscriptions
        assert len(async_manager._post_subscriptions.get(SampleEvent, [])) == 0

    @pytest.mark.asyncio
    async def test_initialize_clears_post_subscriptions(self, async_manager):
        """initialize() should clear post_subscriptions."""

        @async_manager.subscribe(SampleEvent)
        async def handler(event):
            return event.value

        await async_manager.initialize()

        assert len(async_manager._post_subscriptions) == 0

    @pytest.mark.asyncio
    async def test_initialize_multiple_handlers(self, async_manager):
        """initialize() should register all post_subscriptions."""

        @async_manager.subscribe(SampleEvent)
        async def handler1(event):
            return 1

        @async_manager.subscribe(SampleEvent)
        async def handler2(event):
            return 2

        await async_manager.initialize()

        assert len(async_manager._subscriptions[SampleEvent]) == 2


# =============================================================================
# Emit Tests
# =============================================================================


class TestAsyncEmit:
    """Tests for async event emission."""

    @pytest.mark.asyncio
    async def test_emit_calls_handler(self, async_manager):
        """emit() should call registered async handler."""
        results = []

        async def handler(event):
            results.append(event.value)
            return {"value": event.value}

        await async_manager.register(handler, SampleEvent)
        await async_manager.emit(SampleEvent(value=42))

        assert results == [42]

    @pytest.mark.asyncio
    async def test_emit_calls_multiple_handlers(self, async_manager):
        """emit() should call all registered async handlers."""
        results = []

        async def handler1(event):
            results.append("handler1")
            return {"handler1_result": "handler1"}

        async def handler2(event):
            results.append("handler2")
            return {"handler2_result": "handler2"}

        await async_manager.register(handler1, SampleEvent)
        await async_manager.register(handler2, SampleEvent)
        await async_manager.emit(SampleEvent())

        assert "handler1" in results
        assert "handler2" in results

    @pytest.mark.asyncio
    async def test_emit_returns_results(self, async_manager):
        """emit() should return dict of handler results."""

        async def handler1(event):
            return {"handler1_result": "result1"}

        async def handler2(event):
            return {"handler2_result": "result2"}

        await async_manager.register(handler1, SampleEvent)
        await async_manager.register(handler2, SampleEvent)
        results = await async_manager.emit(SampleEvent())

        assert results.get("handler1_result") == "result1"
        assert results.get("handler2_result") == "result2"

    @pytest.mark.asyncio
    async def test_emit_with_no_handlers(self, async_manager):
        """emit() with no handlers should complete without error."""
        result = await async_manager.emit(SampleEvent())
        assert result == {}  # No subscriptions means empty dict

    @pytest.mark.asyncio
    async def test_emit_disabled_event(self, async_manager):
        """emit() should skip disabled events."""
        results = []

        async def handler(event):
            results.append("called")
            return "called"

        await async_manager.register(handler, DisabledEvent)
        await async_manager.emit(DisabledEvent())

        assert results == []

    @pytest.mark.asyncio
    async def test_emit_with_condition_met(self, async_manager):
        """emit() should call handler when condition is met."""
        results = []

        async def handler(event):
            results.append(event.value)
            return {"value": event.value}

        def condition(e):
            return e.value > 10

        await async_manager.register(handler, SampleEvent, condition)
        await async_manager.emit(SampleEvent(value=50))

        assert results == [50]

    @pytest.mark.asyncio
    async def test_emit_with_condition_not_met(self, async_manager):
        """emit() should skip handler when condition is not met."""
        results = []

        async def handler(event):
            results.append(event.value)
            return event.value

        def condition(e):
            return e.value > 100

        await async_manager.register(handler, SampleEvent, condition)
        await async_manager.emit(SampleEvent(value=50))

        assert results == []

    @pytest.mark.asyncio
    async def test_emit_handles_handler_exception(self, async_manager):
        """emit() should continue after handler exception."""
        results = []

        async def failing_handler(event):
            raise ValueError("Test error")

        async def succeeding_handler(event):
            results.append("success")
            return {"success_result": "success"}

        await async_manager.register(failing_handler, SampleEvent)
        await async_manager.register(succeeding_handler, SampleEvent)
        await async_manager.emit(SampleEvent())

        assert results == ["success"]


# =============================================================================
# Reset and Halt Tests
# =============================================================================


class TestAsyncResetAndHalt:
    """Tests for async reset and halt functionality."""

    @pytest.mark.asyncio
    async def test_reset_clears_subscriptions(self, async_manager):
        """reset() should clear all subscriptions."""

        async def handler(event):
            return event.value

        await async_manager.register(handler, SampleEvent)
        await async_manager.reset()

        assert len(async_manager._subscriptions) == 0

    @pytest.mark.asyncio
    async def test_halt_stops_emit_processing(self, async_manager):
        """halt() should stop emit processing and return empty results."""

        async def handler(event):
            return {"result": "value"}

        await async_manager.register(handler, SampleEvent)

        # First emit works
        results = await async_manager.emit(SampleEvent())
        assert results == {"result": "value"}

        # After halt, emit returns empty dict
        async_manager.halt()
        assert async_manager.is_halted

        results = await async_manager.emit(SampleEvent())
        assert results == {}

        # Resume allows processing again
        async_manager.resume()
        assert not async_manager.is_halted
        results = await async_manager.emit(SampleEvent())
        assert results == {"result": "value"}

    @pytest.mark.asyncio
    async def test_reset_allows_re_registration(self, async_manager):
        """After reset(), new registrations should work."""

        async def handler(event):
            return {"result": "works"}

        await async_manager.register(handler, SampleEvent)
        await async_manager.reset()
        await async_manager.register(handler, SampleEvent)

        results = await async_manager.emit(SampleEvent())
        assert results.get("result") == "works"


# =============================================================================
# Halt/Resume Tests
# =============================================================================


class TestAsyncHaltResume:
    """Tests for halt and resume functionality in async context."""

    @pytest.mark.asyncio
    async def test_is_halted_initially_false(self, async_manager):
        """is_halted should be False initially."""
        assert not async_manager.is_halted

    @pytest.mark.asyncio
    async def test_halt_sets_is_halted(self, async_manager):
        """halt() should set is_halted to True."""
        async_manager.halt()
        assert async_manager.is_halted

    @pytest.mark.asyncio
    async def test_resume_clears_is_halted(self, async_manager):
        """resume() should set is_halted to False."""
        async_manager.halt()
        async_manager.resume()
        assert not async_manager.is_halted

    @pytest.mark.asyncio
    async def test_reset_auto_resumes(self, async_manager):
        """reset() should auto-resume from halted state."""
        async_manager.halt()
        assert async_manager.is_halted
        await async_manager.reset()
        assert not async_manager.is_halted


# =============================================================================
# Concurrent Callback Execution Tests
# =============================================================================


class TestConcurrentCallbackExecution:
    """Tests for concurrent callback execution using TaskGroup."""

    @pytest.mark.asyncio
    async def test_handlers_execute_concurrently(self, async_manager):
        """Multiple handlers should execute concurrently."""
        execution_times = []

        async def slow_handler1(event):
            start = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)
            end = asyncio.get_event_loop().time()
            execution_times.append(("handler1", start, end))
            return {"handler1_result": "handler1"}

        async def slow_handler2(event):
            start = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)
            end = asyncio.get_event_loop().time()
            execution_times.append(("handler2", start, end))
            return {"handler2_result": "handler2"}

        await async_manager.register(slow_handler1, SampleEvent)
        await async_manager.register(slow_handler2, SampleEvent)

        start_time = asyncio.get_event_loop().time()
        await async_manager.emit(SampleEvent())
        total_time = asyncio.get_event_loop().time() - start_time

        # If handlers ran concurrently, total time should be ~0.1s not ~0.2s
        # Allow some margin for overhead
        assert total_time < 0.18, (
            f"Handlers should run concurrently, took {total_time}s"
        )

    @pytest.mark.asyncio
    async def test_concurrent_results_all_collected(self, async_manager):
        """All concurrent handler results should be collected."""

        async def handler1(event):
            await asyncio.sleep(0.05)
            return {"handler1_result": "result1"}

        async def handler2(event):
            await asyncio.sleep(0.05)
            return {"handler2_result": "result2"}

        async def handler3(event):
            await asyncio.sleep(0.05)
            return {"handler3_result": "result3"}

        await async_manager.register(handler1, SampleEvent)
        await async_manager.register(handler2, SampleEvent)
        await async_manager.register(handler3, SampleEvent)

        results = await async_manager.emit(SampleEvent())

        assert len(results) == 3
        assert results.get("handler1_result") == "result1"
        assert results.get("handler2_result") == "result2"
        assert results.get("handler3_result") == "result3"


# =============================================================================
# Edge Cases
# =============================================================================


class TestAsyncEdgeCases:
    """Tests for async edge cases."""

    @pytest.mark.asyncio
    async def test_emit_non_event_instance(self, async_manager):
        """emit() with non-Event should return empty dict."""
        result = await async_manager.emit("not_an_event")  # type: ignore
        assert result == {}

    @pytest.mark.asyncio
    async def test_handler_returning_none(self, async_manager):
        """Handler returning None should result in empty dict entry."""

        async def handler(event):
            return None

        await async_manager.register(handler, SampleEvent)
        results = await async_manager.emit(SampleEvent())

        assert results == {}

    @pytest.mark.asyncio
    async def test_handler_with_delay(self, async_manager):
        """Handler with async delay should complete correctly."""

        async def delayed_handler(event):
            await asyncio.sleep(0.01)
            return {"value": event.value * 2}

        await async_manager.register(delayed_handler, SampleEvent)
        results = await async_manager.emit(SampleEvent(value=21))

        assert results.get("value") == 42

    @pytest.mark.asyncio
    async def test_nested_emit(self, async_manager):
        """Handler that emits another event should work."""
        results = []

        async def handler1(event):
            results.append("handler1")
            await async_manager.emit(SampleEvent2(message="nested"))
            return {"handler1_result": "handler1_result"}

        async def handler2(event):
            results.append("handler2")
            return {"handler2_result": "handler2_result"}

        await async_manager.register(handler1, SampleEvent)
        await async_manager.register(handler2, SampleEvent2)
        await async_manager.emit(SampleEvent())

        assert "handler1" in results
        assert "handler2" in results


# =============================================================================
# Full Workflow Tests
# =============================================================================


class TestAsyncFullWorkflow:
    """Tests for complete async workflows."""

    @pytest.mark.asyncio
    async def test_subscribe_initialize_emit_workflow(self, async_manager):
        """Complete workflow: subscribe -> initialize -> emit."""
        results = []

        @async_manager.subscribe(SampleEvent)
        async def handler(event):
            results.append(event.value)
            return {"value": event.value}

        # Initialize to move post_subscriptions to subscriptions
        await async_manager.initialize()

        # Now emit
        await async_manager.emit(SampleEvent(value=123))

        assert results == [123]

    @pytest.mark.asyncio
    async def test_mixed_subscribe_and_register(self, async_manager):
        """Mix of @subscribe and direct register should work."""
        results = []

        @async_manager.subscribe(SampleEvent)
        async def decorated_handler(event):
            results.append("decorated")
            return {"decorated_result": "decorated"}

        async def direct_handler(event):
            results.append("direct")
            return {"direct_result": "direct"}

        # Direct register doesn't need initialize
        await async_manager.register(direct_handler, SampleEvent)

        # Initialize for decorated handler
        await async_manager.initialize()

        await async_manager.emit(SampleEvent())

        assert "decorated" in results
        assert "direct" in results
