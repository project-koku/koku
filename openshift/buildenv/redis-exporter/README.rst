==============
Redis Exporter
==============

Upstream
--------

https://github.com/oliver006/redis_exporter

Requirements
============

Running Redis Exporter
----------------------

The OpenShift template contains environment variables required to connect to the redis instance.

Deploying to OpenShift
======================

$ oc new-project redis-exporter
$ oc create istag go-toolset:latest --from-image=ubi7/go-toolset
$ oc apply -f redis-exporter.yaml
$ oc new-app --template redis-exporter-template [--param]
