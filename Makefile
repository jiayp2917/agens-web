.PHONY: install test lint format smoke run clean

install:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check src tests

format:
	ruff format src tests

run:
	python mobile/main.py

smoke:
	python -m compileall -q src tests mobile/main.py mobile/audio_manager.py mobile/screens mobile/widgets mobile/service demo_full_flow.py
	python -m pytest -q tests/unit/test_mobile_startup.py tests/unit/test_buildozer_spec.py

clean:
	rm -rf runtime/artifacts/* runtime/checkpoints/* runtime/logs/*
	find . -type d -name __pycache__ -exec rm -rf {} +
