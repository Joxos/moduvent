"""
Unit tests for callback expiry handling.

Tests cover:
- CallbackExpiredError exception
- Expired callback detection during emit (sync)
- Expired callback detection during emit (async)
- Automatic cleanup of expired callbacks
"""

import gc
import pytest
from moduvent import Event, CallbackExpiredError
from moduvent.moduvent import EventManager
from moduvent.async_moduvent import AsyncEventManager


# =============================================================================
# Test Events
# =============================================================================


class SampleEvent(Event):
    """Basic test event."""

    def __init__(self, value: int = 0):
        self.value = value


# =============================================================================
# CallbackExpiredError Tests
# =============================================================================


class TestCallbackExpiredError:
    """Tests for CallbackExpiredError exception."""

    def test_creates_with_event_type_and_callback_info(self):
        """Should create exception with event type and callback info."""
        error = CallbackExpiredError(SampleEvent, "test_callback")
        assert error.event_type is SampleEvent
        assert error.callback_info == "test_callback"

    def test_message_contains_event_name(self):
        """Exception message should contain event type name."""
        error = CallbackExpiredError(SampleEvent, "test_callback")
        assert "SampleEvent" in str(error)

    def test_message_contains_callback_info(self):
        """Exception message should contain callback info."""
        error = CallbackExpiredError(SampleEvent, "my_handler")
        assert "my_handler" in str(error)

    def test_message_contains_helpful_guidance(self):
        """Exception message should contain guidance for fixing the issue."""
        error = CallbackExpiredError(SampleEvent, "test_callback")
        message = str(error)
        assert "garbage collected" in message
        assert "unsubscribe" in message.lower()

    def test_inherits_from_runtime_error(self):
        """CallbackExpiredError should inherit from RuntimeError."""
        error = CallbackExpiredError(SampleEvent, "test_callback")
        assert isinstance(error, RuntimeError)


# =============================================================================
# Sync EventManager Expired Callback Tests
# =============================================================================


class TestSyncExpiredCallbackHandling:
    """Tests for expired callback handling in sync EventManager."""

    def test_expired_callback_skipped_during_emit(self):
        """Expired callbacks should be skipped during emit."""
        manager = EventManager()
        results = []

        # Create a callback that will be garbage collected
        def create_local_callback():
            def local_handler(event):
                results.append("local")
                return {"local": True}

            manager.register(local_handler, SampleEvent)

        # Also register a persistent callback
        def persistent_handler(event):
            results.append("persistent")
            return {"persistent": True}

        manager.register(persistent_handler, SampleEvent)
        create_local_callback()

        # Force garbage collection to clear the local callback
        gc.collect()

        # Emit should still work, skipping the expired callback
        emit_results = manager.emit(SampleEvent(value=42))

        # The persistent handler should have been called
        assert "persistent" in results
        assert emit_results.get("persistent") is True

    def test_expired_callback_cleaned_up_after_emit(self):
        """Expired callbacks should be removed from subscriptions after emit."""
        manager = EventManager()

        def create_local_callback():
            def local_handler(event):
                return {"local": True}

            manager.register(local_handler, SampleEvent)

        # Create and immediately lose reference to local callback
        create_local_callback()
        initial_count = len(manager._subscriptions.get(SampleEvent, []))

        # Force garbage collection
        gc.collect()

        # Emit to trigger cleanup
        manager.emit(SampleEvent())

        # The expired callback should have been cleaned up
        final_count = len(manager._subscriptions.get(SampleEvent, []))
        assert final_count < initial_count

    def test_multiple_expired_callbacks_all_cleaned_up(self):
        """Multiple expired callbacks should all be cleaned up."""
        manager = EventManager()

        def create_local_callbacks():
            for i in range(5):

                def local_handler(event, idx=i):
                    return {f"local_{idx}": True}

                manager.register(local_handler, SampleEvent)

        # Register a persistent callback
        def persistent_handler(event):
            return {"persistent": True}

        manager.register(persistent_handler, SampleEvent)

        # Create local callbacks that will be garbage collected
        create_local_callbacks()
        gc.collect()

        # Emit should work and clean up expired callbacks
        results = manager.emit(SampleEvent())

        # Only the persistent handler should have produced results
        assert results == {"persistent": True}

        # Only the persistent callback should remain
        assert len(manager._subscriptions[SampleEvent]) == 1

    def test_emit_continues_after_expired_callback(self):
        """Emit should continue processing callbacks after encountering expired one."""
        manager = EventManager()
        call_order = []

        def first_handler(event):
            call_order.append("first")
            return {"first": True}

        def create_middle_callback():
            def middle_handler(event):
                call_order.append("middle")
                return {"middle": True}

            manager.register(middle_handler, SampleEvent)

        def last_handler(event):
            call_order.append("last")
            return {"last": True}

        manager.register(first_handler, SampleEvent)
        create_middle_callback()
        manager.register(last_handler, SampleEvent)

        gc.collect()

        results = manager.emit(SampleEvent())

        # First and last should have been called
        assert "first" in call_order
        assert "last" in call_order
        assert results.get("first") is True
        assert results.get("last") is True


# =============================================================================
# Async EventManager Expired Callback Tests
# =============================================================================


class TestAsyncExpiredCallbackHandling:
    """Tests for expired callback handling in async AsyncEventManager."""

    @pytest.mark.asyncio
    async def test_async_expired_callback_skipped_during_emit(self):
        """Expired callbacks should be skipped during async emit."""
        manager = AsyncEventManager()
        results = []

        # Create a callback that will be garbage collected
        async def create_local_callback():
            async def local_handler(event):
                results.append("local")
                return {"local": True}

            await manager.register(local_handler, SampleEvent)

        # Also register a persistent callback
        async def persistent_handler(event):
            results.append("persistent")
            return {"persistent": True}

        await manager.register(persistent_handler, SampleEvent)
        await create_local_callback()

        # Force garbage collection
        gc.collect()

        # Emit should still work
        emit_results = await manager.emit(SampleEvent(value=42))

        assert "persistent" in results
        assert emit_results.get("persistent") is True

    @pytest.mark.asyncio
    async def test_async_expired_callback_cleaned_up(self):
        """Expired callbacks should be removed from async subscriptions after emit."""
        manager = AsyncEventManager()

        async def create_local_callback():
            async def local_handler(event):
                return {"local": True}

            await manager.register(local_handler, SampleEvent)

        await create_local_callback()
        initial_count = len(manager._subscriptions.get(SampleEvent, []))

        gc.collect()

        await manager.emit(SampleEvent())

        final_count = len(manager._subscriptions.get(SampleEvent, []))
        assert final_count < initial_count

    @pytest.mark.asyncio
    async def test_async_emit_continues_after_expired_callback(self):
        """Async emit should continue processing after encountering expired callback."""
        manager = AsyncEventManager()
        call_order = []

        async def first_handler(event):
            call_order.append("first")
            return {"first": True}

        async def create_middle_callback():
            async def middle_handler(event):
                call_order.append("middle")
                return {"middle": True}

            await manager.register(middle_handler, SampleEvent)

        async def last_handler(event):
            call_order.append("last")
            return {"last": True}

        await manager.register(first_handler, SampleEvent)
        await create_middle_callback()
        await manager.register(last_handler, SampleEvent)

        gc.collect()

        results = await manager.emit(SampleEvent())

        assert "first" in call_order
        assert "last" in call_order
        assert results.get("first") is True
        assert results.get("last") is True


# =============================================================================
# Bound Method Expiry Tests
# =============================================================================


class TestBoundMethodExpiry:
    """Tests for bound method callback expiry."""

    def test_bound_method_expires_when_object_deleted(self):
        """Bound method callbacks should expire when their object is deleted."""
        manager = EventManager()
        results = []

        class Handler:
            def handle(self, event):
                results.append("handler_method")
                return {"method": True}

        def create_handler_instance():
            handler = Handler()
            manager.register(handler.handle, SampleEvent)

        # Persistent handler
        def persistent_handler(event):
            results.append("persistent")
            return {"persistent": True}

        manager.register(persistent_handler, SampleEvent)
        create_handler_instance()

        gc.collect()

        emit_results = manager.emit(SampleEvent())

        # Only the persistent handler should have been called
        assert "persistent" in results
        assert "handler_method" not in results
        assert emit_results == {"persistent": True}

    @pytest.mark.asyncio
    async def test_async_bound_method_expires_when_object_deleted(self):
        """Async bound method callbacks should expire when their object is deleted."""
        manager = AsyncEventManager()
        results = []

        class AsyncHandler:
            async def handle(self, event):
                results.append("handler_method")
                return {"method": True}

        async def create_handler_instance():
            handler = AsyncHandler()
            await manager.register(handler.handle, SampleEvent)

        async def persistent_handler(event):
            results.append("persistent")
            return {"persistent": True}

        await manager.register(persistent_handler, SampleEvent)
        await create_handler_instance()

        gc.collect()

        emit_results = await manager.emit(SampleEvent())

        assert "persistent" in results
        assert "handler_method" not in results
        assert emit_results == {"persistent": True}


# =============================================================================
# Edge Cases
# =============================================================================


class TestExpiredCallbackEdgeCases:
    """Edge cases for expired callback handling."""

    def test_all_callbacks_expired(self):
        """Emit should return empty dict when all callbacks are expired."""
        manager = EventManager()

        def create_callbacks():
            for i in range(3):

                def handler(event, idx=i):
                    return {f"result_{idx}": True}

                manager.register(handler, SampleEvent)

        create_callbacks()
        gc.collect()

        results = manager.emit(SampleEvent())

        assert results == {}

    def test_no_expired_callbacks_no_cleanup(self):
        """When no callbacks expired, no cleanup should occur."""
        manager = EventManager()

        def handler1(event):
            return {"handler1": True}

        def handler2(event):
            return {"handler2": True}

        manager.register(handler1, SampleEvent)
        manager.register(handler2, SampleEvent)

        initial_count = len(manager._subscriptions[SampleEvent])
        results = manager.emit(SampleEvent())
        final_count = len(manager._subscriptions[SampleEvent])

        assert initial_count == final_count == 2
        assert results == {"handler1": True, "handler2": True}

    @pytest.mark.asyncio
    async def test_async_all_callbacks_expired(self):
        """Async emit should return empty dict when all callbacks are expired."""
        manager = AsyncEventManager()

        async def create_callbacks():
            for i in range(3):

                async def handler(event, idx=i):
                    return {f"result_{idx}": True}

                await manager.register(handler, SampleEvent)

        await create_callbacks()
        gc.collect()

        results = await manager.emit(SampleEvent())

        assert results == {}
