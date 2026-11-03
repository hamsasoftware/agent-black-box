.DEFAULT_GOAL := help
SHELL := /bin/bash

VENV ?= .venv
PYTHON ?= python3
VENV_PY := $(VENV)/bin/python
PY := $(if $(wildcard $(VENV_PY)),$(VENV_PY),$(PYTHON))
TASK ?=
VARIANT ?= bare

.PHONY: help setup test scan lint facts run-task report labels clean

help: ## List the available commands
	@echo "Usage: make <target> [VAR=value]"
	@echo
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "Variables: TASK=<task-id>  VARIANT=bare|plumbed (default bare)"

setup: ## Create .venv and install the project with its dev tools
	$(PYTHON) -m venv $(VENV)
	$(VENV_PY) -m pip install --quiet --upgrade pip
	@if [ -f pyproject.toml ]; then \
		$(VENV_PY) -m pip install --quiet -e ".[dev]" || $(VENV_PY) -m pip install --quiet -e .; \
	fi
	$(VENV_PY) -m pip install --quiet pytest pyyaml
	@echo "Ready. Next: make test"

test: ## Run the offline test suite (never spends money)
	@if [ -d tests ]; then \
		for dir in tests/*/; do echo "== $$dir"; $(PY) -m pytest -q "$$dir" || exit 1; done; \
	else \
		echo "No tests/ directory yet; nothing to run."; \
	fi

scan: ## Scan the working tree for secrets (values are never printed)
	$(PY) scripts/secret_scan.py
	@if command -v gitleaks >/dev/null 2>&1; then \
		gitleaks git --no-banner --redact . ; \
	elif command -v trufflehog >/dev/null 2>&1; then \
		trufflehog git file://. --results=verified,unknown --fail --no-update; \
	else \
		echo "Optional: install gitleaks or trufflehog to also scan git history."; \
	fi

lint: ## Validate YAML, JSON and issue forms; run ruff when installed
	$(PY) scripts/validate_files.py
	$(PY) scripts/incidents.py check
	$(PY) scripts/update_readme_facts.py check
	@if command -v ruff >/dev/null 2>&1 && [ -d src ]; then ruff check src tests; fi

facts: ## Refresh the numbers in README.md from the data
	$(PY) scripts/update_readme_facts.py write

run-task: ## Run one task for real: make run-task TASK=<id> VARIANT=bare|plumbed (spends money)
	@if [ -z "$(TASK)" ]; then echo "Set TASK=<task-id>. Available:"; ls tasks 2>/dev/null || echo "  (no tasks yet)"; exit 2; fi
	@case "$(VARIANT)" in bare|plumbed) ;; *) echo "VARIANT must be bare or plumbed"; exit 2;; esac
	@if [ ! -d "tasks/$(TASK)" ]; then echo "No such task: tasks/$(TASK)"; exit 2; fi
	@if [ ! -d src/blackbox ]; then echo "The harness (src/blackbox) is not installed yet."; exit 2; fi
	$(PY) -m blackbox run --task "$(TASK)" --variant "$(VARIANT)"

report: ## Summarise recorded runs from runs/index.jsonl
	@if [ ! -d src/blackbox ]; then echo "The harness (src/blackbox) is not installed yet."; exit 2; fi
	$(PY) -m blackbox report

labels: ## Create or update the repository labels used by forms and release notes (needs gh)
	scripts/sync_labels.sh

clean: ## Remove caches and build output (keeps .venv and runs/)
	find . -path ./.venv -prune -o -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name '*.egg-info' \) -print -exec rm -rf {} +
	rm -rf build dist lychee workspaces
