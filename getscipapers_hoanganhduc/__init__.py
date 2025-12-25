"""Top-level package wiring for :mod:`getscipapers_hoanganhduc`.

This module exposes metadata, a convenience ``main`` entry point, and a small
dynamic loader so that subcommands like ``getpapers`` and ``request`` can be
invoked via ``python -m getscipapers_hoanganhduc <module>``. The import logic is
kept lightweight to avoid side effects at startup; individual modules own their
configuration and heavy dependencies.
"""

import os
import importlib
from pathlib import Path
import sys
import argparse
import asyncio
import inspect
import platform

__version__ = "0.1.4"
__author__ = "Duc A. Hoang (hoanganhduc)"
__email__ = "anhduc.hoang1990@gmail.com"
__description__ = "A Python package to get and request scientific papers from various sources"

_AUTOLOAD_SKIP = {"zlibrary", "gui"}

# Automatically import all Python modules in this directory except heavy/interactive ones
_current_dir = Path(__file__).parent
for _file in _current_dir.glob("*.py"):
    if (
        _file.name != "__init__.py"
        and not _file.name.startswith("_")
        and _file.stem.lower() not in _AUTOLOAD_SKIP
    ):
        _module_name = _file.stem
        try:
            importlib.import_module(f".{_module_name}", package=__name__)
        except ImportError:
            pass

def main():
    """Main entry point for the getscipapers package."""

    if platform.system() == "Windows":
        # Prefer the selector policy to avoid Proactor cleanup warnings on exit
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Check if we're being called with a module name as first argument
    if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
        module_name = sys.argv[1]

        # Get available modules, excluding interactive or optional imports handled elsewhere
        available_modules = []
        _current_dir = Path(__file__).parent
        for _file in _current_dir.glob("*.py"):
            if (
                _file.name != "__init__.py"
                and not _file.name.startswith("_")
                and _file.stem.lower() not in {"zlibrary"}
            ):
                available_modules.append(_file.stem)
        
        if module_name in available_modules:
            try:
                # Remove the module name from sys.argv so the module can parse its own args
                sys.argv = [sys.argv[0]] + sys.argv[2:]
                
                module = importlib.import_module(f".{module_name}", package=__name__)
                if hasattr(module, 'main'):
                    main_func = getattr(module, 'main')
                    if inspect.iscoroutinefunction(main_func):
                        asyncio.run(main_func())
                    else:
                        main_func()
                else:
                    print(f"Module '{module_name}' has no main() function")
                return
            except ImportError as e:
                print(f"Error importing module '{module_name}': {e}")
                return
    
    # Default behavior - show help
    parser = argparse.ArgumentParser(description=__description__)
    parser.add_argument('module', nargs='?', help='Module name to execute')
    parser.add_argument('--list', action='store_true', help='List available modules')
    parser.add_argument('--version', action='version', version=f'getscipapers {__version__}')
    
    args = parser.parse_args()
    
    if args.list:
        # Get available modules, excluding Zlibrary
        available_modules = []
        _current_dir = Path(__file__).parent
        for _file in _current_dir.glob("*.py"):
            if (
                _file.name != "__init__.py"
                and not _file.name.startswith("_")
                and _file.stem.lower() != "zlibrary"
            ):
                available_modules.append(_file.stem)
        
        print("Available modules:")
        for module in available_modules:
            print(f"  - {module}")
        print(f"\nTo know how to execute a module, use: {os.path.basename(sys.argv[0])} module_name --help")
        return
    
    print(f"getscipapers v{__version__}")
    print(f"Author: {__author__}")
    print(f"Description: {__description__}")
    print("\nUse --help for usage information")
    print(f"To execute a module, use: {os.path.basename(sys.argv[0])} module_name [module_args]")
    print(f"To list available modules, use: {os.path.basename(sys.argv[0])} --list")

if __name__ == "__main__":
    main()

__all__ = [
    "__version__",
    "__author__", 
    "__email__",
    "__description__",
    "main"
]
