#!/bin/bash -ex

# This script is run by Jenkin Generic Webhook Trigger plugin when one of
# the following events happens:
#
# - a pull request issue is commented on
#
# All events must be initiated by one of the whitelisted admins.
#
# The following parameters are passed in:
#
# $1: dockerhub user name
# $2: dockerhub user personal token
# $3: github personal access token
# $4: github pull request number
# $5: github pull request url
# $6: github pull request issue comment url
# $7: github pull request issue comment body
#
# Currently two trigger phrases are recognized:
#
#   test this please    - trigger a build of the pull request
#   publish this please - trigger a push of all the docker images built by
#                         the pull request (this is an unconditional push
#                         that can be used to override an automatic push
#                         by the merge, which only pushes newer llvm-project)
#

DOCKERHUB_USER_NAME=$1
DOCKERHUB_USER_TOKEN=$2
GITHUB_JENKINS_DROID_TOKEN=$3
ONNX_MLIR_PR_NUMBER=$4
GITHUB_PULL_REQUEST_URL=$5
GITHUB_ISSUE_COMMENT_URL=$6
GITHUB_ISSUE_COMMENT_BODY=$7

phrase=$([[ "${GITHUB_ISSUE_COMMENT_BODY}" =~ .*(test|publish)( this please).* ]] && \
         echo ${BASH_REMATCH[1]})

case "${phrase}" in
    test)
	.buildbot/pr-open.sh ${DOCKERHUB_USER_NAME} \
			     ${GITHUB_JENKINS_DROID_TOKEN} \
			     ${ONNX_MLIR_PR_NUMBER}
    ;;
    publish)
	.buildbot/pr-merge.sh ${DOCKERHUB_USER_NAME} \
			      ${DOCKERHUB_USER_TOKEN} \
			      ${GITHUB_JENKINS_DROID_TOKEN} \
			      ${ONNX_MLIR_PR_NUMBER} \
			      ${GITHUB_PULL_REQUEST_URL} \
			      ${GITHUB_ISSUE_COMMENT_URL}
    ;;
esac
