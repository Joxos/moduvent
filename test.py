from moduvent import EventAwareBase, Event, event_manager, subscribe_classmethod, unsubscribe

class TestEvent(Event):
    def __init__(self, data):
        self.data = data

class Test(EventAwareBase):
    def __init__(self, event_manager):
        super().__init__(event_manager)

    @subscribe_classmethod(TestEvent)
    def on_test_event(self, event: TestEvent):
        print(event.data)

if __name__ == '__main__':
    test = Test(event_manager)
    event_manager.emit(TestEvent('hello'))
    unsubscribe(test.on_test_event, TestEvent)
    event_manager.emit(TestEvent('bye'))