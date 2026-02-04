"""
Async scenario tests for TaskGroup behavior in callback execution.

Tests cover:
- TaskGroup concurrent callback execution
- Exception handling within TaskGroup
- Callback execution order/parallelism
- Long-running callback handling
- TaskGroup cancellation behavior
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
    """Basic test event."""

    def __init__(self, value: int = 0):
        self.value = value


# =============================================================================
# TaskGroup Concurrent Execution Tests
# =============================================================================


class TestTaskGroupConcurrency:
    """Tests for TaskGroup concurrent callback execution."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_callbacks_run_in_taskgroup(self, manager):
        """Callbacks should run concurrently within TaskGroup."""
        timing = []
        lock = asyncio.Lock()

        async def callback1(event):
            async with lock:
                timing.append(("c1_start", time.time()))
            await asyncio.sleep(0.1)
            async with lock:
                timing.append(("c1_end", time.time()))
            return {"c1_result": "c1"}

        async def callback2(event):
            async with lock:
                timing.append(("c2_start", time.time()))
            await asyncio.sleep(0.1)
            async with lock:
                timing.append(("c2_end", time.time()))
            return {"c2_result": "c2"}

        async def callback3(event):
            async with lock:
                timing.append(("c3_start", time.time()))
            await asyncio.sleep(0.1)
            async with lock:
                timing.append(("c3_end", time.time()))
            return {"c3_result": "c3"}

        await manager.register(callback1, SampleEvent)
        await manager.register(callback2, SampleEvent)
        await manager.register(callback3, SampleEvent)

        start = time.time()
        await manager.emit(SampleEvent())
        total = time.time() - start

        # All 3 callbacks sleeping 0.1s should complete in ~0.1s if concurrent
        assert total < 0.2, f"Callbacks should run concurrently, took {total}s"

        # All starts should happen before all ends (roughly)
        start_times = [t for name, t in timing if "start" in name]
        end_times = [t for name, t in timing if "end" in name]
        assert max(start_times) < min(end_times), (
            "All callbacks should start before any ends"
        )

    @pytest.mark.asyncio
    async def test_all_callback_results_collected(self, manager):
        """TaskGroup should collect all callback results."""

        async def callback1(event):
            await asyncio.sleep(0.02)
            return {"result1": "result1"}

        async def callback2(event):
            await asyncio.sleep(0.01)
            return {"result2": "result2"}

        async def callback3(event):
            await asyncio.sleep(0.03)
            return {"result3": "result3"}

        await manager.register(callback1, SampleEvent)
        await manager.register(callback2, SampleEvent)
        await manager.register(callback3, SampleEvent)

        results = await manager.emit(SampleEvent())

        assert len(results) == 3
        assert results.get("result1") == "result1"
        assert results.get("result2") == "result2"
        assert results.get("result3") == "result3"


# =============================================================================
# Exception Handling Tests
# =============================================================================


class TestTaskGroupExceptionHandling:
    """Tests for exception handling within TaskGroup."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_single_callback_exception_doesnt_stop_others(self, manager):
        """One failing callback should not prevent others from completing."""
        results = []
        lock = asyncio.Lock()

        async def failing_callback(event):
            await asyncio.sleep(0.01)
            raise ValueError("Intentional failure")

        async def successful_callback1(event):
            await asyncio.sleep(0.02)
            async with lock:
                results.append("success1")
            return {"success1": "success1"}

        async def successful_callback2(event):
            await asyncio.sleep(0.02)
            async with lock:
                results.append("success2")
            return {"success2": "success2"}

        await manager.register(failing_callback, SampleEvent)
        await manager.register(successful_callback1, SampleEvent)
        await manager.register(successful_callback2, SampleEvent)

        # Should not raise despite one callback failing
        await manager.emit(SampleEvent())

        # Successful callbacks should complete
        assert "success1" in results
        assert "success2" in results

    @pytest.mark.asyncio
    async def test_multiple_callback_exceptions(self, manager):
        """Multiple failing callbacks should all be handled."""
        success_count = {"value": 0}
        lock = asyncio.Lock()

        async def failing_callback1(event):
            raise ValueError("Failure 1")

        async def failing_callback2(event):
            raise RuntimeError("Failure 2")

        async def successful_callback(event):
            async with lock:
                success_count["value"] += 1
            return {"success": "success"}

        await manager.register(failing_callback1, SampleEvent)
        await manager.register(successful_callback, SampleEvent)
        await manager.register(failing_callback2, SampleEvent)

        # Should complete without propagating exceptions
        await manager.emit(SampleEvent())

        assert success_count["value"] == 1

    @pytest.mark.asyncio
    async def test_exception_in_slow_callback(self, manager):
        """Exception after delay should not affect other callbacks."""
        results = []
        lock = asyncio.Lock()

        async def slow_failing_callback(event):
            await asyncio.sleep(0.05)
            raise ValueError("Delayed failure")

        async def fast_callback(event):
            async with lock:
                results.append("fast")
            return {"fast_result": "fast"}

        async def medium_callback(event):
            await asyncio.sleep(0.03)
            async with lock:
                results.append("medium")
            return {"medium_result": "medium"}

        await manager.register(slow_failing_callback, SampleEvent)
        await manager.register(fast_callback, SampleEvent)
        await manager.register(medium_callback, SampleEvent)

        await manager.emit(SampleEvent())

        assert "fast" in results
        assert "medium" in results


# =============================================================================
# Long-Running Callback Tests
# =============================================================================


class TestLongRunningCallbacks:
    """Tests for long-running callback handling."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_long_callback_doesnt_block_short_ones(self, manager):
        """Short callbacks should complete while long one is running."""
        completion_order = []
        lock = asyncio.Lock()

        async def long_callback(event):
            await asyncio.sleep(0.2)
            async with lock:
                completion_order.append("long")
            return {"long_result": "long"}

        async def short_callback1(event):
            await asyncio.sleep(0.01)
            async with lock:
                completion_order.append("short1")
            return {"short1_result": "short1"}

        async def short_callback2(event):
            await asyncio.sleep(0.02)
            async with lock:
                completion_order.append("short2")
            return {"short2_result": "short2"}

        await manager.register(long_callback, SampleEvent)
        await manager.register(short_callback1, SampleEvent)
        await manager.register(short_callback2, SampleEvent)

        await manager.emit(SampleEvent())

        # Short callbacks should complete first
        assert completion_order.index("short1") < completion_order.index("long")
        assert completion_order.index("short2") < completion_order.index("long")

    @pytest.mark.asyncio
    async def test_cpu_bound_simulation_with_sleep(self, manager):
        """Simulated CPU-bound work (with sleeps) should not block others."""
        results = []
        lock = asyncio.Lock()

        async def cpu_like_callback(event):
            # Simulate work with periodic yields
            for _ in range(5):
                await asyncio.sleep(0.02)
            async with lock:
                results.append("cpu_like")
            return {"cpu_like_result": "cpu_like"}

        async def io_callback(event):
            await asyncio.sleep(0.01)
            async with lock:
                results.append("io")
            return {"io_result": "io"}

        await manager.register(cpu_like_callback, SampleEvent)
        await manager.register(io_callback, SampleEvent)

        start = time.time()
        await manager.emit(SampleEvent())
        time.time() - start

        assert "cpu_like" in results
        assert "io" in results
        # IO callback should have completed during CPU-like callback's sleeps


# =============================================================================
# Callback Completion Order Tests
# =============================================================================


class TestCallbackCompletionOrder:
    """Tests for callback completion ordering."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_completion_order_not_guaranteed(self, manager):
        """Callbacks may complete in any order."""
        completion_order = []
        lock = asyncio.Lock()

        async def callback_a(event):
            await asyncio.sleep(0.03)
            async with lock:
                completion_order.append("a")
            return {"a_result": "a"}

        async def callback_b(event):
            await asyncio.sleep(0.01)
            async with lock:
                completion_order.append("b")
            return {"b_result": "b"}

        async def callback_c(event):
            await asyncio.sleep(0.02)
            async with lock:
                completion_order.append("c")
            return {"c_result": "c"}

        await manager.register(callback_a, SampleEvent)
        await manager.register(callback_b, SampleEvent)
        await manager.register(callback_c, SampleEvent)

        await manager.emit(SampleEvent())

        # All should complete
        assert set(completion_order) == {"a", "b", "c"}
        # Order should be b, c, a based on sleep times
        assert completion_order == ["b", "c", "a"]

    @pytest.mark.asyncio
    async def test_zero_delay_callbacks_start_together(self, manager):
        """Callbacks with no delay should start nearly simultaneously."""
        start_times = []
        lock = asyncio.Lock()

        # Keep strong references to callbacks to prevent garbage collection
        callbacks = []

        for i in range(5):
            # Create callback directly with closure over i
            async def callback(event, idx=i):
                async with lock:
                    start_times.append((idx, time.time()))
                return {f"callback_{idx}_result": idx}

            callbacks.append(callback)
            await manager.register(callback, SampleEvent)

        await manager.emit(SampleEvent())

        # All start times should be very close (within 50ms)
        times = [t for _, t in start_times]
        assert max(times) - min(times) < 0.05


# =============================================================================
# TaskGroup Behavior Edge Cases
# =============================================================================


class TestTaskGroupEdgeCases:
    """Edge cases for TaskGroup behavior."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_empty_taskgroup(self, manager):
        """Emit with no callbacks should work."""
        # No registered callbacks
        await manager.emit(SampleEvent())
        # Should not crash

    @pytest.mark.asyncio
    async def test_single_callback_taskgroup(self, manager):
        """TaskGroup with single callback should work."""

        async def single_callback(event):
            return {"single_result": "single"}

        await manager.register(single_callback, SampleEvent)
        results = await manager.emit(SampleEvent())

        assert results.get("single_result") == "single"

    @pytest.mark.asyncio
    async def test_callback_returning_none(self, manager):
        """Callback returning None should be handled."""

        async def none_callback(event):
            return None

        async def value_callback(event):
            return {"value_result": "value"}

        await manager.register(none_callback, SampleEvent)
        await manager.register(value_callback, SampleEvent)

        results = await manager.emit(SampleEvent())

        assert results.get("value_result") == "value"

    @pytest.mark.asyncio
    async def test_callback_with_internal_cancellation(self, manager):
        """Callback that internally handles CancelledError should work."""
        results = []
        lock = asyncio.Lock()

        async def self_cancelling_callback(event):
            try:
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                async with lock:
                    results.append("cancelled")
                raise
            async with lock:
                results.append("completed")
            return {"completed_result": "completed"}

        async def normal_callback(event):
            await asyncio.sleep(0.01)
            async with lock:
                results.append("normal")
            return {"normal_result": "normal"}

        await manager.register(self_cancelling_callback, SampleEvent)
        await manager.register(normal_callback, SampleEvent)

        await manager.emit(SampleEvent())

        assert "normal" in results
        assert "completed" in results
