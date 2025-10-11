import importlib
import os
import sys
from pathlib import Path

from loguru import logger

module_logger = logger.bind(source="moduvent_module_loader")


def path_to_import(path):
    """Convert file path to import path"""
    normalized_path = os.path.normpath(path)
    path_obj = Path(normalized_path)

    if path_obj.suffix == ".py":
        path_obj = path_obj.with_suffix("")

    import_path = str(path_obj).replace(os.sep, ".")

    if import_path.startswith("."):
        import_path = import_path.lstrip(".")

    module_logger.debug(f"Converted path '{path}' to import '{import_path}'")
    return import_path.strip(".")


class ModuleLoader:
    def __init__(self):
        self.loaded_modules = set()

    def _discover_item(self, item_path, base_path):
        """Discover and load a single item (file or directory)"""
        item = Path(item_path)

        skip_patterns = ["__", "."]
        if any(
            item.name.startswith(pattern) or item.name == pattern
            for pattern in skip_patterns
        ):
            return

        try:
            if item.is_dir():
                if (item / "__init__.py").exists():
                    module_logger.debug(f"Discovered module: {item.name}")
                    rel_path = item.relative_to(base_path)
                    self.load_module(path_to_import(str(rel_path)))
                else:
                    module_logger.debug(f"Discovered namespace module: {item.name}")
                    self._discover_directory(item, base_path)
            elif item.suffix == ".py":
                rel_path = item.relative_to(base_path)
                import_path = path_to_import(str(rel_path))
                module_logger.debug(f"Discovered file: {import_path}")
                self.load_module(import_path)
            else:
                module_logger.debug(f"Skipping non-python file: {item}")
        except ImportError as e:
            module_logger.error(f"Failed to load module {item.name}: {e}")
        except Exception as ex:
            module_logger.exception(f"Unexpected error loading {item.name}: {ex}")

    def _discover_directory(self, directory, base_path):
        for item in directory.iterdir():
            self._discover_item(item, base_path)

    def discover_modules(self, path: str = "./modules"):
        """Discover and load modules from given path"""
        path_obj = Path(path)

        if not path_obj.exists():
            raise FileNotFoundError(f"Module directory does not exist: {path}")

        abs_path = path_obj.resolve()
        module_logger.debug(f"Discovering modules in: {abs_path}")

        if str(abs_path) not in sys.path:
            sys.path.insert(0, str(abs_path))
            module_logger.debug(f"Added to sys.path: {abs_path}")

        for item in abs_path.iterdir():
            self._discover_item(item, abs_path)

    def load_module(self, module_name: str):
        """Load a module by name"""
        if module_name in self.loaded_modules:
            module_logger.debug(f"Module already loaded: {module_name}")
            return

        try:
            module_logger.debug(f"Attempting to import: {module_name}")
            importlib.import_module(module_name)
            self.loaded_modules.add(module_name)
            module_logger.debug(f"{module_name} successfully loaded.")
        except ImportError as e:
            module_logger.exception(f"Error loading module {module_name}: {e}")
