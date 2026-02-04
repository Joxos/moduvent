"""
Unit tests for EventAwareBase and AsyncEventAwareBase.

Tests cover:
- EventAwareBase class functionality
- subscribe_method decorator
- Automatic registration on instantiation
- Instance method, class method, and static method subscriptions
- AsyncEventAwareBase and async create factory
"""

import pytest
from moduvent import EventManager, Event
from moduvent.moduvent import EventAwareBase
from moduvent.async_moduvent import AsyncEventManager, AsyncEventAwareBase
from moduvent.common import subscribe_method


# =============================================================================
# Test Events
# =============================================================================


class SampleEvent(Event):
    """Basic test event."""

    def __init__(self, value: int = 0):
        self.value = value


class SampleEvent2(Event):
    """Second test event."""

    def __init__(self, message: str = ""):
        self.message = message


# =============================================================================
# EventAwareBase Tests
# =============================================================================


class SampleEventAwareBase:
    """Tests for synchronous EventAwareBase."""

    def test_subclass_has_subscriptions_attribute(self):
        """EventAwareBase subclass should have _subscriptions attribute."""
        manager = EventManager()

        class TestClass(EventAwareBase):
            event_manager = manager

        assert hasattr(TestClass, "_subscriptions")

    def test_subscribe_method_decorator_adds_subscription(self):
        """@subscribe_method should add subscription info to method."""
        manager = EventManager()

        class TestClass(EventAwareBase):
            event_manager = manager

            @subscribe_method(SampleEvent)
            def handle_event(self, event: SampleEvent):
                return event.value

        assert SampleEvent in TestClass._subscriptions

    def test_instantiation_registers_handlers(self):
        """Creating instance should register handlers with event_manager."""
        manager = EventManager()

        class TestClass(EventAwareBase):
            event_manager = manager

            @subscribe_method(SampleEvent)
            def handle_event(self, event: SampleEvent):
                return event.value

        instance = TestClass()
        assert instance

        # Handler should be registered
        assert SampleEvent in manager._subscriptions
        assert len(manager._subscriptions[SampleEvent]) == 1

    def test_handler_receives_events(self):
        """Registered handler should receive emitted events."""
        manager = EventManager()
        received = []

        class TestClass(EventAwareBase):
            event_manager = manager

            @subscribe_method(SampleEvent)
            def handle_event(self, event: SampleEvent):
                received.append(event.value)
                return {"received_value": event.value}

        instance = TestClass()
        assert instance
        manager.emit(SampleEvent(value=42))

        assert received == [42]

    def test_handler_returns_value(self):
        """Handler return value should be in emit results."""
        manager = EventManager()

        class TestClass(EventAwareBase):
            event_manager = manager

            @subscribe_method(SampleEvent)
            def handle_event(self, event: SampleEvent):
                return {"value": event.value * 2}

        instance = TestClass()
        assert instance
        results = manager.emit(SampleEvent(value=21))

        assert results.get("value") == 42

    def test_multiple_handlers_in_same_class(self):
        """Multiple handlers in same class should all be registered."""
        manager = EventManager()

        class TestClass(EventAwareBase):
            event_manager = manager

            @subscribe_method(SampleEvent)
            def handle_test_event(self, event: SampleEvent):
                return "test_event"

            @subscribe_method(SampleEvent2)
            def handle_test_event2(self, event: SampleEvent2):
                return "test_event2"

        instance = TestClass()
        assert instance

        assert SampleEvent in manager._subscriptions
        assert SampleEvent2 in manager._subscriptions

    def test_handler_for_multiple_events(self):
        """Handler can subscribe to multiple event types."""
        manager = EventManager()
        received = []

        class TestClass(EventAwareBase):
            event_manager = manager

            @subscribe_method(SampleEvent, SampleEvent2)
            def handle_both(self, event):
                received.append(type(event).__name__)
                return {"event_type": type(event).__name__}

        instance = TestClass()
        assert instance

        manager.emit(SampleEvent())
        manager.emit(SampleEvent2())

        assert "SampleEvent" in received
        assert "SampleEvent2" in received

    def test_multiple_instances_register_separately(self):
        """Each instance should register its own handlers."""
        manager = EventManager()

        class TestClass(EventAwareBase):
            event_manager = manager

            def __init__(self, name):
                self.name = name
                super().__init__()

            @subscribe_method(SampleEvent)
            def handle_event(self, event: SampleEvent):
                return {f"{self.name}_result": self.name}

        instance1 = TestClass("first")
        instance2 = TestClass("second")
        assert instance1
        assert instance2

        results = manager.emit(SampleEvent())

        assert results.get("first_result") == "first"
        assert results.get("second_result") == "second"

    def test_custom_event_manager(self):
        """Can pass custom event_manager to __init__."""
        default_manager = EventManager()
        custom_manager = EventManager()

        class TestClass(EventAwareBase):
            event_manager = default_manager

            @subscribe_method(SampleEvent)
            def handle_event(self, event: SampleEvent):
                return event.value

        instance = TestClass(event_manager=custom_manager)
        assert instance

        # Should be registered with custom_manager
        assert SampleEvent in custom_manager._subscriptions


# =============================================================================
# subscribe_method Decorator Tests
# =============================================================================


class TestSubscribeMethodDecorator:
    """Tests for subscribe_method decorator."""

    def test_subscribe_method_single_event(self):
        """@subscribe_method(Event) should add subscription."""

        @subscribe_method(SampleEvent)
        def handler(self, event):
            return {"value": event.value}

        assert hasattr(handler, "_subscriptions")
        assert SampleEvent in handler._subscriptions

    def test_subscribe_method_multiple_events(self):
        """@subscribe_method(Event1, Event2) should add both."""

        @subscribe_method(SampleEvent, SampleEvent2)
        def handler(self, event):
            return {"handled": "handled"}

        assert SampleEvent in handler._subscriptions
        assert SampleEvent2 in handler._subscriptions

    def test_subscribe_method_with_condition(self):
        """@subscribe_method with condition should store condition."""

        def condition(e):
            return e.value > 0

        @subscribe_method(SampleEvent, condition)
        def handler(self, event):
            return {"value": event.value}

        assert SampleEvent in handler._subscriptions
        registry = handler._subscriptions[SampleEvent][0]
        assert len(registry.conditions) == 1

    def test_subscribe_method_preserves_function(self):
        """@subscribe_method should return original function."""

        @subscribe_method(SampleEvent)
        def handler(self, event):
            return {"value": event.value}

        # Function should be callable
        assert callable(handler)

    def test_subscribe_method_invalid_first_arg(self):
        """@subscribe_method with non-event first arg should raise."""
        with pytest.raises(ValueError):

            @subscribe_method("not_an_event")
            def handler(self, event):
                pass


# =============================================================================
# Static and Class Method Tests
# =============================================================================


class TestStaticAndClassMethods:
    """Tests for static and class method subscriptions."""

    def test_static_method_subscription(self):
        """Static method can be subscribed."""
        manager = EventManager()
        results = []

        class TestClass(EventAwareBase):
            event_manager = manager

            @subscribe_method(SampleEvent)
            @staticmethod
            def handle_event(event: SampleEvent):
                results.append(event.value)
                return {"static_result": event.value}

        instance = TestClass()
        assert instance
        manager.emit(SampleEvent(value=42))

        assert 42 in results

    def test_class_method_subscription(self):
        """Class method can be subscribed."""
        manager = EventManager()
        results = []

        class TestClass(EventAwareBase):
            event_manager = manager

            @subscribe_method(SampleEvent)
            @classmethod
            def handle_event(cls, event: SampleEvent):
                results.append(event.value)
                return {"class_method_result": event.value}

        instance = TestClass()
        assert instance
        manager.emit(SampleEvent(value=42))

        assert 42 in results


# =============================================================================
# AsyncEventAwareBase Tests
# =============================================================================


class TestAsyncEventAwareBase:
    """Tests for asynchronous AsyncEventAwareBase."""

    @pytest.mark.asyncio
    async def test_async_subclass_has_subscriptions(self):
        """AsyncEventAwareBase subclass should have _subscriptions."""
        manager = AsyncEventManager()

        class TestClass(AsyncEventAwareBase):
            event_manager = manager

        assert hasattr(TestClass, "_subscriptions")

    @pytest.mark.asyncio
    async def test_async_create_factory(self):
        """create() factory should instantiate and register."""
        manager = AsyncEventManager()

        class TestClass(AsyncEventAwareBase):
            event_manager = manager

            @subscribe_method(SampleEvent)
            async def handle_event(self, event: SampleEvent):
                return {"value": event.value}

        instance = await TestClass.create()
        assert instance

        assert SampleEvent in manager._subscriptions
        # Keep instance alive until assertion

    @pytest.mark.asyncio
    async def test_async_handler_receives_events(self):
        """Async handler should receive emitted events."""
        manager = AsyncEventManager()
        received = []

        class TestClass(AsyncEventAwareBase):
            event_manager = manager

            @subscribe_method(SampleEvent)
            async def handle_event(self, event: SampleEvent):
                received.append(event.value)
                return {"received_value": event.value}

        instance = await TestClass.create()
        await manager.emit(SampleEvent(value=42))

        assert received == [42]
        # Keep instance alive until assertion
        assert instance is not None

    @pytest.mark.asyncio
    async def test_async_handler_returns_value(self):
        """Async handler return value should be in emit results."""
        manager = AsyncEventManager()

        class TestClass(AsyncEventAwareBase):
            event_manager = manager

            @subscribe_method(SampleEvent)
            async def handle_event(self, event: SampleEvent):
                return {"value": event.value * 2}

        # Must keep reference to instance to prevent garbage collection
        instance = await TestClass.create()
        results = await manager.emit(SampleEvent(value=21))

        assert results.get("value") == 42
        # Keep instance alive until assertion
        assert instance is not None

    @pytest.mark.asyncio
    async def test_async_multiple_instances(self):
        """Multiple async instances should register separately."""
        manager = AsyncEventManager()

        class TestClass(AsyncEventAwareBase):
            event_manager = manager

            def __init__(self, event_manager=None, name=""):
                self.name = name
                super().__init__(event_manager)

            @subscribe_method(SampleEvent)
            async def handle_event(self, event: SampleEvent):
                return {f"{self.name}_result": self.name}

        instance1 = await TestClass.create(name="first")
        instance2 = await TestClass.create(name="second")
        assert instance1
        assert instance2

        results = await manager.emit(SampleEvent())

        assert results.get("first_result") == "first"
        assert results.get("second_result") == "second"


# =============================================================================
# Edge Cases
# =============================================================================


class SampleEventAwareBaseEdgeCases:
    """Edge case tests for EventAwareBase."""

    def test_class_without_handlers(self):
        """Class without handlers should still work."""
        manager = EventManager()

        class TestClass(EventAwareBase):
            event_manager = manager

            def regular_method(self):
                return "regular"

        instance = TestClass()
        assert instance

    def test_subclass_inherits_parent_subscriptions(self):
        """Subclass should work with its own subscriptions."""
        manager = EventManager()

        class ParentClass(EventAwareBase):
            event_manager = manager

            @subscribe_method(SampleEvent)
            def handle_parent(self, event):
                return {"parent_result": "parent"}

        class ChildClass(ParentClass):
            @subscribe_method(SampleEvent2)
            def handle_child(self, event):
                return {"child_result": "child"}

        instance = ChildClass()
        assert instance

        # Both should be registered
        results1 = manager.emit(SampleEvent())
        results2 = manager.emit(SampleEvent2())

        assert results1.get("parent_result") == "parent"
        assert results2.get("child_result") == "child"
