.PHONY: lint fix test check build bootstrap coverage-diff

check: lint test

lint:
	@agent-harness lint

fix:
	@agent-harness fix

test:
	@uv run pytest tests/

coverage-diff:
	@uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=95

bootstrap:
	uv sync
	@command -v agent-harness >/dev/null 2>&1 || (echo "Install agent-harness: uv tool install agent-harness" && exit 1)
	@command -v prek >/dev/null 2>&1 && prek install || (command -v pre-commit >/dev/null 2>&1 && pre-commit install || echo "Install prek: brew install prek")
	@echo "Dev environment ready. Run 'make lint' to verify."

build:
	uv build
