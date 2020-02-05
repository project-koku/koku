.. _`tox`: https://tox.readthedocs.io/en/latest/
.. _`nise`: https://github.com/project-koku/nise
.. _`.env.example`: https://github.com/project-koku/koku/blob/master/.env.example

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

If you observe the following error when running the unit tests, it may be a false error. This can be due to some tests expecting the DEBUG setting to be TRUE::

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


Run specific unit tests
-----------------------

To run a specific subset of unit tests, you can pass a particular module path to tox. To do this, use positional args using the :code:`--` separator. For example::

    tox -e py36 -- masu.test.external.downloader.azure.test_azure_services.AzureServiceTest

The previous command will selectively run only the AzureServiceTest module
The following are examples of valid module paths:

    - masu.test.external
    - masu.test.external.downloader.azure.test_azure_services.AzureServiceTest.specific_test

Functional Testing
==================

It is often necessary to load test data into a local development environment to test functionality of a new feature.

Using default test data
-----------------------
Within the koku repo there are scripts to automate the creation of a test customer with a default set of sources. This will create one AWS, one Azure, and three OpenShift sources to simulate the following scenarios.

    - OpenShift running on AWS
    - OpenShift running on Azure
    - OpenShift on premises

There is a complementary script to subsequently load test data for each source. The `nise`_ project is used to generate this test data. Nise is a dev dependency of koku, so a working copy of the nise command line tool shoudl be availble after running `pipenv install --dev`. A local clone of the nise repository is also required as it contains static YAML files used by this script. Before using this script, make sure the following variables are defined in your environment. See `.env.example`_ for example values.

    - API_PATH_PREFIX
    - NISE_REPO_PATH
    - KOKU_API_HOSTNAME
    - MASU_API_HOSTNAME
    - KOKU_PORT (if using docker-compose)
    - MASU_PORT (if using docker-compose)

Examples
++++++++

Example 1. Using docker-compose to wipe and rebuild the local database with test data::

    make docker-reinitdb-with-providers
    make load-test-customer-data

Example 2. Assuming the database is already clean and does not need to be rebuilt::

    make create-test-customer
    make load-test-customer-data

Example 3. Using custom date ranges::

    make load-test-customer-data start=2020-01-01 end=2020-02-29

Manually loading test data into the database
--------------------------------------------

Before running any functional testing, you will need to populate your database
with test data.

Using `nise`_ for generating test data is recommended.


Debugging Options
=================

PDB in koku container
---------------------

While koku-server is running in a docker container:

1. Ensure all migrations are run.
2. Stop the server `docker-compose stop koku-server`
3. Run the server with service-ports: :code:`docker-compose run —service-ports koku-server`
4. set a breakpoint using :code:`import pdb; pdb.set_trace()`


PDB in IQE container
--------------------

Set the environment variable ENV_FOR_DYNACONF=local
While IQE (the integration test suite) is running a docker container:

    Start a shell session in the docker container that runs IQE::

        koku/testing/run_test.sh bash

The following command runs all QE api tests. The optional :code:`--pdb` flag will cause any failed test to automatically start a pdb session::

    iqe tests plugin hccm -k test_api --pdb

To run a subset of the above tests, for example only smoke tests::

    iqe tests plugin hccm -k test_api -m hccm_smoke --pdb

To run the vortex the tests::

    iqe tests plugin hccm -k test_api -m qa --pdb

To run a specific subset of the integration test suite, you can specify a single test using the :code:`-k` flag. The single test names can be found in the IQE repo. Here is an example of running a single test named :code:`test_api_aws_storage_filtered_top`::


    iqe tests plugin hccm -k test_api_aws_storage_filtered_top --pdb

The single test name above was found in the hccm plugin repo itself at https://gitlab.cee.redhat.com/insights-qe/hccm-plugin/blob/master/iqe_hccm/tests/rest_api/v1/test_aws_storage_reports.py#L245
Any function definition name in this file can be passed in as the parameter for :code:`-k` to run specifically that test. To find more specific test names, search that repo for test function names.


Smoke testing with IQE
======================

Prerequisites:

    - koku is running and accessible via the network
    - you are connected to the Red Hat internal network

For a quick start on smoke testing, continue to the section Running IQE in Docker below.
Otherwise, for more in-depth information on IQE, see https://gitlab.cee.redhat.com/insights-qe/hccm-plugin/tree/master


Running IQE in Docker
---------------------

To run IQE Smoke, Vortex or API tests, run one of the following commands, respectively::

    make docker-iqe-smokes-tests
    make docker-iqe-vortex-tests
    make docker-iqe-api-tests
