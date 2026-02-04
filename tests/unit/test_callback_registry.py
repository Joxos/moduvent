"""
Unit tests for moduvent callback registry classes.

Tests cover:
- BaseCallbackRegistry
- CallbackRegistry (sync)
- AsyncCallbackRegistry (async)
- PostCallbackRegistry
- CallbackProcessing (sync)
- AsyncCallbackProcessing (async)
"""

import pytest
from moduvent.events import Event
from moduvent.common import (
    PostCallbackRegistry,
)
from moduvent.moduvent import CallbackRegistry, CallbackProcessing
from moduvent.async_moduvent import AsyncCallbackRegistry, AsyncCallbackProcessing
from moduvent.utils import FunctionTypes


# =============================================================================
# Test Classes
# =============================================================================


class SampleEvent(Event):
    """Test event for registry tests."""

    def __init__(self, value: int = 0):
        self.value = value


class AnotherEvent(Event):
    """Another test event."""

    pass


# =============================================================================
# Test Functions and Methods
# =============================================================================


def sample_callback(event: SampleEvent):
    """Sample callback function."""
    return {"value": event.value}


def another_callback(event: SampleEvent):
    """Another sample callback."""
    return {"value": event.value * 2}


async def async_callback(event: SampleEvent):
    """Sample async callback."""
    return {"value": event.value}


class CallbackHolder:
    """Class to hold method callbacks."""

    def method_callback(self, event: SampleEvent):
        return {"value": event.value}

    @staticmethod
    def static_callback(event: SampleEvent):
        return {"value": event.value}


# =============================================================================
# CallbackRegistry Tests
# =============================================================================


class TestCallbackRegistry:
    """Tests for CallbackRegistry (sync)."""

    def test_creates_with_function(self):
        """Should create registry with regular function."""
        registry = CallbackRegistry(
            func=sample_callback,
            event_type=SampleEvent,
        )
        assert registry.func is sample_callback
        assert registry.event_type is SampleEvent
        assert registry.conditions == ()

    def test_creates_with_conditions(self):
        """Should create registry with conditions."""
        cond1 = lambda e: e.value > 0
        cond2 = lambda e: e.value < 100
        registry = CallbackRegistry(
            func=sample_callback,
            event_type=SampleEvent,
            conditions=(cond1, cond2),
        )
        assert len(registry.conditions) == 2

    def test_equality_with_same_function(self):
        """Registries with same function should be equal."""
        reg1 = CallbackRegistry(func=sample_callback, event_type=SampleEvent)
        reg2 = CallbackRegistry(func=sample_callback, event_type=SampleEvent)
        assert reg1 == reg2

    def test_inequality_with_different_functions(self):
        """Registries with different functions should not be equal."""
        reg1 = CallbackRegistry(func=sample_callback, event_type=SampleEvent)
        reg2 = CallbackRegistry(func=another_callback, event_type=SampleEvent)
        assert reg1 != reg2

    def test_equality_with_bare_function(self):
        """Registry should equal its wrapped function."""
        registry = CallbackRegistry(func=sample_callback, event_type=SampleEvent)
        assert registry == sample_callback

    def test_check_conditions_all_pass(self):
        """_check_conditions should return True when all pass."""
        cond1 = lambda e: True
        cond2 = lambda e: True
        registry = CallbackRegistry(
            func=sample_callback,
            event_type=SampleEvent,
            conditions=(cond1, cond2),
        )
        event = SampleEvent(value=42)
        assert registry._check_conditions(event) is True

    def test_check_conditions_one_fails(self):
        """_check_conditions should return False when one fails."""
        cond1 = lambda e: True
        cond2 = lambda e: False
        registry = CallbackRegistry(
            func=sample_callback,
            event_type=SampleEvent,
            conditions=(cond1, cond2),
        )
        event = SampleEvent(value=42)
        assert registry._check_conditions(event) is False

    def test_check_conditions_empty(self):
        """_check_conditions should return True with no conditions."""
        registry = CallbackRegistry(func=sample_callback, event_type=SampleEvent)
        event = SampleEvent(value=42)
        assert registry._check_conditions(event) is True

    def test_str_representation(self):
        """String representation should be informative."""
        registry = CallbackRegistry(func=sample_callback, event_type=SampleEvent)
        result = str(registry)
        assert "Callback" in result
        assert "SampleEvent" in result
        assert "sample_callback" in result

    def test_func_type_detection(self):
        """Should detect function type correctly."""
        registry = CallbackRegistry(func=sample_callback, event_type=SampleEvent)
        assert registry.func_type == FunctionTypes.FUNCTION


class TestCallbackRegistryWithMethods:
    """Tests for CallbackRegistry with bound methods."""

    def test_creates_with_bound_method(self):
        """Should create registry with bound method."""
        holder = CallbackHolder()
        registry = CallbackRegistry(
            func=holder.method_callback,
            event_type=SampleEvent,
        )
        # Use == instead of 'is' because Python creates new method objects on access
        assert registry.func == holder.method_callback
        assert registry.func_type == FunctionTypes.BOUND_METHOD


# =============================================================================
# AsyncCallbackRegistry Tests
# =============================================================================


class TestAsyncCallbackRegistry:
    """Tests for AsyncCallbackRegistry."""

    def test_creates_with_async_function(self):
        """Should create registry with async function."""
        registry = AsyncCallbackRegistry(
            func=async_callback,
            event_type=SampleEvent,
        )
        assert registry.func is async_callback
        assert registry.event_type is SampleEvent

    def test_equality_with_same_function(self):
        """Async registries with same function should be equal."""
        reg1 = AsyncCallbackRegistry(func=async_callback, event_type=SampleEvent)
        reg2 = AsyncCallbackRegistry(func=async_callback, event_type=SampleEvent)
        assert reg1 == reg2


# =============================================================================
# PostCallbackRegistry Tests
# =============================================================================


class TestPostCallbackRegistry:
    """Tests for PostCallbackRegistry."""

    def test_creates_for_deferred_registration(self):
        """Should create registry for deferred registration."""
        registry = PostCallbackRegistry(
            func=sample_callback,
            event_type=SampleEvent,
        )
        assert registry.func is sample_callback
        assert registry.event_type is SampleEvent

    def test_equality_with_same_attributes(self):
        """Post registries with same attributes should be equal."""
        reg1 = PostCallbackRegistry(func=sample_callback, event_type=SampleEvent)
        reg2 = PostCallbackRegistry(func=sample_callback, event_type=SampleEvent)
        assert reg1 == reg2

    def test_inequality_with_different_event_types(self):
        """Post registries with different event types should not be equal."""
        reg1 = PostCallbackRegistry(func=sample_callback, event_type=SampleEvent)
        reg2 = PostCallbackRegistry(func=sample_callback, event_type=AnotherEvent)
        assert reg1 != reg2


# =============================================================================
# CallbackProcessing Tests
# =============================================================================


class TestCallbackProcessing:
    """Tests for CallbackProcessing (sync)."""

    def test_creates_with_event(self):
        """Should create processing with event instance."""
        event = SampleEvent(value=42)
        processing = CallbackProcessing(
            func=sample_callback,
            event=event,
        )
        assert processing.func is sample_callback
        assert processing.event is event

    def test_call_executes_function(self):
        """call() should execute the callback function."""
        event = SampleEvent(value=42)
        processing = CallbackProcessing(
            func=sample_callback,
            event=event,
        )
        result = processing.call()
        assert result == {"value": 42}

    def test_call_with_conditions_met(self):
        """call() should execute when conditions are met."""
        event = SampleEvent(value=50)
        processing = CallbackProcessing(
            func=sample_callback,
            event=event,
            conditions=(lambda e: e.value > 0,),
        )
        result = processing.call()
        assert result == {"value": 50}

    def test_call_skips_when_conditions_not_met(self):
        """call() should skip when conditions are not met."""
        event = SampleEvent(value=50)
        processing = CallbackProcessing(
            func=sample_callback,
            event=event,
            conditions=(lambda e: e.value < 0,),  # Will fail
        )
        result = processing.call()
        assert result is None

    def test_is_callable_returns_true_for_valid_function(self):
        """is_callable() should return True for valid function."""
        event = SampleEvent(value=42)
        processing = CallbackProcessing(
            func=sample_callback,
            event=event,
        )
        assert processing.is_callable() is True

    def test_call_handles_exception(self):
        """call() should handle exceptions gracefully."""

        def failing_callback(event):
            raise ValueError("Test error")

        event = SampleEvent(value=42)
        processing = CallbackProcessing(
            func=failing_callback,
            event=event,
        )
        # Should not raise, just log the error
        result = processing.call()
        assert result is None


# =============================================================================
# AsyncCallbackProcessing Tests
# =============================================================================


class TestAsyncCallbackProcessing:
    """Tests for AsyncCallbackProcessing."""

    @pytest.mark.asyncio
    async def test_call_executes_async_function(self):
        """call() should execute async callback function."""
        event = SampleEvent(value=42)
        processing = AsyncCallbackProcessing(
            func=async_callback,
            event=event,
        )
        result = await processing.call()
        assert result == {"value": 42}

    @pytest.mark.asyncio
    async def test_call_with_conditions_met(self):
        """call() should execute when conditions are met."""
        event = SampleEvent(value=50)
        processing = AsyncCallbackProcessing(
            func=async_callback,
            event=event,
            conditions=(lambda e: e.value > 0,),
        )
        result = await processing.call()
        assert result == {"value": 50}

    @pytest.mark.asyncio
    async def test_call_skips_when_conditions_not_met(self):
        """call() should skip when conditions are not met."""
        event = SampleEvent(value=50)
        processing = AsyncCallbackProcessing(
            func=async_callback,
            event=event,
            conditions=(lambda e: e.value < 0,),  # Will fail
        )
        result = await processing.call()
        assert result is None

    @pytest.mark.asyncio
    async def test_call_handles_async_exception(self):
        """call() should handle async exceptions gracefully."""

        async def failing_async_callback(event):
            raise ValueError("Async test error")

        event = SampleEvent(value=42)
        processing = AsyncCallbackProcessing(
            func=failing_async_callback,
            event=event,
        )
        # Should not raise, just log the error
        result = await processing.call()
        assert result is None
