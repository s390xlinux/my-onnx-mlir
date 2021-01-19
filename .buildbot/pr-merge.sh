#!/bin/bash -ex

# This script is run by Jenkin Generic Webhook Trigger plugin when one of
# the following events happens:
#
# - a pull request is merged (the push event)
# - a pull request is commented on with body containing "publish this please"
#
# Note when a pull request is merged, two events are generated,
# a close event, followed by a push event.
#
# All events must be initiated by one of the whitelisted admins.
#
# The following parameters are passed in:
#
# $1: dockerhub user name
# $2: dockerhub user personal token
# $3: github personoal access token
# $4: github pull request number (if triggered by "publish this please")
# $5: github pull request url
# $6: github pull request issue comment url
#

# Get docker access token for a docker image
#
# $1: dockerhub user name
# $2: docker image name
function get_access_token() {
  curl -s "https://auth.docker.io/token?scope=repository:$1/$2:pull&service=registry.docker.io" | jq -r .token
}

# Get all docker images labels
#
# $1: dockerhub user name
# $2: dockerhub access token
# $3: docker image name
# $4: docker image tag
function get_image_labels() {
  curl -s "https://registry-1.docker.io/v2/$1/$3/manifests/$4" \
       -H "Authorization: Bearer $2" | \
  jq -r ".history[0].v1Compatibility" | \
  jq -r .config.Labels
}

# Get one docker image label
#
# $1: labels JSON from get_image_labels
# $2: label key to get value for
function get_image_label() {
  echo $1 | jq -r .$2
}

function publish_by_push() {
  declare -A local_llvm_project_sha1_date
  declare -A remote_llvm_project_sha1_date

  image=onnx-mlir-llvm-static
  tag=$(uname -m)
  tag=${tag/x86_/amd}
  token=$(get_access_token ${DOCKERHUB_USER_NAME} ${image})
  labels=$(get_image_labels ${DOCKERHUB_USER_NAME} ${image} ${tag} ${token})
  remote_llvm_project_sha1_date=$(get_image_label ${labels} "llvm_project_sha1_date")

}

function publish_by_comment() {
  declare -A mergeable=(
    [behind]=Rejected
    [blocked]=Rejected
    [clean]=Accepted
    [dirty]=Rejected
    [draft]=Rejected
    [has_hooks]=Accepted
    [unknown]=Rejected
    [unstable]=Accepted
  )
  declare -A mergeable_state_message=(
    [behind]="The head ref is out of date"
    [blocked]="The merge is blocked"
    [clean]="Mergeable and passing commit status"
    [dirty]="The merge commit cannot be cleanly created"
    [draft]="The merge is blocked due to the pull request being a draft"
    [has_hooks]="Mergeable with passing commit status and pre-receive hooks"
    [unknown]="The state cannot currently be determined"
    [unstable]="Mergeable with non-passing commit status"
  )

  # Check pull request mergeable state
  mergeable_state=$(curl -s ${GITHUB_PULL_REQUEST_URL} \
                         -X GET -H "Accept: application/json" \
                         -H "Authorization: token ${GITHUB_JENKINS_DROID_TOKEN}" | \
                    jq -r .mergeable_state)

  # Post accept or reject comment on the pull request issue page
  pr-post ${GITHUB_JENKINS_DROID_TOKEN} \
	  ${GITHUB_ISSUE_COMMENT_URL} \
	  "${mergeable[${mergeable_state}]}: ${mergeable_state_message[${mergeable_state}]"

  if [ "${mergeable[${mergeable_state}]}" = "Rejected" ]; then
    exit 1
  fi

  # Tag images with CPU arch and unconditionally push to dockerhub
  i=0
  tag=$(uname -m)
  tag=${tag/x86_/amd}
  docker login -u ${DOCKERHUB_USER_NAME} -p ${DOCKERHUB_USER_TOKEN}
  while [ "${i}" -lt "${#ONNX_MLIR_DOCKER_IMAGES[@]}" ]; do
    image = ${ONNX_MLIR_DOCKER_IMAGES[i]}
    docker tag  ${DOCKERHUB_USER_NAME}/${image}:${ONNX_MLIR_PR_NUMBER} \
                ${DOCKERHUB_USER_NAME}/${image}:${tag}
    docker push ${DOCKERHUB_USER_NAME}/${image}:${tag}
    (( i += 1))
  done
}

#########################
# Execution starts here #
#########################

DOCKERHUB_USER_NAME=$1
DOCKERHUB_USER_TOKEN=$2
GITHUB_JENKINS_DROID_TOKEN=$3
ONNX_MLIR_PR_NUMBER=$4
GITHUB_PULL_REQUEST_URL=$5
GITHUB_ISSUE_COMMENT_URL=$6

ONNX_MLIR_DOCKER_IMAGES=(
  "onnx-mlir-llvm-static"
  "onnx-mlir-llvm-shared"
  "onnx-mlir-dev"
  "onnx-mlir"
)

# Source pr-post function
source .buildbot/pr-post.sh

if [ "${ONNX_MLIR_PR_NUMBER}" = "" ]; then
  publish_by_push
else
  publish_by_comment
fi
