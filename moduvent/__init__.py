from .moduvent import (Event, EventAwareBase, EventManager, ModuleLoader,
                       logger, subscribe_classmethod)

event_manager = EventManager()
module_loader = ModuleLoader(event_manager=event_manager)
discover_modules = module_loader.discover_modules
subscribe = event_manager.subscribe
unsubscribe = event_manager.unsubscribe
unsubscribe_instance = event_manager.unsubscribe_instance
unsubscribe_all = event_manager.remove_function
clear_event_type = event_manager.clear_event_type
emit = event_manager.emit

__all__ = [
    EventAwareBase,
    EventManager,
    Event,
    ModuleLoader,
    discover_modules,
    subscribe,
    subscribe_classmethod,
    emit,
    event_manager,
    module_loader,
    logger,
    unsubscribe,
    unsubscribe_instance,
    unsubscribe_all,
]
