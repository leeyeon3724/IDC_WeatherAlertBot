PYTHON ?= python3

.PHONY: install install-dev run dry-run test test-cov lint typecheck quality clean setup-hooks compose-up compose-down compose-logs cleanup-state perf-report check-docs

install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

run:
	$(PYTHON) main.py

dry-run:
	DRY_RUN=true RUN_ONCE=true $(PYTHON) main.py

test:
	$(PYTHON) -m pytest -q

test-cov:
	$(PYTHON) -m pytest -q --cov=app --cov-report=term-missing --cov-config=.coveragerc

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy

quality: lint typecheck test-cov

setup-hooks:
	git config core.hooksPath .githooks
	@echo "core.hooksPath=$$(git config --get core.hooksPath)"

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f weather-alert-bot

cleanup-state:
	$(PYTHON) main.py cleanup-state --days $${DAYS:-30}

perf-report:
	$(PYTHON) -m scripts.perf_report --output artifacts/perf/local.json --markdown-output artifacts/perf/local.md

check-docs:
	$(PYTHON) -m scripts.check_event_docs_sync

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	rm -rf .pytest_cache
	rm -rf .mypy_cache .ruff_cache htmlcov
	rm -f .coverage .coverage.*
