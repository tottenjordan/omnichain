# Code Standards

Standards that must be adhered to in this project when writing code and making
environment changes. This is a living document — extend it as conventions are
established.

## Git & commits

- **Never** add `Co-Authored-By` trailers to commits or PRs.

## Python

- **Package management:** use [`uv`](https://docs.astral.sh/uv/) for everything.
  Never invoke bare `pip` or `python` — use `uv add`/`uv remove`/`uv sync` and
  `uv run <cmd>`.
- **Lint + format:** use [`ruff`](https://docs.astral.sh/ruff/) for both. Never
  use `black`, `flake8`, or `isort`.
- **Type checking:** use [`ty`](https://github.com/astral-sh/ty).
- Standalone scripts: use PEP 723 inline metadata, not `requirements.txt`.
- Dev/test deps go in `[dependency-groups]`, not `[project.optional-dependencies]`.

## Testing

- Use [`pytest`](https://docs.pytest.org/) for tests.
- Use `ty` for type checking as part of the test/verification workflow.
- Run tests via `uv run pytest`.

## Reference

- Follow the **`modern-python`** skill for project setup, tooling, and migration
  details (uv, ruff, ty, pytest, dependency groups, `pyproject.toml`). It is the
  authoritative source for the specifics behind the rules above.
