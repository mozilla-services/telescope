#!/bin/bash
if [ $1 == "server" ]; then
    exec python poucave

elif [ $1 == "test" ]; then
    # install dependencies (if required)

    if [ $EUID != 0 ]; then
        echo "Need to be root.  Run container with '--user root'"
        exit 1
    fi

    pip install -r dev-requirements.txt
    pytest tests

else
    echo "Unknown mode: $1"
fi