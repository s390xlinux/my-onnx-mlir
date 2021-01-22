#!/usr/bin/env python3

import jenkins
import logging
import os

logging.basicConfig(
    level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

jenkins_rest_api_token = os.getenv('JENKINS_REST_API_TOKEN')
jenkins_job_name       = os.getenv('JOB_NAME')
jenkins_build_number   = os.getenv('BUILD_NUMBER')

onnx_mlir_pr_number    = os.getenv('ONNX_MLIR_PR_NUMBER')

# We allow concurrent builds for different pull request numbers
# but for the same pull request number only one build can run. So
# when a new build starts, a previous build with the same pull
# request number needs to be stopped.
#
# One complication is that a pull request may be built by different
# jobs. For example, it can be built by a push triggered job, or by
# a comment triggered job. And there is no correlation between the
# build numbers of the two jobs.
#
# So we simple look for any running build with the same pull request
# number, which is set by the job parameter.
def stop_previous_build(job_name, build_number, param_name, param_number):
    jenkins_server = jenkins.Jenkins('http://localhost:8080/jenkins',
                                     username = 'jenkins',
                                     password = jenkins_rest_api_token)
    running_builds = jenkins_server.get_running_builds()

    for build in running_builds:
        # Skip ourselves
        if (build['name'] == job_name and build['number'] == int(build_number)):
            continue
        build_info = jenkins_server.get_build_info(build['name'],
                                                   build['number'])
        for action in build_info['actions']:
            # The build uses the same parameter name and value,
            # which means it's a job for the same pull request
            # number. So stop it.
            if ('_class' in action and
                action['_class'] == 'hudson.model.ParametersAction' and
                'parameters' in action and
                action['parameters'] and
                action['parameters'][0]['name'] == param_name and
                action['parameters'][0]['value'] == param_number):

                logging.info('Stopping job %s build #%s for pull request #%s',
                             build['name'], build['number'], param_number)
                jenkins_server.stop_build(build['name'], build['number'])

def main():
    stop_previous_build(jenkins_job_name, jenkins_build_number,
                        'ONNX_MLIR_PR_NUMBER', onnx_mlir_pr_number)

if __name__ == "__main__":
    main()
