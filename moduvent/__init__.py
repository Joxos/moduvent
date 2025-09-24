from .async_moduvent import AsyncEventAwareBase, AsyncEventManager
from .common import Event, ModuleLoader, subscribe_method
from .moduvent import EventAwareBase, EventManager

event_manager = EventManager()
register = event_manager.register
subscribe = event_manager.subscribe
remove_callback = event_manager.remove_callback
remove_function = event_manager.remove_function
clear_event_type = event_manager.clear_event_type
emit = event_manager.emit

async_event_manager = AsyncEventManager()
async_register = async_event_manager.register
async_subscribe = async_event_manager.subscribe
async_remove_callback = async_event_manager.remove_callback
async_remove_function = async_event_manager.remove_function
async_clear_event_type = async_event_manager.clear_event_type
async_emit = async_event_manager.emit

module_loader = ModuleLoader()
discover_modules = module_loader.discover_modules

__all__ = [
    EventAwareBase,
    EventManager,
    Event,
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
    async_event_manager,
    async_register,
    async_subscribe,
    async_remove_callback,
    async_remove_function,
    async_clear_event_type,
    module_loader,
    discover_modules,
]
