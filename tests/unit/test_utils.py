"""
Unit tests for moduvent.utils module.

Tests cover:
- is_class_and_subclass function
- is_instance_and_subclass function
- FunctionTypes enum
- check_function_type function
- SUBSCRIPTION_STRATEGY enum
- get_subscription_strategy function
"""

import pytest
from moduvent.events import Event
from moduvent.utils import (
    is_class_and_subclass,
    is_instance_and_subclass,
    FunctionTypes,
    check_function_type,
    SUBSCRIPTION_STRATEGY,
    get_subscription_strategy,
)


# =============================================================================
# Test Event Classes
# =============================================================================


class SampleEvent(Event):
    """Test event for utils tests."""

    pass


class AnotherEvent(Event):
    """Another test event."""

    pass


# =============================================================================
# is_class_and_subclass Tests
# =============================================================================


class TestIsClassAndSubclass:
    """Tests for is_class_and_subclass function."""

    def test_returns_true_for_event_class(self):
        """Should return True for Event class."""
        assert is_class_and_subclass(Event) is True

    def test_returns_true_for_event_subclass(self):
        """Should return True for Event subclass."""
        assert is_class_and_subclass(SampleEvent) is True

    def test_returns_false_for_event_instance(self):
        """Should return False for Event instance."""
        event = SampleEvent()
        assert is_class_and_subclass(event) is False

    def test_returns_false_for_non_event_class(self):
        """Should return False for non-Event class."""
        assert is_class_and_subclass(str) is False
        assert is_class_and_subclass(int) is False
        assert is_class_and_subclass(list) is False

    def test_returns_false_for_none(self):
        """Should return False for None."""
        assert is_class_and_subclass(None) is False

    def test_returns_false_for_primitives(self):
        """Should return False for primitive values."""
        assert is_class_and_subclass(123) is False
        assert is_class_and_subclass("string") is False
        assert is_class_and_subclass([1, 2, 3]) is False

    def test_returns_false_for_callable(self):
        """Should return False for callable objects."""
        assert is_class_and_subclass(lambda x: x) is False

        def func():
            pass

        assert is_class_and_subclass(func) is False


# =============================================================================
# is_instance_and_subclass Tests
# =============================================================================


class TestIsInstanceAndSubclass:
    """Tests for is_instance_and_subclass function."""

    def test_returns_true_for_event_instance(self):
        """Should return True for Event instance."""
        event = Event()
        assert is_instance_and_subclass(event) is True

    def test_returns_true_for_subclass_instance(self):
        """Should return True for Event subclass instance."""
        event = SampleEvent()
        assert is_instance_and_subclass(event) is True

    def test_returns_false_for_event_class(self):
        """Should return False for Event class itself."""
        assert is_instance_and_subclass(Event) is False

    def test_returns_false_for_non_event_instance(self):
        """Should return False for non-Event instance."""
        assert is_instance_and_subclass("string") is False
        assert is_instance_and_subclass(123) is False
        assert is_instance_and_subclass([]) is False

    def test_returns_false_for_none(self):
        """Should return False for None."""
        assert is_instance_and_subclass(None) is False


# =============================================================================
# FunctionTypes Tests
# =============================================================================


class TestFunctionTypes:
    """Tests for FunctionTypes enum."""

    def test_all_function_types_exist(self):
        """All expected function types should exist."""
        assert hasattr(FunctionTypes, "STATICMETHOD")
        assert hasattr(FunctionTypes, "BOUND_METHOD")
        assert hasattr(FunctionTypes, "UNBOUND_METHOD")
        assert hasattr(FunctionTypes, "FUNCTION")
        assert hasattr(FunctionTypes, "CALLBACK")
        assert hasattr(FunctionTypes, "UNKNOWN")

    def test_function_types_are_unique(self):
        """All function types should have unique values."""
        values = [
            FunctionTypes.STATICMETHOD,
            FunctionTypes.BOUND_METHOD,
            FunctionTypes.UNBOUND_METHOD,
            FunctionTypes.FUNCTION,
            FunctionTypes.CALLBACK,
            FunctionTypes.UNKNOWN,
        ]
        assert len(values) == len(set(values))


# =============================================================================
# check_function_type Tests
# =============================================================================


class TestCheckFunctionType:
    """Tests for check_function_type function."""

    def test_detects_regular_function(self):
        """Should detect regular function."""

        def regular_func():
            pass

        assert check_function_type(regular_func) == FunctionTypes.FUNCTION

    def test_detects_lambda_as_function(self):
        """Should detect lambda as function."""

        def lambda_func(x):
            return x

        assert check_function_type(lambda_func) == FunctionTypes.FUNCTION

    def test_detects_bound_method(self):
        """Should detect bound method."""

        class MyClass:
            def method(self):
                pass

        instance = MyClass()
        assert check_function_type(instance.method) == FunctionTypes.BOUND_METHOD

    def test_detects_staticmethod(self):
        """Should detect staticmethod (before binding)."""

        class MyClass:
            @staticmethod
            def static_method():
                pass

        # Access the raw staticmethod descriptor
        static = MyClass.__dict__["static_method"]
        assert check_function_type(static) == FunctionTypes.STATICMETHOD

    def test_detects_unbound_method_with_subscriptions(self):
        """Should detect unbound method with _subscriptions attribute."""
        from collections import defaultdict

        def handler(event):
            pass

        handler._subscriptions = defaultdict(list)
        assert check_function_type(handler) == FunctionTypes.UNBOUND_METHOD

    def test_detects_builtin_function(self):
        """Should detect builtin function."""
        assert check_function_type(len) == FunctionTypes.FUNCTION
        assert check_function_type(print) == FunctionTypes.FUNCTION

    def test_returns_unknown_for_unrecognized(self):
        """Should return UNKNOWN for unrecognized types."""

        class CustomCallable:
            def __call__(self):
                pass

        custom = CustomCallable()
        assert check_function_type(custom) == FunctionTypes.UNKNOWN


# =============================================================================
# SUBSCRIPTION_STRATEGY Tests
# =============================================================================


class TestSubscriptionStrategy:
    """Tests for SUBSCRIPTION_STRATEGY enum."""

    def test_strategies_exist(self):
        """All expected strategies should exist."""
        assert hasattr(SUBSCRIPTION_STRATEGY, "EVENTS")
        assert hasattr(SUBSCRIPTION_STRATEGY, "CONDITIONS")

    def test_strategies_are_unique(self):
        """Strategies should have unique values."""
        assert SUBSCRIPTION_STRATEGY.EVENTS != SUBSCRIPTION_STRATEGY.CONDITIONS


# =============================================================================
# get_subscription_strategy Tests
# =============================================================================


class TestGetSubscriptionStrategy:
    """Tests for get_subscription_strategy function."""

    def test_single_event_returns_events_strategy(self):
        """Single event type should return EVENTS strategy."""
        result = get_subscription_strategy(SampleEvent)
        assert result == SUBSCRIPTION_STRATEGY.EVENTS

    def test_multiple_events_returns_events_strategy(self):
        """Multiple event types should return EVENTS strategy."""
        result = get_subscription_strategy(SampleEvent, AnotherEvent)
        assert result == SUBSCRIPTION_STRATEGY.EVENTS

    def test_event_with_condition_returns_conditions_strategy(self):
        """Event with condition function should return CONDITIONS strategy."""

        def condition(e):
            return True

        result = get_subscription_strategy(SampleEvent, condition)
        assert result == SUBSCRIPTION_STRATEGY.CONDITIONS

    def test_event_with_multiple_conditions(self):
        """Event with multiple conditions should return CONDITIONS strategy."""

        def cond1(e):
            return True

        def cond2(e):
            return False

        result = get_subscription_strategy(SampleEvent, cond1, cond2)
        assert result == SUBSCRIPTION_STRATEGY.CONDITIONS

    def test_raises_on_empty_args(self):
        """Should raise ValueError when no arguments provided."""
        with pytest.raises(ValueError, match="At least one event type"):
            get_subscription_strategy()

    def test_raises_on_non_event_first_arg(self):
        """Should raise ValueError when first arg is not event type."""
        with pytest.raises(ValueError, match="First argument must be an event type"):
            get_subscription_strategy("not_an_event")

        with pytest.raises(ValueError, match="First argument must be an event type"):
            get_subscription_strategy(123)

        with pytest.raises(ValueError, match="First argument must be an event type"):
            get_subscription_strategy(lambda x: x)

    def test_raises_on_mixed_events_and_conditions(self):
        """Should raise ValueError when mixing events and non-callables."""
        with pytest.raises(ValueError, match="Got .* among events"):
            get_subscription_strategy(
                SampleEvent, AnotherEvent, "not_event_or_callable"
            )

    def test_raises_on_non_callable_in_conditions(self):
        """Should raise ValueError when condition is not callable."""
        with pytest.raises(ValueError, match="Got .* among conditions"):
            get_subscription_strategy(SampleEvent, lambda e: True, "not_callable")


# =============================================================================
# is_coroutine_function Tests
# =============================================================================


class TestIsCoroutineFunction:
    """Tests for is_coroutine_function function."""

    def test_sync_function_returns_false(self):
        """Regular sync function should return False."""
        from moduvent.utils import is_coroutine_function

        def sync_func():
            pass

        assert is_coroutine_function(sync_func) is False

    def test_async_function_returns_true(self):
        """Async function should return True."""
        from moduvent.utils import is_coroutine_function

        async def async_func():
            pass

        assert is_coroutine_function(async_func) is True

    def test_lambda_returns_false(self):
        """Lambda should return False."""
        from moduvent.utils import is_coroutine_function

        def lambda_func(x):
            return x

        assert is_coroutine_function(lambda_func) is False

    def test_sync_bound_method_returns_false(self):
        """Sync bound method should return False."""
        from moduvent.utils import is_coroutine_function

        class MyClass:
            def sync_method(self):
                pass

        instance = MyClass()
        assert is_coroutine_function(instance.sync_method) is False

    def test_async_bound_method_returns_true(self):
        """Async bound method should return True."""
        from moduvent.utils import is_coroutine_function

        class MyClass:
            async def async_method(self):
                pass

        instance = MyClass()
        assert is_coroutine_function(instance.async_method) is True

    def test_staticmethod_sync_returns_false(self):
        """Sync staticmethod should return False."""
        from moduvent.utils import is_coroutine_function

        class MyClass:
            @staticmethod
            def sync_static():
                pass

        # Test with raw descriptor
        static = MyClass.__dict__["sync_static"]
        assert is_coroutine_function(static) is False

        # Test with bound version
        assert is_coroutine_function(MyClass.sync_static) is False

    def test_staticmethod_async_returns_true(self):
        """Async staticmethod should return True."""
        from moduvent.utils import is_coroutine_function

        class MyClass:
            @staticmethod
            async def async_static():
                pass

        # Test with raw descriptor
        static = MyClass.__dict__["async_static"]
        assert is_coroutine_function(static) is True

        # Test with bound version
        assert is_coroutine_function(MyClass.async_static) is True

    def test_classmethod_sync_returns_false(self):
        """Sync classmethod should return False."""
        from moduvent.utils import is_coroutine_function

        class MyClass:
            @classmethod
            def sync_class(cls):
                pass

        # Test with raw descriptor
        cm = MyClass.__dict__["sync_class"]
        assert is_coroutine_function(cm) is False

        # Test with bound version
        assert is_coroutine_function(MyClass.sync_class) is False

    def test_classmethod_async_returns_true(self):
        """Async classmethod should return True."""
        from moduvent.utils import is_coroutine_function

        class MyClass:
            @classmethod
            async def async_class(cls):
                pass

        # Test with raw descriptor
        cm = MyClass.__dict__["async_class"]
        assert is_coroutine_function(cm) is True

        # Test with bound version
        assert is_coroutine_function(MyClass.async_class) is True
