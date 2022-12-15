#!/bin/bash
if [ $1 == "server" ]; then
    exec poetry run python -m telescope

elif [ $1 == "check" ]; then
    exec poetry run python -m telescope $@

elif [ $1 == "test" ]; then
    poetry install --only dev --no-ansi --no-interaction --verbose
    poetry run pytest tests

else
    exec poetry run "$@"
fi
