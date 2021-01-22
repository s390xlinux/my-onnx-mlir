#!/usr/bin/env python3

import docker
import json
import logging
import platform
import os

logging.basicConfig(
    level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

CPU_ARCH                   = platform.machine().replace('x86_', 'amd')
DOCKER_SOCKET              = 'unix://var/run/docker.sock'

LLVM_PROJECT_IMAGE         = { 'dev': 'onnx-mlir-llvm-static',
                               'usr': 'onnx-mlir-llvm-shared' }
ONNX_MLIR_IMAGE            = { 'dev': 'onnx-mlir-dev',
                               'usr': 'onnx-mlir' }
ONNX_MLIR_DOCKERFILE       = { 'dev': 'docker/Dockerfile.onnx-mlir-dev',
                               'usr': 'docker/Dockerfile.onnx-mlir' }

onnx_mlir_pr_number        = os.getenv('ONNX_MLIR_PR_NUMBER')
dockerhub_user_name        = os.getenv('DOCKERHUB_USER_NAME')
#

docker_api                 = docker.APIClient(base_url=DOCKER_SOCKET)

# Build onnx-mlir dev and user images.
def build_private_onnx_mlir(image_type):
    user_name  = dockerhub_user_name
    image_name = ONNX_MLIR_IMAGE[image_type]
    image_tag  = onnx_mlir_pr_number
    image_repo = user_name + '/' + image_name
    image_full = image_repo + ':' + image_tag

    for line in docker_api.build(
            path = '.',
            dockerfile = ONNX_MLIR_DOCKERFILE[image_type],
            tag = image_repo + ':' + onnx_mlir_pr_number,
            decode = True,
            rm = True,
            buildargs = {
                'BASE_IMAGE': dockerhub_user_name + '/' +
                              LLVM_PROJECT_IMAGE[image_type] + ':' +
                              onnx_mlir_pr_number,
                'ONNX_MLIR_PR_NUMBER': onnx_mlir_pr_number
            }):
        print(line['stream'] if 'stream' in line else '',
              end='', flush=True)
        
    id = docker_api.images(name = image_full, all = False, quiet = True)
    logging.info('image %s (%s) built', image_full, id[0][0:19])

def main():
    build_private_onnx_mlir('dev')
    build_private_onnx_mlir('usr')

if __name__ == "__main__":
    main()
