from unittest.mock import MagicMock, call

import pytest
from moduvent import EventManager
from moduvent.events import Event
from moduvent.moduvent import CallbackProcessing, CallbackRegistry


class DummyEvent(Event): ...


class DummyEvent_2(Event): ...


class DisabledEvent(Event):
    enabled = False


def func_1(e: Event): ...
def func_2(e: Event): ...


@pytest.fixture(autouse=True)
def patch_common_logger(monkeypatch):
    # Patch common_logger used in the class
    logger_mock = MagicMock()
    monkeypatch.setattr("moduvent.common.common_logger", logger_mock)
    return logger_mock


@pytest.mark.parametrize(
    "func,event_type,expected_error",
    [
        (None, None, ValueError),  # both None
        (123, None, ValueError),  # func not callable, event_type None
        (None, 123, ValueError),  # event_type not a class
    ],
    ids=["both_none", "func_not_callable", "event_type_not_class"],
)
def test_unsubscribe_check_args_errors(func, event_type, expected_error):
    # Arrange

    mgr = EventManager()

    # Act & Assert

    with pytest.raises(expected_error):
        mgr._unsubscribe_check_args(func, event_type)


@pytest.mark.parametrize(
    "func,event_type,subscriptions,expected_calls,expected_subscriptions",
    [
        # Remove specific func for event_type
        (
            func_1,
            DummyEvent,
            {DummyEvent: [func_1, func_2], DummyEvent_2: [func_1, func_2]},
            [
                call.debug(
                    "Removed subscription for <class 'tests.test_common_base_event_manager.DummyEvent'> and <function <lambda> at"
                )
            ],
            {DummyEvent: [func_2], DummyEvent_2: [func_1, func_2]},
        ),
        # Remove all callbacks for func
        (
            func_1,
            None,
            {DummyEvent: [func_1, func_2], DummyEvent_2: [func_1, func_2]},
            [call.debug("Removed all callbacks for <function <lambda> at")],
            {DummyEvent: [func_2], DummyEvent_2: [func_2]},
        ),
        # Remove all for event_type
        (
            None,
            DummyEvent,
            {DummyEvent: [func_1, func_2], DummyEvent_2: [func_1, func_2]},
            [
                call.debug(
                    "Cleared all subscriptions for <class 'tests.test_common_base_event_manager.DummyEvent'>"
                )
            ],
            {DummyEvent_2: [func_1, func_2]},
        ),
    ],
    ids=["func_and_event_type", "func_only", "event_type_only"],
)
def test_unsubscribe_process_logic(
    func,
    event_type,
    subscriptions,
    expected_calls,
    expected_subscriptions,
    patch_common_logger,
):
    # Arrange

    mgr = EventManager()

    # Patch _remove_subscriptions to actually remove
    def _remove_subscriptions(filter_func):
        new_subs = {}
        for event_type_, callbacks in subscriptions.items():
            for cb in callbacks:
                if not filter_func(event_type_, cb):
                    new_subs.setdefault(event_type_, []).append(cb)
        mgr._subscriptions = new_subs

    mgr._subscriptions = dict(subscriptions)
    mgr._remove_subscriptions = _remove_subscriptions

    # Act

    mgr._unsubscribe_process_logic(func, event_type)

    # Assert

    # Check logger called as expected (partial match for lambda address)
    if expected_calls:
        assert any(
            expected_call[0] == actual_call[0]
            and expected_call[1][0][:20] == actual_call[1][0][:20]
            for expected_call in expected_calls
            for actual_call in patch_common_logger.method_calls
        )
    # Check subscriptions updated
    assert mgr._subscriptions == expected_subscriptions


@pytest.mark.parametrize(
    "event,enabled,expected_valid,expected_type",
    [
        (DummyEvent(), True, True, DummyEvent),
        (DisabledEvent(), False, False, DisabledEvent),
        ("not an event", True, False, "not an event"),
    ],
    ids=["enabled_event", "disabled_event", "not_instance"],
)
def test_emit_check(event, enabled, expected_valid, expected_type, monkeypatch):
    # Arrange

    mgr = EventManager()
    # Patch is_instance_and_subclass to simulate
    monkeypatch.setattr(
        "moduvent.common.is_instance_and_subclass",
        lambda x: isinstance(x, (DummyEvent, DisabledEvent)),
    )
    # Patch enabled attribute
    if hasattr(event, "enabled"):
        event.enabled = enabled

    # Act

    valid, event_type = mgr._emit_check(event)

    # Assert

    assert valid == expected_valid
    if not valid and isinstance(event, str):
        assert event_type == event
    else:
        assert event_type is type(event)


def test_register_and_emit_happy_path(patch_common_logger):
    # Arrange

    mgr = EventManager()
    called = []

    def cb(event):
        # Arrange
        called.append(event)

    # Act

    mgr.register(cb, DummyEvent)
    event = DummyEvent()
    mgr.emit(event)

    # Assert

    assert called == [event]
    assert mgr._get_callqueue_length() == 0  # _process_callqueue clears it


def test_register_multiple_conditions_and_emit():
    # Arrange

    mgr = EventManager()
    called = []

    def cb(event):
        called.append(event)

    cond1 = lambda e: True
    cond2 = lambda e: True

    # Act

    mgr.register(cb, DummyEvent, cond1, cond2)
    event = DummyEvent()
    mgr.emit(event)

    # Assert

    assert called == [event]


def test_emit_no_subscriptions(monkeypatch):
    # Arrange

    mgr = EventManager()
    event = DummyEvent()
    # Patch _emit_check to always valid
    monkeypatch.setattr(mgr, "_emit_check", lambda e: (True, DummyEvent))

    # Act

    mgr.emit(event)

    # Assert

    assert mgr._get_callqueue_length() == 0


def test_emit_disabled_event(monkeypatch):
    # Arrange

    mgr = EventManager()
    event = DisabledEvent()
    # Patch _emit_check to always invalid
    monkeypatch.setattr(mgr, "_emit_check", lambda e: (False, DisabledEvent))

    # Act

    mgr.emit(event)

    # Assert

    assert mgr._get_callqueue_length() == 0


def test_unsubscribe_removes_callback():
    # Arrange

    mgr = EventManager()
    called = []

    def cb(event):
        called.append(event)

    mgr.register(cb, DummyEvent)
    event = DummyEvent()
    mgr.unsubscribe(cb, DummyEvent)

    # Act

    mgr.emit(event)

    # Assert

    assert not called


def test_unsubscribe_all_for_event_type():
    # Arrange

    mgr = EventManager()
    called = []

    def cb(event):
        called.append(event)

    mgr.register(cb, DummyEvent)
    mgr.unsubscribe(event_type=DummyEvent)

    # Act

    mgr.emit(DummyEvent())

    # Assert

    assert not called


def test_reset_clears_subscriptions():
    # Arrange

    mgr = EventManager()
    mgr.register(func_1, DummyEvent)
    mgr._append_to_callqueue(CallbackProcessing(func_1, DummyEvent()))

    # Act

    mgr.reset()

    # Assert

    assert mgr._subscriptions == {}


def test_halt_clears_callqueue():
    # Arrange

    mgr = EventManager()
    mgr._append_to_callqueue(CallbackProcessing(func_1, DummyEvent()))

    # Act

    mgr.halt()

    # Assert

    assert mgr._get_callqueue_length() == 0


def test_remove_subscriptions_filters_correctly():
    # Arrange

    mgr = EventManager()
    cb1 = CallbackRegistry(func_1, DummyEvent)
    cb2 = CallbackRegistry(func_2, DummyEvent)
    mgr._subscriptions = {DummyEvent: [cb1, cb2]}

    # Act

    mgr._remove_subscriptions(lambda e, c: c == cb1)

    # Assert

    assert mgr._subscriptions == {DummyEvent: [cb2]}
