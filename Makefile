# OpenShift settings
OC_VERSION	= v3.11
OC_DATA_DIR	= ${HOME}/.oc/openshift.local.data
OC_SOURCE	= registry.access.redhat.com/openshift3/ose

# PostgreSQL settings
PGSQL_VERSION   = 9.6

# Basic environment settings
PYTHON	= $(shell which python)
TOPDIR  = $(shell pwd)
PYDIR	= koku
APIDOC  = apidoc

# How to execute Django's manage.py
DJANGO_MANAGE = DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py

# required OpenShift template parameters
# if a value is defined in a parameter file, we try to use that.
# otherwise, we use a default value
NAME = $(or $(shell grep -h '^NAME=' openshift/parameters/* 2>/dev/null | uniq | awk -F= '{print $$2}'), koku)
NAMESPACE = $(or $(shell grep -h '^[^\#]*NAMESPACE=' openshift/parameters/* 2>/dev/null | uniq | awk -F= '{print $$2}'), koku)

OC_TEMPLATE_DIR = $(TOPDIR)/openshift
OC_PARAM_DIR = $(OC_TEMPLATE_DIR)/parameters
OC_TEMPLATES = $(wildcard $(OC_TEMPLATE_DIR))

# Platform differences
#
# - Use 'sudo' on Linux
# - Don't use 'sudo' on MacOS
#
OS := $(shell uname)
ifeq ($(OS),Darwin)
	PREFIX	=
else
	PREFIX	= sudo
endif

help:
	@echo "Please use \`make <target>' where <target> is one of:"
	@echo ""
	@echo "--- General Commands ---"
	@echo "  clean                                clean the project directory of any scratch files, bytecode, logs, etc"
	@echo "  help                                 show this message"
	@echo "  html                                 create html documentation for the project"
	@echo "  lint                                 run linting against the project"
	@echo ""
	@echo "--- Commands using local services ---"
	@echo "  create-test-customer                 create a test customer and tenant in the database"
	@echo "  create-test-customer-no-providers    create a test customer and tenant in the database without test providers"
	@echo "  collect-static                       collect static files to host"
	@echo "  make-migrations                      make migrations for the database"
	@echo "  requirements                         generate Pipfile.lock, RTD requirements and manifest for product security"
	@echo "  manifest                             create/update manifest for product security"
	@echo "  check-manifest                       check that the manifest is up to date"
	@echo "  remove-db                            remove local directory $(TOPDIR)/pg_data"
	@echo "  run-migrations                       run migrations against database"
	@echo "  serve                                run the Django app on localhost"
	@echo "  superuser                            create a Django super user"
	@echo "  unittest                             run unittests"
	@echo ""
	@echo "--- Commands using Docker Compose ---"
	@echo "  docker-up                            run django and database"
	@echo "  docker-up-db                         run database only"
	@echo "  docker-down                          shut down all containers"
	@echo "  docker-rabbit                        run RabbitMQ container"
	@echo "  docker-reinitdb                      drop and recreate the database"
	@echo "  docker-reinitdb-with-providers       drop and recreate the database with fake providers"
	@echo "  docker-shell                         run Django and database containers with shell access to server (for pdb)"
	@echo "  docker-logs                          connect to console logs for all services"
	@echo "  docker-test-all                      run unittests"
	@echo ""
	@echo "--- Commands using an OpenShift Cluster ---"
	@echo "  oc-clean                             stop openshift cluster & remove local config data"
	@echo "  oc-create-all                        create all application pods"
	@echo "  oc-create-celery-exporter            create the Celery Prometheus exporter pod"
	@echo "  oc-create-celery-scheduler           create the Celery scheduler pod"
	@echo "  oc-create-celery-worker              create the Celery worker pod"
	@echo "  oc-create-configmap                  create the ConfigMaps"
	@echo "  oc-create-database                   create the PostgreSQL DB pod"
	@echo "  oc-create-flower                     create the Celery Flower pod"
	@echo "  oc-create-imagestream                create ImageStreams"
	@echo "  oc-create-koku-api                   create the Koku API pod"
	@echo "  oc-create-koku-auth-cache            create the Redis pod for auth caching"
	@echo "  oc-create-listener                   create Masu Listener pod (deprecated)"
	@echo "  oc-create-masu                       create Masu pod (deprecated)"
	@echo "  oc-create-rabbitmq                   create RabbitMQ pod"
	@echo "  oc-create-route                      create routes for Koku APIs"
	@echo "  oc-create-secret                     create Secrets"
	@echo "  oc-create-worker                     create Celery worker pod"
	@echo "  oc-delete-all                        delete most Openshift objects without a cluster restart"
	@echo "  oc-delete-celery-worker              delete the Celery worker pod"
	@echo "  oc-delete-configmap                  delete the ConfigMaps"
	@echo "  oc-delete-database                   delete the PostgreSQL DB pod"
	@echo "  oc-delete-flower                     delete the Celery Flower pod"
	@echo "  oc-delete-imagestream                delete ImageStreams"
	@echo "  oc-delete-koku-api                   delete the Koku API pod"
	@echo "  oc-delete-koku-auth-cache            delete the Redis pod for auth caching"
	@echo "  oc-delete-listener                   delete Masu Listener pod (deprecated)"
	@echo "  oc-delete-masu                       delete Masu pod (deprecated)"
	@echo "  oc-delete-rabbitmq                   delete RabbitMQ pod"
	@echo "  oc-delete-secret                     delete Secrets"
	@echo "  oc-delete-worker                     delete Celery worker pod"
	@echo "  oc-down                              stop app & openshift cluster"
	@echo "  oc-forward-ports                     port forward the DB to localhost"
	@echo "  oc-login-dev                         login to an openshift cluster as 'developer'"
	@echo "  oc-reinit                            remove existing app and restart app in initialized openshift cluster"
	@echo "  oc-run-migrations                    run Django migrations in the Openshift DB"
	@echo "  oc-stop-forwarding-ports             stop port forwarding the DB to localhost"
	@echo "  oc-up                                initialize an openshift cluster"
	@echo "  oc-up-all                            run app in openshift cluster"
	@echo "  oc-up-db                             run Postgres in an openshift cluster"
	@echo ""
	@echo "--- Create Providers ---"
	@echo "  ocp_provider_from_yaml               Create ocp provider using a yaml file."
	@echo "      cluster_id=<cluster_name>            @param - Required. The name of your cluster (ex. my-ocp-cluster-0)"
	@echo "      srf_yaml=<filename>                  @param - Required. Path of static-report-file yaml (ex. '/ocp_static_report.yml')"
	@echo "      ocp_name=<provider_name>             @param - defaults to cluser_id param"
	@echo "  aws_provider                        Create aws provider using environment variables"
	@echo "      aws_name=<provider_name>             @param - Required. Name of the provider"
	@echo "      bucket=<bucket_name>                 @param - Required. Name of the bucket"

### General Commands ###

clean:
	git clean -fdx -e .idea/ -e *env/

html:
	@cd docs; $(MAKE) html

lint:
	tox -e lint

create-test-customer: run-migrations
	sleep 1
	$(DJANGO_MANAGE) runserver > /dev/null 2>&1 &
	sleep 5
	$(PYTHON) $(TOPDIR)/scripts/create_test_customer.py --bypass-api || echo "WARNING: create_test_customer failed unexpectedly!"
	kill -HUP $$(ps -eo pid,command | grep "manage.py runserver" | grep -v grep | awk '{print $$1}')

create-test-customer-no-providers: run-migrations
	sleep 1
	$(DJANGO_MANAGE) runserver > /dev/null 2>&1 &
	sleep 5
	$(PYTHON) $(TOPDIR)/scripts/create_test_customer.py --no-providers --bypass-api || echo "WARNING: create_test_customer failed unexpectedly!"
	kill -HUP $$(ps -eo pid,command | grep "manage.py runserver" | grep -v grep | awk '{print $$1}')


collect-static:
	$(DJANGO_MANAGE) collectstatic --no-input

make-migrations:
	$(DJANGO_MANAGE) makemigrations api reporting reporting_common cost_models

remove-db:
	$(PREFIX) rm -rf $(TOPDIR)/pg_data

requirements:
	pipenv lock
	pipenv lock -r > docs/rtd_requirements.txt
	python scripts/create_manifest.py

manifest:
	python scripts/create_manifest.py

check-manifest:
	./.travis/check_manifest.sh

run-migrations:
	$(DJANGO_MANAGE) migrate_schemas

serve:
	$(DJANGO_MANAGE) runserver

# FIXME: (deprecated) this will be removed after masu is fully merged.
serve-masu:
	FLASK_APP=masu \
	FLASK_ENV=development \
	MASU_SECRET_KEY='t@@ m4nY 53Cr3tZ' \
	flask run

unittest:
	$(DJANGO_MANAGE) test $(PYDIR) -v 2

superuser:
	$(DJANGO_MANAGE) createsuperuser

####################################
# Commands using OpenShift Cluster #
####################################

oc-clean: oc-down
	$(PREFIX) rm -rf $(OC_DATA_DIR)

oc-create-all: oc-create-database oc-create-rabbitmq oc-create-koku-auth-cache oc-create-koku-api oc-create-masu oc-create-celery-exporter oc-create-celery-scheduler oc-create-celery-worker oc-create-flower oc-create-listener

oc-create-celery-exporter: OC_OBJECT := dc/$(NAME)-celery-exporter
oc-create-celery-exporter: OC_PARAMETER_FILE := celery-exporter.env
oc-create-celery-exporter: OC_TEMPLATE_FILE := celery-exporter.yaml
oc-create-celery-exporter: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-celery-exporter:
	$(OC_PARAMS) $(MAKE) oc-create-imagestream
	$(OC_PARAMS) $(MAKE) oc-create-configmap
	$(OC_PARAMS) $(MAKE) oc-create-secret
	$(OC_PARAMS) $(MAKE) __oc-apply-object
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-celery-scheduler: OC_OBJECT := 'bc/$(NAME)-scheduler dc/$(NAME)-scheduler'
oc-create-celery-scheduler: OC_PARAMETER_FILE := celery-scheduler.env
oc-create-celery-scheduler: OC_TEMPLATE_FILE := celery-scheduler.yaml
oc-create-celery-scheduler: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-celery-scheduler:
	$(OC_PARAMS) $(MAKE) oc-create-imagestream
	$(OC_PARAMS) $(MAKE) oc-create-configmap
	$(OC_PARAMS) $(MAKE) oc-create-secret
	$(OC_PARAMS) $(MAKE) __oc-apply-object
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-celery-worker: OC_OBJECT := 'sts/$(NAME)-worker'
oc-create-celery-worker: OC_PARAMETER_FILE := celery-worker.env
oc-create-celery-worker: OC_TEMPLATE_FILE := celery-worker.yaml
oc-create-celery-worker: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-celery-worker:
	$(OC_PARAMS) $(MAKE) oc-create-imagestream
	$(OC_PARAMS) $(MAKE) oc-create-configmap
	$(OC_PARAMS) $(MAKE) oc-create-secret
	$(OC_PARAMS) $(MAKE) __oc-apply-object
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-configmap: OC_OBJECT := 'configmap -l app=$(NAME)'
oc-create-configmap: OC_PARAMETER_FILE := configmap.env
oc-create-configmap: OC_TEMPLATE_FILE := configmap.yaml
oc-create-configmap: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-configmap:
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-database: OC_OBJECT := 'bc/$(NAME)-db dc/$(NAME)-db'
oc-create-database: OC_PARAMETER_FILE := $(NAME)-database.env
oc-create-database: OC_TEMPLATE_FILE := $(NAME)-database.yaml
oc-create-database: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-database:
	$(OC_PARAMS) $(MAKE) oc-create-imagestream
	$(OC_PARAMS) $(MAKE) oc-create-configmap
	$(OC_PARAMS) $(MAKE) oc-create-secret
	$(OC_PARAMS) $(MAKE) __oc-apply-object
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-flower: OC_OBJECT := 'bc/$(NAME)-flower dc/$(NAME)-flower'
oc-create-flower: OC_PARAMETER_FILE := celery-flower.env
oc-create-flower: OC_TEMPLATE_FILE := celery-flower.yaml
oc-create-flower: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-flower:
	$(OC_PARAMS) $(MAKE) oc-create-imagestream
	$(OC_PARAMS) $(MAKE) oc-create-configmap
	$(OC_PARAMS) $(MAKE) oc-create-secret
	$(OC_PARAMS) $(MAKE) __oc-apply-object
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-imagestream: OC_OBJECT := 'is/centos is/python-36-centos7 is/postgresql'
oc-create-imagestream: OC_PARAMETER_FILE := imagestream.env
oc-create-imagestream: OC_TEMPLATE_FILE := imagestream.yaml
oc-create-imagestream: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-imagestream:
	$(OC_PARAMS) $(MAKE) __oc-apply-object
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-koku-api: OC_OBJECT := 'bc/$(NAME) dc/$(NAME)'
oc-create-koku-api: OC_PARAMETER_FILE := $(NAME).env
oc-create-koku-api: OC_TEMPLATE_FILE := $(NAME).yaml
oc-create-koku-api: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-koku-api:
	$(OC_PARAMS) $(MAKE) oc-create-imagestream
	$(OC_PARAMS) $(MAKE) oc-create-configmap
	$(OC_PARAMS) $(MAKE) oc-create-secret
	$(OC_PARAMS) $(MAKE) __oc-apply-object
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-koku-auth-cache: OC_OBJECT := 'dc/$(NAME)-redis'
oc-create-koku-auth-cache: OC_PARAMETER_FILE := $(NAME)-auth-cache.env
oc-create-koku-auth-cache: OC_TEMPLATE_FILE := $(NAME)-auth-cache.yaml
oc-create-koku-auth-cache: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-koku-auth-cache:
	$(OC_PARAMS) $(MAKE) oc-create-imagestream
	$(OC_PARAMS) $(MAKE) oc-create-configmap
	$(OC_PARAMS) $(MAKE) oc-create-secret
	$(OC_PARAMS) $(MAKE) __oc-apply-object
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-listener: OC_OBJECT := 'sts/$(NAME)-listener'
oc-create-listener: OC_PARAMETER_FILE := masu-listener.env
oc-create-listener: OC_TEMPLATE_FILE := masu-listener.yaml
oc-create-listener: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-listener:
	$(OC_PARAMS) $(MAKE) oc-create-imagestream
	$(OC_PARAMS) $(MAKE) oc-create-configmap
	$(OC_PARAMS) $(MAKE) oc-create-secret
	$(OC_PARAMS) $(MAKE) __oc-apply-object
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-masu: OC_OBJECT := 'bc/$(NAME)-masu dc/$(NAME)-masu'
oc-create-masu: OC_PARAMETER_FILE := masu.env
oc-create-masu: OC_TEMPLATE_FILE := masu.yaml
oc-create-masu: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-masu:
	$(OC_PARAMS) $(MAKE) oc-create-imagestream
	$(OC_PARAMS) $(MAKE) oc-create-configmap
	$(OC_PARAMS) $(MAKE) oc-create-secret
	$(OC_PARAMS) $(MAKE) __oc-apply-object
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-sources: OC_OBJECT := 'bc/$(NAME)-sources dc/$(NAME)-sources'
oc-create-sources: OC_PARAMETER_FILE := sources.env
oc-create-sources: OC_TEMPLATE_FILE := sources.yaml
oc-create-sources: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-sources:
	$(OC_PARAMS) $(MAKE) oc-create-imagestream
	$(OC_PARAMS) $(MAKE) oc-create-configmap
	$(OC_PARAMS) $(MAKE) oc-create-secret
	$(OC_PARAMS) $(MAKE) __oc-apply-object
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-rabbitmq: OC_OBJECT := statefulsets/rabbitmq
oc-create-rabbitmq: OC_PARAMETER_FILE := rabbitmq.env
oc-create-rabbitmq: OC_TEMPLATE_FILE := rabbitmq.yaml
oc-create-rabbitmq: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-rabbitmq:
	$(OC_PARAMS) $(MAKE) __oc-apply-object
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-route: OC_OBJECT := 'route/koku route/koku-masu'
oc-create-route: OC_PARAMETER_FILE := route.env
oc-create-route: OC_TEMPLATE_FILE := route.yaml
oc-create-route: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-route:
	$(OC_PARAMS) $(MAKE) __oc-apply-object
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-create-secret: OC_OBJECT := 'secret -l app=$(NAME)'
oc-create-secret: OC_PARAMETER_FILE := secret.env
oc-create-secret: OC_TEMPLATE_FILE := secret.yaml
oc-create-secret: OC_PARAMS := OC_OBJECT=$(OC_OBJECT) OC_PARAMETER_FILE=$(OC_PARAMETER_FILE) OC_TEMPLATE_FILE=$(OC_TEMPLATE_FILE)
oc-create-secret:
	$(OC_PARAMS) $(MAKE) __oc-create-object

oc-delete-all:
	oc delete all -l app=koku

# it's the only way to be sure...
oc-nuke-from-orbit:
	oc delete all,configmap,secret,pvc -l app=koku

oc-delete-celery-exporter:
	oc delete all -n $(NAMESPACE) -l template=koku-celery-exporter

oc-delete-celery-scheduler:
	oc delete all -n $(NAMESPACE) -l template=koku-celery-scheduler

oc-delete-celery-worker:
	oc delete all -n $(NAMESPACE) -l template=koku-celery-worker

oc-delete-configmap:
	oc delete configmap -n $(NAMESPACE) -l template=koku-configmap

oc-delete-database:
	oc delete all -n $(NAMESPACE) -l template=koku-database

oc-delete-flower:
	oc delete all -n $(NAMESPACE) -l template=koku-celery-flower

oc-delete-imagestream:
	oc delete all -n $(NAMESPACE) -l template=koku-imagestream

oc-delete-koku-api:
	oc delete all -n $(NAMESPACE) -l template=koku

oc-delete-koku-auth-cache:
	oc delete all -n $(NAMESPACE) -l template=koku-auth-cache

oc-delete-listener:
	oc delete all -n $(NAMESPACE) -l template=koku-masu-listener

oc-delete-masu:
	oc delete all -n $(NAMESPACE) -l template=koku-masu

oc-delete-rabbitmq:
	oc delete all -n $(NAMESPACE) -l template=rabbitmq

oc-delete-route:
	oc delete all -n $(NAMESPACE) -l template=koku-route

oc-delete-secret:
	oc delete secret -n $(NAMESPACE) -l template=koku-secret

oc-down:
	oc cluster down

oc-forward-ports: oc-stop-forwarding-ports
	@oc port-forward $$(oc get pods -o jsonpath='{.items[?(.status.phase=="Running")].metadata.name}' -l name=koku-db) 15432:5432 >/dev/null 2>&1 &

oc-login-dev:
	oc login -u developer --insecure-skip-tls-verify=true localhost:8443

oc-make-migrations: oc-forward-ports
	sleep 1
	$(DJANGO_MANAGE) makemigrations api reporting reporting_common cost_models
	$(MAKE) oc-stop-forwarding-ports

oc-reinit: oc-delete-all oc-create-koku

oc-run-migrations: oc-forward-ports
	sleep 1
	$(DJANGO_MANAGE) migrate_schemas
	$(MAKE) oc-stop-forwarding-ports

oc-stop-forwarding-ports:
	@kill -HUP $$(ps -eo pid,command | grep "oc port-forward" | grep -v grep | awk '{print $$1}') 2>/dev/null || true

oc-up:
	oc cluster up \
		--image=$(OC_SOURCE) \
		--version=$(OC_VERSION) \
		--host-data-dir=$(OC_DATA_DIR) \
		--use-existing-config=true
	sleep 60

oc-up-all: oc-up oc-create-koku

oc-up-db: oc-up oc-create-db


###############################
### Docker-compose Commands ###
###############################

docker-down:
	docker-compose down

docker-down-db:
	docker-compose stop db
	docker ps -a -f name=koku_db -q | xargs docker container rm

docker-logs:
	docker-compose logs -f

docker-rabbit:
	docker-compose up -d rabbit

docker-reinitdb: docker-down-db remove-db docker-up-db
	sleep 5
	$(MAKE) create-test-customer-no-providers

docker-reinitdb-with-providers: docker-down-db remove-db docker-up-db
	sleep 5
	$(MAKE) create-test-customer

docker-shell:
	docker-compose run --service-ports koku-server

docker-test-all:
	docker-compose -f koku-test.yml up --build

docker-up:
	docker-compose up --build -d

docker-up-db:
	docker-compose up -d db

docker-iqe-smokes-tests:
	$(MAKE) docker-reinitdb
	./testing/run_smoke_tests.sh

docker-iqe-api-tests:
	$(MAKE) docker-reinitdb
	./testing/run_api_tests.sh

docker-iqe-vortex-tests:
	$(MAKE) docker-reinitdb
	./testing/run_vortex_api_tests.sh

### Provider targets ###
ocp_provider_from_yaml:
#parameter validation
ifndef cluster_id
	$(error param cluster_id is not set)
endif
ifndef srf_yaml
	$(error param srf_yaml is not set)
endif
ifndef ocp_name
override ocp_name = $(cluster_id)
endif
	(command -v nise > /dev/null 2>&1) || (echo 'nise is not installed, please install nise.' && exit 1 )
	mkdir -p testing/pvc_dir/insights_local
	nise --ocp --ocp-cluster-id $(cluster_id) --insights-upload testing/pvc_dir/insights_local --static-report-file $(srf_yaml)
	curl -d '{"name": "$(ocp_name)", "type": "OCP", "authentication": {"provider_resource_name": "$(cluster_id)"}}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8000/api/cost-management/v1/providers/
# These csv could be cleaned up by: https://github.com/project-koku/koku/issues/1602 is resolved.
	rm *ocp_pod_usage.csv
	rm *ocp_storage_usage.csv
# From here you can hit the http://127.0.0.1:5000/api/cost-management/v1/download/ endpoint to start running masu.
# After masu has run these endpoints should have data in them: (v1/reports/openshift/memory, v1/reports/openshift/compute/, v1/reports/openshift/volumes/)

aws_provider:
ifndef aws_name
	$(error param aws_name is not set)
endif
ifndef bucket
	$(error param bucket is not set)
endif
	(printenv AWS_RESOURCE_NAME > /dev/null 2>&1) || (echo 'AWS_RESOURCE_NAME is not set in .env' && exit 1)
	curl -d '{"name": "$(aws_name)", "type": "AWS", "authentication": {"provider_resource_name": "${AWS_RESOURCE_NAME}"}, "billing_source": {"bucket": "$(bucket)"}}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8000/api/cost-management/v1/providers/

########################
### Internal targets ###
########################

__oc-create-project:
	@if [[ ! $$(oc get -o name project/$(NAMESPACE) 2>/dev/null) ]]; then \
		oc new-project $(NAMESPACE) ;\
	fi

# if object doesn't already exist,
# create it from the provided template and parameters
__oc-create-object: __oc-create-project
	@if [[ $$(oc get -o name $(OC_OBJECT) 2>&1) == '' ]] || \
	[[ $$(oc get -o name $(OC_OBJECT) 2>&1 | grep 'not found') ]]; then \
		if [ -f $(OC_PARAM_DIR)/$(OC_PARAMETER_FILE) ]; then \
			oc process -f $(OC_TEMPLATE_DIR)/$(OC_TEMPLATE_FILE) \
				--param-file=$(OC_PARAM_DIR)/$(OC_PARAMETER_FILE) \
			| oc create --save-config=True -n $(NAMESPACE) -f - 2>&1 || /usr/bin/true ;\
		else \
			oc process -f $(OC_TEMPLATE_DIR)/$(OC_TEMPLATE_FILE) \
				$(foreach PARAM, $(OC_PARAMETERS), -p $(PARAM)) \
			| oc create --save-config=True -n $(NAMESPACE) -f - 2>&1 || /usr/bin/true ;\
		fi ;\
	fi

__oc-apply-object: __oc-create-project
	@if [[ $$(oc get -o name $(OC_OBJECT)) != '' ]] || \
	[[ $$(oc get -o name $(OC_OBJECT) 2>&1 | grep -v 'not found') ]]; then \
		echo "WARNING: Resources matching 'oc get $(OC_OBJECT)' exists. Updating template. Skipping object creation." ;\
		if [ -f $(OC_PARAM_DIR)/$(OC_PARAMETER_FILE) ]; then \
			bash -c "oc process -f $(OC_TEMPLATE_DIR)/$(OC_TEMPLATE_FILE) \
				--param-file=$(OC_PARAM_DIR)/$(OC_PARAMETER_FILE) \
			| tee >(oc apply -n $(NAMESPACE) -f -) >(oc replace -f -) || /usr/bin/true" ;\
		else \
			bash -c "oc process -f $(OC_TEMPLATE_DIR)/$(OC_TEMPLATE_FILE) \
				$(foreach PARAM, $(OC_PARAMETERS), -p $(PARAM)) \
			| tee >(oc apply -n $(NAMESPACE) -f -) >(oc replace -f -) || /usr/bin/true" ;\
		fi ;\
	fi

#
# Phony targets
#
.PHONY: docs __oc-create-object __oc-create-project __oc-apply-object
