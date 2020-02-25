NAME := poucave
CONFIG_FILE := $(shell echo $${CONFIG_FILE-config.toml})
VERSION_FILE := $(shell echo $${VERSION_FILE-version.json})
SOURCE := $(shell git config remote.origin.url | sed -e 's|git@|https://|g' | sed -e 's|github.com:|github.com/|g')
VERSION := $(shell git describe --always --tag)
COMMIT := $(shell git log --pretty=format:'%H' -n 1)
COMMIT_HOOK := .git/hooks/pre-commit
VENV := $(shell echo $${VIRTUAL_ENV-.venv})
PYTHON := $(VENV)/bin/python3
VIRTUALENV := virtualenv --python=python3.7
PIP_INSTALL := $(VENV)/bin/pip install --progress-bar=off
INSTALL_STAMP := $(VENV)/.install.stamp

.PHONY: clean check lint format tests

install: $(INSTALL_STAMP) $(COMMIT_HOOK)
$(INSTALL_STAMP): $(PYTHON) requirements/dev.txt requirements/default.txt checks/remotesettings/requirements.txt
	$(PIP_INSTALL) -Ur requirements/default.txt
	# No deps because this includes kinto-signer, which depends on Pyramid. We don't want all of Pyramid
	$(PIP_INSTALL) --no-deps -Ur checks/remotesettings/requirements.txt
	$(PIP_INSTALL) -Ur requirements/dev.txt
	touch $(INSTALL_STAMP)

$(PYTHON):
	$(VIRTUALENV) $(VENV)

$(COMMIT_HOOK):
	echo "make format" > $(COMMIT_HOOK)
	chmod +x $(COMMIT_HOOK)

clean:
	find . -type d -name "__pycache__" | xargs rm -rf {};
	rm -rf $(VENV)

lint: $(INSTALL_STAMP)
	$(VENV)/bin/isort --line-width=88 --check-only --lines-after-imports=2 -rc checks tests $(NAME) --virtual-env=$(VENV)
	$(VENV)/bin/black --check checks tests $(NAME) --diff
	$(VENV)/bin/flake8 checks tests $(NAME)
	$(VENV)/bin/mypy checks tests $(NAME) --ignore-missing-imports

format:
	$(VENV)/bin/isort --line-width=88 --lines-after-imports=2 -rc checks tests $(NAME) --virtual-env=$(VENV)
	$(VENV)/bin/black checks tests $(NAME)

$(CONFIG_FILE):
	cp config.toml.sample $(CONFIG_FILE)

$(VERSION_FILE):
	echo '{"name":"$(NAME)","version":"$(VERSION)","source":"$(SOURCE)","commit":"$(COMMIT)"}' > $(VERSION_FILE)

serve: $(INSTALL_STAMP) $(VERSION_FILE) $(CONFIG_FILE)
	PYTHONPATH=. $(PYTHON) $(NAME)

check: $(INSTALL_STAMP) $(CONFIG_FILE)
	PYTHONPATH=. LOG_LEVEL=DEBUG LOG_FORMAT=text $(PYTHON) $(NAME) $(project) $(check)

tests: $(INSTALL_STAMP) $(VERSION_FILE)
	PYTHONPATH=. $(VENV)/bin/pytest tests --cov-report term-missing --cov-fail-under 100 --cov poucave --cov checks
