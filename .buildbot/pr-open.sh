#!/bin/bash
set -ex

# This script is run by Jenkin Generic Webhook Trigger plugin when one of
# the following events happens:
#
# - a pull request is opened
# - a pull request is reopened
# - a pull request is updated
# - a pull request is commented on with body containing "test this please"
#
# All events must be initiated by one of the whitelisted admins.
#
# It expects the following env vars to be set when invoked:
#
#   GITHUB_JENKINS_DROID_TOKEN
#   DOCKERHUB_USERNAME
#   PULL_REQUST_NUMBER

# Cleanup dangling images and containers from a previous failed build
# $1: pull request number
function cleanup_dangling() {
  ids=$(docker images -q \
               --filter dangling=true \
	       --filter label=pull_request_number=$1)
  for id in ${ids}; do
    docker rm -f $(docker ps -aq --filter ancestor=${id}) || true
  done

  docker rmi -f ${ids} || true
}

# Get an image ID given its name and tag
# $1: image name
# $2: image tag
#
# Optionally, a series of label key/value pairs can be specified
# The image must contain all the keys with the specified values
# $3: label key
# $4: label value
# ...
function get_image_id() {
  cmd="docker images -q --filter reference=$1:$2"
  shift 2

  # Note we use -gt 1 not -gt 0. We consume 2 parameters at a time.
  # However, if for some reason some parameters are empty and we can
  # get an odd number of parameters. When that happens, ${#} will
  # eventually get down to 1 and shift 2 will never change ${#} again,
  # i.e., it will stay at 1. So using -gt 0 will loop forever.
  while test ${#} -gt 1; do
    if [ "$1" != "" ] && [ "$2" != "" ]; then
      cmd+=" --filter label=$1=$2"
    fi
    shift 2
  done

  echo $(${cmd})
}

# Get an image's label value given its ID and label key
# $1: image ID
# $2: label key
function get_image_label() {
  image_id=$1
  label_key=$2

  echo $(docker inspect ${image_id} \
                --format "{{ index .Config.Labels \"${label_key}\" }}")
}

# Setup per pull request private llvm-project image
#
# We first look for an image
#
#    ${DOCKERHUB_USERNAME}/onnx-mlir-llvm-{static|shared}:${PULL_REQUEST_NUMBER}
#
# with the expected llvm-project commit sha1 and Dockerfile.llvm-project file sha1.
# If it's found, we can just use it. Otherwise, we try to pull
#
#    ${DOCKERHUB_USERNAME}/onnx-mlir-llvm-{static|shared}:latest
#
# If the pulled image has the expected llvm-project commit hash, we tag the
# pulled image with ${PULL_REQUEST_NUMBER} and we use it.
#
# If the pull didn't work, we will build one from scratch.

# $1: image name
# $2: image tag
function setup_private_llvm() {
  image_name=$1
  image_tag=$2

  # Try to get the local llvm-project image ID with expected llvm-project sha1
  # and Dockerfile.llvm-project sha1.
  local_image_id=$(get_image_id ${image_name} ${image_tag} \
                     "llvm_project_sha1" ${EXPECTED_LLVM_PROJECT_SHA1} \
                     "llvm_dockerfile_sha1" ${EXPECTED_LLVM_DOCKERFILE_SHA1})

  # If not found, try to pull one, then build one if necessary.
  if [ "${local_image_id}" = "" ]; then
    # First try to pull one and see if it's usable, ignore pull error
    docker pull ${image_name}:latest || true

    pulled_llvm_project_sha1=""
    pulled_llvm_project_sha1_date=""
    pulled_llvm_dockerfile_sha1=""
    pulled_image_id=$(get_image_id ${image_name} "latest")

    # If pull successful, get llvm-project commit sha1 and date, and
    # Dockerfile.llvm-project sha1.
    if [ "${pulled_image_id}" != "" ]; then
      pulled_llvm_project_sha1=$(get_image_label \
                                   ${pulled_image_id} "llvm_project_sha1")
      pulled_llvm_project_sha1_date=$(get_image_label \
                                        ${pulled_image_id} "llvm_project_sha1_date")
      pulled_llvm_dockerfile_sha1=$(get_image_label \
                                      ${pulled_image_id} "llvm_dockerfile_sha1")
    fi

    # Pulled image has expected llvm-project commit sha1 and
    # Dockerfile.llvm-project sha1, tag it with pull request number
    # for our private use.
    if [ "${pulled_llvm_project_sha1}" = \
         "${EXPECTED_LLVM_PROJECT_SHA1}" ] &&
       [ "${pulled_llvm_dockerfile_sha1}" = \
         "${EXPECTED_LLVM_DOCKERFILE_SHA1}" ]; then
      docker tag ${pulled_image_id} ${image_name}:${image_tag}

    # Pulled image has an llvm-project commit hash date earlier than
    # what we expect, so we will build one with the newer commit sha1,
    # regardless of Dockerfile.llvm-project sha1 being expected or not.
    #
    # Note that if pull failed and pulled_llvm_project_sha1_date is
    # empty, the comparison will be true.
    elif [[ "${pulled_llvm_project_sha1_date}" < \
            "${EXPECTED_LLVM_PROJECT_SHA1_DATE}" ]]; then
      docker build -t ${image_name}:${image_tag} \
             --build-arg BUILD_SHARED_LIBS=${BUILD_SHARED_LIBS[${image_name}]} \
             --build-arg LLVM_PROJECT_SHA1=${EXPECTED_LLVM_PROJECT_SHA1} \
             --build-arg LLVM_PROJECT_SHA1_DATE=${EXPECTED_LLVM_PROJECT_SHA1_DATE} \
	     --build-arg LLVM_DOCKERFILE_SHA1=${EXPECTED_LLVM_DOCKERFILE_SHA1} \
             --build-arg PULL_REQUEST_NUMBER=${PULL_REQUEST_NUMBER} \
             -f docker/Dockerfile.llvm-project .

    # Pulled image has an llvm-project commit hash date later than
    # what we expect, the build source is out of date. Exit to fail
    # the build, regardless of Dockerfile.llvm-project sha1 being
    # expected or not.
    else
      echo "pulled   ${image_name}:latest"
      echo "  llvm_project_sha1      = ${pulled_llvm_project_sha1}"
      echo "  llvm_project_sha1 date = ${pulled_llvm_project_sha1_date}"
      echo "  llvm_dockerfile_sha1   = ${pulled_llvm_dockerfile_sha1}"
      echo "expected ${image_name}:${image_tag}"
      echo "  llvm_project_sha1      = ${EXPECTED_LLVM_PROJECT_SHA1}"
      echo "  llvm_project_sha1 date = ${EXPECTED_LLVM_PROJECT_SHA1_DATE}"
      echo "  llvm_dockerfile_sha1   = ${EXPECTED_LLVM_DOCKERFILE_SHA1}"
      echo "source out of date, rebase then rebuild"
      exit 1
    fi

    # We now should have an llvm-project image with expected commit hash,
    # either pulled or built. Get the image ID.
    local_image_id=$(get_image_id ${image_name} ${image_tag} \
                       "llvm_project_sha1" ${EXPECTED_LLVM_PROJECT_SHA1} \
                       "llvm_dockerfile_sha1" ${EXPECTED_LLVM_DOCKERFILE_SHA1})
  fi

  # Set global llvm_image_id
  llvm_image_id[${image_name}]=${local_image_id}
}

#########################
# Execution starts here #
#########################

# Static and shared llvm-project image name
DOCKERHUB_USERNAME=${DOCKERHUB_USERNAME:-onnxmlirczar}

LLVM_STATIC_IMAGE=${DOCKERHUB_USERNAME}/onnx-mlir-llvm-static
LLVM_SHARED_IMAGE=${DOCKERHUB_USERNAME}/onnx-mlir-llvm-shared

# onnx-mlir dev and user image name
ONNX_MLIR_DEV_IMAGE=${DOCKERHUB_USERNAME}/onnx-mlir-dev
ONNX_MLIR_IMAGE=${DOCKERHUB_USERNAME}/onnx-mlir

# Expected llvm-project commit sha1 and date
EXPECTED_LLVM_PROJECT_SHA1=$(cat utils/clone-mlir.sh | \
  grep -Po '(?<=git checkout )[0-9a-f]+')
LLVM_PROJECT_COMMITS_URL=https://api.github.com/repos/llvm/llvm-project/commits
EXPECTED_LLVM_PROJECT_SHA1_DATE=$(curl -s \
  ${LLVM_PROJECT_COMMITS_URL}/${EXPECTED_LLVM_PROJECT_SHA1} \
  -X GET \
  -H "Accept: application/json" \
  -H "Authorization: token ${GITHUB_JENKINS_DROID_TOKEN}" \
  | jq -r .commit.author.date)

# Expected Dockerfile.llvm-project sha1
EXPECTED_LLVM_DOCKERFILE_SHA1=$(IFS=" "; \
  set -- $(sha1sum docker/Dockerfile.llvm-project); echo $1)

# Global associated array for static and shared lib build flag and
# llvm-project image ID
declare -A BUILD_SHARED_LIBS=([${LLVM_STATIC_IMAGE}]=OFF [${LLVM_SHARED_IMAGE}]=ON)
declare -A llvm_image_id

# Setup per pull request private llvm-project image
setup_private_llvm ${LLVM_STATIC_IMAGE} ${PULL_REQUEST_NUMBER}
setup_private_llvm ${LLVM_SHARED_IMAGE} ${PULL_REQUEST_NUMBER}
echo "Using llvm-project images:"
echo "  ${LLVM_STATIC_IMAGE}:${PULL_REQUEST_NUMBER} ${llvm_image_id[${LLVM_STATIC_IMAGE}]}"
echo "  ${LLVM_SHARED_IMAGE}:${PULL_REQUEST_NUMBER} ${llvm_image_id[${LLVM_SHARED_IMAGE}]}"

# third_party/onnx commit hash
THIRD_PARTY_ONNX_SHA1=$(git -C third_party/onnx rev-parse HEAD)

# Use the static lib llvm-project image to build the onnx-mlir-dev image
docker build -t ${ONNX_MLIR_DEV_IMAGE}:${PULL_REQUEST_NUMBER} \
             --build-arg BASE_IMAGE=${LLVM_STATIC_IMAGE}:${PULL_REQUEST_NUMBER} \
             --build-arg PULL_REQUEST_NUMBER=${PULL_REQUEST_NUMBER} \
             --build-arg THIRD_PARTY_ONNX_SHA1=${THIRD_PARTY_ONNX_SHA1} \
             -f docker/Dockerfile.onnx-mlir-dev .

# Use the shared lib llvm-project image to build the onnx-mlir image
docker build -t ${ONNX_MLIR_IMAGE}:${PULL_REQUEST_NUMBER} \
             --build-arg BASE_IMAGE=${LLVM_SHARED_IMAGE}:${PULL_REQUEST_NUMBER} \
             --build-arg PULL_REQUEST_NUMBER=${PULL_REQUEST_NUMBER} \
             --build-arg THIRD_PARTY_ONNX_SHA1=${THIRD_PARTY_ONNX_SHA1} \
             -f docker/Dockerfile.onnx-mlir .

# Cleanup dangling images and containers if all images have been built successfully
cleanup_dangling ${PULL_REQUEST_NUMBER}
