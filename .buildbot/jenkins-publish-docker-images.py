#!/usr/bin/env python3

import docker
import json
import logging
import os
import requests
import sys

logging.basicConfig(
    level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

cpu_arch                   = os.getenv('CPU_ARCH')
docker_daemon_socket       = os.getenv('DOCKER_DAEMON_SOCKET')

dockerhub_user_name        = os.getenv('DOCKERHUB_USER_NAME')
dockerhub_user_token       = os.getenv('DOCKERHUB_USER_TOKEN')
github_jenkins_droid_token = os.getenv('GITHUB_JENKINS_DROID_TOKEN')

onnx_mlir_pr_number        = os.getenv('ONNX_MLIR_PR_NUMBER')
onnx_mlir_pr_phrase        = os.getenv('ONNX_MLIR_PR_PHRASE')
onnx_mlir_pr_request_url   = os.getenv('ONNX_MLIR_PR_REQUEST_URL')

docker_api                 = docker.APIClient(base_url=docker_daemon_socket)

LLVM_PROJECT_LABELS        = [ 'llvm_project_sha1',
                               'llvm_project_sha1_date',
                               'llvm_project_dockerfile_sha1']
ONNX_MLIR_LABELS           = [ 'onnx_mlir_sha1',
                               'onnx_mlir_sha1_date',
                               'onnx_mlir_dockerfile_sha1' ]
IMAGE_NAME                 = { 'static': 'onnx-mlir-llvm-static',
                               'shared': 'onnx-mlir-llvm-shared',
                               'dev': 'onnx-mlir-dev',
                               'usr': 'onnx-mlir' }
IMAGE_TAG                  = { 'push': 'master',
                               'publish': onnx_mlir_pr_number }
IMAGE_LABELS               = { 'onnx-mlir-llvm-static': LLVM_PROJECT_LABELS,
                               'onnx-mlir-llvm-shared': LLVM_PROJECT_LABELS,
                               'onnx-mlir-dev': ONNX_MLIR_LABELS,
                               'onnx-mlir': ONNX_MLIR_LABELS }
commit_sha1_date_label     = { 'onnx-mlir-llvm-static': 'llvm_project_sha1_date',
                               'onnx-mlir-llvm-shared': 'llvm_project_sha1_date',
                               'onnx-mlir-dev': 'onnx_mlir_sha1_date',
                               'onnx-mlir': 'onnx_mlir_sha1_date' }
dockerfile_sha1_label      = { 'onnx-mlir-llvm-static': 'llvm_project_dockerfile_sha1',
                               'onnx-mlir-llvm-shared': 'llvm_project_dockerfile_sha1',
                               'onnx-mlir-dev': 'onnx_mlir_dockerfile_sha1',
                               'onnx-mlir': 'onnx_mlir_dockerfile_sha1' }
pr_mergeable_state         = {
    'behind':    { 'mergeable': False,
                   'desc': 'the head ref is out of date' },
    'blocked':   { 'mergeable': False,
                   'desc': 'the merge is blocked' },
    'clean':     { 'mergeable': True,
                   'desc': 'mergeable and passing commit status' },
    'dirty':     { 'mergeable': False,
                   'desc': 'the merge commit cannot be cleanly created' },
    'draft':     { 'mergeable': False,
                   'desc': 'the merge is blocked due to the pull request being a draft' },
    'has_hooks': { 'mergeable': True,
                   'desc': 'mergeable with passing commit status and pre-receive hooks' },
    'unknown':   { 'mergeable': False,
                   'desc': 'the state cannot currently be determined' },
    'unstable':  { 'mergeable': True,
                   'desc': 'mergeable with non-passing commit status' } }

# Get the labels of a local docker image, raise exception
# if image doesn't exist or has invalid labels.
def get_local_image_labels(user_name, image_name, image_tag, image_labels):
    info = docker_api.inspect_image(
        user_name + '/' + image_name + ':' + image_tag)
    logging.info('local %s/%s:%s labels: %s', user_name, image_name, image_tag,
                 info['Config']['Labels'])
    labels = info['Config']['Labels']
    if (labels):
        labels_ok = True
        for label in image_labels:
            if not labels[label]:
                labels_ok = False
                break
        if labels_ok:
            return labels
    raise Exception('local image {}/{}:{} does not exist ' +
                    'or has invalid labels'.format(
                        user_name, image_name, image_tag))

# Get the labels of a docker image in the docker registry.
# python docker SDK does not support this so we have to make
# our own REST calls.
def get_remote_image_labels(user_name, image_name, image_tag, image_labels):
    try:
        # Get access token
        resp = requests.get(
            'https://auth.docker.io/token?scope=repository:' +
            user_name + '/' + image_name +
            ':pull&service=registry.docker.io')
        resp.raise_for_status()
        access_token = resp.json()['token']

        # Get manifest, only v1 schema has labels so accept v1 only
        resp = requests.get(
            'https://registry-1.docker.io/v2/' +
            user_name + '/' + image_name + '/manifests/' + image_tag,
            headers={
                'Accept': 'application/vnd.docker.distribution.manifest.v1+json',
                'Authorization': 'Bearer ' + access_token })
        resp.raise_for_status()

        # v1Compatibility is a quoted JSON string, not a JSON object
        manifest = json.loads(resp.json()['history'][0]['v1Compatibility'])
        logging.info('remote %s/%s:%s labels: %s', user_name, image_name, image_tag,
                     manifest['config']['Labels'])
        labels = manifest['config']['Labels']
        if (labels):
            labels_ok = True
            for label in image_labels:
                if not labels[label]:
                    labels_ok = False
                    break
            if labels_ok:
                return labels
        raise Exception('remote image {}/{}:{} does not exist ' +
                        'or has invalid labels'.format(
                            user_name, image_name, image_tag))
    except:
        logging.info(sys.exc_info()[1])
        return ''

# Post a comment on the pull request issue page when the pull request
# source is outdated and publish is rejected.
def post_pr_comment(url, msg):
    try:
        resp = requests.post(
            url,
            headers = {
                'Accept': 'application/json',
                'Authorization': 'token ' + github_jenkins_droid_token },
            data = { 'body': msg })
        resp.raise_for_status()
        logging.info(
            '{ "url": "%s", "created_at": "%s", ' + '"updated_at": "%s", "body": "%s" }',
            resp.json()['url'],
            resp.json()['created_at'],
            resp.json()['updated_at'],
            resp.json()['body'])
    except:
        logging.info(sys.exc_info()[1])

# Get pull request source mergeable state
def get_pr_mergeable_state(url):
    try:
        resp = requests.get(
            url,
            headers = {
                'Accept': 'application/json',
                'Authorization': 'token ' + github_jenkins_droid_token })
        resp.raise_for_status()
        return resp.json()['mergeable_state']
    except:
        logging.info(sys.exc_info()[1])
        return 'unknown'

# Decide whether we should publish the local images or not
def image_publishable(image_type, trigger_phrase):
    user_name    = dockerhub_user_name
    image_name   = IMAGE_NAME[image_type]
    image_tag    = IMAGE_TAG[trigger_phrase]
    image_labels = IMAGE_LABELS[image_name]

    # If local image is missing or has invalid labels, exception
    # will be raised to fail the build.
    local_labels = get_local_image_labels(
        user_name, image_name, image_tag, image_labels)
    remote_labels = get_remote_image_labels(
        user_name, image_name, cpu_arch, image_labels)

    # If url is 'none', it's a push event from merging so skip
    # mergeable state check.
    if onnx_mlir_pr_request_url != 'none':
        state = get_pr_mergeable_state(onnx_mlir_pr_request_url)
        logging.info('mergeable state %s, %s',
                     state, pr_mergeable_state[state]['desc'])
        if not pr_mergeable_state[state]['mergeable']:
            logging.info('publish skipped due to unmergeable state')
            return False
    if not remote_labels:
        logging.info('publish due to invalid remote labels')
        return True
    if onnx_mlir_pr_phrase == 'publish':
        logging.info('publish forced by trigger phrase')
        return True
    if (local_labels[commit_sha1_date_label[image_name]] >
        remote_labels[commit_sha1_date_label[image_name]]):
        logging.info('publish due to newer local sha1 date')
        return True
    # Commits can only be merged one at a time so it's guaranteed
    # that the same commit sha1 date will have the same commit sha1,
    # and vise versa.
    #
    # For llvm-project images, if commit sha1 are the same but the
    # dockerfile for building them changed, they will be published.
    # For onnx-mlir images, if commit sha1 are the same, it's
    # guaranteed the dockerfile for building them are the same, so
    # they will not be published.
    if (local_labels[commit_sha1_date_label[image_name]] ==
        remote_labels[commit_sha1_date_label[image_name]] and
        local_labels[dockerfile_sha1_label[image_name]] !=
        remote_labels[dockerfile_sha1_label[image_name]]):
        logging.info('publish due to different dockerfile sha1')
        return True

    logging.info('publish skipped due to older or identical local image')
    return False

def publish_image(image_type, trigger_phrase):

    if not image_publishable(image_type, trigger_phrase):
        return

    user_name   = dockerhub_user_name
    image_name  = IMAGE_NAME[image_type]
    image_tag   = IMAGE_TAG[trigger_phrase]
    image_repo  = user_name + '/' + image_name

    # Tag the image with arch
    logging.info('tagging %s:%s -> %s:%s',
                 image_repo, image_tag, image_repo, cpu_arch)
    docker_api.tag(image_repo + ':' + image_tag,
                   image_repo, cpu_arch, force = True)

    # Push the image tagged with arch then remove it, regardless of
    # whether the push worked or not.
    logging.info('pushing %s:%s', image_repo, cpu_arch)
    try:
        for line in docker_api.push(repository = image_repo,
                                    tag = cpu_arch,
                                    auth_config = {
                                        'username': dockerhub_user_name,
                                        'password': dockerhub_user_token },
                                    stream = True, decode = True):
            print((line['id']+': '
                   if 'id' in line and 'progress' not in line else '') +
                  (line['status'] + '\n'
                   if 'status' in line and 'progress' not in line else ''),
                  end = '', flush = True)
    finally:
        docker_api.remove_image(image_repo + ':' + cpu_arch, force = True)

def main():
    for image_type in [ 'static', 'shared', 'dev', 'usr' ]:
        publish_image(image_type, onnx_mlir_pr_phrase)

if __name__ == "__main__":
    main()
