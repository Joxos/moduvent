# =============================================================================
# Custom Exceptions
# =============================================================================


class DuplicateResultKeyError(Exception):
    """Raised when multiple callbacks return the same result key."""

    def __init__(self, key: str, callback1: str, callback2: str):
        self.key = key
        self.callback1 = callback1
        self.callback2 = callback2
        super().__init__(
            f"Duplicate result key '{key}' returned by callbacks: "
            f"'{callback1}' and '{callback2}'"
        )


class InvalidCallbackReturnError(TypeError):
    """Raised when a callback returns an invalid type (not None or dict[str, Any])."""

    def __init__(self, callback_name: str, return_type: type):
        self.callback_name = callback_name
        self.return_type = return_type
        super().__init__(
            f"Callback '{callback_name}' returned invalid type '{return_type.__name__}'. "
            f"Expected None or dict[str, Any]."
        )


class InvalidCallbackRegistryError(TypeError):
    """Raised when registering a callback with wrong type (sync vs async mismatch)."""

    def __init__(self, callback_name: str, expected: str, got: str):
        self.callback_name = callback_name
        self.expected = expected
        self.got = got
        super().__init__(
            f"Cannot register '{callback_name}': expected {expected} callback, "
            f"got {got} callback."
        )


class CallbackExpiredError(RuntimeError):
    """Raised when a callback's weak reference has expired (been garbage collected).

    This typically happens when:
    1. A local function was registered as a callback but went out of scope
    2. An object with a bound method callback was deleted without unsubscribing

    To fix this:
    - Keep a reference to the callback function/object alive
    - Or call unsubscribe() before the callback goes out of scope
    """

    def __init__(self, event_type: type, callback_info: str):
        self.event_type = event_type
        self.callback_info = callback_info
        super().__init__(
            f"Callback expired for event '{event_type.__name__}': {callback_info}. "
            f"The callback was garbage collected before being unsubscribed. "
            f"Keep a reference to the callback or unsubscribe before it goes out of scope."
        )
