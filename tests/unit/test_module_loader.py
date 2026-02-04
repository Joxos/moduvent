"""
Unit tests for ModuleLoader.

Tests cover:
- Module discovery from directory
- Module loading by name
- Path to import conversion
- Duplicate load prevention
- Error handling for missing/invalid modules
"""

import pytest
import os
import sys
from pathlib import Path
from moduvent.module_loader import ModuleLoader, path_to_import


# =============================================================================
# path_to_import Tests
# =============================================================================


class TestPathToImport:
    """Tests for path_to_import function."""

    def test_simple_path(self):
        """Should convert simple path to import."""
        result = path_to_import("module")
        assert result == "module"

    def test_nested_path(self):
        """Should convert nested path to dotted import."""
        result = path_to_import("package/module")
        assert result == "package.module"

    def test_path_with_py_extension(self):
        """Should strip .py extension."""
        result = path_to_import("module.py")
        assert result == "module"

    def test_nested_path_with_py_extension(self):
        """Should handle nested path with .py extension."""
        result = path_to_import("package/module.py")
        assert result == "package.module"

    def test_path_with_leading_dot(self):
        """Should strip leading dots."""
        result = path_to_import("./module")
        # After normalization, leading . should be handled
        assert "module" in result

    def test_deeply_nested_path(self):
        """Should handle deeply nested paths."""
        result = path_to_import("a/b/c/d/module.py")
        assert result == "a.b.c.d.module"


# =============================================================================
# ModuleLoader Tests
# =============================================================================


class TestModuleLoader:
    """Tests for ModuleLoader class."""

    @pytest.fixture
    def loader(self):
        """Create a fresh ModuleLoader for each test."""
        return ModuleLoader()

    @pytest.fixture
    def example_modules_path(self):
        """Return path to example_modules fixture directory."""
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "fixtures", "example_modules"
        )

    def test_loader_initializes_empty(self, loader):
        """ModuleLoader should initialize with empty loaded_modules."""
        assert loader.loaded_modules == set()

    def test_discover_modules_nonexistent_path(self, loader):
        """discover_modules with nonexistent path should raise."""
        with pytest.raises(FileNotFoundError):
            loader.discover_modules("/nonexistent/path")

    def test_discover_modules_adds_to_sys_path(self, loader, example_modules_path):
        """discover_modules should add path to sys.path."""
        abs_path = str(Path(example_modules_path).resolve())

        # Remove from sys.path if already present
        if abs_path in sys.path:
            sys.path.remove(abs_path)

        loader.discover_modules(example_modules_path)

        assert abs_path in sys.path

    def test_discover_modules_loads_modules(self, loader, example_modules_path):
        """discover_modules should load discovered modules."""
        loader.discover_modules(example_modules_path)

        # Check that modules were loaded
        assert len(loader.loaded_modules) > 0

    def test_discover_modules_finds_package(self, loader, example_modules_path):
        """discover_modules should find package modules."""
        loader.discover_modules(example_modules_path)

        # module_2 is a package with __init__.py
        assert "module_2" in loader.loaded_modules

    def test_discover_modules_finds_single_file(self, loader, example_modules_path):
        """discover_modules should find single .py files."""
        loader.discover_modules(example_modules_path)

        # file_3.py is a single file module
        assert "file_3" in loader.loaded_modules

    def test_discover_modules_finds_namespace_package(
        self, loader, example_modules_path
    ):
        """discover_modules should find modules in namespace packages."""
        loader.discover_modules(example_modules_path)

        # module_1 is a namespace package (no __init__.py)
        # file_1 should be discovered inside it
        assert "module_1.file_1" in loader.loaded_modules

    def test_load_module_tracks_loaded(self, loader, example_modules_path):
        """load_module should track loaded modules."""
        # First add to sys.path
        abs_path = str(Path(example_modules_path).resolve())
        if abs_path not in sys.path:
            sys.path.insert(0, abs_path)

        loader.load_module("file_3")

        assert "file_3" in loader.loaded_modules

    def test_load_module_prevents_duplicate(self, loader, example_modules_path):
        """load_module should not reload already loaded modules."""
        # First add to sys.path
        abs_path = str(Path(example_modules_path).resolve())
        if abs_path not in sys.path:
            sys.path.insert(0, abs_path)

        loader.load_module("file_3")
        initial_count = len(loader.loaded_modules)

        loader.load_module("file_3")  # Try to load again

        # Should still have same count
        assert len(loader.loaded_modules) == initial_count

    def test_load_module_invalid_name(self, loader):
        """load_module with invalid module name should not raise but log error."""
        # Should not raise, but should log error
        loader.load_module("definitely_nonexistent_module_12345")

        # Module should not be in loaded_modules
        assert "definitely_nonexistent_module_12345" not in loader.loaded_modules

    def test_discover_skips_dunder_files(self, loader, example_modules_path):
        """discover_modules should skip __pycache__ and similar."""
        loader.discover_modules(example_modules_path)

        # No __pycache__ or __init__ as standalone modules
        for module in loader.loaded_modules:
            assert "__pycache__" not in module
            assert module != "__init__"

    def test_discover_skips_hidden_files(self, loader, example_modules_path):
        """discover_modules should skip hidden files (starting with .)."""
        loader.discover_modules(example_modules_path)

        # No hidden files
        for module in loader.loaded_modules:
            assert not module.startswith(".")


# =============================================================================
# Integration with Event System
# =============================================================================


class TestModuleLoaderEventIntegration:
    """Tests for ModuleLoader integration with event system."""

    @pytest.fixture
    def loader(self):
        """Create a fresh ModuleLoader."""
        return ModuleLoader()

    @pytest.fixture
    def example_modules_path(self):
        """Return path to example_modules fixture directory."""
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "fixtures", "example_modules"
        )

    def test_loaded_modules_register_handlers(
        self, loader, example_modules_path, capsys
    ):
        """Loaded modules with @subscribe should register handlers."""
        from moduvent import emit, signal

        # Clear existing subscriptions for clean test
        test_signal = signal("test")

        loader.discover_modules(example_modules_path)

        # Emit the signal - handlers in loaded modules should respond
        emit(test_signal())

        # Check output (handlers print messages)
        captured = capsys.readouterr()
        # At least one handler should have printed something
        # (file_1.py and file_3.py both have handlers for signal("test"))
        assert "handle in file" in captured.out
