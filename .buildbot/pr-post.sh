#!/bin/bash -ex

# $1: github pull request issue comment url
# $2: github personal access token
# $3: comment body
function pr-post() {
  curl -s $1 \
       -X POST \
       -H "Accept: application/json" \
       -H "Authorization: token $2" \
       -d '{"body": '"$3"'}'
}
