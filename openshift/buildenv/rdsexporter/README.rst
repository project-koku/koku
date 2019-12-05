============
RDS Exporter
============

Upstream
--------

https://github.com/percona/rds_exporter

Requirements
============

Building RDS Exporter
---------------------

RDS_EXPORTER_CONFIG environment variable must be present in the build
environment.

RDS_EXPORTER_CONFIG should be JSON. It will be converted to YAML and
deployed as the rdsexporter's "config.yaml".

See upstream docs for config.yaml syntax.

Running RDS Exporter
--------------------

AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables must be
present in the running container.

Deploying to OpenShift
======================

$ oc new-project rdsexporter
$ oc create istag go-toolset-7-centos7:latest --from-image=centos/go-toolset-7-centos7
$ oc apply -f rdsexporter.yaml
$ oc new-app --template rdsexporter [--param]
