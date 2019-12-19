.. _`tox`: https://tox.readthedocs.io/en/latest/
.. _`nise`: https://github.com/project-koku/nise

~~~~~~~~~~~~
Testing Koku
~~~~~~~~~~~~

Unit testing
============

Unit testing for Koku is handled through `tox`_.

Running the test suite requires a minimum of an accessible database and Koku API server.

Unit testing using docker-compose
---------------------------------

Example:
::
    $ make docker-up
    $ tox
    $ make docker-down

Unit testing using OpenShift
---------------------------------

The ``Makefile`` provides convenience commands for enabling port-forwarding. This is required for accessing a database pod hosted within an OpenShift environment.

Example:
::
    $ make oc-create-all
    $ make oc-forward-ports
    $ tox
    $ make stop-forwarding-ports

Smoke testing
=============

Running the QE functional and smoke tests is achieved through the scripts provided in ``koku.git/testing``

Requirements
------------
In order to run the test suite, there need to be clones of the following git repositories:

  - koku
  - iqe
  - hccm-plugin

You will need to edit the settings file to match your environment: ``koku.git/testing/conf/settings.local.yaml``

Loading test data into the database
-----------------------------------

Before running any functional testing, you will need to populate your database
with test data.

Using `nise`_ for generating test data is recommended.

Testing using OpenShift
-----------------------

If your test environment is hosted on an OpenShift cluster, you will need to
ensure that routes are created to expose the Koku and Masu API endpoints.

You can use the ``oc expose`` command to accomplish this.

Examples
--------

settings.local.yaml:
::
    local:
      hccm:
        ocp_dir: /var/tmp/masu/insights_local
        aws_dir: /tmp/local_bucket
        azure_dir: /tmp/local_container
        masu:
          path: api/cost-management/v1
          port: 5000
          hostname: masu-hccm.apps-crc.testing
          scheme: http
      main:
        hostname: koku-hccm.apps-crc.testing
        scheme: http
        default_user: default
        api_path: api/cost-management/v1
      http:
        default_auth_type: basic
      users:
        default:
          username: user_dev@foo.com
          password: password
   

Smoke test:
::
    $ cd koku/testing
    $ ./run_smoke_tests.sh
    
To use pdb while running the koku-server in docker:
Ensure all migrations are run.
Stop the server `docker-compose stop koku-server`
Run the server with service-ports: `docker-compose run —service-ports koku-server`
Breakpoints will now be stopped in this terminal window.

To test a specific file using tox, edit this line, for example:
`coverage run {toxinidir}/koku/manage.py test --noinput -v 2 {posargs: masu.test.database}`
This will selectively run only the masu database tests, instead of running all of the rest of the tox tests.
