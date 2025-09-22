from .moduvent import (Event, EventAwareBase, EventManager, ModuleLoader,
                       logger, subscribe_classmethod)

event_manager = EventManager()
register = event_manager.register
subscribe = event_manager.subscribe
remove_callback = event_manager.remove_callback
remove_function = event_manager.remove_function
clear_event_type = event_manager.clear_event_type
emit = event_manager.emit
module_loader = ModuleLoader(event_manager=event_manager)
discover_modules = module_loader.discover_modules

__all__ = [
    EventAwareBase,
    EventManager,
    Event,
    ModuleLoader,
    register,
    subscribe,
    subscribe_classmethod,
    remove_callback,
    remove_function,
    clear_event_type,
    emit,
    module_loader,
    discover_modules,
    logger,
]
