NAME := poucave
CONFIG_FILE := $(shell echo $${CONFIG_FILE-config.toml})
VERSION_FILE := $(shell echo $${VERSION_FILE-version.json})
SOURCE := $(shell git config remote.origin.url | sed -e 's|git@|https://|g' | sed -e 's|github.com:|github.com/|g')
VERSION := $(shell git describe --always --tag)
COMMIT := $(shell git log --pretty=format:'%H' -n 1)
COMMIT_HOOK := .git/hooks/pre-commit
VENV := $(shell echo $${VIRTUAL_ENV-.venv})
PYTHON := $(VENV)/bin/python3
VIRTUALENV := virtualenv --python=python3
INSTALL_STAMP := $(VENV)/.install.stamp

.PHONY: clean check lint format tests

install: $(INSTALL_STAMP) $(COMMIT_HOOK)
$(INSTALL_STAMP): $(PYTHON) dev-requirements.txt requirements.txt
	$(VENV)/bin/pip install -Ur requirements.txt
	$(VENV)/bin/pip install -Ur checks/remotesettings/requirements.txt
	$(VENV)/bin/pip install -Ur dev-requirements.txt
	touch $(INSTALL_STAMP)

$(PYTHON):
	$(VIRTUALENV) $(VENV)

$(COMMIT_HOOK):
	echo "make format" > $(COMMIT_HOOK)
	chmod +x $(COMMIT_HOOK)

clean:
	find . -type d -name "__pycache__" | xargs rm -rf {};

lint:
	$(VENV)/bin/black --check checks tests $(NAME) --diff
	$(VENV)/bin/flake8 --max-line-length=88 --ignore=E501 checks tests $(NAME)

format:
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
	PYTHONPATH=. $(VENV)/bin/pytest tests
