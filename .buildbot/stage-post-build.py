#!/usr/bin/env python3

import docker
import glob
import logging
import os
import shutil

logging.basicConfig(
    level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

onnx_mlir_pr_number = os.getenv('ONNX_MLIR_PR_NUMBER')
onnx_mlir_pr_action = os.getenv('ONNX_MLIR_PR_ACTION')
jenkins_home        = os.getenv('JENKINS_HOME')
jenkins_job_name    = os.getenv('JOB_NAME')

DOCKER_SOCKET       = 'unix://var/run/docker.sock'
docker_api          = docker.APIClient(base_url=DOCKER_SOCKET)

# Cleanup docker images and containers associated with a pull request number.
# For action open/reopen/synchronize, only dangling images and containers are
# removed. For action close, non-dangling images and containers are removed.
def cleanup_docker_images(pr_number):
    logging.info('Cleanup docker images and containers for pull request #%s',
                 pr_number)

    # Find all the docker images associated with the pull request number
    images = docker_api.images(
        filters = {
            'dangling': not onnx_mlir_pr_action == 'closed',
            'label': [ 'onnx_mlir_pr_number=' + pr_number ] },
        all = True, quiet = True)

    # For each image found, find and remove all the dependant containers
    for image in images:
        containers = docker_api.containers(
            filters = { 'ancestor': image },
            all = True, quiet = True)
        for container in containers:
            docker_api.remove_container(container['Id'], v = True, force = True)
            logging.info('Id:%s removed', container['Id'])

        # Remove the docker images associated with the pull request number
        docker_api.remove_image(image, force = True)
        logging.info('%s removed', image)

# Cleanup Jenkins workspace associated with a pull request number.
def cleanup_jenkins_workspace(pr_number):
    p = "{}/workspace/{}@pr_{}*".format(
        jenkins_home, jenkins_job_name, onnx_mlir_pr_number)
    wrkdirs = glob.glob(p)
    for wrkdir in wrkdirs:
        logging.info('Removing workdir %s', wrkdir)
        shutil.rmtree(wrkdir)

def main():
    cleanup_docker_images(onnx_mlir_pr_number)
    if onnx_mlir_pr_action == 'closed':
        cleanup_jenkins_workspace(onnx_mlir_pr_number)

if __name__ == "__main__":
    main()
