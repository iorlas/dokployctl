.PHONY: lint fix test check build bootstrap coverage-diff

check: lint test

lint:
	@uv run ruff format --check || (echo "Formatting issues found. Run 'make fix' to auto-fix." && exit 1)
	@uv run ruff check || (echo "Lint issues found. Fixable ones can be resolved with 'make fix'." && exit 1)
	@git ls-files '*.py' | xargs awk 'ENDFILE{if(FNR>500){print FILENAME": "FNR" lines (max 500)" > "/dev/stderr"; err=1}} END{exit err}'
	@conftest test pyproject.toml -p .harness/policy/python/ --all-namespaces
	@conftest test .gitignore --parser ignore -p .harness/policy/gitignore/ --all-namespaces

fix:
	uv run ruff check --fix
	uv run ruff format
	$(MAKE) lint

test:
	uv run pytest tests/

coverage-diff:
	uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=95

bootstrap:
	uv sync
	@command -v prek >/dev/null 2>&1 && prek install || (command -v pre-commit >/dev/null 2>&1 && pre-commit install || echo "Install prek: brew install prek")
	@echo "Dev environment ready. Run 'make lint' to verify."

build:
	uv build
