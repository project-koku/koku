#!/bin/bash

oc login -u system:admin https://127.0.0.1:8443

OUT=$(oc get -n openshift -o yaml is postgresql | grep -c 'tag: "9\.6"')
if [ $OUT != 1 ]; then
    oc create -n openshift istag postgresql:9.6 --from-image=centos/postgresql-96-centos7
fi
OUT=$(oc get -n openshift -o yaml is python | grep -c 'tag: "3\.6"')
if [ $OUT != 1 ]; then
    oc create -n openshift istag python:3.6 --from-image=centos/python-36-centos7
fi

# TODO: add intelligence or user-prompt for git tag or somesuch
oc new-app --file=openshift/saltcellar-template.yaml \
           --code=https://github.com/SaltCellar/SaltCellar.git#36-status-endpoint
