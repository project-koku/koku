Working with OpenShift
======================

local development cluster
-------------------------

::

  # bring up a new dev cluster
  oc cluster up \
        --image=$(OC_SOURCE) \
        --version=$(OC_VERSION) \
        --host-data-dir=$(OC_DATA_DIR)

  # log in as cluster admin
  oc login -u system:admin

  # import postgresql-9.6 imagestream
  oc create -n openshift istag postgresql:9.6 --from-image=centos/postgresql-96-centos7

  # import python-3.6 imagestream
  oc create -n openshift istag python:3.6 --from-image=centos/python-36-centos7

  # create the app
  oc new-app openshift/templates/django-postgresql-persistent.json

