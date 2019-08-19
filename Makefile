.PHONY: clean tests

clean:git g
	find . -type d -name "__pycache__" | xargs rm -rf {};

config.toml:
	cp config.toml.sample config.toml

NAME := poucave
SOURCE := $(shell git config remote.origin.url | sed -e 's|git@|https://|g' | sed -e 's|github.com:|github.com/|g')
VERSION := $(shell git describe --always --tag)
COMMIT := $(shell git log --pretty=format:'%H' -n 1)
version.json:
	echo '{"name":"$(NAME)","version":"$(VERSION)","source":"$(SOURCE)","commit":"$(COMMIT)"}' > version.json

serve: version.json config.toml
	PYTHONPATH=. python poucave

tests: version.json
	PYTHONPATH=. pytest tests
