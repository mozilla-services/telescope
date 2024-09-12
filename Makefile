NAME := telescope
INSTALL_STAMP := .install.stamp
POETRY := $(shell command -v poetry 2> /dev/null)

CONFIG_FILE := $(shell echo $${CONFIG_FILE-config.toml})
VERSION_FILE := $(shell echo $${VERSION_FILE-version.json})
SOURCE := $(shell git config remote.origin.url | sed -e 's|git@|https://|g' | sed -e 's|github.com:|github.com/|g')
VERSION := $(shell git describe --always --tag)
COMMIT := $(shell git log --pretty=format:'%H' -n 1)

.PHONY: help clean lint format tests check

help:
	@echo "Please use 'make <target>' where <target> is one of the following commands.\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
	@echo "\nCheck the Makefile to know exactly what each target is doing."

install: $(INSTALL_STAMP)  ## Install dependencies
$(INSTALL_STAMP): pyproject.toml poetry.lock
	@if [ -z $(POETRY) ]; then echo "Poetry could not be found. See https://python-poetry.org/docs/"; exit 2; fi
	$(POETRY) --version
	$(POETRY) install --with remotesettings --no-ansi --no-interaction --verbose
	touch $(INSTALL_STAMP)

clean:  ## Delete cache files
	find . -type d -name "__pycache__" | xargs rm -rf {};
	rm -rf .install.stamp .coverage .mypy_cache $(VERSION_FILE)

lint: $(INSTALL_STAMP)  ## Analyze code base
	$(POETRY) run ruff check checks tests $(NAME)
	$(POETRY) run ruff format --check checks tests $(NAME)
	$(POETRY) run mypy checks tests $(NAME) --ignore-missing-imports
	$(POETRY) run bandit -r $(NAME) -b .bandit.baseline
	$(POETRY) run poetry run detect-secrets-hook `git ls-files | grep -v poetry.lock` --baseline .secrets.baseline

format: $(INSTALL_STAMP)  ## Format code base
	$(POETRY) run ruff check --fix checks tests $(NAME)
	$(POETRY) run ruff format checks tests $(NAME)

test: tests  ## Run unit tests
tests: $(INSTALL_STAMP) $(VERSION_FILE)
	$(POETRY) run pytest tests --cov-report term-missing --cov-fail-under 100 --cov $(NAME) --cov checks

$(CONFIG_FILE):  ## Initialize default configuration
	cp config.toml.sample $(CONFIG_FILE)

$(VERSION_FILE):  ## Initialize version metadata
	echo '{"name":"$(NAME)","version":"$(VERSION)","source":"$(SOURCE)","commit":"$(COMMIT)"}' > $(VERSION_FILE)

start: $(INSTALL_STAMP) $(VERSION_FILE) $(CONFIG_FILE)  ## Start the service
	LOG_LEVEL=DEBUG LOG_FORMAT=text $(POETRY) run python -m $(NAME)

check: $(INSTALL_STAMP) $(CONFIG_FILE)  ## Execute a single check (eg. `make check project=X check=Y`)
	LOG_LEVEL=DEBUG LOG_FORMAT=text $(POETRY) run python -m $(NAME) check $(project) $(check)
