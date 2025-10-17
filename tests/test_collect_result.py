from moduvent import emit, signal, subscribe

sig = signal("sig")


@subscribe(sig)
def handler1(data):
    return "handler1"


@subscribe(sig)
def handler2(data):
    return "handler2"


@subscribe(sig, lambda sig: sig.sender == "sender1")
def handler3(data):
    return "handler3"


def test_collect_result():
    assert emit(sig()) == ["handler1", "handler2"]


if __name__ == "__main__":
    test_collect_result()
