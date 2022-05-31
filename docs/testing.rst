.. _`tox`: https://tox.readthedocs.io/en/latest/
.. _`nise`: https://github.com/project-koku/nise
.. _`.env.example`: https://github.com/project-koku/koku/blob/main/.env.example

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
          port: 5042
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

There is a complementary script to subsequently load test data for each source. The `nise`_ project is used to generate this test data. Nise is a dev dependency of koku, so a working copy of the nise command line tool should be available after running `pipenv install --dev`. See `.env.example`_ for example values.

    - API_PATH_PREFIX
    - KOKU_API_HOSTNAME
    - MASU_API_HOSTNAME
    - KOKU_PORT (if using docker-compose)
    - MASU_PORT (if using docker-compose)

Examples
++++++++

Example 1. Using docker-compose to wipe and rebuild the local database with test data::

    make docker-reinitdb-with-sources
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

Testing with Ingress
====================

It may be necessary to test changes related to Kafka using Ingress in a local development environment to test the functionality of a new feature.

Setting up Ingress
------------------

First, you need to obtain the source for the ingress project::

    git clone https://github.com/RedHatInsights/insights-ingress-go

Next, you should add/modify the following variables in the existing ``.env`` file for the ingress environment::

    STORAGE_DRIVER=localdisk
    ASYNC_TEST_TIMEOUT=10
    MINIO_DATA_DIR=/tmp/hccm/mnt/data
    MINIO_CONFIG_DIR=/tmp/hccm/mnt/config
    INGRESS_VALID_TOPICS=testareno,advisor,hccm

Since both Ingress and Koku are ran locally via docker-compose files, we must ensure that all of the services are on the same network. We can do that by creating a network in the Ingress ``docker-compose.yml`` file and adding it to each of the services in both Ingress and Koku. To create a network, add the following to the Ingress ``docker-compose.yml``::

    networks:
      myNetwork:
        driver: bridge

Add ``myNetwork`` to each of the Ingress services using the following example::

    kafka:
      image: confluentinc/cp-kafka
      ports:
        - 29092:29092
      depends_on:
        - zookeeper
      environment:
        - KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:29092
        - KAFKA_BROKER_ID=1
        - KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1
        - KAFKA_ZOOKEEPER_CONNECT=zookeeper:32181
        - LISTENER_EXTERNAL=PLAINTEXT://localhost:29092
      networks:
        - myNetwork

Now, we must define the external network that we just created in Ingress in the ``docker-compose.yml`` for koku. Modify the file to include the external network and add it to each service using the kafka example above, noting that the name of the external network is ``insightsingressgo_myNetwork``::

    networks:
      insightsingressgo_myNetwork:
        external: true


Next, install the development requirements, enter the pip environment and bring up the ingress service::

    pipenv install --dev
    pipenv shell
    docker-compose up --build

If necessary, you can bring up a consumer to see the contents of messages that are uploaded to the ``hccm`` topic using the following command within the ingress environment::

     docker-compose exec kafka kafka-console-consumer --topic=platform.upload.hccm --bootstrap-server=localhost:29092

Finally, you can bring up Koku project via docker-compose and check the koku-listener logs to ensure the listener has successfully connected and is listening for messages.

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

Testing Performance with cProfile
=================================

Tools such as `cProfile <https://docs.python.org/3/library/profile.html>`_ and `pstats <https://docs.python.org/3/library/profile.html#module-pstats>`_ can be used to identify potential performance problems within the code base.

**Creating the Profiler Code**

The cProfile code written in this step will heavily depend on what part of the project's code you are trying to profile. For example, the code below is profiling the ``DateHelper`` function inside of ``koku.api.utils``::

    import cProfile
    profile_text = """
    # The section of code you want to profile:
    from api.utils import DateHelper
    dh = DateHelper
    dh.now
    dh.now_utc
    """
    cProfile.run(profile_text, filename="ouput_filename.file")

**Runnin the Profiler Code**

The profiler code must be executed inside of a django environment in order to import koku's python modules. The profiler code can be directly ran through a shell through the following method::

    DJANGO_READ_DOT_ENV_FILE=True python koku/manage.py shell
    >>> import cProfile
    >>> profile_text = """
    ... from api.utils import DateHelper
    ... dh = DateHelper
    ... dh.now
    ... dh.now_utc
    ... """
    >>> cProfile.run(profile_text, filename="ouput_filename.file")

However, if the profiler code is rather large it can be saved into a python script and executed inside of the django environment::

    DJANGO_READ_DOT_ENV_FILE=True python koku/manage.py shell < profile_code.py

**Analyzing the Results**

After running the profiler code, statistics regarding the code is stored in the filename specified here: ``cProfile.run(profile_text, filename="ouput_filename.file")``. Pstats can be used to organize the information inside of this file, for example::

    import pstats

    ps = pstats.Stats("ouput_filename.file")

    print('###### All Results #######')
    ps.strip_dirs().sort_stats().print_stats()

    print('#### SORTED BY TOP 25 CUMULATIVE TIME ####')
    ps.strip_dirs().sort_stats('cumtime').print_stats(25)

    print('#### SORTED BY TOP 25 TOTAL TIME ####')
    ps.strip_dirs().sort_stats('tottime').print_stats(25)

    print('#### SORTED BY TOP 25 NUMBER OF CALLS ####')
    ps.strip_dirs().sort_stats('ncalls').print_stats(25)
