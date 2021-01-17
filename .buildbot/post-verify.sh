#!/bin/bash

curl -s ${GITHUB_ISSUE_COMMENTS_URL} \
     -X POST \
     -H "Accept: application/json" \
     -H "Authorization: token ${GITHUB_JENKINS_DROID_TOKEN}" \
     -d '{"body": "Can one of the admins verify this patch?"}'
