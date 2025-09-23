from moduvent import (Event, EventAwareBase, clear_event_type, event_manager,
                      register, remove_callback, remove_function, subscribe,
                      subscribe_method)


class TestEvent_1(Event):
    def __init__(self, data):
        self.data = data


class TestEvent_2(Event):
    def __init__(self, data):
        self.data = data


class TestClass_1(EventAwareBase):
    name: str = "default"

    def __init__(self, event_manager, name):
        super().__init__(event_manager)
        self.name = name

    @subscribe_method(TestEvent_1)
    def on_test_event(self, event: TestEvent_1):
        print(f"{event.data} from on_test_event of {self.name}")

    @subscribe_method(TestEvent_2)
    @staticmethod
    def test_static_method(event: TestEvent_2):
        print(f"{event.data} from test_static_method")

    @subscribe_method(TestEvent_2)
    @classmethod
    def test_class_method(cls, event: TestEvent_2):
        print(f"{event.data} from test_class_method of {cls.name}")


@subscribe(TestEvent_1, TestEvent_2)
def test_func(event: TestEvent_1):
    print(f"{event.data} from test_func")


class TestException(Exception):
    pass


def test_error(event: TestEvent_1):
    raise TestException(f"test_error with {event.data}")


if __name__ == "__main__":
    alice = TestClass_1(event_manager, "Alice")
    bob = TestClass_1(event_manager, "Bob")
    event_manager.emit(TestEvent_1("hello"))

    remove_callback(alice.on_test_event, TestEvent_1)
    event_manager.emit(TestEvent_1("hello without Alice"))

    register(test_error, TestEvent_1)
    event_manager.emit(TestEvent_1("hello with test_error"))

    remove_callback(test_error, TestEvent_1)
    register(alice.on_test_event, TestEvent_1)
    event_manager.emit(TestEvent_1("hello with Alice again and without test_error"))

    remove_function(test_func)
    event_manager.emit(TestEvent_1("hello without test_func"))

    register(test_func, TestEvent_2)
    register(alice.on_test_event, TestEvent_2)
    event_manager.emit(TestEvent_2("hello from TestEvent_2"))

    clear_event_type(TestEvent_2)
    event_manager.emit(
        TestEvent_2("hello without TestEvent_2 (this should not be printed)")
    )
