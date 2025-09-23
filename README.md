# Moduvent - Python Event-Driven Framework

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

Everything below can be imporrted from the `moduvent` package.

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
remove_callback(handle_user_login, UserLoggedIn)
# or
remove_callback(a_user_manager_instance.handle_user_login, UserLoggedIn)

# Unsubscribe a function from all event types
remove_function(handle_user_login)

# Unsubscribe all functions from an event type
clear_event_type(UserLoggedIn)
```

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

## API Reference

### Core Classes

- `Event`: Base class for all events

- `EventManager`: Central event system coordinator

- `EventAwareBase`: Base class for event-handling components

- `ModuleLoader`: Dynamic module loader

### Decorators

- `subscribe(*event_types)`: Decorator for functions to subscribe to events

- `subscribe_method(*event_types)`: Decorator for class methods

### Functions

- `register(func: Callable[[Event], None], event_type: Type[Event])`: Register a function as an event handler

- `emit(event)`: Emit an event to all subscribers

- `discover_modules(modules_dir="modules")`: Discover and load modules from a directory

- `remove_callback(func: Callable[[Event], None], event_type: Type[Event])`: Unsubscribe a function from an event type

- `remove_function(func: Callable[[Event], None])`: Unsubscribe a function from all event types

- `clear_event_type(event_type: Type[Event])`: Unsubscribe all functions from an event type

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

- Event filters

- Event priorities and consequences

- Customized callback arguments

- Customized exceptions handling

- Cached callbacks

- Optimized data structures of _subscriptions

- Weak references

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.
