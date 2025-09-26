from .async_moduvent import AsyncEventAwareBase, AsyncEventManager
from .common import ModuleLoader, subscribe_method
from .events import DataEvent, DataEventFactory, Event, Signal, SignalFactory
from .moduvent import EventAwareBase, EventManager

event_manager = EventManager()
verbose_subscriptions = event_manager.verbose_subscriptions
register = event_manager.register
subscribe = event_manager.subscribe
unsubscribe = event_manager.unsubscribe
emit = event_manager.emit

aevent_manager = AsyncEventManager()
averbose_subscriptions = aevent_manager.verbose_subscriptions
aregister = aevent_manager.register
asubscribe = aevent_manager.subscribe
aunsubscribe = aevent_manager.unsubscribe
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
    unsubscribe,
    emit,
    AsyncEventManager,
    AsyncEventAwareBase,
    aevent_manager,
    aregister,
    asubscribe,
    aunsubscribe,
    module_loader,
    discover_modules,
    Signal,
    signal,
    DataEvent,
    data_event,
]
