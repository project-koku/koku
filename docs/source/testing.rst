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

Example::

    $ make docker-up
    $ tox
    $ make docker-down

Unit testing using OpenShift
---------------------------------

The ``Makefile`` provides convenience commands for enabling port-forwarding. This is required for accessing a database pod hosted within an OpenShift environment.

Example::

    $ make oc-create-all
    $ make oc-forward-ports
    $ tox
    $ make stop-forwarding-ports

Unit testing log messages
-------------------------
The logger is disabled by default during unit tests. If you are building a unit test that asserts log messages, you must re-enable the logger. For example::

    import logging
    with self.assertLogs(logger='masu.external.downloader.aws.aws_report_downloader', 
    level='WARN') as cm:
                logging.disable(logging.NOTSET)
                self.aws_report_downloader._remove_manifest_file("None")
                self.assertEqual(['WARN: Could not delete manifest file at'], cm.output)

If you observe the following error in the tox tests, you may sometimes ignore it, due to the environment variable DEBUG=TRUE sometimes not being TRUE::
    
    FAIL: test_delete_single_provider_skips_delete_archived_data_if_customer_is_none 
    (api.provider.test.tests_models.ProviderModelTest)
    Assert the delete_archived_data task is not called if Customer is None.
    ----------------------------------------------------------------------
    Traceback (most recent call last):
    File "/usr/local/Cellar/python/3.7.4_1/Frameworks/Python.framework/Versions/3.7/lib/python3.7/unittest/mock.py", line 1209, in patched
    return func(*args, **keywargs)
    File "/Users/nbonilla/Documents/Koku/koku/koku/api/provider/test/tests_models.py", line 43, in test_delete_single_provider_skips_delete_archived_data_if_customer_is_none
    self.aws_provider.delete()
    AssertionError: no logs of level WARNING or higher triggered on api.provider.models


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

settings.local.yaml::

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
   

Smoke test::

    $ cd koku/testing
    $ ./run_smoke_tests.sh
    

tox
===

To run a specific tox test, you may run a command below, replacing everything after the :code:`--` with your specific modules and files::

    tox -e py36 -- masu.test.external.downloader.azure.test_azure_services.AzureServiceTest

This will selectively run only the AzureServiceTest module
The argument can be vague or specified further, for example the following arguments would separately be considered valid:

    - masu.test.external
    - masu.test.external.downloader.azure.test_azure_services.AzureServiceTest.specific_test

Debugging Options
=================

Running PDB in dockerized koku
------------------------------

To use pdb while running the koku-server in docker:
    1. Ensure all migrations are run.
    2. Stop the server `docker-compose stop koku-server`
    3. Run the server with service-ports: :code:`docker-compose run —service-ports koku- 
       server`
    4. set a breakpoint using :code:`import pdb; pdb.set_trace()`

Breakpoints should now be stopped at, in this terminal window.


Running PDB in IQE
------------------
To run PDB while using dockerized IQE: 
    Start a shell session in the docker container that runs IQE::

        koku/testing/run_test.sh bash

To run a specific test, use the following command. Replace :code:`-k` flag's input to a specific test you want to run::

    iqe tests plugin hccm -k test_api_aws_storage_filtered_top --pdb

optionally you can, run all tests::

    iqe tests plugin hccm --pdb

Any test that fails should start a PDB session.

Smoke testing with IQE
======================

Prerequisites:
    - koku is deployed via docker-compose or other method, 
    - you are connected to the Red Hat internal network

Running IQE in Docker
---------------------

To run IQE Smoke, Vortex or API tests, run one of the following commands, respectively::

    make docker-iqe-smokes-tests
    make docker-iqe-vortex-tests
    make docker-iqe-api-tests

Running IQE source code
-------------------------------
There need to be clones of the following git repositories:

  - koku
  - iqe
  - hccm-plugin

You will need to edit the settings file to match your environment: ``koku.git/testing/conf/settings.local.yaml``
