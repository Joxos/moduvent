import os

from moduvent import discover_modules, emit, module_loader, signal


def discover_modules_main(modules_dir):
    discover_modules(modules_dir)

    emit(signal("test")())
    assert {"module_1.file_1", "module_2", "file_3"}.issubset(
        module_loader.loaded_modules
    )


if __name__ == "__main__":
    discover_modules_main(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "example_modules")
    )
