.. _`OpenShift`: https://docs.okd.io/
.. _`minishift`: https://github.com/minishift/minishift
.. _`Kubernetes`: https://kubernetes.io/docs/home/
.. _`Docker`: https://docs.docker.com/
.. _`crc`: https://github.com/code-ready/crc
.. _`Red Hat Registry Authentication`: https://access.redhat.com/RegistryAuthentication

~~~~~~~~~~~~~~~~~~~~~~~~~~
Developing using OpenShift
~~~~~~~~~~~~~~~~~~~~~~~~~~

The recommended development workflow is to develop using the same tools the application uses as its target environment. In this case, Koku is intended for use inside an OpenShift deployment. Therefore, it is recommended that Koku development also use an OpenShift deployment. Developing using OpenShift will align not only the software architecture, but also ensures the developer builds familiarity with the toolchain.

Prerequistes
============

Developing Koku using OpenShift requires prerequisite knowledge and workstation configuration. Please ensure that you are familiar with the following software and have configured your workstation accordingly.

- `OpenShift`_
- `Kubernetes`_
- `Docker`_

When ready, your workstation should be able to run containers and deploy `OpenShift`_, either using `minishift`_ or an alternative installer.

Local Development
=================

Minishift (OKD 3.11)
--------------------

The recommended way to deploy a local OpenShift 3.x installation on Linux for Koku development is to use `minishift`_. This runs an OpenShift cluster inside of a VM.

Installing and configuring `minishift`_ is outside the scope of this document.  Please refer to the `minishift`_ documentation for details.

In order to access RHEL images for building Koku, you must configure `Red Hat Registry Authentication`_:

For username/password, you can use the minishift's ``redhat-registry-login``
addon:

::
    minishift addons enable redhat-registry-login
    minishift addons apply redhat-registry-login --addon-env REGISTRY_USERNAME=${USERNAME} --addon-env REGISTRY_PASSWORD=${PASSWORD}


For token-based authentication, you will need to configure the secret manually
in your project:

::
    # this extracts the nested object from the file distributed by https://access.redhat.com/terms-based-registry
    cat /path/to/registry-pull-secret.yaml | \
             python -c 'import yaml, sys; print(yaml.safe_load(sys.stdin).get("data").get(".dockerconfigjson"))' | \
             base64 -d | \
             oc create secret generic registry-redhat-io-secret \
                                    --from-file=.dockerconfigjson=/dev/stdin \
                                    -n myproject \
                                    --type=kubernetes.io/dockerconfigjson
    oc secrets link default registry-redhat-io-secret -n myproject --for=pull
    oc secrets link builder registry-redhat-io-secret -n myproject

CodeReady Containers (OKD 4.x)
------------------------------
The recommended way to deploy a local OpenShift 4.x installation on Linux for Koku development is to use `crc`_. This runs an OpenShift cluster inside of a VM.

Installing and configuring `crc`_ is outside the scope of this document.  Please refer to the `crc`_ documentation for details.

In order to access RHEL images for building Koku, you must configure `Red Hat Registry Authentication`_.


Running locally in OpenShift using e2e-deploy
---------------------------------------------
The script ``scripts/e2e-deploy.sh`` handles setup and configuration of `crc`_ or OKD 3.11, including `Red Hat Registry Authentication`_. To use the script, complete the following steps.

1. First, make sure that you have cloned and followed the setup instructions of the following repos::

    - https://github.com/project-koku/koku
    - https://github.com/RedHatInsights/e2e-deploy
    - https://gitlab.cee.redhat.com/insights-qe/iqe-tests.git

2. Next, make sure that you have the following tools installed::

    - oc
    - ocdeployer
    - iqe
    - python
    - base64

3. Finally, either export the following environment variables or add them to a .env file and enter the IQE virtual environment::

    OPENSHIFT_API_URL=YOUR_OPENSHIFT_API_URL
    REGISTRY_REDHAT_IO_SECRETS=PATH_TO_RH_REGISTRY_YAML
    E2E_REPO=PATH_TO_LOCAL_E2E_REPO

**Note:**  If you're using crc the ``OPENSHIFT_API_URL`` will be ``https://api.crc.testing:6443`` and if you're using OKD 3.11 it will be ``https://127.0.0.1:8443/``. The ``REGISTRY_REDHAT_IO_SECRETS`` will be the path to the  file distributed by https://access.redhat.com/terms-based-registry. If your account does not have access to the content, you should file an issue with https://redhat.service-now.com/help and reach out to a teammate to share the file so that you are unblocked.

4. Now that you are inside of the IQE virtual environment, change directories to the scripts folder inside of the koku repo (``koku/scripts``). Make sure that you have initiated a bare bones OpenShift cluster (``oc cluster up`` if you are using OKD 3.11) and then run the e2e-deploy script. This will set up your secrets in the secrets project, pull down and build the required images for koku, and deploy the project.

**Note:** If you are getting intermittent deployment failures that don't make sense, you could try increasing the memory and CPUs allotted to docker.

5. To delete all of the objects created by running the e2e-deploy script, run ``make oc-delete-e2e``.

Deploying Services
------------------

Koku is implemented as a collection of services. During development, it is not required to deploy all services. It is possible to deploy subsets of services based on the focus of the development effort.

The ``Makefile`` in the Koku git repository provides targets intended to assist with development by enabling deployment and management of Koku's services within a local OpenShift installation. See ``make help`` for more information about the available targets.

Service Dependencies
^^^^^^^^^^^^^^^^^^^^

- PostgreSQL: the database is required for most Koku services.

- RabbitMQ: the message bus is required for report polling and processing.

- Redis: the key-value store is required for caching credentials from an external authentication service.

OpenShift Templates
^^^^^^^^^^^^^^^^^^^

OpenShift templates are provided for all service resources. Each template includes parameters to enable customization to the target environment.

The ``Makefile`` targets include scripting to dynamically pass parameter values into the OpenShift templates. A developer may define parameter values by placing a parameter file into the ``koku.git/openshift/parameters`` directory.

Examples of parameter files are provided in the ``koku.git/openshift/parameters/examples`` directory.

The ``Makefile`` scripting applies parameter values only to matching templates based on matching the filenames of each file. For example, parameters defined in ``koku-api.env`` are applied *only* to the ``koku-api.yaml`` template. As a result, common parameters like ``NAMESPACE`` must be defined consistently within *each* parameter file.


General Platform information
============================

When developing using OpenShift, there are different setup requirements for Linux and Mac OS. Linux instructions are provided for Fedora/RHEL/CentOS.

CLI Tab Completion
------------------
The Openshift client (``oc``) does offer shell/tab completion. It can be generated for either bash/zsh and is available by running `oc completion bash|zsh` The following example generates a shell script for completion and sources the file.  ::

    oc completion zsh > $HOME/.oc/oc_completion.sh
    source $HOME/.oc/oc_completion.sh

Mac OS
-------

There is a known issue with Docker for Mac ignoring `NO_PROXY` settings which are required for OpenShift. (https://github.com/openshift/origin/issues/18596) The current solution is to use a version of Docker prior to 17.12.0-ce, the most recent of which can be found at `docker-community-edition-17091-ce-mac42-2017-12-11`_

Docker needs to be configured for OpenShift. A local registry and proxy are used by OpenShift and Docker needs to be made aware.

Add `172.30.0.0/16` to the Docker insecure registries which can be accomplished from Docker -> Preferences -> Daemon. This article details information about insecure registries `Test an insecure registry | Docker Documentation`_

Add `172.30.1.1` to the list of proxies to bypass. This can be found at Docker -> Preferences -> Proxies

.. _`docker-community-edition-17091-ce-mac42-2017-12-11`: https://docs.docker.com/docker-for-mac/release-notes/#docker-community-edition-17091-ce-mac42-2017-12-11
.. _`Test an insecure registry | Docker Documentation`: https://docs.docker.com/registry/insecure/


Troubleshooting
---------------

- When running a cluster locally for developement, it is recommended that your workstation can allocate at least 4 GB of memory available for use.

- Accessing the database when it is running inside an OpenShift deployment will require either a remote shell or port forwarding. The ``Makefile`` provides targets for managing port forwarding.
