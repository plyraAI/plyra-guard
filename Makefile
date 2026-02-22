.PHONY: install dev test test-cov lint format typecheck clean serve
.PHONY: precommit-install precommit-run build
.PHONY: example-basic example-policies example-multiagent example-langchain example-async

install:
	pip install -e .

dev:
	pip install -e ".[dev,sidecar]"

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=plyra_guard --cov-report=term-missing

lint:
	ruff check plyra_guard/ tests/
	ruff format --check plyra_guard/ tests/

format:
	ruff format plyra_guard/ tests/

typecheck:
	mypy plyra_guard/ --ignore-missing-imports

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build:
	python -m build

serve:
	plyra-guard serve --config guard_config.example.yaml

precommit-install:
	pre-commit install

precommit-run:
	pre-commit run --all-files

example-basic:
	python examples/single_agent_basic.py

example-policies:
	python examples/single_agent_with_policies.py

example-multiagent:
	python examples/multiagent_orchestrator.py

example-langchain:
	python examples/langchain_integration.py

example-async:
	python examples/async_agent.py
