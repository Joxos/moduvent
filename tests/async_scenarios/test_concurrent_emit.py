"""
Async scenario tests for concurrent event emission.

Tests cover:
- Multiple concurrent emit() calls
- Concurrent emit with different event types
- Results collection under concurrency
- Event order and timing behavior
- Stress testing with many concurrent emits
"""

import pytest
import asyncio
import time
from moduvent.async_moduvent import AsyncEventManager
from moduvent.events import Event


# =============================================================================
# Test Events
# =============================================================================


class SampleEvent(Event):
    """Basic test event with value."""

    def __init__(self, value: int = 0):
        self.value = value


class SampleEvent2(Event):
    """Second event type for multi-event tests."""

    def __init__(self, id: int = 0):
        self.id = id


class SlowEvent(Event):
    """Event that triggers slow handlers."""

    def __init__(self, delay: float = 0.1):
        self.delay = delay


# =============================================================================
# Concurrent Emit Tests
# =============================================================================


class TestConcurrentEmit:
    """Tests for concurrent event emission."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_concurrent_emit_same_event_type(self, manager):
        """Multiple concurrent emits of same event type should all execute."""
        results = []
        lock = asyncio.Lock()

        async def handler(event):
            async with lock:
                results.append(event.value)
            return {"value": event.value}

        await manager.register(handler, SampleEvent)

        # Emit 10 events concurrently
        tasks = [
            asyncio.create_task(manager.emit(SampleEvent(value=i))) for i in range(10)
        ]
        await asyncio.gather(*tasks)

        assert len(results) == 10
        assert set(results) == set(range(10))

    @pytest.mark.asyncio
    async def test_concurrent_emit_different_event_types(self, manager):
        """Concurrent emits of different event types should all execute."""
        results1 = []
        results2 = []
        lock = asyncio.Lock()

        async def handler1(event):
            async with lock:
                results1.append(event.value)
            return {"event1_value": event.value}

        async def handler2(event):
            async with lock:
                results2.append(event.id)
            return {"event2_id": event.id}

        await manager.register(handler1, SampleEvent)
        await manager.register(handler2, SampleEvent2)

        # Emit both types concurrently
        tasks = []
        for i in range(5):
            tasks.append(asyncio.create_task(manager.emit(SampleEvent(value=i))))
            tasks.append(asyncio.create_task(manager.emit(SampleEvent2(id=i + 100))))

        await asyncio.gather(*tasks)

        assert len(results1) == 5
        assert len(results2) == 5
        assert set(results1) == set(range(5))
        assert set(results2) == set(range(100, 105))

    @pytest.mark.asyncio
    async def test_concurrent_emit_with_slow_handlers(self, manager):
        """Concurrent emits with slow handlers should complete concurrently."""
        execution_times = []

        async def slow_handler(event):
            start = time.time()
            await asyncio.sleep(event.delay)
            end = time.time()
            execution_times.append((event.delay, start, end))
            return {"delay": event.delay}

        await manager.register(slow_handler, SlowEvent)

        # Start multiple slow events concurrently
        start_time = time.time()
        tasks = [
            asyncio.create_task(manager.emit(SlowEvent(delay=0.1))) for _ in range(5)
        ]
        await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        # If running concurrently, total time should be ~0.1s, not ~0.5s
        assert total_time < 0.3, f"Expected concurrent execution, took {total_time}s"
        assert len(execution_times) == 5

    @pytest.mark.asyncio
    async def test_concurrent_emit_results_isolation(self, manager):
        """Each emit should return only its own results."""

        async def handler(event):
            await asyncio.sleep(0.01)  # Small delay to interleave
            return {"value": event.value}

        await manager.register(handler, SampleEvent)

        async def emit_and_check(value):
            results = await manager.emit(SampleEvent(value=value))
            # Each emit should get its own result
            assert results.get("value") == value
            return results

        tasks = [asyncio.create_task(emit_and_check(i)) for i in range(5)]
        all_results = await asyncio.gather(*tasks)

        # Each task should have returned results containing its value
        for i, results in enumerate(all_results):
            assert results.get("value") == i

    @pytest.mark.asyncio
    async def test_concurrent_emit_with_multiple_handlers(self, manager):
        """Concurrent emits with multiple handlers should all execute."""
        handler1_calls = []
        handler2_calls = []
        handler3_calls = []
        lock = asyncio.Lock()

        async def handler1(event):
            async with lock:
                handler1_calls.append(event.value)
            return {"h1_value": event.value}

        async def handler2(event):
            async with lock:
                handler2_calls.append(event.value)
            return {"h2_value": event.value}

        async def handler3(event):
            async with lock:
                handler3_calls.append(event.value)
            return {"h3_value": event.value}

        await manager.register(handler1, SampleEvent)
        await manager.register(handler2, SampleEvent)
        await manager.register(handler3, SampleEvent)

        tasks = [
            asyncio.create_task(manager.emit(SampleEvent(value=i))) for i in range(5)
        ]
        await asyncio.gather(*tasks)

        # Each handler should be called for each event
        assert len(handler1_calls) == 5
        assert len(handler2_calls) == 5
        assert len(handler3_calls) == 5


# =============================================================================
# Stress Tests
# =============================================================================


class TestConcurrentEmitStress:
    """Stress tests for concurrent emit."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_many_concurrent_emits(self, manager):
        """Handle many (100+) concurrent emits without issues."""
        counter = {"count": 0}
        lock = asyncio.Lock()

        async def counter_handler(event):
            async with lock:
                counter["count"] += 1
            return {"value": event.value}

        await manager.register(counter_handler, SampleEvent)

        num_emits = 100
        tasks = [
            asyncio.create_task(manager.emit(SampleEvent(value=i)))
            for i in range(num_emits)
        ]
        await asyncio.gather(*tasks)

        assert counter["count"] == num_emits

    @pytest.mark.asyncio
    async def test_rapid_fire_emits(self, manager):
        """Handle rapid sequential emits."""
        results = []
        lock = asyncio.Lock()

        async def handler(event):
            async with lock:
                results.append(event.value)
            return {"value": event.value}

        await manager.register(handler, SampleEvent)

        # Fire many emits in rapid succession
        for i in range(50):
            asyncio.create_task(manager.emit(SampleEvent(value=i)))

        # Wait for all to complete
        await asyncio.sleep(0.5)

        # All should have been processed
        assert len(results) == 50

    @pytest.mark.asyncio
    async def test_concurrent_emit_with_exception_handlers(self, manager):
        """Concurrent emits should handle handler exceptions gracefully."""
        successful_calls = []
        lock = asyncio.Lock()

        async def failing_handler(event):
            if event.value % 2 == 0:
                raise ValueError(f"Even value: {event.value}")
            async with lock:
                successful_calls.append(event.value)
            return {"value": event.value}

        async def always_succeed_handler(event):
            async with lock:
                successful_calls.append(f"success_{event.value}")
            return {"success_value": event.value}

        await manager.register(failing_handler, SampleEvent)
        await manager.register(always_succeed_handler, SampleEvent)

        tasks = [
            asyncio.create_task(manager.emit(SampleEvent(value=i))) for i in range(10)
        ]
        await asyncio.gather(*tasks)

        # always_succeed_handler should be called for all 10 events
        success_count = sum(
            1 for x in successful_calls if str(x).startswith("success_")
        )
        assert success_count == 10


# =============================================================================
# Timing and Order Tests
# =============================================================================


class TestConcurrentEmitTiming:
    """Tests for timing and ordering behavior."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_handlers_within_single_emit_run_concurrently(self, manager):
        """Multiple handlers for single emit should run concurrently."""
        start_times = []
        end_times = []
        lock = asyncio.Lock()

        async def slow_handler_1(event):
            async with lock:
                start_times.append(("h1", time.time()))
            await asyncio.sleep(0.1)
            async with lock:
                end_times.append(("h1", time.time()))
            return {"h1_result": "h1"}

        async def slow_handler_2(event):
            async with lock:
                start_times.append(("h2", time.time()))
            await asyncio.sleep(0.1)
            async with lock:
                end_times.append(("h2", time.time()))
            return {"h2_result": "h2"}

        await manager.register(slow_handler_1, SampleEvent)
        await manager.register(slow_handler_2, SampleEvent)

        start = time.time()
        await manager.emit(SampleEvent())
        total = time.time() - start

        # Both handlers should run concurrently, so total ~0.1s not ~0.2s
        assert total < 0.18, f"Handlers should be concurrent, took {total}s"

    @pytest.mark.asyncio
    async def test_emit_completes_before_next_emit_starts_processing(self, manager):
        """Each emit's handlers complete before returning."""
        order = []
        lock = asyncio.Lock()

        async def tracking_handler(event):
            async with lock:
                order.append(f"start_{event.value}")
            await asyncio.sleep(0.05)
            async with lock:
                order.append(f"end_{event.value}")
            return {"value": event.value}

        await manager.register(tracking_handler, SampleEvent)

        # Sequential emits should complete in order
        await manager.emit(SampleEvent(value=1))
        await manager.emit(SampleEvent(value=2))

        # Verify order: start_1, end_1, start_2, end_2
        assert order == ["start_1", "end_1", "start_2", "end_2"]
