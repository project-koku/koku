============
PostgreSQL Exporter
============

Upstream
--------

https://github.com/wrouesnel/postgres_exporter

Requirements
============

Running PostgreSQL Exporter
--------------------

The OpenShift template contains a secret object that defines the environment variables required to connect to the DB.

DATA_SOURCE_NAME - connection info; see upstream docs for details.

Example:::

    $ oc new-app --template postgresql-exporter-template \
                 --param 'DATA_SOURCE_NAME=postgresql://username:password@hostname.projectname.svc.cluster.local:5432/dbname?sslmode=disable'

Deploying to OpenShift
======================

$ oc new-project postgresql-exporter
$ oc create istag go-toolset-7-centos7:latest --from-image=centos/go-toolset-7-centos7
$ oc apply -f postgresql-exporter.yaml
$ oc new-app --template postgresql-exporter-template [--param]
