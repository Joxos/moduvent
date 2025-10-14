from moduvent import signal, subscribe


@subscribe(signal("test"))
def handle_test(e):
    print("handle in file 1.")
