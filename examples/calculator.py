import random

from loguru import logger

from moduvent import (
    Event,
    EventAwareBase,
    EventFactory,
    data_event,
    emit,
    subscribe,
    subscribe_method,
)

logger.remove()


class BinaryCalculation(Event):
    def __init__(self, id: int, a: float, b: float):
        self.id = id
        self.a = a
        self.b = b
        self.string = ""


BinaryCalculationFactory = EventFactory.create(BinaryCalculation)
binary_calculation = BinaryCalculationFactory.new
Addition = binary_calculation("Addition")
Subtraction = binary_calculation("Subtraction")
Multiplication = binary_calculation("Multiplication")
Division = binary_calculation("Division")
Exponentiation = binary_calculation("Exponentiation")
ResultBroadcast = data_event("ResultBroadcast")


class Calculator(EventAwareBase):
    def __init__(self, name: str, event_manager=None):
        super().__init__(event_manager)
        self.name = name

    @subscribe_method(Addition)
    def add(self, event: BinaryCalculation):
        emit(ResultBroadcast(data=event.a + event.b, sender=f"{event.a} + {event.b}"))

    @subscribe_method(Subtraction)
    def subtract(self, event: BinaryCalculation):
        emit(ResultBroadcast(data=event.a - event.b, sender=f"{event.a} - {event.b}"))

    @subscribe_method(Multiplication)
    def multiply(self, event: BinaryCalculation):
        emit(ResultBroadcast(data=event.a * event.b, sender=f"{event.a} * {event.b}"))

    @subscribe_method(Division)
    def divide(self, event: BinaryCalculation):
        emit(ResultBroadcast(data=event.a / event.b, sender=f"{event.a} / {event.b}"))

    @subscribe_method(Exponentiation)
    def exponentiate(self, event: BinaryCalculation):
        emit(ResultBroadcast(data=event.a**event.b, sender=f"{event.a} ** {event.b}"))


@subscribe(ResultBroadcast)
def show_result(event: ResultBroadcast):
    print(f"{event.sender} = {event.data}")


if __name__ == "__main__":
    # calculator_num = 5
    # calculators = [Calculator(f"Calculator {i}") for i in range(calculator_num)]
    calculator = Calculator("Calculator")
    calculation_types = [
        Addition,
        Subtraction,
        Multiplication,
        Division,
        Exponentiation,
    ]
    generate_times = 20

    for i in range(generate_times):
        calc_type = random.choice(calculation_types)
        calc_id = i
        calc_a = int(random.random() * 10 + 1)
        calc_b = int(random.random() * 10 + 1)
        emit(calc_type(id=calc_id, a=calc_a, b=calc_b))
