#!/bin/bash

set -e

# configure docker creds
echo "$DOCKER_PASS" | docker login -u="$DOCKER_USER" --password-stdin

# docker tag and push git branch to dockerhub
if [ -n "$1" ]; then
    [ "$1" == master ] && TAG=latest || TAG="$1"
    docker tag app:build "$DOCKERHUB_REPO:$TAG" ||
        (echo "Couldn't tag app:build as $DOCKERHUB_REPO:$TAG" && false)
    docker push "$DOCKERHUB_REPO:$TAG" ||
        (echo "Couldn't push $DOCKERHUB_REPO:$TAG" && false)
    echo "Pushed $DOCKERHUB_REPO:$TAG"
fi
