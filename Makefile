PYTHON ?= python3

.PHONY: install install-dev run dry-run test clean setup-hooks compose-up compose-down compose-logs

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

setup-hooks:
	git config core.hooksPath .githooks
	@echo "core.hooksPath=$$(git config --get core.hooksPath)"

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f weather-alert-bot

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	rm -rf .pytest_cache
