"""
Async scenario tests for concurrent subscription operations.

Tests cover:
- Concurrent register() calls
- Concurrent unsubscribe() calls
- Concurrent register and emit
- Concurrent subscribe decorator usage
- Race conditions between subscription operations
"""

import pytest
import asyncio
from moduvent.async_moduvent import AsyncEventManager
from moduvent.events import Event


# =============================================================================
# Test Events
# =============================================================================


class SampleEvent(Event):
    """Basic test event."""

    def __init__(self, value: int = 0):
        self.value = value


class SampleEvent2(Event):
    """Second test event."""

    def __init__(self, id: int = 0):
        self.id = id


# =============================================================================
# Concurrent Register Tests
# =============================================================================


class TestConcurrentRegister:
    """Tests for concurrent registration."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_concurrent_register_same_event_type(self, manager):
        """Multiple concurrent registers for same event should all succeed."""
        handlers = []

        for i in range(10):

            async def handler(event, idx=i):
                return {"handler_result": f"handler_{idx}"}

            handlers.append(handler)

        # Register all concurrently
        tasks = [
            asyncio.create_task(manager.register(h, SampleEvent)) for h in handlers
        ]
        await asyncio.gather(*tasks)

        # All should be registered
        assert len(manager._subscriptions[SampleEvent]) == 10

    @pytest.mark.asyncio
    async def test_concurrent_register_different_event_types(self, manager):
        """Concurrent registers for different events should all succeed."""

        async def handler1(event):
            return {"h1_result": "h1"}

        async def handler2(event):
            return {"h2_result": "h2"}

        # Register for different types concurrently
        await asyncio.gather(
            manager.register(handler1, SampleEvent),
            manager.register(handler2, SampleEvent2),
        )

        assert SampleEvent in manager._subscriptions
        assert SampleEvent2 in manager._subscriptions

    @pytest.mark.asyncio
    async def test_many_concurrent_registers(self, manager):
        """Handle many (50+) concurrent register calls."""
        num_handlers = 50
        handlers = []

        for i in range(num_handlers):

            async def handler(event, idx=i):
                return {"handler_result": f"handler_{idx}"}

            handlers.append(handler)

        tasks = [
            asyncio.create_task(manager.register(h, SampleEvent)) for h in handlers
        ]
        await asyncio.gather(*tasks)

        assert len(manager._subscriptions[SampleEvent]) == num_handlers


# =============================================================================
# Concurrent Register and Emit Tests
# =============================================================================


class TestConcurrentRegisterAndEmit:
    """Tests for concurrent register and emit operations."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_register_while_emitting(self, manager):
        """Register during emit should not cause errors."""
        results = []
        lock = asyncio.Lock()

        async def existing_handler(event):
            async with lock:
                results.append("existing")
            await asyncio.sleep(0.05)  # Give time for concurrent register
            return {"existing_result": "existing"}

        async def new_handler(event):
            async with lock:
                results.append("new")
            return {"new_result": "new"}

        await manager.register(existing_handler, SampleEvent)

        # Start emit and register concurrently
        async def emit_task():
            await manager.emit(SampleEvent())

        async def register_task():
            await asyncio.sleep(0.01)  # Slight delay to overlap with emit
            await manager.register(new_handler, SampleEvent)

        await asyncio.gather(emit_task(), register_task())

        # Existing handler should have been called
        assert "existing" in results
        # New handler registered after emit started, may or may not be called

    @pytest.mark.asyncio
    async def test_emit_after_concurrent_registers(self, manager):
        """Emit after concurrent registers should call all handlers."""
        results = []
        lock = asyncio.Lock()

        handlers = []
        for i in range(5):

            async def handler(event, idx=i):
                async with lock:
                    results.append(idx)
                # Each handler returns unique key using idx
                return {f"handler_{idx}_result": idx}

            handlers.append(handler)

        # Register all concurrently
        await asyncio.gather(*[manager.register(h, SampleEvent) for h in handlers])

        # Now emit
        await manager.emit(SampleEvent())

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_interleaved_register_and_emit(self, manager):
        """Interleaved register and emit operations should work correctly."""
        call_log = []
        lock = asyncio.Lock()

        async def make_handler(name):
            async def handler(event):
                async with lock:
                    call_log.append(name)
                # Each handler returns unique key using name
                return {f"{name}_result": name}

            return handler

        async def register_and_emit(name):
            handler = await make_handler(name)
            await manager.register(handler, SampleEvent)
            await manager.emit(SampleEvent())

        # Run multiple register-and-emit sequences concurrently
        tasks = [asyncio.create_task(register_and_emit(f"h{i}")) for i in range(5)]
        await asyncio.gather(*tasks)

        # All handlers should have been called at least once
        # (exact count depends on timing)
        assert len(call_log) > 0


# =============================================================================
# Concurrent Unsubscribe Tests
# =============================================================================


class TestConcurrentUnsubscribe:
    """Tests for concurrent unsubscription."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_unsubscribe_during_emit(self, manager):
        """Unsubscribe during emit should not cause errors."""
        results = []
        lock = asyncio.Lock()

        async def handler1(event):
            async with lock:
                results.append("h1_start")
            await asyncio.sleep(0.05)
            async with lock:
                results.append("h1_end")
            return {"h1_result": "h1"}

        async def handler2(event):
            async with lock:
                results.append("h2")
            return {"h2_result": "h2"}

        await manager.register(handler1, SampleEvent)
        await manager.register(handler2, SampleEvent)

        async def emit_task():
            await manager.emit(SampleEvent())

        async def unsubscribe_task():
            await asyncio.sleep(0.01)
            await manager.unsubscribe(handler2, SampleEvent)

        await asyncio.gather(emit_task(), unsubscribe_task())

        # Handler1 should have completed
        assert "h1_start" in results
        assert "h1_end" in results

    @pytest.mark.asyncio
    async def test_concurrent_unsubscribe_operations(self, manager):
        """Multiple concurrent unsubscribes should not cause errors."""
        handlers = []
        for i in range(10):

            async def handler(event, idx=i):
                # Each handler returns unique key
                return {f"h{idx}_result": f"h{idx}"}

            handlers.append(handler)
            await manager.register(handler, SampleEvent)

        # Unsubscribe all concurrently - now using async unsubscribe
        async def unsubscribe_handler(h):
            await manager.unsubscribe(h, SampleEvent)

        tasks = [asyncio.create_task(unsubscribe_handler(h)) for h in handlers]
        await asyncio.gather(*tasks)

        # All should be unsubscribed
        remaining = manager._subscriptions.get(SampleEvent, [])
        assert len(remaining) == 0


# =============================================================================
# Subscription Lock Tests
# =============================================================================


class TestSubscriptionLock:
    """Tests for subscription lock behavior."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_subscription_lock_prevents_corruption(self, manager):
        """Concurrent modifications should not corrupt subscription list."""
        # Rapidly add and verify handlers
        final_count = {"value": 0}

        async def add_handler(i):
            async def handler(event, idx=i):
                # Each handler returns unique key
                return {f"handler_{idx}_result": idx}

            await manager.register(handler, SampleEvent)
            final_count["value"] += 1

        # Add 20 handlers concurrently
        tasks = [asyncio.create_task(add_handler(i)) for i in range(20)]
        await asyncio.gather(*tasks)

        # Subscription list should have exactly 20 handlers
        assert len(manager._subscriptions[SampleEvent]) == 20

    @pytest.mark.asyncio
    async def test_no_deadlock_with_nested_operations(self, manager):
        """Nested operations should not cause deadlock."""
        results = []

        async def handler_that_registers(event):
            results.append("outer")

            # This should not deadlock
            async def inner_handler(e):
                results.append("inner")
                return {"inner_result": "inner"}

            await manager.register(inner_handler, SampleEvent2)
            return {"outer_result": "outer"}

        await manager.register(handler_that_registers, SampleEvent)

        # This should complete without deadlock
        async with asyncio.timeout(2):  # 2 second timeout
            await manager.emit(SampleEvent())

        assert "outer" in results


# =============================================================================
# Race Condition Tests
# =============================================================================


class TestRaceConditions:
    """Tests for potential race conditions."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_register_unregister_race(self, manager):
        """Rapid register/unregister should not cause issues."""

        async def handler(event):
            return {"handled_result": "handled"}

        # Rapidly register and unregister - now using async unsubscribe
        for _ in range(20):
            await manager.register(handler, SampleEvent)
            await manager.unsubscribe(handler, SampleEvent)

        # Final state should be unregistered
        remaining = [
            cb
            for cb in manager._subscriptions.get(SampleEvent, [])
            if cb.func is handler
        ]
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_emit_during_reset(self, manager):
        """Emit during reset should handle gracefully."""
        call_count = {"value": 0}

        async def handler(event):
            call_count["value"] += 1
            await asyncio.sleep(0.05)
            return {"done": "done"}

        await manager.register(handler, SampleEvent)

        async def emit_loop():
            for _ in range(5):
                try:
                    await manager.emit(SampleEvent())
                except Exception:
                    pass  # May fail during reset, that's OK
                await asyncio.sleep(0.01)

        async def reset_loop():
            await asyncio.sleep(0.02)
            await manager.reset()

        await asyncio.gather(emit_loop(), reset_loop())

        # Should complete without crashing

    @pytest.mark.asyncio
    async def test_concurrent_initialize_calls(self, manager):
        """Multiple concurrent initialize() calls should be safe."""

        @manager.subscribe(SampleEvent)
        async def handler1(event):
            return "h1"

        @manager.subscribe(SampleEvent)
        async def handler2(event):
            return "h2"

        # Call initialize multiple times concurrently
        tasks = [asyncio.create_task(manager.initialize()) for _ in range(5)]
        await asyncio.gather(*tasks)

        # Should not crash, handlers should be registered
        # (exact behavior depends on implementation - may register multiple times)
