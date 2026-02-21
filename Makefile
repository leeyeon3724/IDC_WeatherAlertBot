PYTHON ?= python3

.PHONY: install install-dev run dry-run test test-cov lint typecheck quality gate clean setup-hooks compose-up compose-down compose-logs cleanup-state perf-report perf-baseline soak-report slo-report check-docs check-arch check-hygiene

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

gate: lint typecheck check-arch check-docs check-hygiene test-cov

quality: gate

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

perf-baseline:
	$(PYTHON) -m scripts.perf_baseline --reports artifacts/perf/local.json --max-samples 20 --output artifacts/perf/baseline.local.json --markdown-output artifacts/perf/baseline.local.md

soak-report:
	$(PYTHON) -m scripts.soak_report --cycles $${CYCLES:-3000} --area-count $${AREAS:-3} --max-memory-growth-kib $${MAX_MEMORY_GROWTH_KIB:-8192} --json-output artifacts/soak/local.json --markdown-output artifacts/soak/local.md

slo-report:
	$(PYTHON) -m scripts.slo_report --log-file $${LOG_FILE:-artifacts/canary/service.log} --json-output artifacts/slo/local.json --markdown-output artifacts/slo/local.md

check-docs:
	$(PYTHON) -m scripts.check_event_docs_sync

check-arch:
	$(PYTHON) -m scripts.check_architecture_rules

check-hygiene:
	$(PYTHON) -m scripts.check_repo_hygiene

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	rm -rf .pytest_cache
	rm -rf .mypy_cache .ruff_cache htmlcov
	rm -f .coverage .coverage.*
