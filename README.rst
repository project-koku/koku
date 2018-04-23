===========
SaltCellar
===========

|license| |Build Status| |codecov| |Updates| |Python 3| |Docs|

~~~~~
About
~~~~~

SaltCellar's goal is to provide an open source solution for cost management of cloud and hybrid cloud environments. This is offered via a web interface that exposes resource consumption and cost data in easily digestible and filterable views. The project also aims to provide insight into this data and ultimately provide suggested optimizations for reducing cost and eliminating unnecessary resource usage.

Full documentation is available through readthedocs_.


Getting Started
===============

This is a Python project developed using Python 3.6. Make sure you have at least this version installed.

Development
------------
To get started developing against SaltCellar first clone a local copy of the git repository. ::

    git clone https://github.com/SaltCellar/SaltCellar

Developing inside a virtual environment is recommended. A Pipfile is provided. Pipenv is recommended for combining virtual environment (virtualenv) and dependency management (pip). To install pipenv, use pip ::

    pip3 install pipenv

Then project dependencies and a virtual environment can be created using ::

    pipenv install --dev

To activate the virtual environment run ::

    pipenv shell

Configuration
~~~~~~~~~~~~~

This project is developed using the Django web framework. Many configuration settings can be read in from a `.env` file. An example file `.env.example` is provided in the repository. To use the defaults simply ::

    mv .env.example .env


Modify as you see fit.

Database
~~~~~~~~

PostgreSQL is used as the database backend for SaltCellar. A docker-compose file is provided for creating a local database container. If modifications were made to the .env file the docker-compose file will need to be modified to ensure matching database credentials. Several commands are available for interacting with the database. ::

    # This will launch a Postgres container
    make start-db

    # This will run Django's migrations against the database
    make run-migrations

    # This will stop and remove a currently running database and run the above commands
    make reinitdb

Assuming the default .env file values are used, to access the database directly using psql run ::

    psql saltcellar -U saltcellar -h localhost -p 15432


Server
~~~~~~

To run a local dev Django server you can use ::

    make serve

Testing and Linting
~~~~~~~~~~~~~~~~~~~

SaltCellar uses tox to standardize the environment used when running tests. Essentially, tox manages its own virtual environment and a copy of required dependencies to run tests. To ensure a clean tox environement run ::

    tox -r

This will rebuild the tox virtual env and then run all tests.

To run unit tests specifically::

    tox -e py36

To lint the code base ::

    tox -e lint


Contributing
=============

Please refer to contributing.rst_.



.. _readthedocs: http://saltcellar.readthedocs.io/en/latest/
.. _contributing.rst: https://github.com/SaltCellar/SaltCellar/blob/master/CONTRIBUTING.rst

.. |license| image:: https://img.shields.io/github/license/SaltCellar/SaltCellar.svg
   :target: https://github.com/SaltCellar/SaltCellar/blob/master/LICENSE
.. |Build Status| image:: https://travis-ci.org/SaltCellar/SaltCellar.svg?branch=master
   :target: https://travis-ci.org/SaltCellar/SaltCellar
.. |codecov| image:: https://codecov.io/gh/SaltCellar/SaltCellar/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/SaltCellar/SaltCellar
.. |Updates| image:: https://pyup.io/repos/github/SaltCellar/SaltCellar/shield.svg?t=1524249231720
   :target: https://pyup.io/repos/github/SaltCellar/SaltCellar/
.. |Python 3| image:: https://pyup.io/repos/github/SaltCellar/SaltCellar/python-3-shield.svg?t=1524249231720
   :target: https://pyup.io/repos/github/SaltCellar/SaltCellar/
.. |Docs| image:: https://readthedocs.org/projects/saltcellar/badge/
   :target: https://saltcellar.readthedocs.io/en/latest/
