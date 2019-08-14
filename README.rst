===========
Koku README
===========

|license| |Build Status| |codecov| |Updates| |Python 3| |Docs|

~~~~~
About
~~~~~

Koku's goal is to provide an open source solution for cost management of cloud and hybrid cloud environments. This solution is offered via a web interface that exposes resource consumption and cost data in easily digestible and filterable views. The project also aims to provide insight into this data and ultimately provide suggested optimizations for reducing cost and eliminating unnecessary resource usage.

Full documentation is available through readthedocs_.


Getting Started
===============

This project is developed using Python 3.6. Make sure you have at least this version installed.

Prerequisites
-------------

* Docker
* PostgreSQL
* Node.js
* apiDoc

For Mac OSX
^^^^^^^^^^^

    `Install Docker for Mac`_

    `Install brew`_

    Install PostgreSQL: ::

        brew install postgresql

    Install Node.js: ::

        brew install node

    Install apiDoc: ::

        npm install apidoc -g


Development
===========

To get started developing against Koku first clone a local copy of the git repository. ::

    git clone https://github.com/project-koku/koku

Developing inside a virtual environment is recommended. A Pipfile is provided. Pipenv is recommended for combining virtual environment (virtualenv) and dependency management (pip). To install pipenv, use pip ::

    pip3 install pipenv

Then project dependencies and a virtual environment can be created using ::

    pipenv install --dev

**Note for Mac OSX users**

psycopg2 is a dependency of Django and installing the psycopg2 wheel will likely fail. The following steps should be taken to allow installation to succeed: ::


    brew install openssl
    brew unlink openssl && brew link openssl --force

    `/usr/local/opt/openssl/bin` should be appended to the PATH environment variable

    The following environment variables can be set in the koku repo's .env file
        LDFLAGS="-L/usr/local/opt/openssl/lib"
        CPPFLAGS="-I/usr/local/opt/openssl/include"

If dependency installation still fails, try using ::

    pipenv install --dev --sequential

To activate the virtual environment run ::

    pipenv shell

Preferred Environment
---------------------

Please refer to `Working with Openshift`_.

Alternative Environment
-----------------------
If deploying with Openshift seems overly complex you can try an alternate local environment where you will need to install and setup some of the dependencies and configuration.

Configuration
^^^^^^^^^^^^^

This project is developed using the Django web framework. Many configuration settings can be read in from a `.env` file. An example file `.env.example` is provided in the repository. To use the defaults simply ::

    cp .env.example .env


Modify as you see fit.

Database
^^^^^^^^

PostgreSQL is used as the database backend for Koku. A docker-compose file is provided for creating a local database container. If modifications were made to the .env file the docker-compose file will need to be modified to ensure matching database credentials. Several commands are available for interacting with the database. ::

    # Initialize the docker network for koku services if it doesn't already exist
    docker network create koku-network

    # This will launch a Postgres container
    make docker-up-db

    # This will run Django's migrations against the database
    make run-migrations

    # This will stop and remove a currently running database and run the above commands
    make docker-reinitdb

Assuming the default .env file values are used, to access the database directly using psql run ::

    PGPASSWORD=postgres psql postgres -U postgres -h localhost -p 15432

There is a known limitation with docker-compose and Linux environments with SELinux enabled. You may see the following error during the postgres container deployment::

    "mkdir: cannot create directory '/var/lib/pgsql/data/userdata': Permission denied" can be resolved by granting ./pg_data ownership permissions to uid:26 (postgres user in centos/postgresql-96-centos7)

If a docker container running Postgres is not feasible, it is possible to run Postgres locally as documented in the Postgres tutorial_. The default port for local Postgres installations is `5432`. Make sure to modify the `.env` file accordingly. To initialize the database run ::

    make run-migrations

API Documentation Generation
----------------------------

To generate and host the API documentation locally you need to `Install APIDoc`_.

Generate the project API documenttion by running the following command ::

  make gen-apidoc

In order to host the docs locally you need to collect the static files ::

  make collect-static

Now start the server with as described above and point your browser to **http://127.0.0.1:8000/apidoc/index.html**.

Server
^^^^^^

To run a local dev Django server you can use ::

    make serve

Testing and Linting
-------------------

Koku uses tox to standardize the environment used when running tests. Essentially, tox manages its own virtual environment and a copy of required dependencies to run tests. To ensure a clean tox environment run ::

    tox -r

This will rebuild the tox virtual env and then run all tests.

To run unit tests specifically::

    tox -e py36

To lint the code base ::

    tox -e lint

Contributing
=============

Please refer to Contributing_.

.. _readthedocs: http://koku.readthedocs.io/en/latest/
.. _`Install Docker for Mac`: https://docs.docker.com/v17.12/docker-for-mac/install/
.. _`Install brew`: https://brew.sh/
.. _tutorial: https://www.postgresql.org/docs/10/static/tutorial-start.html
.. _`Install APIDoc`: http://apidocjs.com/#install
.. _`Working with Openshift`: https://koku.readthedocs.io/en/latest/openshift.html
.. _Contributing: https://koku.readthedocs.io/en/latest/CONTRIBUTING.html

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
   :target: https://koku.readthedocs.io/en/latest/
