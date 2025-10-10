# Moduvent - Python Event-Driven Framework

[![zread](https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTQuOTYxNTYgMS42MDAxSDIuMjQxNTZDMS44ODgxIDEuNjAwMSAxLjYwMTU2IDEuODg2NjQgMS42MDE1NiAyLjI0MDFWNC45NjAxQzEuNjAxNTYgNS4zMTM1NiAxLjg4ODEgNS42MDAxIDIuMjQxNTYgNS42MDAxSDQuOTYxNTZDNS4zMTUwMiA1LjYwMDEgNS42MDE1NiA1LjMxMzU2IDUuNjAxNTYgNC45NjAxVjIuMjQwMUM1LjYwMTU2IDEuODg2NjQgNS4zMTUwMiAxLjYwMDEgNC45NjE1NiAxLjYwMDFaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00Ljk2MTU2IDEwLjM5OTlIMi4yNDE1NkMxLjg4ODEgMTAuMzk5OSAxLjYwMTU2IDEwLjY4NjQgMS42MDE1NiAxMS4wMzk5VjEzLjc1OTlDMS42MDE1NiAxNC4xMTM0IDEuODg4MSAxNC4zOTk5IDIuMjQxNTYgMTQuMzk5OUg0Ljk2MTU2QzUuMzE1MDIgMTQuMzk5OSA1LjYwMTU2IDE0LjExMzQgNS42MDE1NiAxMy43NTk5VjExLjAzOTlDNS42MDE1NiAxMC42ODY0IDUuMzE1MDIgMTAuMzk5OSA0Ljk2MTU2IDEwLjM5OTlaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik0xMy43NTg0IDEuNjAwMUgxMS4wMzg0QzEwLjY4NSAxLjYwMDEgMTAuMzk4NCAxLjg4NjY0IDEwLjM5ODQgMi4yNDAxVjQuOTYwMUMxMC4zOTg0IDUuMzEzNTYgMTAuNjg1IDUuNjAwMSAxMS4wMzg0IDUuNjAwMUgxMy43NTg0QzE0LjExMTkgNS42MDAxIDE0LjM5ODQgNS4zMTM1NiAxNC4zOTg0IDQuOTYwMVYyLjI0MDFDMTQuMzk4NCAxLjg4NjY0IDE0LjExMTkgMS42MDAxIDEzLjc1ODQgMS42MDAxWiIgZmlsbD0iI2ZmZiIvPgo8cGF0aCBkPSJNNCAxMkwxMiA0TDQgMTJaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00IDEyTDEyIDQiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgo8L3N2Zz4K&logoColor=ffffff)](https://zread.ai/Joxos/moduvent)

A lightweight, modular event system for Python applications with plugin architecture support.

## Features

🎯 Simple and intuitive event subscription and emission

🧩 Dynamic module loading system for extensibility

📝 Comprehensive logging with Loguru integration

🏗️ Class-based event handlers with metaclass support

🔧 Type annotations throughout for better development experience

## Installation

```bash
pip install moduvent
```

## Quick Start

Everything below can be imported from the `moduvent` package.

### Define a custom event

We say an event holds data that is relevant to a certain type of event. For example, a `UserLoggedIn` event might hold the user ID and timestamp of the login.

```python
class UserLoggedIn(Event):
    def __init__(self, user_id, timestamp):
        self.user_id = user_id
        self.timestamp = timestamp
```

### Subscribe your events

Once you finished defining your events, you can subscribe some functions (both bound methods and unbound functions) to them using the `subscribe` decorator for unbound functions and `subscribe_method` for bound methods.

```python
# Unbound function
@subscribe(UserLoggedIn)
def handle_user_login(event):
    """Once a UserLoggedIn event is emitted, this function will be called."""
    # use your event data!
    print(f"User {event.user_id} logged in at {event.timestamp}")

# Bound method
class UserManager(EventAwareBase):
    @subscribe_method(UserLoggedIn)
    def on_user_login(self, event):
        """Once a UserLoggedIn event is emitted, this method will be called."""
        # use your event data here!
        print(f"UserManager noticed login: {event.user_id}")

    # !!IMPORTANT:
    # When you are subscribing a static or class method, you should always KNOW WHAT YOU ARE DOING since the subscription will be registered every time the class is instantiated.
    # This in most cases is not what you want.
    @subscribe_method(UserLoggedIn)
    @staticmethod
    def handle_user_login(event):
        """Static method can also be subscribed to events."""
        # use your event data here!
        pass

    @subscribe_method(UserLoggedIn)
    @classmethod
    def handle_user_login_cls(cls, event):
        """Class method can also be subscribed to events."""
        # use your event data here!
        pass

# Or also subscribe it by hand
register(handle_user_login, UserLoggedIn)
```

The regirstration of a bound method is realized by inherting from the `EventAwareBase` class, which provides a metaclass that automatically registers the class method as an event handler when the class is instantiated.

### Emit events

```python
if __name__ == "__main__":
    emit(UserLoggedIn(user_id=123, timestamp="2023-01-01 12:00:00"))
    # or anywhere else in your code
```

### Unsubscribe events

You can unsubscribe subscriptions in many ways:

```python
# Unsubscribe a function from an event type
unsubscribe(handle_user_login, UserLoggedIn)
# or
unsubscribe(a_user_manager_instance.handle_user_login, UserLoggedIn)

# Unsubscribe a function from all event types
unsubscribe(handle_user_login)

# Unsubscribe all functions from an event type
unsubscribe(UserLoggedIn)
```

It is critically important to unsubscribe subscriptions before deleting objects.

### Clear and halt

Use `clear` to remove all subscriptions and `halt` to stop the event system.

### Module System

Moduvent includes a dynamic module loader for plugin architecture:

```python
from moduvent import discover_modules

# Load all modules from the 'modules' directory (default)
discover_modules()

# Or specify a custom directory
discover_modules("plugins")
```

This will try to load all modules in the specified directory and register their event handlers if possible.

### Logging

By default, Moduvent uses [loguru](https://github.com/Delgan/loguru) for logging and all logging messages are hidden. You can configure the `logger` object to enable logging.

```python
# in your files
from loguru import logger

# This is strongly recommended to avoid duplicate logs
# For more info, see: https://loguru.readthedocs.io/en/stable/resources/troubleshooting.html#why-are-my-logs-duplicated-in-the-output
logger.remove()

# add your own handlers
logger.add(...)
```

When it comes to detailed configuration, please refer to the [loguru documentation](https://loguru.readthedocs.io/en/stable/overview.html).

## API Reference

TODO

### Module Structure

Modules should be placed in a directory (default: modules) with a structure similar as the following:

```text
modules/
    analytics/
        __init__.py
        events.py
        ...
    auth/
        __init__.py
        ...
    notifications/
        __init__.py
        ...
```

## Configuration

Moduvent uses [loguru](https://github.com/Delgan/loguru) for logging, which can be configured using the `logger` object.

```python
from moduvent import logger

# Intercept standard logging
logger.add(
    "moduvent.log",
    rotation="10 MB",
    retention="10 days",
    level="DEBUG"
)
```

## TODOs

- Event priorities and consequences

- Customized exception handling

- Cached callbacks

- Optimized data structures of _subscriptions

- Handling duplicate subscriptions

- Documentation of events

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.
