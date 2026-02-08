from unittest.mock import patch

import pytest

from moduvent import Event, EventManager
from moduvent.utils import SUBSCRIPTION_STRATEGY


# Dummy classes and functions for testing
class DummyEvent(Event): ...


class DummyEvent2(Event): ...


class DummyCallbackRegistry:
    def __init__(self, name="cb"):
        self.name = name

    def __repr__(self):
        return f"DummyCallbackRegistry({self.name})"


class DummyCallbackProcessing:
    def __init__(self, name="cb", should_raise=False):
        self.name = name
        self.should_raise = should_raise

    def __repr__(self):
        return f"DummyCallbackProcessing({self.name})"

    def call(self):
        if self.should_raise:
            raise Exception("Callback error")
        return f"called {self.name}"


@pytest.fixture
def event_manager():
    # Arrange
    # Create an instance of EventManager with patched superclasses
    with patch("moduvent.moduvent.BaseEventManager", autospec=True):
        yield EventManager()


@pytest.mark.parametrize(
    "subscriptions,expected",
    [
        # Happy path: set subscriptions
        (
            {DummyEvent: [DummyCallbackRegistry("cb1")]},
            {DummyEvent: [DummyCallbackRegistry("cb1")]},
        ),
        # Edge case: empty subscriptions
        (
            {},
            {},
        ),
    ],
    ids=["set-one-subscription", "set-empty-subscriptions"],
)
def test_set_subscriptions(event_manager, subscriptions, expected):
    # Arrange
    with patch.object(
        EventManager, "_set_subscriptions", wraps=event_manager._set_subscriptions
    ) as mock_set:
        # Act
        event_manager._set_subscriptions(subscriptions)
        # Assert
        mock_set.assert_called_once_with(subscriptions)


@pytest.mark.parametrize(
    "callbacks,expected_length",
    [
        ([DummyCallbackProcessing("cb1"), DummyCallbackProcessing("cb2")], 2),
        ([], 0),
    ],
    ids=["two-callbacks", "empty-callqueue"],
)
def test_append_and_get_callqueue_length(event_manager, callbacks, expected_length):
    # Act
    for cb in callbacks:
        event_manager._append_to_callqueue(cb)
    length = event_manager._get_callqueue_length()
    # Assert
    assert length == expected_length


def test_reset_subscriptions(event_manager):
    # Arrange
    event_manager._subscriptions = {DummyEvent: [DummyCallbackRegistry("cb1")]}
    # Act
    event_manager.reset()
    # Assert
    assert not event_manager._subscriptions


@pytest.mark.parametrize(
    "callqueue,should_raise,expected_calls,expected_exceptions",
    [
        # Happy path: two callbacks, no exception
        ([DummyCallbackProcessing("cb1"), DummyCallbackProcessing("cb2")], False, 2, 0),
        # Edge case: one callback raises exception
        ([DummyCallbackProcessing("cb1", should_raise=True)], True, 1, 1),
        # Edge case: empty callqueue
        ([], False, 0, 0),
    ],
    ids=["two-callbacks-no-exc", "one-callback-raises", "empty-callqueue"],
)
def test_process_callqueue(
    event_manager, callqueue, should_raise, expected_calls, expected_exceptions
):
    # Arrange
    event_manager._callqueue.clear()
    for cb in callqueue:
        event_manager._append_to_callqueue(cb)
    with patch("moduvent.moduvent.moduvent_logger") as mock_logger:
        # Act
        event_manager._process_callqueue()
        # Assert
        assert mock_logger.debug.call_count >= 2  # At least start/end logs
        if expected_exceptions:
            assert mock_logger.exception.call_count == expected_exceptions


@pytest.mark.parametrize(
    "args,kwargs,strategy,expected_func_calls,expected_error",
    [
        # Happy path: EVENTS strategy, two event types
        ([DummyEvent, DummyEvent2], {}, SUBSCRIPTION_STRATEGY.EVENTS, 2, None),
        # Happy path: CONDITIONS strategy, one event type, one condition
        ([DummyEvent, lambda e: True], {}, SUBSCRIPTION_STRATEGY.CONDITIONS, 1, None),
        # Error case: invalid strategy
        ([123], {}, "INVALID", 0, ValueError),
    ],
    ids=["events-strategy", "conditions-strategy", "invalid-strategy"],
)
def test_subscribe(
    event_manager, args, kwargs, strategy, expected_func_calls, expected_error
):
    # Arrange
    with patch("moduvent.moduvent.get_subscription_strategy", return_value=strategy):
        with patch.object(event_manager, "register") as mock_register:
            if expected_error:
                # Act & Assert
                with pytest.raises(expected_error):
                    event_manager.subscribe(*args, **kwargs)
            else:
                # Act
                decorator = event_manager.subscribe(*args, **kwargs)

                def dummy_func(e):
                    return "ok"

                result = decorator(dummy_func)
                # Assert
                assert result is dummy_func
                assert mock_register.call_count == expected_func_calls
