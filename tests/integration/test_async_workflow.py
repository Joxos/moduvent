"""
Integration tests for complete asynchronous event workflows.

Tests cover:
- Full async registration -> emit -> handler workflow
- Async event propagation through multiple handlers
- Async event chain scenarios (handler emitting another event)
- Async result collection patterns
- AsyncEventAwareBase integration
- Concurrent workflow execution
"""

import pytest
import asyncio
from moduvent.async_moduvent import AsyncEventManager, AsyncEventAwareBase
from moduvent.events import Event
from moduvent.common import subscribe_method
from moduvent import signal, data_event


# =============================================================================
# Test Events
# =============================================================================


class StartEvent(Event):
    """Event signaling workflow start."""

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id


class ProcessEvent(Event):
    """Event for processing step."""

    def __init__(self, data: dict, step: int = 1):
        self.data = data
        self.step = step


class CompleteEvent(Event):
    """Event signaling completion."""

    def __init__(self, workflow_id: str, result: str = ""):
        self.workflow_id = workflow_id
        self.result = result


class AsyncTaskEvent(Event):
    """Event for async task execution."""

    def __init__(self, task_id: str, duration: float = 0.01):
        self.task_id = task_id
        self.duration = duration


# =============================================================================
# Basic Async Workflow Tests
# =============================================================================


class TestBasicAsyncWorkflow:
    """Tests for basic asynchronous event workflows."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_simple_async_workflow(self, manager):
        """Simple async start -> process -> complete workflow."""
        log = []

        async def on_start(event):
            log.append(f"started: {event.workflow_id}")
            return {"status": "started"}

        async def on_process(event):
            await asyncio.sleep(0.001)  # Simulate async work
            log.append(f"processing step {event.step}")
            return {"status": f"step_{event.step}"}

        async def on_complete(event):
            log.append(f"completed: {event.workflow_id} with {event.result}")
            return {"status": "completed"}

        await manager.register(on_start, StartEvent)
        await manager.register(on_process, ProcessEvent)
        await manager.register(on_complete, CompleteEvent)

        # Execute workflow
        await manager.emit(StartEvent(workflow_id="wf-001"))
        await manager.emit(ProcessEvent(data={"key": "value"}, step=1))
        await manager.emit(ProcessEvent(data={"key": "value2"}, step=2))
        await manager.emit(CompleteEvent(workflow_id="wf-001", result="success"))

        assert log == [
            "started: wf-001",
            "processing step 1",
            "processing step 2",
            "completed: wf-001 with success",
        ]

    @pytest.mark.asyncio
    async def test_async_event_chain_workflow(self, manager):
        """Async handler that emits another event creating a chain."""
        log = []

        async def on_start(event):
            log.append(f"start: {event.workflow_id}")
            # Emit process event from start handler
            await manager.emit(ProcessEvent(data={"auto": True}, step=1))
            return {"status": "started"}

        async def on_process(event):
            log.append(f"process: step {event.step}")
            if event.step < 3:
                # Chain to next step
                await manager.emit(ProcessEvent(data=event.data, step=event.step + 1))
            else:
                # Chain to complete
                await manager.emit(CompleteEvent(workflow_id="auto", result="done"))
            return {"status": f"processed_{event.step}"}

        async def on_complete(event):
            log.append(f"complete: {event.result}")
            return {"status": "completed"}

        await manager.register(on_start, StartEvent)
        await manager.register(on_process, ProcessEvent)
        await manager.register(on_complete, CompleteEvent)

        # Single emit triggers chain
        await manager.emit(StartEvent(workflow_id="chain-001"))

        assert log == [
            "start: chain-001",
            "process: step 1",
            "process: step 2",
            "process: step 3",
            "complete: done",
        ]

    @pytest.mark.asyncio
    async def test_concurrent_handlers_workflow(self, manager):
        """Multiple async handlers should run concurrently."""
        execution_log = []
        lock = asyncio.Lock()

        async def slow_handler_1(event):
            async with lock:
                execution_log.append(f"h1_start_{event.task_id}")
            await asyncio.sleep(event.duration)
            async with lock:
                execution_log.append(f"h1_end_{event.task_id}")
            return {"h1_result": "h1"}

        async def slow_handler_2(event):
            async with lock:
                execution_log.append(f"h2_start_{event.task_id}")
            await asyncio.sleep(event.duration)
            async with lock:
                execution_log.append(f"h2_end_{event.task_id}")
            return {"h2_result": "h2"}

        await manager.register(slow_handler_1, AsyncTaskEvent)
        await manager.register(slow_handler_2, AsyncTaskEvent)

        import time

        start = time.time()
        await manager.emit(AsyncTaskEvent(task_id="t1", duration=0.1))
        elapsed = time.time() - start

        # Both handlers should run concurrently (~0.1s not ~0.2s)
        assert elapsed < 0.18, f"Expected concurrent execution, took {elapsed}s"

        # Both handlers should have started and completed
        assert "h1_start_t1" in execution_log
        assert "h2_start_t1" in execution_log
        assert "h1_end_t1" in execution_log
        assert "h2_end_t1" in execution_log


# =============================================================================
# Async Result Collection Tests
# =============================================================================


class TestAsyncResultCollection:
    """Tests for async result collection patterns."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_collect_all_async_results(self, manager):
        """Collect results from all async handlers."""

        async def handler1(event):
            await asyncio.sleep(0.01)
            return {"handler1_score": event.step * 10}

        async def handler2(event):
            await asyncio.sleep(0.01)
            return {"handler2_score": event.step * 100}

        async def handler3(event):
            await asyncio.sleep(0.01)
            return {"handler3_score": event.step * 1000}

        await manager.register(handler1, ProcessEvent)
        await manager.register(handler2, ProcessEvent)
        await manager.register(handler3, ProcessEvent)

        results = await manager.emit(ProcessEvent(data={}, step=5))

        assert results.get("handler1_score") == 50
        assert results.get("handler2_score") == 500
        assert results.get("handler3_score") == 5000

    @pytest.mark.asyncio
    async def test_async_results_with_exceptions(self, manager):
        """Handlers that raise exceptions shouldn't prevent other results."""

        async def good_handler(event):
            return {"good_result": "good"}

        async def bad_handler(event):
            raise ValueError("intentional error")

        async def another_good_handler(event):
            return {"another_good_result": "also_good"}

        await manager.register(good_handler, ProcessEvent)
        await manager.register(bad_handler, ProcessEvent)
        await manager.register(another_good_handler, ProcessEvent)

        results = await manager.emit(ProcessEvent(data={}, step=1))

        # Good handlers should still return results
        assert results.get("good_result") == "good"
        assert results.get("another_good_result") == "also_good"

    @pytest.mark.asyncio
    async def test_aggregate_async_results(self, manager):
        """Aggregate results from concurrent async handlers."""

        async def score_handler_1(event):
            await asyncio.sleep(0.01)  # Simulate async work
            return {"score_h1": 10, "source_h1": "h1"}

        async def score_handler_2(event):
            await asyncio.sleep(0.02)
            return {"score_h2": 20, "source_h2": "h2"}

        async def score_handler_3(event):
            await asyncio.sleep(0.01)
            return {"score_h3": 30, "source_h3": "h3"}

        await manager.register(score_handler_1, ProcessEvent)
        await manager.register(score_handler_2, ProcessEvent)
        await manager.register(score_handler_3, ProcessEvent)

        results = await manager.emit(ProcessEvent(data={}, step=1))

        # All results collected despite different completion times
        total_score = (
            results.get("score_h1", 0)
            + results.get("score_h2", 0)
            + results.get("score_h3", 0)
        )
        assert total_score == 60


# =============================================================================
# AsyncEventAwareBase Integration Tests
# =============================================================================


class TestAsyncEventAwareBaseIntegration:
    """Tests for AsyncEventAwareBase class integration."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_async_event_aware_class_workflow(self, manager):
        """AsyncEventAwareBase subclass should participate in workflows."""

        class AsyncWorkflowProcessor(AsyncEventAwareBase):
            event_manager = manager

            def __init__(self, event_manager=None):
                self.events_received = []
                super().__init__(event_manager)

            @classmethod
            async def create(cls, event_manager):
                instance = cls(event_manager)
                await instance._register()
                return instance

            @subscribe_method(StartEvent)
            async def handle_start(self, event):
                self.events_received.append(("start", event.workflow_id))
                return {"start_result": "handled_start"}

            @subscribe_method(CompleteEvent)
            async def handle_complete(self, event):
                self.events_received.append(("complete", event.workflow_id))
                return {"complete_result": "handled_complete"}

        processor = await AsyncWorkflowProcessor.create(manager)

        await manager.emit(StartEvent(workflow_id="aware-001"))
        await manager.emit(CompleteEvent(workflow_id="aware-001", result="ok"))

        assert processor.events_received == [
            ("start", "aware-001"),
            ("complete", "aware-001"),
        ]

    @pytest.mark.asyncio
    async def test_multiple_async_event_aware_instances(self, manager):
        """Multiple AsyncEventAwareBase instances should all receive events."""
        results = []
        lock = asyncio.Lock()

        class AsyncCounter(AsyncEventAwareBase):
            event_manager = manager

            def __init__(self, name, event_manager=None):
                self.name = name
                self.count = 0
                super().__init__(event_manager)

            @classmethod
            async def create(cls, name, event_manager):
                instance = cls(name, event_manager)
                await instance._register()
                return instance

            @subscribe_method(ProcessEvent)
            async def handle_process(self, event):
                async with lock:
                    self.count += 1
                    results.append(f"{self.name}_{self.count}")
                # Each instance has a unique name, so keys won't collide
                return {f"{self.name}_counted": self.count}

        counter1 = await AsyncCounter.create("c1", manager)
        counter2 = await AsyncCounter.create("c2", manager)
        counter3 = await AsyncCounter.create("c3", manager)

        for _ in range(3):
            await manager.emit(ProcessEvent(data={}, step=1))

        assert counter1.count == 3
        assert counter2.count == 3
        assert counter3.count == 3


# =============================================================================
# Subscribe Decorator Workflow Tests
# =============================================================================


class TestSubscribeDecoratorWorkflow:
    """Tests for @subscribe decorator in async workflows."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_subscribe_decorator_workflow(self, manager):
        """Full workflow using @subscribe decorator."""
        log = []

        @manager.subscribe(StartEvent)
        async def on_start(event):
            log.append(f"start: {event.workflow_id}")
            return {"start_result": "started"}

        @manager.subscribe(ProcessEvent)
        async def on_process(event):
            log.append(f"process: {event.step}")
            return {"process_result": f"step_{event.step}"}

        @manager.subscribe(CompleteEvent)
        async def on_complete(event):
            log.append(f"complete: {event.result}")
            return {"complete_result": "completed"}

        # Initialize to activate subscriptions
        await manager.initialize()

        await manager.emit(StartEvent(workflow_id="dec-001"))
        await manager.emit(ProcessEvent(data={}, step=1))
        await manager.emit(CompleteEvent(workflow_id="dec-001", result="ok"))

        assert log == ["start: dec-001", "process: 1", "complete: ok"]

    @pytest.mark.asyncio
    async def test_mixed_decorator_and_register(self, manager):
        """Mix @subscribe decorator with direct register."""
        log = []
        lock = asyncio.Lock()

        @manager.subscribe(StartEvent)
        async def decorated_handler(event):
            async with lock:
                log.append("decorated")
            return {"decorated_result": "decorated"}

        async def direct_handler(event):
            async with lock:
                log.append("direct")
            return {"direct_result": "direct"}

        await manager.register(direct_handler, StartEvent)
        await manager.initialize()

        await manager.emit(StartEvent(workflow_id="mix-001"))

        assert "decorated" in log
        assert "direct" in log


# =============================================================================
# Concurrent Workflow Tests
# =============================================================================


class TestConcurrentWorkflows:
    """Tests for running multiple workflows concurrently."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_parallel_workflow_execution(self, manager):
        """Multiple workflows should execute in parallel."""
        workflow_log = []
        lock = asyncio.Lock()

        async def on_task(event):
            async with lock:
                workflow_log.append(f"start_{event.task_id}")
            await asyncio.sleep(event.duration)
            async with lock:
                workflow_log.append(f"end_{event.task_id}")
            return {"task_id": event.task_id}

        await manager.register(on_task, AsyncTaskEvent)

        # Launch multiple workflows in parallel
        import time

        start = time.time()
        await asyncio.gather(
            manager.emit(AsyncTaskEvent(task_id="wf1", duration=0.1)),
            manager.emit(AsyncTaskEvent(task_id="wf2", duration=0.1)),
            manager.emit(AsyncTaskEvent(task_id="wf3", duration=0.1)),
        )
        elapsed = time.time() - start

        # All should run concurrently (~0.1s not ~0.3s)
        assert elapsed < 0.25, f"Expected parallel execution, took {elapsed}s"

        # All workflows completed
        assert "end_wf1" in workflow_log
        assert "end_wf2" in workflow_log
        assert "end_wf3" in workflow_log

    @pytest.mark.asyncio
    async def test_workflow_isolation(self, manager):
        """Concurrent workflows should not interfere with each other."""
        results = {}
        lock = asyncio.Lock()

        async def accumulator(event):
            await asyncio.sleep(0.01)  # Simulate work
            async with lock:
                wf_id = event.workflow_id
                if wf_id not in results:
                    results[wf_id] = []
                results[wf_id].append(event.result)
            return {"result": event.result}

        await manager.register(accumulator, CompleteEvent)

        # Run workflows with different IDs
        async def workflow(wf_id, count):
            for i in range(count):
                await manager.emit(
                    CompleteEvent(workflow_id=wf_id, result=f"{wf_id}_result_{i}")
                )

        await asyncio.gather(
            workflow("wf-A", 3),
            workflow("wf-B", 3),
            workflow("wf-C", 3),
        )

        # Each workflow should have its own results
        assert len(results["wf-A"]) == 3
        assert len(results["wf-B"]) == 3
        assert len(results["wf-C"]) == 3

        # Results should be workflow-specific
        assert all("wf-A" in r for r in results["wf-A"])
        assert all("wf-B" in r for r in results["wf-B"])
        assert all("wf-C" in r for r in results["wf-C"])


# =============================================================================
# Async Signal and DataEvent Tests
# =============================================================================


class TestAsyncSignalDataEvent:
    """Tests for Signal and DataEvent in async workflows."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_async_signal_workflow(self, manager):
        """Workflow using Signal events with async handlers."""
        log = []
        lock = asyncio.Lock()

        ready = signal("async_ready")
        done = signal("async_done")

        async def on_ready(event):
            async with lock:
                log.append(f"ready from {event.sender}")
            return {"ready_result": "ready_handled"}

        async def on_done(event):
            async with lock:
                log.append(f"done from {event.sender}")
            return {"done_result": "done_handled"}

        await manager.register(on_ready, ready)
        await manager.register(on_done, done)

        await manager.emit(ready("component-A"))
        await manager.emit(ready("component-B"))
        await manager.emit(done("workflow"))

        assert log == [
            "ready from component-A",
            "ready from component-B",
            "done from workflow",
        ]

    @pytest.mark.asyncio
    async def test_async_data_event_request_response(self, manager):
        """Request-response pattern with DataEvent and async handlers."""
        responses = []
        lock = asyncio.Lock()

        request = data_event("async_request")
        response = data_event("async_response")

        async def on_request(event):
            # Simulate async processing
            await asyncio.sleep(0.01)
            # Send response
            await manager.emit(
                response(
                    {"result": event.data["query"] + "_processed"},
                    "async_server",
                )
            )
            return {"request_result": "request_handled"}

        async def on_response(event):
            async with lock:
                responses.append(event.data)
            return {"response_result": "response_received"}

        await manager.register(on_request, request)
        await manager.register(on_response, response)

        await manager.emit(request({"query": "async_search"}, "async_client"))

        assert len(responses) == 1
        assert responses[0]["result"] == "async_search_processed"


# =============================================================================
# Lifecycle Management Tests
# =============================================================================


class TestAsyncLifecycleManagement:
    """Tests for async workflow lifecycle management."""

    @pytest.fixture
    def manager(self):
        """Create fresh AsyncEventManager for each test."""
        return AsyncEventManager()

    @pytest.mark.asyncio
    async def test_reset_clears_async_workflow(self, manager):
        """Reset should clear all async workflow handlers."""
        call_count = {"value": 0}

        async def handler(event):
            call_count["value"] += 1
            return {"result": "result"}

        await manager.register(handler, ProcessEvent)

        await manager.emit(ProcessEvent(data={}, step=1))
        assert call_count["value"] == 1

        await manager.reset()

        await manager.emit(ProcessEvent(data={}, step=2))
        assert call_count["value"] == 1  # No additional call after reset

    @pytest.mark.asyncio
    async def test_halt_stops_async_workflow(self, manager):
        """Halt should stop async workflow processing."""
        call_count = {"value": 0}

        async def handler(event):
            call_count["value"] += 1
            return {"result": "result"}

        await manager.register(handler, ProcessEvent)

        await manager.emit(ProcessEvent(data={}, step=1))
        assert call_count["value"] == 1

        manager.halt()

        # After halt, emit returns empty results (but subscriptions remain)
        assert manager.is_halted
        results = await manager.emit(ProcessEvent(data={}, step=2))
        assert results == {}
        assert call_count["value"] == 1  # Handler not called

        # Resume allows processing again
        manager.resume()
        results = await manager.emit(ProcessEvent(data={}, step=3))
        assert results == {"result": "result"}
        assert call_count["value"] == 2

    @pytest.mark.asyncio
    async def test_unsubscribe_during_async_workflow(self, manager):
        """Handler can unsubscribe itself during async workflow."""
        log = []
        lock = asyncio.Lock()

        async def one_shot_handler(event):
            async with lock:
                log.append(f"one-shot: {event.step}")
            await manager.unsubscribe(one_shot_handler, ProcessEvent)
            return {"one_shot_result": "one_shot"}

        async def persistent_handler(event):
            async with lock:
                log.append(f"persistent: {event.step}")
            return {"persistent_result": "persistent"}

        await manager.register(one_shot_handler, ProcessEvent)
        await manager.register(persistent_handler, ProcessEvent)

        await manager.emit(ProcessEvent(data={}, step=1))
        await manager.emit(ProcessEvent(data={}, step=2))
        await manager.emit(ProcessEvent(data={}, step=3))

        assert "one-shot: 1" in log
        assert "persistent: 1" in log
        assert "persistent: 2" in log
        assert "persistent: 3" in log
        # one-shot should only appear once
        assert log.count("one-shot: 1") == 1
