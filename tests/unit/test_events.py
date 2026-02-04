"""
Unit tests for moduvent.events module.

Tests cover:
- Event base class
- MutedContext context manager
- Signal class
- DataEvent class
- EventFactory and related factories
- EventMeta metaclass
"""

import pytest
from moduvent.events import (
    Event,
    MutedContext,
    Signal,
    DataEvent,
    EventFactory,
    SignalFactory,
    DataEventFactory,
    EventMeta,
)


# =============================================================================
# Event Base Class Tests
# =============================================================================


class TestEvent:
    """Tests for the Event base class."""

    def test_event_enabled_by_default(self):
        """Event should be enabled by default."""
        assert Event.enabled is True

    def test_event_instance_inherits_enabled(self):
        """Event instance should inherit enabled status from class."""
        event = Event()
        assert type(event).enabled is True

    def test_event_str_representation_empty(self):
        """Event without attributes should have minimal string representation."""
        event = Event()
        result = str(event)
        assert "Event()" in result

    def test_event_str_representation_with_attributes(self, dummy_event):
        """Event with attributes should include them in string representation."""
        result = str(dummy_event)
        assert "DummyEvent" in result
        assert "value=42" in result

    def test_event_str_excludes_dunder_attributes(self):
        """Event string representation should exclude __dunder__ attributes."""

        class TestEvent(Event):
            def __init__(self):
                self.__private = "hidden"
                self.public = "visible"

        event = TestEvent()
        result = str(event)
        assert "public=visible" in result
        assert "__private" not in result

    def test_event_subclass_enabled(self):
        """Subclass should inherit enabled status."""

        class SubEvent(Event):
            pass

        assert SubEvent.enabled is True

    def test_event_subclass_can_override_enabled(self):
        """Subclass can override enabled status."""

        class DisabledSubEvent(Event):
            enabled = False

        assert DisabledSubEvent.enabled is False


# =============================================================================
# MutedContext Tests
# =============================================================================


class TestMutedContext:
    """Tests for MutedContext context manager."""

    def test_muted_context_disables_event(self):
        """MutedContext should disable event inside context."""

        class TestEvent(Event):
            pass

        with MutedContext(TestEvent):
            assert TestEvent.enabled is False

    def test_muted_context_restores_event(self):
        """MutedContext should restore enabled status after context."""

        class TestEvent(Event):
            pass

        with MutedContext(TestEvent):
            pass
        assert TestEvent.enabled is True

    def test_muted_context_via_muted_method(self):
        """Event.muted() should return a MutedContext."""

        class TestEvent(Event):
            pass

        ctx = TestEvent.muted()
        assert isinstance(ctx, MutedContext)

    def test_muted_context_works_with_exception(self):
        """MutedContext should restore enabled even if exception occurs."""

        class TestEvent(Event):
            pass

        try:
            with TestEvent.muted():
                raise ValueError("test error")
        except ValueError:
            pass

        assert TestEvent.enabled is True


# =============================================================================
# Signal Tests
# =============================================================================


class TestSignal:
    """Tests for the Signal class."""

    def test_signal_inherits_from_event(self):
        """Signal should inherit from Event."""
        assert issubclass(Signal, Event)

    def test_signal_default_sender_is_none(self):
        """Signal without sender should have None sender."""
        signal = Signal()
        assert signal.sender is None

    def test_signal_with_sender(self):
        """Signal should store sender correctly."""
        sender = object()
        signal = Signal(sender=sender)
        assert signal.sender is sender

    def test_signal_str_representation(self):
        """Signal should have proper string representation."""
        signal = Signal(sender="test_sender")
        result = str(signal)
        assert "Signal" in result
        assert "test_sender" in result


# =============================================================================
# DataEvent Tests
# =============================================================================


class TestDataEvent:
    """Tests for the DataEvent class."""

    def test_data_event_inherits_from_signal(self):
        """DataEvent should inherit from Signal."""
        assert issubclass(DataEvent, Signal)

    def test_data_event_stores_data(self):
        """DataEvent should store data correctly."""
        data = {"key": "value"}
        event = DataEvent(data=data)
        assert event.data == data

    def test_data_event_stores_sender(self):
        """DataEvent should store sender correctly."""
        sender = object()
        event = DataEvent(data="test", sender=sender)
        assert event.sender is sender

    def test_data_event_default_sender_is_none(self):
        """DataEvent without sender should have None sender."""
        event = DataEvent(data="test")
        assert event.sender is None

    def test_data_event_with_various_data_types(self):
        """DataEvent should accept various data types."""
        # Test with different data types
        assert DataEvent(data=123).data == 123
        assert DataEvent(data="string").data == "string"
        assert DataEvent(data=[1, 2, 3]).data == [1, 2, 3]
        assert DataEvent(data=None).data is None


# =============================================================================
# EventFactory Tests
# =============================================================================


class TestEventFactory:
    """Tests for the EventFactory class."""

    def test_create_with_default_base_class(self):
        """EventFactory.create() with no args should use Event as base."""
        factory = EventFactory.create()
        new_event = factory.new("TestEvent")
        assert issubclass(new_event, Event)

    def test_create_with_custom_base_class(self):
        """EventFactory.create() should accept custom base class."""

        class CustomEvent(Event):
            custom_attr = True

        factory = EventFactory.create(CustomEvent)
        new_event = factory.new("TestEvent")
        assert issubclass(new_event, CustomEvent)
        assert new_event.custom_attr is True

    def test_create_rejects_non_event_base_class(self):
        """EventFactory.create() should reject non-Event base class."""
        with pytest.raises(TypeError):
            EventFactory.create(str)

    def test_new_creates_named_event(self):
        """factory.new() should create event with given name."""
        factory = EventFactory.create()
        new_event = factory.new("MyEvent")
        assert new_event.__name__ == "MyEvent"

    def test_new_returns_same_event_for_same_name(self):
        """factory.new() should return same class for same name."""
        factory = EventFactory.create()
        event1 = factory.new("SameEvent")
        event2 = factory.new("SameEvent")
        assert event1 is event2

    def test_new_creates_different_events_for_different_names(self):
        """factory.new() should create different classes for different names."""
        factory = EventFactory.create()
        event1 = factory.new("Event1")
        event2 = factory.new("Event2")
        assert event1 is not event2

    def test_new_without_name_creates_unique_event(self):
        """factory.new() without name should create unique event."""
        factory = EventFactory.create()
        event1 = factory.new()
        event2 = factory.new()
        assert event1 is not event2

    def test_factory_stores_created_events(self):
        """Factory should store created events in dict."""
        factory = EventFactory.create()
        event = factory.new("StoredEvent")
        assert "StoredEvent" in factory
        assert factory["StoredEvent"] is event


# =============================================================================
# Pre-built Factory Tests
# =============================================================================


class TestSignalFactory:
    """Tests for the SignalFactory."""

    def test_signal_factory_creates_signal_subclass(self):
        """SignalFactory should create Signal subclasses."""
        new_signal = SignalFactory.new("TestSignal")
        assert issubclass(new_signal, Signal)

    def test_signal_factory_same_name_returns_same_class(self):
        """SignalFactory should return same class for same name."""
        signal1 = SignalFactory.new("SameSignal")
        signal2 = SignalFactory.new("SameSignal")
        assert signal1 is signal2


class TestDataEventFactory:
    """Tests for the DataEventFactory."""

    def test_data_event_factory_creates_data_event_subclass(self):
        """DataEventFactory should create DataEvent subclasses."""
        new_event = DataEventFactory.new("TestDataEvent")
        assert issubclass(new_event, DataEvent)

    def test_data_event_factory_same_name_returns_same_class(self):
        """DataEventFactory should return same class for same name."""
        event1 = DataEventFactory.new("SameDataEvent")
        event2 = DataEventFactory.new("SameDataEvent")
        assert event1 is event2


# =============================================================================
# EventMeta Tests
# =============================================================================


class TestEventMeta:
    """Tests for the EventMeta metaclass."""

    def test_event_meta_gathers_subscriptions(self):
        """EventMeta should gather _subscriptions from methods."""
        from collections import defaultdict

        class TestEvent(Event):
            pass

        def dummy_handler(event):
            pass

        # Simulate what subscribe_method does
        dummy_handler._subscriptions = defaultdict(list)
        dummy_handler._subscriptions[TestEvent].append("mock_registry")

        class TestClass(metaclass=EventMeta):
            handler = dummy_handler

        assert hasattr(TestClass, "_subscriptions")
        assert TestEvent in TestClass._subscriptions

    def test_event_meta_empty_subscriptions(self):
        """EventMeta should create empty _subscriptions if no handlers."""

        class TestClass(metaclass=EventMeta):
            def regular_method(self):
                pass

        assert hasattr(TestClass, "_subscriptions")
        assert len(TestClass._subscriptions) == 0

    def test_event_meta_multiple_handlers(self):
        """EventMeta should gather subscriptions from multiple handlers."""
        from collections import defaultdict

        class Event1(Event):
            pass

        class Event2(Event):
            pass

        def handler1(event):
            pass

        def handler2(event):
            pass

        handler1._subscriptions = defaultdict(list)
        handler1._subscriptions[Event1].append("registry1")

        handler2._subscriptions = defaultdict(list)
        handler2._subscriptions[Event2].append("registry2")

        class TestClass(metaclass=EventMeta):
            h1 = handler1
            h2 = handler2

        assert Event1 in TestClass._subscriptions
        assert Event2 in TestClass._subscriptions
