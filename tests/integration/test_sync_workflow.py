"""
Integration tests for complete synchronous event workflows.

Tests cover:
- Full registration -> emit -> handler workflow
- Event propagation through multiple handlers
- Event chain scenarios (handler emitting another event)
- Result collection patterns
- EventAwareBase integration
- Module loading integration
"""

import pytest
from moduvent import EventManager, Event, signal, data_event
from moduvent.moduvent import EventAwareBase
from moduvent.base import subscribe_method


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


class ErrorEvent(Event):
    """Event for error handling."""

    def __init__(self, error_message: str, recoverable: bool = True):
        self.error_message = error_message
        self.recoverable = recoverable


# =============================================================================
# Basic Workflow Tests
# =============================================================================


class TestBasicSyncWorkflow:
    """Tests for basic synchronous event workflows."""

    @pytest.fixture
    def manager(self):
        """Create fresh EventManager for each test."""
        return EventManager()

    def test_simple_workflow(self, manager):
        """Simple start -> process -> complete workflow."""
        log = []

        def on_start(event):
            log.append(f"started: {event.workflow_id}")
            return {"status": "started"}

        def on_process(event):
            log.append(f"processing step {event.step}")
            return {"status": f"step_{event.step}"}

        def on_complete(event):
            log.append(f"completed: {event.workflow_id} with {event.result}")
            return {"status": "completed"}

        manager.register(on_start, StartEvent)
        manager.register(on_process, ProcessEvent)
        manager.register(on_complete, CompleteEvent)

        # Execute workflow
        manager.emit(StartEvent(workflow_id="wf-001"))
        manager.emit(ProcessEvent(data={"key": "value"}, step=1))
        manager.emit(ProcessEvent(data={"key": "value2"}, step=2))
        manager.emit(CompleteEvent(workflow_id="wf-001", result="success"))

        assert log == [
            "started: wf-001",
            "processing step 1",
            "processing step 2",
            "completed: wf-001 with success",
        ]

    def test_event_chain_workflow(self, manager):
        """Handler that emits another event creating a chain."""
        log = []

        def on_start(event):
            log.append(f"start: {event.workflow_id}")
            # Emit process event from start handler
            manager.emit(ProcessEvent(data={"auto": True}, step=1))
            return {"status": "started"}

        def on_process(event):
            log.append(f"process: step {event.step}")
            if event.step < 3:
                # Chain to next step
                manager.emit(ProcessEvent(data=event.data, step=event.step + 1))
            else:
                # Chain to complete
                manager.emit(CompleteEvent(workflow_id="auto", result="done"))
            return {"status": f"processed_{event.step}"}

        def on_complete(event):
            log.append(f"complete: {event.result}")
            return {"status": "completed"}

        manager.register(on_start, StartEvent)
        manager.register(on_process, ProcessEvent)
        manager.register(on_complete, CompleteEvent)

        # Single emit triggers chain
        manager.emit(StartEvent(workflow_id="chain-001"))

        assert log == [
            "start: chain-001",
            "process: step 1",
            "process: step 2",
            "process: step 3",
            "complete: done",
        ]

    def test_multiple_handlers_workflow(self, manager):
        """Multiple handlers for same event type."""
        log = []

        def logger_handler(event):
            log.append(f"LOG: {event.workflow_id}")
            return {"logger_result": "logged"}

        def validator_handler(event):
            log.append(f"VALIDATE: {event.workflow_id}")
            return {"validator_result": "validated"}

        def processor_handler(event):
            log.append(f"PROCESS: {event.workflow_id}")
            return {"processor_result": "processed"}

        manager.register(logger_handler, StartEvent)
        manager.register(validator_handler, StartEvent)
        manager.register(processor_handler, StartEvent)

        results = manager.emit(StartEvent(workflow_id="multi-001"))

        # All handlers executed
        assert len(log) == 3
        assert "LOG: multi-001" in log
        assert "VALIDATE: multi-001" in log
        assert "PROCESS: multi-001" in log

        # All results collected
        assert len(results) == 3


# =============================================================================
# Conditional Workflow Tests
# =============================================================================


class TestConditionalWorkflow:
    """Tests for workflows with conditional handler execution."""

    @pytest.fixture
    def manager(self):
        """Create fresh EventManager for each test."""
        return EventManager()

    def test_conditional_handler_execution(self, manager):
        """Handlers with conditions should execute selectively."""
        log = []

        def early_step_handler(event):
            log.append(f"early: step {event.step}")
            return {"early_result": "early"}

        def late_step_handler(event):
            log.append(f"late: step {event.step}")
            return {"late_result": "late"}

        # Register with conditions
        manager.register(early_step_handler, ProcessEvent, lambda e: e.step <= 2)
        manager.register(late_step_handler, ProcessEvent, lambda e: e.step > 2)

        manager.emit(ProcessEvent(data={}, step=1))
        manager.emit(ProcessEvent(data={}, step=3))
        manager.emit(ProcessEvent(data={}, step=5))

        assert log == ["early: step 1", "late: step 3", "late: step 5"]

    def test_error_handling_workflow(self, manager):
        """Workflow with error events and conditional recovery."""
        log = []

        def error_logger(event):
            log.append(f"ERROR: {event.error_message}")
            return {"error_logged": event.error_message}

        def recovery_handler(event):
            if event.recoverable:
                log.append(f"RECOVER: {event.error_message}")
                return {"recovery_result": "recovered"}
            else:
                log.append(f"FATAL: {event.error_message}")
                return {"recovery_result": "fatal"}

        manager.register(error_logger, ErrorEvent)
        manager.register(recovery_handler, ErrorEvent)

        manager.emit(ErrorEvent(error_message="timeout", recoverable=True))
        manager.emit(ErrorEvent(error_message="crash", recoverable=False))

        assert "ERROR: timeout" in log
        assert "RECOVER: timeout" in log
        assert "ERROR: crash" in log
        assert "FATAL: crash" in log


# =============================================================================
# Result Collection Tests
# =============================================================================


class TestResultCollection:
    """Tests for result collection patterns."""

    @pytest.fixture
    def manager(self):
        """Create fresh EventManager for each test."""
        return EventManager()

    def test_collect_all_results(self, manager):
        """Collect results from all handlers."""

        def handler1(event):
            return {"handler1_score": event.step * 10}

        def handler2(event):
            return {"handler2_score": event.step * 100}

        def handler3(event):
            return {"handler3_score": event.step * 1000}

        manager.register(handler1, ProcessEvent)
        manager.register(handler2, ProcessEvent)
        manager.register(handler3, ProcessEvent)

        results = manager.emit(ProcessEvent(data={}, step=5))

        assert results.get("handler1_score") == 50
        assert results.get("handler2_score") == 500
        assert results.get("handler3_score") == 5000

    def test_results_with_none_returns(self, manager):
        """Handlers returning None should result in empty dict contribution."""

        def returning_handler(event):
            return {"step": event.step}

        def void_handler(event):
            pass  # Returns None

        manager.register(returning_handler, ProcessEvent)
        manager.register(void_handler, ProcessEvent)

        results = manager.emit(ProcessEvent(data={}, step=42))

        assert results.get("step") == 42

    def test_aggregate_results(self, manager):
        """Aggregate results from multiple handlers."""

        def score_handler_1(event):
            return {"score_h1": 10, "source_h1": "h1"}

        def score_handler_2(event):
            return {"score_h2": 20, "source_h2": "h2"}

        def score_handler_3(event):
            return {"score_h3": 30, "source_h3": "h3"}

        manager.register(score_handler_1, ProcessEvent)
        manager.register(score_handler_2, ProcessEvent)
        manager.register(score_handler_3, ProcessEvent)

        results = manager.emit(ProcessEvent(data={}, step=1))

        # Aggregate scores
        total_score = (
            results.get("score_h1", 0)
            + results.get("score_h2", 0)
            + results.get("score_h3", 0)
        )
        assert total_score == 60


# =============================================================================
# EventAwareBase Integration Tests
# =============================================================================


class TestEventAwareBaseIntegration:
    """Tests for EventAwareBase class integration."""

    @pytest.fixture
    def manager(self):
        """Create fresh EventManager for each test."""
        return EventManager()

    def test_event_aware_class_workflow(self, manager):
        """EventAwareBase subclass should participate in workflows."""

        class WorkflowProcessor(EventAwareBase):
            event_manager = manager

            def __init__(self):
                self.events_received = []
                super().__init__()

            @subscribe_method(StartEvent)
            def handle_start(self, event):
                self.events_received.append(("start", event.workflow_id))
                return {"start_result": "handled_start"}

            @subscribe_method(CompleteEvent)
            def handle_complete(self, event):
                self.events_received.append(("complete", event.workflow_id))
                return {"complete_result": "handled_complete"}

        processor = WorkflowProcessor()

        manager.emit(StartEvent(workflow_id="aware-001"))
        manager.emit(CompleteEvent(workflow_id="aware-001", result="ok"))

        assert processor.events_received == [
            ("start", "aware-001"),
            ("complete", "aware-001"),
        ]

    def test_multiple_event_aware_instances(self, manager):
        """Multiple EventAwareBase instances should all receive events."""

        class Counter(EventAwareBase):
            event_manager = manager

            def __init__(self, name):
                self.name = name
                self.count = 0
                super().__init__()

            @subscribe_method(ProcessEvent)
            def handle_process(self, event):
                self.count += 1
                # Each instance has unique name so keys won't collide
                return {f"{self.name}_counted": self.count}

        counter1 = Counter("c1")
        counter2 = Counter("c2")
        counter3 = Counter("c3")

        for _ in range(5):
            manager.emit(ProcessEvent(data={}, step=1))

        assert counter1.count == 5
        assert counter2.count == 5
        assert counter3.count == 5


# =============================================================================
# Signal and DataEvent Workflow Tests
# =============================================================================


class TestSignalDataEventWorkflow:
    """Tests for Signal and DataEvent in workflows."""

    @pytest.fixture
    def manager(self):
        """Create fresh EventManager for each test."""
        return EventManager()

    def test_signal_workflow(self, manager):
        """Workflow using Signal events."""
        log = []

        ready = signal("ready")
        done = signal("done")

        @manager.subscribe(ready)
        def on_ready(event):
            log.append(f"ready from {event.sender}")
            return {"ready_result": "ready_handled"}

        @manager.subscribe(done)
        def on_done(event):
            log.append(f"done from {event.sender}")
            return {"done_result": "done_handled"}

        manager.emit(ready("component-A"))
        manager.emit(ready("component-B"))
        manager.emit(done("workflow"))

        assert log == [
            "ready from component-A",
            "ready from component-B",
            "done from workflow",
        ]

    def test_data_event_workflow(self, manager):
        """Workflow using DataEvent events."""
        log = []

        request = data_event("request")
        response = data_event("response")

        @manager.subscribe(request)
        def on_request(event):
            log.append(f"request: {event.data}")
            # Simulate processing and respond
            manager.emit(
                response({"result": event.data["query"] + "_result"}, "server")
            )
            return {"request_result": "request_handled"}

        @manager.subscribe(response)
        def on_response(event):
            log.append(f"response: {event.data}")
            return {"response_result": "response_handled"}

        manager.emit(request({"query": "search"}, "client"))

        assert len(log) == 2
        assert "request: {'query': 'search'}" in log
        assert "response: {'result': 'search_result'}" in log


# =============================================================================
# Lifecycle Tests
# =============================================================================


class TestWorkflowLifecycle:
    """Tests for workflow lifecycle management."""

    @pytest.fixture
    def manager(self):
        """Create fresh EventManager for each test."""
        return EventManager()

    def test_unsubscribe_during_workflow(self, manager):
        """Handler can unsubscribe itself during workflow."""
        log = []

        def one_shot_handler(event):
            log.append(f"one-shot: {event.step}")
            manager.unsubscribe(one_shot_handler, ProcessEvent)
            return {"one_shot_result": "one_shot"}

        def persistent_handler(event):
            log.append(f"persistent: {event.step}")
            return {"persistent_result": "persistent"}

        manager.register(one_shot_handler, ProcessEvent)
        manager.register(persistent_handler, ProcessEvent)

        manager.emit(ProcessEvent(data={}, step=1))
        manager.emit(ProcessEvent(data={}, step=2))
        manager.emit(ProcessEvent(data={}, step=3))

        assert log == [
            "one-shot: 1",
            "persistent: 1",
            "persistent: 2",
            "persistent: 3",
        ]

    def test_reset_clears_workflow(self, manager):
        """Reset should clear all workflow handlers."""
        log = []

        def handler(event):
            log.append("called")
            return {"result": "result"}

        manager.register(handler, ProcessEvent)

        manager.emit(ProcessEvent(data={}, step=1))
        assert log == ["called"]

        manager.reset()

        manager.emit(ProcessEvent(data={}, step=2))
        assert log == ["called"]  # No additional call after reset

    def test_muted_event_in_workflow(self, manager):
        """Muted events should not trigger handlers."""
        log = []

        MutedSignal = signal("muted_signal")

        @manager.subscribe(MutedSignal)
        def handler(event):
            log.append("handled")
            return {"result": "result"}

        # Normal emit
        manager.emit(MutedSignal("sender1"))
        assert log == ["handled"]

        # Muted emit
        with MutedSignal.muted():
            manager.emit(MutedSignal("sender2"))
        assert log == ["handled"]  # No additional entry

        # Normal emit again
        manager.emit(MutedSignal("sender3"))
        assert log == ["handled", "handled"]
