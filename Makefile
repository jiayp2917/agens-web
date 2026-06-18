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
	uvicorn web.backend.app:app --host 127.0.0.1 --port 8000 --reload

smoke:
	python -m compileall -q src tests web
	python -m pytest -q tests/web

clean:
	rm -rf runtime/artifacts/* runtime/checkpoints/* runtime/logs/* runtime/web/*
	find . -type d -name __pycache__ -exec rm -rf {} +
