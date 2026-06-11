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
	python -m agens_novel.cli run --input "$(INPUT)"

smoke:
	python -m agens_novel.cli init
	python -m agens_novel.cli status

clean:
	rm -rf runtime/artifacts/* runtime/checkpoints/* runtime/logs/*
	find . -type d -name __pycache__ -exec rm -rf {} +
