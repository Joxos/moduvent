from moduvent import EventAwareBase, Event, event_manager, subscribe_classmethod, unsubscribe, subscribe

class TestEvent(Event):
    def __init__(self, data):
        self.data = data

class Test(EventAwareBase):
    def __init__(self, event_manager, name):
        super().__init__(event_manager)
        self.name = name

    @subscribe_classmethod(TestEvent)
    def on_test_event(self, event: TestEvent):
        print(f"{event.data} from on_test_event of {self.name}")

@subscribe(TestEvent)
def test_func(event: TestEvent):
    print(f"{event.data} from test_func")

if __name__ == '__main__':
    alice = Test(event_manager, 'Alice')
    bob = Test(event_manager, 'Bob')
    event_manager.emit(TestEvent('hello'))
    unsubscribe(alice.on_test_event, TestEvent)
    event_manager.emit(TestEvent('hello without Alice'))