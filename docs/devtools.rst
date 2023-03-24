Developer Tools
===============

This section describes tooling and features included in Koku to assist
developers contributing to Koku.

Environment Variables
---------------------

Koku makes use of environment variables to configure features and application
capabilities.

In the repository, there is an ``.env.example`` file with sample environment
settings. The ``.env`` file is used by Django's tools as well as Koku's scripting.
It is the recommended way to configure your local development environment
settings.

This section documents environment variables that may be of interest to
developers.

``DEVELOPMENT=(True|False)`` - Enables development features. Not for production use.
``DEVELOPMENT_IDENTITY=(JSON)`` - A JSON Object representing a User

Authentication
--------------

When ``DEVELOPMENT`` is not set, Koku expects to use an external service to
handle authentication and access control for most API endpoints.

When ``DEVELOPMENT`` is set, the development middleware is
enabled. This allows passing in custom identity information into Koku for
development and testing purposes using the ``DEVELOPMENT_IDENTITY`` variable.

Example DEVELOPMENT_IDENTITY object::

    {
        "identity": {
            "account_number": "10001",
            "type": "User",
            "user": {
                "username": "user_dev",
                "email": "user_dev@foo.com",
                "is_org_admin": False
                "access": {
                    "aws.account": {
                        "read": ["1234567890AB", "234567890AB1"]
                    }
                    "gcp.account": {
                        "read": ["*"]
                    }
                    "gcp.project": {
                        "read": ["*"]
                    }
                    "azure.subscription_guid": {
                        "read": ["*"]
                    }
                    "openshift.cluster": {
                        "read": ["*"]
                    }
                    "openshift.project": {
                        "read": ["*"]
                    }
                    "openshift.node": {
                        "read": ["*"]
                    }
                }
            },
        },
        "entitlements": {"cost_management": {"is_entitled": True}},
    }

.. note:: This example is pretty-printed for readability. When setting the enviroment variable, it should be collapsed to one single line.


Trino Tips
----------

Trino is an SQL query engine, but not an SQL database. What does that mean? Traditional databases
typically consist of a query engine and a storage engine. Trino is just a query engine and does not
store data. So, inside of koku our download workers will retrieve cost data from the cloud providers
in the form of CSVs. Then during processing we convert these csv files to parquet
files (Look for the following function in the codebase: `convert_csv_to_parquet`).
After the files are converted they are then sent up to an S3 bucket. During runtime the Trino
coordinator utilizes the existing HIVE metastore metadata and files residing in storage to
query the files for data.

Trino Specific Env Vars::

    S3_BUCKET_NAME=koku-bucket
    S3_ENDPOINT=http://kokuminio:9000
    S3_ACCESS_KEY=kokuminioaccess
    S3_SECRET=kokuminiosecret
    S3_BUCKET_PATH=data
    TRINO_DATE_STEP=31

::

Additional Reads:

- https://trino.io/blog/2020/10/20/intro-to-hive-connector.html#trino-runtime-replaces-hive-runtime

MinIO
"""""
MinIO is the file storage location we use locally. Since, we query the parquet files based off the S3 path,
we use this tool locally to see the csv & parquet files are in their expected place. It will also allow
you to download them.

Minio UI:

- http://127.0.0.1:9090/minio/

The username & password is set inside of the .env file::

    S3_ACCESS_KEY=kokuminioaccess
    S3_SECRET=kokuminiosecret

::

Trino Coordinator
"""""""""""""""""

This is the brain of the Trino installation, and the node the client connects to submit statements for execution.
The coordinator keeps track of the activity on each worker and coordinates the execution of a query.
The coordinator creates a logical model of a query involving a series of stages,
which is then translated into a series of connected tasks running on a cluster of Trino workers.

You can use the trino UI to see the queries run in trino:

- http://127.0.0.1:8080/ui/

You can also manually run queries inside of the trino container::

    docker exec -it trino trino --catalog hive --schema org1234567 --user admin --debug
    SHOW CREATE TABLE <table_name>;

::

Additional Reads:

- https://trino.io/docs/current/overview/concepts.html#coordinator


PostgreSQL Tips:
----------------

Connect to Postgres::

PGPASSWORD=postgres psql postgres -U postgres -h localhost -p 15432

::

Below is a list of Koku commonly used psql commands:

1. Set search Schema: `set search_path=org1234567`
2. find datatable: `\dt` or `\dt reporting_ocpgcp*`
3. Tidy up display: `\x auto`
4. List columns for a table: `\d+ reporting_ocpusagelineitem_daily_summary`

Commonly used sql pieces:

Search for Tag Key::
WHERE pod_labels ? 'environment';
::

Jinja Templated SQL
"""""""""""""""""""

We have a development python script that will replace the jinja variables inside of a template file.

Example::

python3 dev/scripts/render_templated_sql.py -f /path/to/template.sql -b 11

::
