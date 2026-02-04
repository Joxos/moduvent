"""
Unit tests for moduvent.descriptors module.

Tests cover:
- Checker base class
- EventInheritor descriptor
- EventInstance descriptor
- WeakReference descriptor
"""

import pytest
import weakref
from moduvent.events import Event
from moduvent.descriptors import (
    Checker,
    EventInheritor,
    EventInstance,
    WeakReference,
)
from moduvent.utils import FunctionTypes


# =============================================================================
# Test Classes
# =============================================================================


class SampleEvent(Event):
    """Test event class."""

    pass


class AnotherEvent(Event):
    """Another test event class."""

    pass


# =============================================================================
# Checker Tests
# =============================================================================


class TestChecker:
    """Tests for the Checker base class."""

    def test_checker_set_name(self):
        """Checker should set public and private names."""

        class TestClass:
            attr: Checker = Checker()

        # Access descriptor to trigger __set_name__
        assert hasattr(TestClass, "_attr")

    def test_checker_get_returns_value(self):
        """Checker __get__ should return stored value."""

        class TestClass:
            attr: Checker = Checker()

        obj = TestClass()
        obj._attr = "test_value"
        assert obj.attr == "test_value"

    def test_checker_set_stores_value_when_conditions_pass(self):
        """Checker __set__ should store value when conditions pass."""

        class AlwaysPassChecker(Checker):
            conditions = [lambda x: True]

        class TestClass:
            attr = AlwaysPassChecker()

        obj = TestClass()
        obj.attr = "test_value"
        assert obj._attr == "test_value"

    def test_checker_raises_on_failed_condition(self):
        """Checker should raise error when condition fails."""

        class AlwaysFailChecker(Checker):
            conditions = [lambda x: False]

        class TestClass:
            attr = AlwaysFailChecker()

        obj = TestClass()
        with pytest.raises(TypeError):
            obj.attr = "any_value"


# =============================================================================
# EventInheritor Tests
# =============================================================================


class SampleEventInheritor:
    """Tests for the EventInheritor descriptor."""

    def test_accepts_event_class(self):
        """EventInheritor should accept Event class."""

        class TestClass:
            event_type = EventInheritor()

        obj = TestClass()
        obj.event_type = Event
        assert obj.event_type is Event

    def test_accepts_event_subclass(self):
        """EventInheritor should accept Event subclass."""

        class TestClass:
            event_type = EventInheritor()

        obj = TestClass()
        obj.event_type = SampleEvent
        assert obj.event_type is SampleEvent

    def test_rejects_non_event_class(self):
        """EventInheritor should reject non-Event class."""

        class TestClass:
            event_type = EventInheritor()

        obj = TestClass()
        with pytest.raises(TypeError, match="not an inheritor"):
            obj.event_type = str

    def test_rejects_event_instance(self):
        """EventInheritor should reject Event instance."""

        class TestClass:
            event_type = EventInheritor()

        obj = TestClass()
        with pytest.raises(TypeError, match="not an inheritor"):
            obj.event_type = SampleEvent()

    def test_rejects_none(self):
        """EventInheritor should reject None."""

        class TestClass:
            event_type = EventInheritor()

        obj = TestClass()
        with pytest.raises(TypeError, match="not an inheritor"):
            obj.event_type = None

    def test_rejects_primitive_values(self):
        """EventInheritor should reject primitive values."""

        class TestClass:
            event_type = EventInheritor()

        obj = TestClass()
        with pytest.raises(TypeError):
            obj.event_type = 123
        with pytest.raises(TypeError):
            obj.event_type = "string"


# =============================================================================
# EventInstance Tests
# =============================================================================


class SampleEventInstance:
    """Tests for the EventInstance descriptor."""

    def test_accepts_event_instance(self):
        """EventInstance should accept Event instance."""

        class TestClass:
            event = EventInstance()

        obj = TestClass()
        event = Event()
        obj.event = event
        assert obj.event is event

    def test_accepts_subclass_instance(self):
        """EventInstance should accept Event subclass instance."""

        class TestClass:
            event = EventInstance()

        obj = TestClass()
        event = SampleEvent()
        obj.event = event
        assert obj.event is event

    def test_rejects_event_class(self):
        """EventInstance should reject Event class."""

        class TestClass:
            event = EventInstance()

        obj = TestClass()
        with pytest.raises(TypeError, match="not an instance"):
            obj.event = SampleEvent

    def test_rejects_non_event_instance(self):
        """EventInstance should reject non-Event instance."""

        class TestClass:
            event = EventInstance()

        obj = TestClass()
        with pytest.raises(TypeError):
            obj.event = "not an event"
        with pytest.raises(TypeError):
            obj.event = 123

    def test_rejects_none(self):
        """EventInstance should reject None."""

        class TestClass:
            event = EventInstance()

        obj = TestClass()
        with pytest.raises(TypeError, match="not an instance"):
            obj.event = None


# =============================================================================
# WeakReference Tests
# =============================================================================


class TestWeakReference:
    """Tests for the WeakReference descriptor."""

    def test_stores_weakref_for_function(self):
        """WeakReference should store weak reference for function."""

        class TestClass:
            func = WeakReference()

            def __init__(self):
                self._func_ref = None
                self.func_type = FunctionTypes.FUNCTION

        def test_func():
            pass

        obj = TestClass()
        obj.func = test_func
        assert obj._func_ref is not None
        assert obj.func is test_func

    def test_stores_weakmethod_for_bound_method(self):
        """WeakReference should store WeakMethod for bound method."""

        class TestClass:
            func = WeakReference()

            def __init__(self):
                self._func_ref = None
                self.func_type = FunctionTypes.BOUND_METHOD

        class SomeClass:
            def method(self):
                pass

        some_obj = SomeClass()
        obj = TestClass()
        obj.func = some_obj.method
        assert isinstance(obj._func_ref, weakref.WeakMethod)

    def test_returns_none_when_referent_is_garbage_collected(self):
        """WeakReference should return None when referent is collected."""

        class TestClass:
            func = WeakReference()

            def __init__(self):
                self._func_ref = None
                self.func_type = FunctionTypes.BOUND_METHOD

        class SomeClass:
            def method(self):
                pass

        obj = TestClass()
        some_obj = SomeClass()
        obj.func = some_obj.method

        # Delete the object holding the method
        del some_obj

        # WeakMethod should now return None
        assert obj.func is None

    def test_raises_on_none_value(self):
        """WeakReference should raise ValueError when setting None."""

        class TestClass:
            func = WeakReference()

            def __init__(self):
                self._func_ref = None
                self.func_type = FunctionTypes.FUNCTION

        obj = TestClass()
        with pytest.raises(ValueError, match="Cannot set weak reference of None"):
            obj.func = None

    def test_raises_on_non_weakreferenceable(self):
        """WeakReference should raise TypeError for non-weakreferenceable."""

        class TestClass:
            func = WeakReference()

            def __init__(self):
                self._func_ref = None
                self.func_type = FunctionTypes.FUNCTION

        obj = TestClass()
        # Integers are not weakly referenceable
        with pytest.raises(TypeError, match="Cannot set weak reference"):
            obj.func = 123

    def test_get_dereferences_weakref(self):
        """WeakReference __get__ should dereference and return actual value."""

        class TestClass:
            func = WeakReference()

            def __init__(self):
                self._func_ref = None
                self.func_type = FunctionTypes.FUNCTION

        def test_func():
            return "result"

        obj = TestClass()
        obj.func = test_func
        retrieved = obj.func
        assert retrieved is test_func
        assert retrieved() == "result"
