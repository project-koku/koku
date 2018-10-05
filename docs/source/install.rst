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

Instructions for deploying the Koku UI can be found here: https://github.com/project-koku/koku-ui#getting-started

Deploying Masu
----------------------
The Masu application contains several components - a web service, message bus, and workers. Masu also uses the Koku database. Configuration and management of the database are controlled from the Koku API application.

Instructions for deploying Masu can be found here: https://github.com/project-koku/masu#getting-started
