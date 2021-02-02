#!/usr/bin/env python3

import docker
import glob
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

docker_daemon_socket = os.getenv('DOCKER_DAEMON_SOCKET')

jenkins_scriptspace  = os.getenv('JENKINS_SCRIPTSPACE')
jenkins_workspace    = os.getenv('JENKINS_WORKSPACE')
jenkins_home         = os.getenv('JENKINS_HOME')
jenkins_job_name     = os.getenv('JOB_NAME')
jenkins_build_result = os.getenv('JENKINS_BUILD_RESULT')

onnx_mlir_pr_number  = os.getenv('ONNX_MLIR_PR_NUMBER')
onnx_mlir_pr_action  = os.getenv('ONNX_MLIR_PR_ACTION')

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
    if jenkins_build_result == 'FAILURE':
        return

    # Don't cleanup in case of failure for debugging purpose
    dangling = True if (jenkins_build_result == 'UNKNOWN' or
                        onnx_mlir_pr_action != 'closed') else False

    logging.info('Docker cleanup for pull request: #%s, ' +
                 'build result: %s, action: %s, dangling: %s',
                 onnx_mlir_pr_number,
                 jenkins_build_result,
                 onnx_mlir_pr_action,
                 dangling)

    cleanup_docker_images(onnx_mlir_pr_number, dangling)

if __name__ == "__main__":
    main()
