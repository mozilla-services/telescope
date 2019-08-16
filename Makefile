.PHONY: tests

tests:
	pytest tests

config.toml:
	cp config.toml.sample config.toml

serve: config.toml
	PYTHONPATH=. python poucave
