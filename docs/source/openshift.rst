Working with OpenShift
======================

We are currently developing using OpenShift version 3.7. There are different setup requirements for Mac OS and Linux (instructions are provided for Fedora).

Run `oc cluster up` once before running the make commands to generate the referenced config file.

Openshift does offer shell/tab completion. It can be generated for either bash/zsh and is available by running `oc completion bash|zsh` The following example generates a shell script for completion and sources the file.  ::

    oc completion zsh > $HOME/.oc/oc_completion.sh
    source $HOME/.oc/oc_completion.sh

Local Development Cluster
-------------------------
The following commands can be used to manually create an OpenShift cluster with the necessary components to run koku. ::

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

Alternatively, make commands are provided as a convenience. ::

  # Start the OpenShift cluster
  make oc-up

  # Terminate the OpenShift cluster
  make oc-down

  # Clean out local data
  make oc-clean

There are a few ways to use OpenShift while developing Koku. It is possible to spin up the entire application and its dependent services, or just the dependent services can be spun up while using the local Django dev server. ::

  # Run everything through OpenShift
  make oc-up-all

  # Run *just* a database in Openshift, while running the server locally
  make oc-up-db
  # Run Django migrations to initialize the database
  make oc-run-migrations
  # Run the Django server locally with access to the OpenShift database
  make oc-serve

To gain temporary access to the database within OpenShift, port forwarding is used. ::

  # Port forward to 15432
  make oc-forwrd-ports

  psql koku -U kokuadmin -p 15432 -h localhost

  # Stop port forwarding
  make oc-stop-forwarding-ports

Fedora
------

The setup process for Fedora is well outlined in two articles.
First, get Docker up and running. `Getting Started with Docker on Fedora`_.

Then follow these instructions to get OpenShift setup `OpenShift — Fedora Developer Portal`_.


Mac OS
-------

There is a known issue with Docker for Mac ignoring `NO_PROXY` settings which are required for OpenShift. (https://github.com/openshift/origin/issues/18596) The current solution is to use a version of Docker prior to 17.12.0-ce, the most recent of which can be found at `docker-community-edition-17091-ce-mac42-2017-12-11`_

Docker needs to be configured for OpenShift. A local registry and proxy are used by OpenShift and Docker needs to be made aware.

Add `172.30.0.0/16` to the Docker insecure registries which can be accomplished from Docker -> Preferences -> Daemon. This article details information about insecure registries `Test an insecure registry | Docker Documentation`_

Add `172.30.1.1` to the list of proxies to bypass. This can be found at Docker -> Preferences -> Proxies

.. _`Getting Started with Docker on Fedora`: https://developer.fedoraproject.org/tools/docker/docker-installation.html
.. _`OpenShift — Fedora Developer Portal`: https://developer.fedoraproject.org/deployment/openshift/about.html
.. _`docker-community-edition-17091-ce-mac42-2017-12-11`: https://docs.docker.com/docker-for-mac/release-notes/#docker-community-edition-17091-ce-mac42-2017-12-11
.. _`Test an insecure registry | Docker Documentation`: https://docs.docker.com/registry/insecure/


Troubleshooting
---------------

OpenShift uses Docker to run containers. When running a cluster locally for developement, deployment can be strained by low resource allowances in Docker. For development it is recommended that Docker have at least 4 GB of memory available for use.

Also, if Openshift services misbehave or do not deploy properly, it can be useful to spin the cluster down, restart the Docker service and retry.

Generating the Template
=======================

To generate a new template from a running configuration, use this command. ::

    oc export all -o yaml --as-template=my-new-template > openshift/my-new-template.yaml
