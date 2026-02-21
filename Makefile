PYTHON ?= python3

.PHONY: install install-dev run dry-run live-e2e-local test test-cov testing-snapshot lint typecheck quality gate clean setup-hooks compose-up compose-down compose-logs cleanup-state perf-report perf-baseline soak-report slo-report select-tests check-docs check-arch check-hygiene

install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

run:
	$(PYTHON) main.py

dry-run:
	DRY_RUN=true RUN_ONCE=true $(PYTHON) main.py

live-e2e-local:
	./scripts/run_live_e2e_local.sh $${ENV_FILE:-.env.live-e2e}

test:
	$(PYTHON) -m pytest -q

test-cov:
	$(PYTHON) -m pytest -q --cov=app --cov-report=term-missing --cov-config=.coveragerc

testing-snapshot:
	$(PYTHON) -m scripts.update_testing_snapshot --doc-file docs/TESTING.md --cov-config .coveragerc --log-output artifacts/testing/test-cov.log

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

select-tests:
	$(PYTHON) -m scripts.select_tests --changed-files-file $${CHANGED_FILES:-artifacts/pr-fast/changed_files.txt} --selected-output artifacts/pr-fast/selected_tests.txt --json-output artifacts/pr-fast/selection.json --markdown-output artifacts/pr-fast/selection.md

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
