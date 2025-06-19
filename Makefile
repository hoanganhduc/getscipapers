.PHONY: build install clean test lint help setup venv activate

# Variables
VENV_PATH = ~/.getscipapers
PACKAGE_NAME = getscipapers_hoanganhduc
VERSION = 0.1.0

# Default target
help:
	@echo "Available targets:"
	@echo "  setup    - Complete setup: create venv, install deps, build and install package"
	@echo "  venv     - Create virtual environment"
	@echo "  build    - Build the Python package"
	@echo "  install  - Install the package in development mode"
	@echo "  clean    - Remove build artifacts"
	@echo "  format   - Format code with black"
	@echo "  help     - Show this help message"

setup: venv
	@echo "Setting up getscipapers..."
	bash -c "source $(VENV_PATH)/bin/activate && \
		pip install --upgrade pip && \
		pip install build && \
		pip install -r requirements.txt && \
		python -m build"
	@echo "Setup completed successfully!"

venv:
	@echo "Creating virtual environment at $(VENV_PATH)..."
	python -m venv $(VENV_PATH)

build:
	python -m build

install:
	pip install -e .

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

format:
	python -m black .

dist: clean build
	@echo "Package built successfully"