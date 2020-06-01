===========
Koku README
===========
|license| |Build Status| |codecov| |Updates| |Python 3| |Docs|

About
=====

Koku's goal is to provide an open source solution for cost management of cloud and hybrid cloud environments. This solution is offered via a web interface that exposes resource consumption and cost data in easily digestible and filterable views. The project also aims to provide insight into this data and ultimately provide suggested optimizations for reducing cost and eliminating unnecessary resource usage.

Full documentation is available through readthedocs_.


Getting Started
===============

This project is developed using Python 3.6. Make sure you have at least this version installed.

Prerequisites
-------------

* Docker
* PostgreSQL

For Mac OSX
^^^^^^^^^^^

    `Install Docker for Mac`_

    `Install brew`_

    Install PostgreSQL: ::

        brew install postgresql


Development
===========

To get started developing against Koku you first need to clone a local copy of the git repositories. ::

    git clone https://github.com/project-koku/koku
    git clone https://github.com/project-koku/nise

This project is developed using the Django web framework. Many configuration settings can be read in from a ``.env`` file. To configure, do the following:

1. Copy ``.env.example`` into a ``.env``
2. Obtain AWS values and update the following in your ``.env``::

    AWS_ACCESS_KEY_ID=YOUR_AWS_ACCESS_KEY
    AWS_SECRET_ACCESS_KEY=YOUR_AWS_SECRET_KEY
    AWS_RESOURCE_NAME=YOUR_COST_MANAGEMENT_AWS_ARN

3. (Mac Only) If you are on Mac, do the following note that psycopg2 is a dependency of Django and installing the psycopg2 wheel will likely fail. The following steps should be taken to allow installation to succeed: ::

    brew install openssl
    brew unlink openssl && brew link openssl --force

4. (Mac Only) Also add the following to your ``.env``::

    LDFLAGS="-L/usr/local/opt/openssl/lib"
    CPPFLAGS="-I/usr/local/opt/openssl/include"

5. Developing inside a virtual environment is recommended. A Pipfile is provided. Pipenv is recommended for combining virtual environment (virtualenv) and dependency management (pip). To install pipenv, use pip ::

    pip3 install pipenv

6. Then project dependencies and a virtual environment can be created using ::

    pipenv install --dev

7. If dependency installation still fails, try using ::

    pipenv install --dev --sequential

8. To activate the virtual environment run ::

    pipenv shell

9. Install the pre-commit hooks for the repository ::

    pre-commit install


Developing with Docker Compose
------------------------------

This will explain how to start the server and its dependencies using Docker, create AWS/OCP sources, and view reports. This will not cover all API or scenarios but should give you an end to end flow.

Starting Koku using Docker Compose
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Start the docker containers::

    make docker-up

2. Display log output from the docker containers. It is recommended that logs be kept in a second terminal ::

    docker-compose logs -f koku-server koku-worker

3. Install koku-nise::

    pip install koku-nise

Run AWS Scenario
^^^^^^^^^^^^^^^^

1. Create AWS Source::

    make aws-source aws_name=AWS-SOURCE-001 bucket=cost-usage-bucket

2. Verify source exists by visiting http://127.0.0.1:8000/api/cost-management/v1/sources/?name=AWS-SOURCE-001
3. Trigger MASU processing by visiting http://127.0.0.1:5000/api/cost-management/v1/download/
4. Wait for processing to complete
5. Verify data existing using AWS API endpoints

    - http://127.0.0.1:8000/api/cost-management/v1/reports/aws/instance-types/
    - http://127.0.0.1:8000/api/cost-management/v1/reports/aws/costs/
    - http://127.0.0.1:8000/api/cost-management/v1/reports/aws/storage/

Run OCP Scenario
^^^^^^^^^^^^^^^^

1. Create OCP Source::

    make ocp-source-from-yaml cluster_id=my_test_cluster srf_yaml=../nise/example_ocp_static_data.yml ocp_name=my_ocp_name

2. Verify provider exists by visiting http://127.0.0.1:8000/api/cost-management/v1/sources/?name=my_ocp_name
3. Trigger MASU processing by visiting http://127.0.0.1:5000/api/cost-management/v1/download/
4. Wait for processing to complete
5. Verify data exists using API endpoints

    - http://127.0.0.1:8000/api/cost-management/v1/reports/openshift/volumes/
    - http://127.0.0.1:8000/api/cost-management/v1/reports/openshift/memory/
    - http://127.0.0.1:8000/api/cost-management/v1/reports/openshift/compute/

Stopping Koku using Docker Compose
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
To bring down all the docker containers, run the following command::

    make docker-down


Database
^^^^^^^^

PostgreSQL is used as the database backend for Koku. A docker-compose file is provided for creating a local database container. Assuming the default .env file values are used, to access the database directly using psql run ::

    PGPASSWORD=postgres psql postgres -U postgres -h localhost -p 15432

**Note:** There is a known limitation with docker-compose and Linux environments with SELinux enabled. You may see the following error during the postgres container deployment::

    "mkdir: cannot create directory '/var/lib/pgsql/data/userdata': Permission denied" can be resolved by granting ./pg_data ownership permissions to uid:26 (postgres user in centos/postgresql-96-centos7)

If you see this error, run the following command (assuming you are at the project top level directory)::

    setfacl -m u:26:-wx ./pg_data

See  https://access.redhat.com/containers/?tab=overview#/registry.access.redhat.com/rhel8/postgresql-12


Database Query Monitoring
^^^^^^^^^^^^^^^^^^^^^^^^^

A basic level of query monitoring has been included leveraging a local grafana container which will be built with the `docker-up` make target.

To use the monitor, open a new web browser tab or window and enter the following URL:

    http://localhost:3001

You will be presented with the grafana login page. For this monitor, use the following credentials::

    User: admin
    Password: admin12

Once you have logged into the server, you will be taken straight to the main dashboard. It will have 5 panels.

    +--------------------------+
    |                          |
    | Query statistics         |
    |                          |
    +---------+----------------+
    | Connect | Active Queries |
    | States  |                |
    +---------+----------------+
    | Lock    | Lock Detail    |
    | Types   |                |
    +---------+----------------+

- Query Statistics - The max execution time, the mean execution time, number of calls and the query text
- Connect States   - Shows the connection states (active, idle, idle in transaction, etc)
- Active Queries   - Shows the approximate run time (based on the probe time) and the query text of queries detected
- Lock Types       - Shows the discrete lock types detected during the probe
- Lock Detail      - Shows any detail informaiton for the lock and the affected query.

The Query Statistics panel is cumulative. The remaining panels are ephemeral.

Information about PostgreSQL statistics can be found here: https://www.postgresql.org/docs/10/monitoring-stats.html

Information about Grafana dashboards can be found here: https://grafana.com/docs/grafana/latest/features/dashboard/dashboards/


Developing with OpenShift
-------------------------

Our production deployment runs on OpenShift. At times you may need to run on OpenShift if you are working on deployment templates or would like to test in a production like environment. This is a more advanced scenario that many new developers will not need. To learn how to run OpenShift refer to `Working with Openshift`_.

Testing
-------

Koku uses tox to standardize the environment used when running tests. Essentially, tox manages its own virtual environment and a copy of required dependencies to run tests. To ensure a clean tox environment run ::

    tox -r

This will rebuild the tox virtual env and then run all tests.

To run unit tests specifically::

    tox -e py36

To run a specific subset of unit tests, you can pass a particular module path to tox. To do this, use positional args using the -- separator. For example::

    tox -e py36 -- masu.test.external.downloader.azure.test_azure_services.AzureServiceTest

To run IQE Smoke, Vortex or API tests, while on the Red Hat network and koku deployed via docker-compose run::

    make docker-iqe-smokes-tests
    make docker-iqe-vortex-tests
    make docker-iqe-api-tests

Individual IQE tests can be ran with run_test.sh::

    <koku_topdir>/testing/run_test.sh iqe tests plugin hccm -k test_api_cost_model_markup_calculation_ocp

Linting
-------
This repository uses `pre-commit`_ to check and enforce code style. It uses `Black`_ to reformat the Python code and `Flake8`_ to check it
afterwards. Other formats and text files are linted as well.

To run pre-commit checks::

    pre-commit run --all-files

pgAdmin
-------

If you want to interact with the Postgres database from a GUI:

 1. Copy the `pgadmin_servers.json.example` into a `pgadmin_servers.json` file and if necessary, change any variables to match your database.
 2. `docker-compose up` causes pgAdmin to run on http://localhost:8432
 3. In the login screen, the default login email is `postgres`

Side note: The `pgadmin_servers.json` file uses [pgadmin servers.json syntax](https://www.pgadmin.org/docs/pgadmin4/development/import_export_servers.html#json-format)

Contributing
=============

Please refer to Contributing_.

.. _readthedocs: http://koku.readthedocs.io/en/latest/
.. _`Install Docker for Mac`: https://docs.docker.com/v17.12/docker-for-mac/install/
.. _`Install brew`: https://brew.sh/
.. _tutorial: https://www.postgresql.org/docs/12/tutorial-start.html
.. _`Working with Openshift`: https://koku.readthedocs.io/en/latest/openshift.html
.. _Contributing: https://koku.readthedocs.io/en/latest/CONTRIBUTING.html
.. _pre-commit: https://pre-commit.com
.. _Black: https://github.com/psf/black
.. _Flake8: http://flake8.pycqa.org

.. |license| image:: https://img.shields.io/github/license/project-koku/koku.svg
   :target: https://github.com/project-koku/koku/blob/master/LICENSE
.. |Build Status| image:: https://travis-ci.org/project-koku/koku.svg?branch=master
   :target: https://travis-ci.org/project-koku/koku
.. |codecov| image:: https://codecov.io/gh/project-koku/koku/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/project-koku/koku
.. |Updates| image:: https://pyup.io/repos/github/project-koku/koku/shield.svg?t=1524249231720
   :target: https://pyup.io/repos/github/project-koku/koku/
.. |Python 3| image:: https://pyup.io/repos/github/project-koku/koku/python-3-shield.svg?t=1524249231720
   :target: https://pyup.io/repos/github/project-koku/koku/
.. |Docs| image:: https://readthedocs.org/projects/koku/badge/
   :target: https://koku.readthedocs.io/en/latest
