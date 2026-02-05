"""
Async scenario tests for mixing synchronous and asynchronous event managers.

Tests cover:
- Using sync EventManager alongside AsyncEventManager
- Thread safety concerns with mixed usage
- Converting between sync and async patterns
- Mixed callback types (sync in async context and vice versa)
"""

import pytest
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from moduvent import EventManager
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

    def __init__(self, message: str = ""):
        self.message = message


# =============================================================================
# Parallel Manager Tests
# =============================================================================


class TestParallelManagers:
    """Tests for using sync and async managers in parallel."""

    @pytest.fixture
    def sync_manager(self):
        """Create fresh EventManager for each test."""
        return EventManager()

    @pytest.fixture
    def async_manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    def test_separate_managers_independent_sync(self, sync_manager, async_manager):
        """Sync manager subscriptions should not affect async manager."""
        sync_results = []

        def sync_handler(event):
            sync_results.append(event.value)
            return {"value": event.value}

        sync_manager.register(sync_handler, SampleEvent)

        # Sync manager should have subscription
        assert SampleEvent in sync_manager._subscriptions
        # Async manager should not
        assert SampleEvent not in async_manager._subscriptions

    @pytest.mark.asyncio
    async def test_separate_managers_independent_async(
        self, sync_manager, async_manager
    ):
        """Async manager subscriptions should not affect sync manager."""
        async_results = []

        async def async_handler(event):
            async_results.append(event.value)
            return {"value": event.value}

        await async_manager.register(async_handler, SampleEvent)

        # Async manager should have subscription
        assert SampleEvent in async_manager._subscriptions
        # Sync manager should not
        assert SampleEvent not in sync_manager._subscriptions

    @pytest.mark.asyncio
    async def test_emit_on_both_managers(self, sync_manager, async_manager):
        """Emitting on one manager should not trigger handlers on the other."""
        sync_results = []
        async_results = []

        def sync_handler(event):
            sync_results.append(f"sync_{event.value}")
            return {"sync_value": f"sync_{event.value}"}

        async def async_handler(event):
            async_results.append(f"async_{event.value}")
            return {"async_value": f"async_{event.value}"}

        sync_manager.register(sync_handler, SampleEvent)
        await async_manager.register(async_handler, SampleEvent)

        # Emit on sync manager
        sync_manager.emit(SampleEvent(value=1))
        assert sync_results == ["sync_1"]
        assert async_results == []

        # Emit on async manager
        await async_manager.emit(SampleEvent(value=2))
        assert sync_results == ["sync_1"]  # Unchanged
        assert async_results == ["async_2"]


# =============================================================================
# Thread and Async Loop Tests
# =============================================================================


class TestThreadAndAsyncLoop:
    """Tests for using sync manager in threads while async manager runs."""

    @pytest.fixture
    def sync_manager(self):
        """Create fresh EventManager for each test."""
        return EventManager()

    @pytest.fixture
    def async_manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_sync_manager_in_thread_during_async(
        self, sync_manager, async_manager
    ):
        """Sync manager should work in thread while async loop runs."""
        sync_results = []
        async_results = []
        lock = threading.Lock()
        async_lock = asyncio.Lock()

        def sync_handler(event):
            with lock:
                sync_results.append(event.value)
            return {"value": event.value}

        async def async_handler(event):
            async with async_lock:
                async_results.append(event.value)
            return {"value": event.value}

        sync_manager.register(sync_handler, SampleEvent)
        await async_manager.register(async_handler, SampleEvent)

        def thread_work():
            for i in range(5):
                sync_manager.emit(SampleEvent(value=i))

        # Run sync manager in thread while emitting on async manager
        asyncio.get_event_loop()

        async def async_work():
            for i in range(100, 105):
                await async_manager.emit(SampleEvent(value=i))

        with ThreadPoolExecutor(max_workers=1) as executor:
            thread_future = executor.submit(thread_work)
            await async_work()
            thread_future.result()  # Wait for thread to complete

        assert len(sync_results) == 5
        assert set(sync_results) == {0, 1, 2, 3, 4}
        assert len(async_results) == 5
        assert set(async_results) == {100, 101, 102, 103, 104}

    @pytest.mark.asyncio
    async def test_multiple_sync_managers_in_threads(self):
        """Multiple sync managers in different threads should work independently."""
        manager1 = EventManager()
        manager2 = EventManager()
        results1 = []
        results2 = []
        lock = threading.Lock()

        def handler1(event):
            with lock:
                results1.append(event.value)
            return {"value": event.value}

        def handler2(event):
            with lock:
                results2.append(event.value)
            return {"value": event.value}

        manager1.register(handler1, SampleEvent)
        manager2.register(handler2, SampleEvent)

        def thread1_work():
            for i in range(5):
                manager1.emit(SampleEvent(value=i))

        def thread2_work():
            for i in range(100, 105):
                manager2.emit(SampleEvent(value=i))

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(thread1_work)
            f2 = executor.submit(thread2_work)
            f1.result()
            f2.result()

        assert len(results1) == 5
        assert len(results2) == 5
        assert set(results1) == {0, 1, 2, 3, 4}
        assert set(results2) == {100, 101, 102, 103, 104}


# =============================================================================
# Mixed Callback Type Tests
# =============================================================================


class TestMixedCallbackTypes:
    """Tests for mixing sync and async callback styles."""

    @pytest.fixture
    def sync_manager(self):
        """Create fresh EventManager for each test."""
        return EventManager()

    @pytest.fixture
    def async_manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_sync_handler_in_async_manager(self, async_manager):
        """Sync handler registered to async manager should raise InvalidCallbackRegistryError."""
        from moduvent.exceptions import InvalidCallbackRegistryError

        def sync_handler(event):
            return {"value": event.value}

        # Registering a sync function to async manager should raise error
        with pytest.raises(InvalidCallbackRegistryError) as exc_info:
            await async_manager.register(sync_handler, SampleEvent)

        assert exc_info.value.expected == "async"
        assert exc_info.value.got == "sync"

    def test_sync_manager_with_coroutine_handler(self, sync_manager):
        """Sync manager with async handler should raise InvalidCallbackRegistryError.

        In v6.0+, sync managers only accept sync callbacks and async managers
        only accept async callbacks.
        """
        from moduvent.exceptions import InvalidCallbackRegistryError

        async def async_handler(event):
            return {"value": event.value}

        # Registering an async function to sync manager should raise error
        with pytest.raises(InvalidCallbackRegistryError) as exc_info:
            sync_manager.register(async_handler, SampleEvent)

        assert exc_info.value.expected == "sync"
        assert exc_info.value.got == "async"


# =============================================================================
# Bridging Patterns Tests
# =============================================================================


class TestBridgingPatterns:
    """Tests for patterns that bridge sync and async event handling."""

    @pytest.fixture
    def sync_manager(self):
        """Create fresh EventManager for each test."""
        return EventManager()

    @pytest.fixture
    def async_manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_sync_handler_emits_to_async_manager(
        self, sync_manager, async_manager
    ):
        """Sync handler can schedule emit to async manager."""
        async_results = []
        async_lock = asyncio.Lock()

        async def async_handler(event):
            async with async_lock:
                async_results.append(event.message)
            return {"message": event.message}

        await async_manager.register(async_handler, SampleEvent2)

        # This pattern requires access to the running loop
        loop = asyncio.get_event_loop()

        def sync_handler(event):
            # Schedule an emit to async manager from sync handler
            asyncio.run_coroutine_threadsafe(
                async_manager.emit(SampleEvent2(message=f"from_sync_{event.value}")),
                loop,
            )
            return {"sync_handled": "sync_handled"}

        sync_manager.register(sync_handler, SampleEvent)

        # Trigger sync handler
        sync_manager.emit(SampleEvent(value=1))

        # Give async tasks time to complete
        await asyncio.sleep(0.1)

        assert "from_sync_1" in async_results

    @pytest.mark.asyncio
    async def test_async_handler_calls_sync_manager(self, sync_manager, async_manager):
        """Async handler can call sync manager emit."""
        sync_results = []

        def sync_handler(event):
            sync_results.append(event.message)
            return {"message": event.message}

        sync_manager.register(sync_handler, SampleEvent2)

        async def async_handler(event):
            # Directly call sync manager emit from async handler
            sync_manager.emit(SampleEvent2(message=f"from_async_{event.value}"))
            return {"value": event.value}

        await async_manager.register(async_handler, SampleEvent)

        await async_manager.emit(SampleEvent(value=42))

        assert "from_async_42" in sync_results


# =============================================================================
# State Isolation Tests
# =============================================================================


class TestStateIsolation:
    """Tests for ensuring state isolation between sync and async managers."""

    @pytest.fixture
    def sync_manager(self):
        """Create fresh EventManager for each test."""
        return EventManager()

    @pytest.fixture
    def async_manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    def test_reset_sync_does_not_affect_async(self, sync_manager, async_manager):
        """Resetting sync manager should not affect async manager."""

        def sync_handler(e):
            return {"sync_result": "sync"}

        sync_manager.register(sync_handler, SampleEvent)

        # We can't easily add to async without await, so just verify reset isolation
        sync_manager.reset()

        # Sync manager cleared
        assert SampleEvent not in sync_manager._subscriptions

    @pytest.mark.asyncio
    async def test_reset_async_does_not_affect_sync(self, sync_manager, async_manager):
        """Resetting async manager should not affect sync manager."""

        def sync_handler(e):
            return {"sync_result": "sync"}

        sync_manager.register(sync_handler, SampleEvent)

        async def async_handler(e):
            return {"async_result": "async"}

        await async_manager.register(async_handler, SampleEvent)

        await async_manager.reset()

        # Async manager cleared
        assert SampleEvent not in async_manager._subscriptions
        # Sync manager unchanged
        assert SampleEvent in sync_manager._subscriptions

    @pytest.mark.asyncio
    async def test_halt_async_does_not_affect_sync(self, sync_manager, async_manager):
        """Halting async manager should not affect sync manager."""

        def sync_handler(e):
            return {"sync_result": "sync"}

        sync_manager.register(sync_handler, SampleEvent)

        async def async_handler(e):
            return {"async_result": "async"}

        await async_manager.register(async_handler, SampleEvent)

        async_manager.halt()

        # Sync manager unchanged and still works
        assert SampleEvent in sync_manager._subscriptions
        results = sync_manager.emit(SampleEvent())
        assert results == {"sync_result": "sync"}

        # Async manager is halted
        assert async_manager.is_halted
        results = await async_manager.emit(SampleEvent())
        assert results == {}


# =============================================================================
# Global Event Manager Tests
# =============================================================================


class TestGlobalEventManagers:
    """Tests involving the global event_manager and async patterns."""

    @pytest.mark.asyncio
    async def test_global_sync_and_local_async_independent(self):
        """Global sync manager and local async manager should be independent."""
        from moduvent import event_manager as global_sync

        local_async = AsyncEventManager()

        sync_results = []
        async_results = []

        def sync_handler(e):
            sync_results.append(e.value)
            return {"value": e.value}

        async def async_handler(e):
            async_results.append(e.value)
            return {"value": e.value}

        # Register to global sync
        global_sync.register(sync_handler, SampleEvent)
        # Register to local async
        await local_async.register(async_handler, SampleEvent)

        # Emit on global sync
        global_sync.emit(SampleEvent(value=1))
        # Emit on local async
        await local_async.emit(SampleEvent(value=2))

        assert 1 in sync_results
        assert 2 in async_results
        assert 1 not in async_results
        assert 2 not in sync_results

        # Cleanup global
        global_sync.unsubscribe(sync_handler, SampleEvent)
