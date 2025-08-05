#!/bin/bash
export UV_NO_EDITABLE=1
UV_PROD_ARGS="--no-dev --frozen"

if [ $1 == "server" ]; then
    exec uv run $UV_PROD_ARGS python -m telescope

elif [ $1 == "check" ]; then
    exec uv run $UV_PROD_ARGS python -m telescope $@

elif [ $1 == "test" ]; then
    uv sync --group remotesettings --verbose
    uv run pytest tests

else
    exec uv run $UV_PROD_ARGS -- "$@"
fi
