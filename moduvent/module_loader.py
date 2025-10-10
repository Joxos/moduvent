import importlib
from pathlib import Path

from loguru import logger

module_logger = logger.bind(source="moduvent_module_loader")


class ModuleLoader:
    def __init__(self):
        self.loaded_modules = set()

    def discover_modules(self, modules_dir: str = "modules"):
        modules_path = Path(modules_dir)

        if not modules_path.exists():
            module_logger.warning(f"Module directory does not exist: {modules_dir}")
            return

        for item in modules_path.iterdir():
            if item.is_dir() and not item.name.startswith("__"):
                try:
                    module_name = f"{modules_dir}.{item.name}"
                    self.load_module(module_name)
                    module_logger.debug(f"Discovered module: {module_name}")
                except ImportError as e:
                    module_logger.error(f"Failed to load module {item.name}: {e}")
                except Exception as ex:
                    module_logger.exception(
                        f"Unexpected error occurred while loading module {item.name}: {ex}"
                    )

    def load_module(self, module_name: str):
        if module_name in self.loaded_modules:
            module_logger.debug(f"Module already loaded: {module_name}")
            return

        try:
            importlib.import_module(module_name)
            self.loaded_modules.add(module_name)
            module_logger.debug(f"Successfully loaded module: {module_name}")

        except ImportError as e:
            module_logger.exception(f"Error while loading module {module_name}: {e}")
