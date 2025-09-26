from .async_moduvent import AsyncEventAwareBase, AsyncEventManager
from .common import ModuleLoader, subscribe_method
from .moduvent import EventAwareBase, EventManager
from .events import Event, Signal, SignalFactory, DataEvent, DataEventFactory

event_manager = EventManager()
verbose_subscriptions = event_manager.verbose_subscriptions
register = event_manager.register
subscribe = event_manager.subscribe
remove_callback = event_manager.remove_callback
remove_function = event_manager.remove_function
clear_event_type = event_manager.clear_event_type
emit = event_manager.emit

aevent_manager = AsyncEventManager()
averbose_subscriptions = aevent_manager.verbose_subscriptions
aregister = aevent_manager.register
asubscribe = aevent_manager.subscribe
aremove_callback = aevent_manager.remove_callback
aremove_function = aevent_manager.remove_function
aclear_event_type = aevent_manager.clear_event_type
aemit = aevent_manager.emit

module_loader = ModuleLoader()
discover_modules = module_loader.discover_modules
signal = SignalFactory.new
data_event = DataEventFactory.new

__all__ = [
    EventAwareBase,
    EventManager,
    Event,
    DataEvent,
    ModuleLoader,
    register,
    subscribe,
    subscribe_method,
    remove_callback,
    remove_function,
    clear_event_type,
    emit,
    AsyncEventManager,
    AsyncEventAwareBase,
    aevent_manager,
    aregister,
    asubscribe,
    aremove_callback,
    aremove_function,
    aclear_event_type,
    module_loader,
    discover_modules,
    Signal,
    signal,
    DataEvent,
    data_event,
]
