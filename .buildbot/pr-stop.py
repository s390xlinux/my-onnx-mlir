#!/usr/bin/env python3

import jenkins

def stop_previous_build(job_name, build_number, param_name):
    """We allow concurrent builds for different pull request numbers
    but for the same pull request number only one build can run. So
    when a new build starts, a previous build with the same pull request
    number needs to be stopped."""

    jenkins_server = jenkins.Jenkins('http://localhost:8080/jenkins',
                                     username='jenkins',
                                     password=os.getenv('JENKINS_API_TOKEN'))
    running_builds = jenkins_server.get_running_builds()

    # Look for a running build that has the same job_name and uses the
    # same parameter value. When found, the build MUST have a smaller
    # build number if not ourselves.
    for build in running_builds:
        if (build['name'] == job_name and build['number'] < build_number):
            build_info = jenkins_server.get_build_info(build['name'],
                                                       build['number'])
            print(build_info['actions'][1])
    
