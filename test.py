from moduvent import (
    EventAwareBase,
    Event,
    event_manager,
    subscribe_classmethod,
    remove_callback,
    subscribe,
    register,
    remove_function,
    clear_event_type,
)


class TestEvent_1(Event):
    def __init__(self, data):
        self.data = data


class TestEvent_2(Event):
    def __init__(self, data):
        self.data = data


class Test(EventAwareBase):
    def __init__(self, event_manager, name):
        super().__init__(event_manager)
        self.name = name

    @subscribe_classmethod(TestEvent_1)
    def on_test_event(self, event: TestEvent_1):
        print(f"{event.data} from on_test_event of {self.name}")


@subscribe(TestEvent_1, TestEvent_2)
def test_func(event: TestEvent_1):
    print(f"{event.data} from test_func")

def test_error(event: TestEvent_1):
    raise Exception("test_error")

if __name__ == "__main__":
    alice = Test(event_manager, "Alice")
    bob = Test(event_manager, "Bob")
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
