# Contributing to plyra-guard

Thank you for your interest in contributing to plyra-guard, part of the Plyra agentic infrastructure suite! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Running Linting](#running-linting)
- [Branch Strategy](#branch-strategy)
- [Pull Request Requirements](#pull-request-requirements)
- [Commit Message Format](#commit-message-format)
- [How to Add a New Evaluator](#how-to-add-a-new-evaluator)
- [How to Add a New Adapter](#how-to-add-a-new-adapter)
- [How to Add a Rollback Handler](#how-to-add-a-rollback-handler)
- [Code Style](#code-style)

---

## Development Setup

We use [uv](https://github.com/astral-sh/uv) for dependency management:

```bash
# Clone the repository
git clone https://github.com/plyraAI/plyra-guard.git
cd actionguard

# Install all dependencies (including dev and optional extras)
uv sync --all-extras

# Or using pip
pip install -e ".[dev,sidecar]"

# Install pre-commit hooks
make precommit-install
```

## Running Tests

```bash
# Run all tests
make test

# Run tests with coverage
make test-cov

# Run a specific test file
pytest tests/unit/test_policy_engine.py -v

# Run tests matching a pattern
pytest tests/ -k "test_blocked" -v
```

## Running Linting

```bash
# Lint check (ruff + mypy)
make lint

# Auto-format code
make format

# Type check only
make typecheck

# Run all pre-commit hooks
make precommit-run
```

## Branch Strategy

```
main        ← stable releases only, protected
  ↑
develop     ← active development, CI must pass
  ↑
feature/*   ← individual features/fixes
```

- **`main`** — Stable, tagged releases. Never commit directly.
- **`develop`** — Integration branch. All PRs target here.
- **`feature/*`** — Short-lived feature branches off `develop`.
- **`fix/*`** — Bug fix branches off `develop`.
- **`release/*`** — Release preparation branches (version bumps, changelog).

## Pull Request Requirements

Before submitting a PR:

1. **All tests must pass**: `pytest tests/ -v --tb=short`
2. **Coverage must not drop**: check with `make test-cov`
3. **Linting must pass**: `make lint`
4. **Formatting must pass**: `ruff format --check .`
5. **Type checking must pass**: `make typecheck`
6. **Write tests** for any new functionality
7. **Update documentation** if changing public API

## Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

| Type       | Description                                 |
| ---------- | ------------------------------------------- |
| `feat`     | A new feature                               |
| `fix`      | A bug fix                                   |
| `docs`     | Documentation only                          |
| `chore`    | Build process, CI, dependencies             |
| `test`     | Adding or updating tests                    |
| `refactor` | Code change that neither fixes nor adds     |
| `perf`     | Performance improvement                     |
| `ci`       | CI configuration changes                    |

### Examples

```
feat(policy): add nested condition group support
fix(rate-limiter): prevent race condition under concurrent load
docs: update README quickstart example
test(budget): add concurrent budget aggregation tests
chore(ci): add Python 3.13 to test matrix
```

---

## How to Add a New Evaluator

Evaluators are the core pipeline components. To add one:

### Step 1 — Create the evaluator class

Create `plyra_guard/evaluators/my_evaluator.py`:

```python
from plyra_guard.core.intent import ActionIntent, EvaluatorResult
from plyra_guard.core.verdict import Verdict
from plyra_guard.evaluators.base import BaseEvaluator


class MyEvaluator(BaseEvaluator):
    """Describe what this evaluator checks."""

    @property
    def name(self) -> str:
        return "my_evaluator"

    @property
    def priority(self) -> int:
        return 35  # Lower = runs earlier in pipeline

    def evaluate(self, intent: ActionIntent) -> EvaluatorResult:
        # Your evaluation logic here
        if some_condition(intent):
            return EvaluatorResult(
                verdict=Verdict.BLOCK,
                reason="Why this was blocked",
                confidence=1.0,
                evaluator_name=self.name,
            )
        return EvaluatorResult(
            verdict=Verdict.ALLOW,
            reason="Check passed",
            confidence=1.0,
            evaluator_name=self.name,
        )
```

### Step 2 — Register in the pipeline

In `plyra_guard/core/guard.py`, add to `_setup_evaluators()`:

```python
my_eval = MyEvaluator(config_param=self._config.my_setting)
if ev_cfg.my_evaluator.enabled:
    self.pipeline.add(my_eval)
```

### Step 3 — Add configuration schema

In `plyra_guard/config/schema.py`, add toggle to `EvaluatorConfig`:

```python
my_evaluator: EvaluatorToggles = Field(
    default_factory=lambda: EvaluatorToggles(enabled=True)
)
```

### Step 4 — Write tests

Create `tests/unit/test_my_evaluator.py` with tests for:
- Normal allow case
- Blocking case
- Edge cases and error handling

### Step 5 — Export

Add to `plyra_guard/evaluators/__init__.py`:

```python
from plyra_guard.evaluators.my_evaluator import MyEvaluator
```

---

## How to Add a New Adapter

Adapters integrate plyra-guard with agent frameworks (LangChain, AutoGen, etc.).

### Step 1 — Create the adapter

Create `plyra_guard/adapters/my_framework.py`:

```python
from plyra_guard.adapters.base import BaseAdapter


class MyFrameworkAdapter(BaseAdapter):
    """Adapter for MyFramework tools."""

    @property
    def name(self) -> str:
        return "my_framework"

    def wrap_tool(self, tool, guard, action_type, **kwargs):
        """Wrap a MyFramework tool with plyra-guard protection."""
        # Framework-specific wrapping logic
        original_func = tool.run

        def guarded_run(*args, **kw):
            return guard._execute_guarded(
                intent=self._create_intent(tool, args, kw),
                func=original_func,
                args=args,
                kwargs=kw,
            )

        tool.run = guarded_run
        return tool
```

### Step 2 — Register in the adapter registry

Add to `plyra_guard/adapters/registry.py`.

### Step 3 — Add optional dependency

In `pyproject.toml`:

```toml
[project.optional-dependencies]
myframework = ["my-framework>=1.0"]
```

---

## How to Add a Rollback Handler

Rollback handlers enable automatic state restoration after blocked actions.

### Step 1 — Create the handler

Create `plyra_guard/rollback/handlers/my_handler.py`:

```python
from plyra_guard.rollback.handlers.base_handler import BaseRollbackHandler, Snapshot


class MyRollbackHandler(BaseRollbackHandler):
    """Rollback handler for MyService operations."""

    @property
    def name(self) -> str:
        return "my_service"

    def capture_snapshot(self, intent) -> Snapshot:
        """Capture state before the action executes."""
        current_state = my_service.get_state(intent.parameters)
        return Snapshot(
            action_id=intent.action_id,
            action_type=intent.action_type,
            data={"state": current_state},
        )

    def restore(self, snapshot: Snapshot) -> bool:
        """Restore the captured state."""
        my_service.set_state(snapshot.data["state"])
        return True
```

### Step 2 — Register for action types

```python
@guard.rollback_handler("my_service.update")
class MyHandler(BaseRollbackHandler):
    ...
```

---

## Code Style

- **Formatter**: [Ruff](https://docs.astral.sh/ruff/) — enforced in CI
- **Line length**: 88 characters
- **Target Python**: 3.11+
- **Docstrings**: Required on all public classes, methods, and functions
- **Type hints**: Required on all public API signatures
- **Imports**: Sorted by ruff (`isort` rules)

### Naming Conventions

| Item           | Convention          | Example                    |
| -------------- | ------------------- | -------------------------- |
| Classes        | `PascalCase`        | `PolicyEngine`             |
| Functions      | `snake_case`        | `evaluate_intent`          |
| Constants      | `UPPER_SNAKE_CASE`  | `MAX_DELEGATION_DEPTH`     |
| Private        | `_leading_underscore` | `_compile_condition`     |
| File names     | `snake_case.py`     | `rate_limiter.py`          |
| Test files     | `test_*.py`         | `test_policy_engine.py`    |

---

## Questions?

If you're unsure about anything, open a [discussion](https://github.com/plyraAI/plyra-guard/discussions) or ask in your PR. We're happy to help!
