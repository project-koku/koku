# Koku README

[![license](https://img.shields.io/github/license/project-koku/koku.svg)](https://github.com/project-koku/koku/blob/main/LICENSE)
[![CI](https://github.com/project-koku/koku/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/project-koku/koku/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/project-koku/koku/branch/main/graph/badge.svg)](https://codecov.io/gh/project-koku/koku)

## About

Koku's goal is to provide an open source solution for cost management of cloud and hybrid cloud environments. This solution is offered via a web interface that exposes resource consumption and cost data in easily digestible and filterable views. The project also aims to provide insight into this data and ultimately provide suggested optimizations for reducing cost and eliminating unnecessary resource usage.

Full documentation is available in [docs folder](docs).

To submit an issue please visit https://issues.redhat.com/projects/COST/.

## Getting Started

This project is developed using Python 3.11. Make sure you have at least this version installed.

### Prerequisites

- Docker or Rancher Desktop
- (macOS only) [Install Homebrew](https://brew.sh/)

## Development

To get started developing against Koku you first need to clone a local
copy of the git repositories.:

    git clone https://github.com/project-koku/koku
    git clone https://github.com/project-koku/nise

This project is developed using the Django web framework. Many
configuration settings can be read in from a `.env` file. To configure,
do the following:

1.  Copy [`.env.example`](.env.example) into a `.env` and update the following in your `.env`:

        AWS_RESOURCE_NAME=YOUR_COST_MANAGEMENT_AWS_ARN

    **For on-premise deployments** without access to Red Hat SaaS services, also set:

        ONPREM=True


2.  Copy [`dev/credentials/aws.example`](dev/credentials/aws.example) into `dev/credentials/aws`, obtain AWS credentials, then update the credentials file:

        [default]
        aws_access_key_id=YOUR_AWS_ACCESS_KEY_ID
        aws_secret_access_key=YOUR_AWS_SECRET_ACCESS_KEY

3.  (macOS only) Install libraries for building wheels on ARM:

        brew install openssl librdkafka postgresql@16

3.  (Fedora only) Install libraries for building wheels on Linux:

        dnf install openssl-devel libpq-devel postgresql golang-sigs-k8s-kustomize

4.  (macOS only) Also add the following to your `.env` or shell profile:

        LDFLAGS="-L$(brew --prefix openssl)/lib -L$(brew --prefix librdkafka)/lib"
        CPPFLAGS="-I$(brew --prefix openssl)/include -I$(brew --prefix librdkafka)/include"
        PATH="$PATH:$(brew --prefix postgresql@16)/bin"

5.  Developing inside a virtual environment is recommended. A Pipfile is provided. Pipenv is recommended for combining virtual environment and dependency management. To install `pipenv`:

        pip3 install pipenv

6.  Then project dependencies and a virtual environment can be created using:

        pipenv install --dev

7.  To activate the virtual environment run:

        pipenv shell

8.  Install the pre-commit hooks for the repository:

        pre-commit install

### Developing with Docker Compose

This will explain how to start the server and its dependencies using Docker (or Rancher Desktop), create AWS/OCP sources, and view reports. This will not cover all API or scenarios but should give you an end-to-end flow.

#### Starting Koku using Docker Compose

> **Note**
>
> In order for the `koku_base` image to build correctly, buildkit must be enabled by setting `DOCKER_BUILDKIT=1`. This is set in the `.env` file, but if you are having issues building the `koku_base` image, make sure buildkit is enabled.

1.  Start the containers:

        make docker-up-min

2.  Display log output from the containers. It is recommended that logs be kept in a second terminal:

        make docker-logs

With all containers running any source added will be processed by saving CSV files in MinIO and storing Parquet files in MinIO. The source's data will be summarized via Trino. Summarized data will land in the appropriate daily_summary table for the source type for consumption by the API.

To add test sources and data:

    make create-test-customer
    make load-test-customer-data # Optional parameters: start={start_date} end={end_date} test_source=AWS

The MinIO UI will be available at http://127.0.0.1:9090/minio/. Use the `S3_ACCESS_KEY` and `S3_SECRET` set in your `.env` file as login credentials.

The Trinio UI will be available at http://127.0.0.1:8080/ui/. Details can be found there on queries. This is particularly useful for troubleshooting failures.

Access the Trino CLI using the following command:

    docker exec -it trino trino --server 127.0.0.1:8080 --catalog hive --schema org1234567 --user admin --debug

Example usage:

    SHOW tables;
    SELECT * from aws_line_items WHERE source='{source}' AND year='2023' AND month='02' LIMIT 100;

#### Run AWS Scenario

1.  Create AWS Source:

        make aws-source aws_name=AWS-SOURCE-001 bucket=cost-usage-bucket

2.  Verify source exists by visiting

    http://127.0.0.1:8000/api/cost-management/v1/sources/?name=AWS-SOURCE-001

3.  Trigger MASU processing by visiting

    http://127.0.0.1:5042/api/cost-management/v1/download/

4.  Wait for processing to complete

5.  Verify data existing using AWS API endpoints

    -   http://127.0.0.1:8000/api/cost-management/v1/reports/aws/instance-types/
    -   http://127.0.0.1:8000/api/cost-management/v1/reports/aws/costs/
    -   http://127.0.0.1:8000/api/cost-management/v1/reports/aws/storage/

#### Run OCP Scenario

1.  Create OCP Source:

        make ocp-source-from-yaml cluster_id=my_test_cluster srf_yaml=../nise/example_ocp_static_data.yml ocp_name=my_ocp_name

2.  Verify provider exists by visiting

    http://127.0.0.1:8000/api/cost-management/v1/sources/?name=my_ocp_name

3.  Trigger MASU processing by visiting

    http://127.0.0.1:5042/api/cost-management/v1/download/

4.  Wait for processing to complete

5.  Verify data exists using API endpoints

    -   http://127.0.0.1:8000/api/cost-management/v1/reports/openshift/volumes/
    -   http://127.0.0.1:8000/api/cost-management/v1/reports/openshift/memory/
    -   http://127.0.0.1:8000/api/cost-management/v1/reports/openshift/compute/

#### Run GCP Scenario

1.  Set Environment variables:

        GCP_DATASET - The name of the BigQuery dataset in your GCP setup.
        GCP_TABLE_ID - The identifier for the table you are pulling for the billing information.
        GCP_PROJECT_ID - The identifier for the GCP project.

2.  Create GCP source:

        make gcp-source gcp_name=my_gcp_source

3.  Verify provider exists by visiting

    http://127.0.0.1:8000/api/cost-management/v1/sources/?name=my_gcp_source

#### Stopping Koku using Docker Compose

To bring down all the docker containers, run the following command:

    make docker-down

#### Database

PostgreSQL is used as the database backend for Koku. A docker compose file is provided for creating a local database container. Assuming the default `.env` file values are used, to access the database directly using psql run:

    PGPASSWORD=postgres psql postgres -U postgres -h 127.0.0.1 -p 15432

> **Note**
>
> There is a known limitation with Docker Compose and Linux environments with SELinux enabled. You may see the following error during the postgres container deployment:
>
>       "mkdir: cannot create directory '/var/lib/pgsql/data/userdata': Permission denied" can be resolved by granting ./pg_data ownership permissions to uid:26 (postgres user in centos/postgresql-96-centos7)
>
> If you see this error, run the following command (assuming you are at the project top level directory):
>
>       setfacl -m u:26:-wx ./pg_data


#### Database Query Monitoring

A basic level of query monitoring has been included leveraging a local grafana container which will be built with the docker-up make target.

To use the monitor, open a new web browser tab or window and enter the following URL: http://127.0.0.1:3001

You will be presented with the grafana login page. For this monitor, use the following credentials:

    User: admin
    Password: admin12

Once you have logged into the server, you will be taken straight to the main dashboard. It will have 5 panels.

<table>
    <tr>
        <td colspan="2">Query statistics</td>
    </tr>
    <tr>
        <td>Connect States</td><td>Active Queries</td>
    </tr>
    <tr>
        <td>Lock Types</td><td>Lock Detail</td>
    </tr>
</table>


-   Query Statistics - The max execution time, the mean execution time, number of calls and the query text
-   Connect States - Shows the connection states (active, idle, idle in transaction, etc)
-   Active Queries - Shows the approximate run time (based on the probe time) and the query text of queries detected
-   Lock Types - Shows the discrete lock types detected during the probe
-   Lock Detail - Shows any detail informaiton for the lock and the affected query.

The Query Statistics panel is cumulative. The remaining panels are ephemeral.

Information about PostgreSQL statistics can be found here: https://www.postgresql.org/docs/12/monitoring-stats.html

Information about Grafana dashboards can be found here: https://grafana.com/docs/grafana/latest/features/dashboard/dashboards/


### Developing with OpenShift

Our production deployment runs on OpenShift. At times you may need to run on OpenShift if you are working on deployment templates or would like to test in a production like environment. This is a more advanced scenario that many new developers will not need. To learn how to run OpenShift refer to [Working with OpenShift](docs/openshift.md).

### Testing

Koku uses tox to standardize the environment used when running tests. Essentially, tox manages its own virtual environment and a copy of required dependencies to run tests. To ensure a clean tox environment run:

    tox -r

This will rebuild the tox virtual env and then run all tests.

To run unit tests specifically:

    tox -e py311

To run a specific subset of unit tests, you can pass a particular module path to tox. To do this, use positional args using the -- separator. For example:

    tox -e py311 -- masu.test.external.downloader.azure.test_azure_services.AzureServiceTest

To run IQE Smoke, Vortex or API tests, while on the Red Hat network and koku deployed via docker compose run:

    make docker-iqe-smokes-tests
    make docker-iqe-vortex-tests
    make docker-iqe-api-tests

Individual IQE tests can be ran with run_test.sh:

    <koku_topdir>/testing/run_test.sh iqe tests plugin hccm -k test_api_cost_model_markup_calculation_ocp

### Linting

This repository uses [pre-commit](https://pre-commit.com) to check and enforce code style. It uses [Black](https://github.com/psf/black) to reformat the Python code and [Flake8](http://flake8.pycqa.org) to check it afterwards. Other formats and text files are linted as well.

To run pre-commit checks:

    pre-commit run --all-files

### pgAdmin

If you want to interact with the Postgres database from a GUI:

1.  Copy the [pgadmin_servers.json.example](pgadmin_servers.json.example) into a `pgadmin_servers.json` file and if necessary, change any variables to match your database.
2.  `docker compose up -d pgadmin` causes pgAdmin to run on http://127.0.0.1:8432
3.  In the login screen, the default login email:password is `postgres@local.dev:postgres`

> **Note**
>
> The pgadmin_servers.json file is written in [json format](https://www.pgadmin.org/docs/pgadmin4/development/import_export_servers.html#json-format).

### Partitioned Tables

The koku project is now making use of partitioned tables with PostgreSQL 12. Currently, there are only a limited number of modules supporting table partitoning with Django. For this reason, the partitioned tables are being unmanaged by Django models.

There is a stored procedure that helps create table partitions on-the-fly during masu data processing. This procedure is called `create_date_partitons` and is in the `public` schema. It is designed to scan a table for partition range start values and compare them against a tracking table of table partitions. For any range start not present in the table, a table partition will be created. This allows for partition creation for any uncovered range, past, present, or future. See `db_functions/create_date_partitions.sql` for the code and parameter documentation.

## Contributing

Please refer to [Contributing](https://github.com/project-koku/koku/blob/main/CONTRIBUTING.md).
