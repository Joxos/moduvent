import weakref
from typing import Callable, Type
from .events import Event
from .utils import check_function_type, FunctionTypes, is_class_and_subclass, is_instance_and_subclass

class Checker:
    conditions: list[Callable[[Event], bool]] = []
    error_message = "{value} with {value_type} type is invalid for {name} attribute"
    error_type = TypeError

    def __set_name__(self, owner, name):
        self.public_name = name
        self.private_name = f"_{name}"
        setattr(owner, self.private_name, None)

    def __set__(self, obj: object, value: Type[Event] | None):
        for condition in self.conditions:
            if not condition(value):
                raise self.error_type(
                    self.error_message.format(
                        name=self.public_name,
                        value=value,
                        value_type=type(value),
                    )
                )
        setattr(obj, self.private_name, value)

    def __get__(self, obj, objtype=None):
        return getattr(obj, self.private_name)


class EventInheritor(Checker):
    conditions = [is_class_and_subclass]
    error_message = (
        "{value} with {value_type} type is not an inheritor of base event class"
    )


class EventInstance(Checker):
    conditions = [is_instance_and_subclass]
    error_message = "{value} with {value_type} type is not an instance of an inheritor of base event class"


class WeakReference:
    def __set__(self, obj, value):
        if obj is not None:
            if value is None:
                obj._func_ref = None
                raise ValueError(f"Cannot set weak reference of None to {obj}")
            elif check_function_type(value) == FunctionTypes.BOUND_METHOD:
                obj._func_ref = weakref.WeakMethod(value)
            else:
                try:
                    obj._func_ref = weakref.ref(value)
                except TypeError as e:
                    raise TypeError(
                        f"Cannot set weak reference of {value} to {obj}"
                    ) from e

    def __get__(self, obj, objtype=None):
        ref = obj._func_ref
        return None if ref is None else ref()
