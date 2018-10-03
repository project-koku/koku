Installation
============

Project Koku is divided into logical components. To achieve a fully functional
application, it requires the deployment of multiple micro-applications.

The primary applications for Project Koku are:

* Koku API (Reporting and Query API service)
* Koku UI (Front-end Web UI)
* Masu (Data ingestion service)

For development and testing, Project Koku also includes:

* Nise (Test data generator)
* Hansei (Test automation framework)

This guide will focus on deploying Project Koku into an existing `OpenShift <https://www.okd.io/>`_ cluster.

Deploying the Koku API
----------------------

The Koku application contains two components - a web service and database.

A basic deployment configuration is contained within the application's `openshift template file <https://github.com/project-koku/koku/blob/master/openshift/koku-template.yaml>`__. This template should be acceptable for most use cases. It provides parameterized values for most configuration options.

To deploy the Koku API application using the provided templates, you can use
the provided ``Makefile``:

    ``make oc-create-all``

To deploy individual components, there are also ``make`` commands provided for your convenience:

    Deploy the API web application: ``make oc-create-koku``
    Deploy the PostgreSQL database: ``make oc-create-db``

Deploying the Koku UI
----------------------

The Koku-UI application is the web-based frontend for Project Koku. It is built
using `Patternfly <https://www.patternfly.org/>`_ and `ReactJS <https://reactjs.org/>`_.

A basic deployment configuration is contained within the application's `openshift template file <https://github.com/project-koku/koku-ui/blob/master/openshift>`__. This template should be acceptable for most use cases. It provides parameterized values for most configuration options.

To deploy the Koku UI, you can execute this command:

    ``oc process -f openshift/koku-ui-template.yml -p <PARAM>=<VALUE> [...] | oc create -f -``

Next, you will need to manually start a new build of the application: ``oc start-build bc/koku-ui``

Deploying Masu
----------------------

The Masu application contains several components - a web service, message bus, and workers. Masu also uses the Koku database. Configuration and management of the database are controlled from the Koku API application.

A basic deployment configuration is contained within the application's `openshift template files <https://github.com/project-koku/masu/blob/master/openshift>`__. These templates should be acceptable for most use cases.

Parameterized values for most configuration options can be set using the provided example files. Copy the example file, removing the ``.example`` suffix. Then, update the parameter values as needed.

Once the parameter files have been configured, the provided ``Makefile`` can be used to deploy the Masu components.

To deploy all Masu components at once:

    ``make oc-create-all``

There are also ``make`` commands to deploy individual components:

    Deploy the web application: ``make oc-create-masu``
    Deploy the message bus: ``make oc-create-rabbit``
    Deploy the workers: ``make oc-create-worker``

