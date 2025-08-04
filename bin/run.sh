#!/bin/bash
if [ $1 == "server" ]; then
    exec uv run python -m telescope

elif [ $1 == "check" ]; then
    exec uv run python -m telescope $@

elif [ $1 == "test" ]; then
    uv install --group remotesettings --verbose
    uv run pytest tests

else
    exec uv run "$@"
fi
