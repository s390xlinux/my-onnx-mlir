#!/usr/bin/env python3

import docker
import glob
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

LLVM_PROJECT_IMAGES  = [ 'onnx-mlir-llvm-static',
                         'onnx-mlir-llvm-shared' ]

docker_daemon_socket = os.getenv('DOCKER_DAEMON_SOCKET')
dockerhub_user_name  = os.getenv('DOCKERHUB_USER_NAME')
jenkins_build_result = os.getenv('JENKINS_BUILD_RESULT')

onnx_mlir_pr_number  = os.getenv('ONNX_MLIR_PR_NUMBER2')
onnx_mlir_pr_action  = os.getenv('ONNX_MLIR_PR_ACTION')
onnx_mlir_pr_merged  = os.getenv('ONNX_MLIR_PR_MERGED')

docker_api           = docker.APIClient(base_url=docker_daemon_socket)

# Cleanup docker images and containers associated with a pull request number.
# For action open/reopen/synchronize, only dangling images and containers are
# removed. For action close, non-dangling images and containers are removed.
def cleanup_docker_images(pr_number, dangling):
    # Find all the docker images associated with the pull request number
    filters = { 'label': [ 'onnx_mlir_pr_number=' + pr_number ] }
    if dangling:
        filters['dangling'] = True
    images = docker_api.images(filters = filters, quiet = True)

    # The llvm-project images is built by a previous pull request until we
    # bump its commit sha1. So the filter will not catch them. For final
    # cleanup, they are cleaned by untagging the image. Untagging is done
    # by simply passing the full image name instead of the image sha256 to
    # remove_image.
    if not dangling:
        for image_name in LLVM_PROJECT_IMAGES:
            image_full = dockerhub_user_name + '/' + image_name + ':' + pr_number
            images.extend(image_full)

    # When a build is aborted the cleanup may try to remove an intermediate
    # image or container that the docker build process itself is already doing,
    # resulting a conflict. So we catch the exception and ignore it.

    # For each image found, find and remove all the dependant containers
    for image in images:
        containers = docker_api.containers(
            filters = { 'ancestor': image }, all = True, quiet = True)
        for container in containers:
            try:
                logging.info('Removing Id:%s', container['Id'])
                docker_api.remove_container(container['Id'], v = True, force = True)
            except:
                logging.info(sys.exc_info()[1])

        # Remove the docker images associated with the pull request number
        try:
            logging.info('Removing %s', image)
            docker_api.remove_image(image, force = True)
        except:
            logging.info(sys.exc_info()[1])

def main():
    # Don't cleanup in case of failure for debugging purpose.
    if jenkins_build_result == 'FAILURE':
        return

    # Only cleanup dangling if we are starting up (build result UNKNOWN)
    #
    # Only cleanup dangling if the pull request is closed by merging
    # since a push event will be coming so we want the build for the
    # push event to be able to reuse cached docker image layers. The
    # push event will do full cleanup after publish.

    dangling = False if (jenkins_build_result != 'UNKNOWN' and
                         ((onnx_mlir_pr_action == 'closed' and
                           onnx_mlir_pr_merged == 'false') or
                          onnx_mlir_pr_action == 'push')) else True

    logging.info('Docker cleanup for pull request: #%s, ' +
                 'build result: %s, action: %s, merged: %s, dangling: %s',
                 onnx_mlir_pr_number,
                 jenkins_build_result,
                 onnx_mlir_pr_action,
                 onnx_mlir_pr_merged,
                 dangling)

    cleanup_docker_images(onnx_mlir_pr_number, dangling)

if __name__ == "__main__":
    main()
