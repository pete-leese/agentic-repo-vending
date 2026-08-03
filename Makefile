.PHONY: help sync lint format format-check typecheck test doctor hooks ci

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

sync: ## Install runtime + dev + cursor + otel extras via uv
	uv sync --group dev --extra cursor --extra otel

lint: ## Ruff lint
	uv run ruff check .

format: ## Ruff format (write)
	uv run ruff format .

format-check: ## Ruff format (check only)
	uv run ruff format --check .

typecheck: ## Mypy on naming/spec/workflow
	uv run mypy src/repo_vendor/naming.py src/repo_vendor/spec.py src/repo_vendor/workflow.py

test: ## Pytest with coverage gate
	uv run pytest

doctor: ## Config / secrets readiness
	uv run python -m repo_vendor doctor

hooks: ## Install git pre-commit + pre-push hooks
	uv run pre-commit install --hook-types pre-commit --hook-types pre-push || \
		pre-commit install --hook-types pre-commit --hook-types pre-push

ci: lint format-check typecheck test ## Local equivalent of GitHub Actions ci.yml
