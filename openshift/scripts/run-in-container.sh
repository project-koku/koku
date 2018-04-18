#!/bin/bash

# Use this script to run one-off commands inside a container of a pod where your
# Python application code lives in.

# You can accomplish the same results by using regular commands from OpenShift.
# This script is just wrapping calls to `oc` to make it a little more
# convenient to use. In the future, the `oc` cli tool might incorporate changes
# that make this script obsolete.

# Related GitHub issues:
# - https://github.com/GoogleCloudPlatform/kubernetes/issues/8876
# - https://github.com/openshift/origin/issues/2001


# Usage examples:
#
#     ./run-in-container.sh ./manage.py migrate
#     ./run-in-container.sh ./manage.py createsuperuser
#     ./run-in-container.sh ./manage.py shell
#
# If your Python pods are labeled with a name other than "django", you can use:
#
#     POD_NAME=name ./run-in-container.sh ./manage.py check
#
# If there is more than one replica, you can also specify a POD by index:
#
#     POD_INDEX=1 ./run-in-container.sh ./manage.py shell
#
# Or both together:
#
#     POD_NAME=frontend POD_INDEX=2 ./run-in-container.sh ./manage.py shell


# Get name of a currently deployed pod by label and index
POD_INSTANCE_NAME=`oc get pods \
  -l "name=${POD_NAME:-django-frontend}" \
  -t "{{ with index .items ${POD_INDEX:-0} }}{{ .metadata.name }}{{ end }}"`

# Run command in a container of the specified pod:
oc exec -p "$POD_INSTANCE_NAME" -it -- bash -c "${@:-echo}"
