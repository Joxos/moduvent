"""
Shared pytest fixtures for moduvent tests.
"""

import pytest
import asyncio
from typing import Type, List
from unittest.mock import MagicMock

from moduvent import EventManager, Event, Signal, DataEvent
from moduvent.async_moduvent import AsyncEventManager, AsyncEventAwareBase
from moduvent.moduvent import EventAwareBase
from moduvent.events import EventFactory


# =============================================================================
# Event Classes for Testing
# =============================================================================


class DummyEvent(Event):
    """Basic event for testing."""

    def __init__(self, value: int = 0):
        self.value = value


class DummyEvent2(Event):
    """Secondary event for testing multiple event types."""

    def __init__(self, message: str = ""):
        self.message = message


class DisabledEvent(Event):
    """Event that is disabled by default."""

    enabled = False


class EventWithData(Event):
    """Event with multiple data fields."""

    def __init__(self, name: str, count: int, items: List[str] = None):
        self.name = name
        self.count = count
        self.items = items or []


# =============================================================================
# Pytest Configuration
# =============================================================================


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy."""
    return asyncio.DefaultEventLoopPolicy()


# =============================================================================
# Event Manager Fixtures
# =============================================================================


@pytest.fixture
def event_manager() -> EventManager:
    """Create a fresh EventManager instance for each test."""
    return EventManager()


@pytest.fixture
def async_event_manager() -> AsyncEventManager:
    """Create a fresh AsyncEventManager instance for each test."""
    return AsyncEventManager()


# =============================================================================
# Event Fixtures
# =============================================================================


@pytest.fixture
def dummy_event() -> DummyEvent:
    """Create a DummyEvent instance."""
    return DummyEvent(value=42)


@pytest.fixture
def dummy_event2() -> DummyEvent2:
    """Create a DummyEvent2 instance."""
    return DummyEvent2(message="test")


@pytest.fixture
def disabled_event() -> DisabledEvent:
    """Create a DisabledEvent instance."""
    return DisabledEvent()


@pytest.fixture
def event_with_data() -> EventWithData:
    """Create an EventWithData instance."""
    return EventWithData(name="test", count=5, items=["a", "b", "c"])


# =============================================================================
# Event Class Fixtures
# =============================================================================


@pytest.fixture
def dummy_event_class() -> Type[DummyEvent]:
    """Return the DummyEvent class."""
    return DummyEvent


@pytest.fixture
def dummy_event2_class() -> Type[DummyEvent2]:
    """Return the DummyEvent2 class."""
    return DummyEvent2


@pytest.fixture
def disabled_event_class() -> Type[DisabledEvent]:
    """Return the DisabledEvent class."""
    return DisabledEvent


# =============================================================================
# Factory Fixtures
# =============================================================================


@pytest.fixture
def event_factory() -> EventFactory:
    """Create a fresh EventFactory."""
    return EventFactory.create(Event)


@pytest.fixture
def signal_factory() -> EventFactory:
    """Create a factory for Signal events."""
    return EventFactory.create(Signal)


@pytest.fixture
def data_event_factory() -> EventFactory:
    """Create a factory for DataEvent events."""
    return EventFactory.create(DataEvent)


# =============================================================================
# Logger Fixtures
# =============================================================================


@pytest.fixture
def mock_logger(monkeypatch) -> MagicMock:
    """Mock all loggers used in moduvent."""
    logger_mock = MagicMock()
    monkeypatch.setattr("moduvent.common.common_logger", logger_mock)
    monkeypatch.setattr("moduvent.moduvent.moduvent_logger", logger_mock)
    monkeypatch.setattr("moduvent.async_moduvent.async_moduvent_logger", logger_mock)
    monkeypatch.setattr("moduvent.module_loader.module_logger", logger_mock)
    return logger_mock


# =============================================================================
# Callback Tracking Fixtures
# =============================================================================


@pytest.fixture
def call_tracker():
    """Track function calls for verification."""

    class CallTracker:
        def __init__(self):
            self.calls: List = []
            self.call_count: int = 0

        def record(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            self.call_count += 1

        def reset(self):
            self.calls.clear()
            self.call_count = 0

        def get_call_args(self, index: int = 0):
            if index < len(self.calls):
                return self.calls[index]
            return None

    return CallTracker()


@pytest.fixture
def async_call_tracker():
    """Track async function calls for verification."""

    class AsyncCallTracker:
        def __init__(self):
            self.calls: List = []
            self.call_count: int = 0
            self.lock = asyncio.Lock()

        async def record(self, *args, **kwargs):
            async with self.lock:
                self.calls.append((args, kwargs))
                self.call_count += 1

        def reset(self):
            self.calls.clear()
            self.call_count = 0

        def get_call_args(self, index: int = 0):
            if index < len(self.calls):
                return self.calls[index]
            return None

    return AsyncCallTracker()


# =============================================================================
# EventAwareBase Test Classes
# =============================================================================


@pytest.fixture
def event_aware_class(event_manager):
    """Create a test EventAwareBase subclass."""
    from moduvent.common import subscribe_method

    class TestEventAware(EventAwareBase):
        event_manager = event_manager

        def __init__(self):
            self.handled_events = []
            super().__init__()

        @subscribe_method(DummyEvent)
        def handle_dummy(self, event: DummyEvent):
            self.handled_events.append(event)
            return event.value

    return TestEventAware


@pytest.fixture
def async_event_aware_class(async_event_manager):
    """Create a test AsyncEventAwareBase subclass."""
    from moduvent.common import subscribe_method

    class TestAsyncEventAware(AsyncEventAwareBase):
        event_manager = async_event_manager

        def __init__(self, event_manager=None):
            self.handled_events = []
            super().__init__(event_manager)

        @classmethod
        async def create(cls, event_manager):
            instance = cls(event_manager)
            await instance._register()
            return instance

        @subscribe_method(DummyEvent)
        async def handle_dummy(self, event: DummyEvent):
            self.handled_events.append(event)
            return event.value

    return TestAsyncEventAware


# =============================================================================
# Path Fixtures
# =============================================================================


@pytest.fixture
def fixtures_path():
    """Return the path to the fixtures directory."""
    import os

    return os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def example_modules_path(fixtures_path):
    """Return the path to the example_modules directory."""
    import os

    return os.path.join(fixtures_path, "example_modules")
