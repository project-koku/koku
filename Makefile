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

# OpenShift template parameters
NAME = koku
NAMESPACE = koku

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

define HELP_TEXT =
Please use \`make <target>' where <target> is one of:

--- General Commands ---
  clean                    clean the project directory of any scratch files, bytecode, logs, etc.
  help                     show this message
  html                     create html documentation for the project
  lint                     run linting against the project

--- Commands using local services ---
  create-test-db-file      create a Postgres DB dump file for Masu
  collect-static           collect static files to host
  gen-apidoc               create api documentation
  make-migrations          make migrations for the database
  reinitdb                 drop and recreate the database
  requirements             generate Pipfile.lock and RTD requirements
  remove-db                remove local directory: $(TOPDIR)/pg_data
  run-migrations           run migrations against database
  serve                    run the Django app on localhost
  superuser                create a Django super user
  unittest                 run unittests

--- Commands using Docker Compose ---
  docker-up                 run django and database
  docker-up-db              run database only
  docker-down               shut down all containers
  docker-rabbit             run RabbitMQ container
  docker-shell              run Django and database containers with shell access to server (for pdb)
  docker-logs               connect to console logs for all services
  docker-test-all           run unittests

--- Commands using an OpenShift Cluster ---
  oc-clean                     stop openshift cluster & remove local config data
  oc-create-all                create all application pods
  oc-create-celery-exporter    create the Celery Prometheus exporter pod
  oc-create-celery-scheduler   create the Celery scheduler pod
  oc-create-celery-worker      create the Celery worker pod
  oc-create-configmap          create the ConfigMaps
  oc-create-database           create the PostgreSQL DB pod
  oc-create-flower             create the Celery Flower pod
  oc-create-imagestream        create ImageStreams
  oc-create-koku-api           create the Koku API pod
  oc-create-koku-auth-cache    create the Redis pod for auth caching
  oc-create-listener           create Masu Listener pod (deprecated)
  oc-create-masu               create Masu pod (deprecated)
  oc-create-rabbitmq           create RabbitMQ pod
  oc-create-secret             create Secrets
  oc-create-worker             create Celery worker pod
  oc-create-test-db-file       create a Postgres DB dump file for Masu
  oc-delete-all                delete most Openshift objects without a cluster restart
  oc-delete-celery-worker      delete the Celery worker pod
  oc-delete-configmap          delete the ConfigMaps
  oc-delete-database           delete the PostgreSQL DB pod
  oc-delete-flower             delete the Celery Flower pod
  oc-delete-imagestream        delete ImageStreams
  oc-delete-koku-api           delete the Koku API pod
  oc-delete-koku-auth-cache    delete the Redis pod for auth caching
  oc-delete-listener           delete Masu Listener pod (deprecated)
  oc-delete-masu               delete Masu pod (deprecated)
  oc-delete-rabbitmq           delete RabbitMQ pod
  oc-delete-secret             delete Secrets
  oc-delete-worker             delete Celery worker pod
  oc-down                      stop app & openshift cluster
  oc-forward-ports             port forward the DB to localhost
  oc-login-dev                 login to an openshift cluster as 'developer'
  oc-reinit                    remove existing app and restart app in initialized openshift cluster
  oc-run-migrations            run Django migrations in the Openshift DB
  oc-stop-forwarding-ports     stop port forwarding the DB to localhost
  oc-up                        initialize an openshift cluster
  oc-up-all                    run app in openshift cluster
  oc-up-db                     run Postgres in an openshift cluster
endef
export HELP_TEXT

# help always comes first.
help:
	@echo "$$HELP_TEXT"


### General Commands ###

clean:
	git clean -fdx -e .idea/ -e *env/

html:
	@cd docs; $(MAKE) html

lint:
	tox -e lint

#####################################
### Commands using local services ###
#####################################

# FIXME: may need updating after masu is fully merged.
create-masu-test-db:
	$(TOPDIR)/tests/create_db.sh

create-test-db-file: run-migrations
	sleep 1
	$(DJANGO_MANAGE) runserver > /dev/null 2>&1 &
	sleep 5
	$(PYTHON) $(TOPDIR)/scripts/create_test_customer.py --bypass-api
	pg_dump -d $(DATABASE_NAME) -h $(POSTGRES_SQL_SERVICE_HOST) -p $(POSTGRES_SQL_SERVICE_PORT) -U $(DATABASE_USER) > test.sql
	kill -HUP $$(ps -eo pid,command | grep "manage.py runserver" | grep -v grep | awk '{print $$1}')

collect-static:
	$(DJANGO_MANAGE) collectstatic --no-input

gen-apidoc:
	rm -fr $(PYDIR)/staticfiles/
	rm -fr $(APIDOC)
	apidoc -i $(PYDIR) -o $(APIDOC)
	cp docs/source/specs/openapi.json $(APIDOC)/

make-migrations:
	$(DJANGO_MANAGE) makemigrations api reporting reporting_common rates

reinitdb: stop-compose remove-db start-db
	sleep 5
	$(MAKE) run-migrations
	$(MAKE) create-test-db-file

remove-db:
	$(PREFIX) rm -rf $(TOPDIR)/pg_data

requirements:
	pipenv lock
	pipenv lock -r > docs/rtd_requirements.txt

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

oc-create-all: oc-create-celery-exporter oc-create-configmap oc-create-database oc-create-flower oc-create-imagestream oc-create-koku-api oc-create-koku-auth-cache oc-create-listener oc-create-masu oc-create-rabbitmq oc-create-secret oc-create-worker

oc-create-celery-exporter: export OC_OBJECT = dc/$(NAME)-celery-exporter
oc-create-celery-exporter: export OC_PARAMETER_FILE = celery-exporter.env
oc-create-celery-exporter: export OC_TEMPLATE_FILE = celery-exporter.yaml
oc-create-celery-exporter:
	$(MAKE) oc-create-imagestream
	$(MAKE) oc-create-configmap
	$(MAKE) oc-create-secret
	$(MAKE) __oc-create-object

oc-create-celery-scheduler: export OC_OBJECT = bc/$(NAME)-scheduler dc/$(NAME)-scheduler
oc-create-celery-scheduler: export OC_PARAMETER_FILE = celery-scheduler.env
oc-create-celery-scheduler: export OC_TEMPLATE_FILE = celery-scheduler.yaml
oc-create-celery-scheduler:
	$(MAKE) oc-create-imagestream
	$(MAKE) oc-create-configmap
	$(MAKE) oc-create-secret
	$(MAKE) __oc-create-object

oc-create-celery-worker: export OC_OBJECT = bc/$(NAME)-worker dc/$(NAME)-worker
oc-create-celery-worker: export OC_PARAMETER_FILE = celery-worker.env
oc-create-celery-worker: export OC_TEMPLATE_FILE = celery-worker.yaml
oc-create-celery-worker:
	$(MAKE) oc-create-imagestream
	$(MAKE) oc-create-configmap
	$(MAKE) oc-create-secret
	$(MAKE) __oc-create-object

oc-create-configmap: export OC_OBJECT = configmap -l app=$(NAME)
oc-create-configmap: export OC_PARAMETER_FILE = configmap.env
oc-create-configmap: export OC_TEMPLATE_FILE = configmap.yaml
oc-create-configmap:
	$(MAKE) __oc-create-object

oc-create-database: export OC_OBJECT = bc/$(NAME)-db dc/$(NAME)-db
oc-create-database: export OC_PARAMETER_FILE = $(NAME)-database.env
oc-create-database: export OC_TEMPLATE_FILE = $(NAME)-database.yaml
oc-create-database:
	$(MAKE) oc-create-imagestream
	$(MAKE) oc-create-configmap
	$(MAKE) oc-create-secret
	$(MAKE) __oc-create-object

oc-create-flower: export OC_OBJECT = bc/$(NAME)-flower dc/$(NAME)-flower
oc-create-flower: export OC_PARAMETER_FILE = celery-flower.env
oc-create-flower: export OC_TEMPLATE_FILE = celery-flower.yaml
oc-create-flower:
	$(MAKE) oc-create-imagestream
	$(MAKE) oc-create-configmap
	$(MAKE) oc-create-secret
	$(MAKE) __oc-create-object

oc-create-imagestream: export OC_OBJECT = is/centos
oc-create-imagestream: export OC_TEMPLATE_FILE = imagestream.yaml
oc-create-imagestream:
	$(MAKE) __oc-create-object

oc-create-koku-api: export OC_OBJECT = bc/$(NAME) dc/$(NAME)
oc-create-koku-api: export OC_PARAMETER_FILE = $(NAME)-api.env
oc-create-koku-api: export OC_TEMPLATE_FILE = $(NAME)-api.yaml
oc-create-koku-api:
	$(MAKE) oc-create-imagestream
	$(MAKE) oc-create-configmap
	$(MAKE) oc-create-secret
	$(MAKE) __oc-create-object

oc-create-koku-auth-cache: export OC_OBJECT = bc/$(NAME)-redis dc/$(NAME)-redis
oc-create-koku-auth-cache: export OC_PARAMETER_FILE = $(NAME)-auth-cache.env
oc-create-koku-auth-cache: export OC_TEMPLATE_FILE = $(NAME)-auth-cache.yaml
oc-create-koku-auth-cache:
	$(MAKE) oc-create-imagestream
	$(MAKE) oc-create-configmap
	$(MAKE) oc-create-secret
	$(MAKE) __oc-create-object

oc-create-listener: export OC_OBJECT = bc/$(NAME)-listener dc/$(NAME)-listener
oc-create-listener: export OC_PARAMETER_FILE = masu-listener.env
oc-create-listener: export OC_TEMPLATE_FILE = masu-listener.yaml
oc-create-listener:
	$(MAKE) oc-create-imagestream
	$(MAKE) oc-create-configmap
	$(MAKE) oc-create-secret
	$(MAKE) __oc-create-object

oc-create-masu: export OC_OBJECT = bc/$(NAME)-masu dc/$(NAME)-masu
oc-create-masu: export OC_PARAMETER_FILE = masu-flask.env
oc-create-masu: export OC_TEMPLATE_FILE = masu-flask.yaml
oc-create-masu:
	$(MAKE) oc-create-imagestream
	$(MAKE) oc-create-configmap
	$(MAKE) oc-create-secret
	$(MAKE) __oc-create-object

oc-create-rabbitmq: export OC_OBJECT = statefulsets/rabbitmq
oc-create-rabbitmq: export OC_PARAMETER_FILE = rabbitmq.env
oc-create-rabbitmq: export OC_TEMPLATE_FILE = rabbitmq.yaml
oc-create-rabbitmq:
	$(MAKE) __oc-create-object

oc-create-secret: export OC_OBJECT = secret -l app=$(NAME)
oc-create-secret: export OC_PARAMETER_FILE = secret.env
oc-create-secret: export OC_TEMPLATE_FILE = secret.yaml
oc-create-secret:
	$(MAKE) __oc-create-object

oc-create-test-db-file: oc-run-migrations
	sleep 1
	make oc-forward-ports
	sleep 1
	$(DJANGO_MANAGE) runserver > /dev/null 2>&1 &
	sleep 5
	$(PYTHON) $(TOPDIR)/scripts/create_test_customer.py --bypass-api
	pg_dump -d $(DATABASE_NAME) -h $(POSTGRES_SQL_SERVICE_HOST) -p $(POSTGRES_SQL_SERVICE_PORT) -U $(DATABASE_USER) > test.sql
	kill -HUP $$(ps -eo pid,command | grep "manage.py runserver" | grep -v grep | awk '{print $$1}')
	$(MAKE) oc-stop-forwarding-ports

oc-delete-all:
	oc delete all -l app=koku

oc-delete-all-all:
	oc delete all,configmap,secret,pvc -l app=koku

oc-delete-celery-exporter:
	oc delete all -n $(NAMESPACE) -l template=koku-celery-exporter

oc-delete-celery-scheduler:
	oc delete all -n $(NAMESPACE) -l template=koku-celery-scheduler

oc-delete-celery-worker:
	oc delete all -n $(NAMESPACE) -l template=koku-celery-worker

oc-delete-configmap:
	oc delete all -n $(NAMESPACE) -l template=koku-configmap

oc-delete-database:
	oc delete all -n $(NAMESPACE) -l template=koku-database

oc-delete-flower:
	oc delete all -n $(NAMESPACE) -l template=koku-celery-flower

oc-delete-imagestream:
	oc delete all -n $(NAMESPACE) -l template=koku-imagestream

oc-delete-koku-api:
	oc delete all -n $(NAMESPACE) -l template=koku-api

oc-delete-koku-auth-cache:
	oc delete all -n $(NAMESPACE) -l template=koku-auth-cache

oc-delete-listener:
	oc delete all -n $(NAMESPACE) -l template=koku-masu-listener

oc-delete-masu:
	oc delete all -n $(NAMESPACE) -l template=koku-masu-flask

oc-delete-rabbitmq:
	oc delete all -n $(NAMESPACE) -l template=rabbitmq

oc-delete-secret:
	oc delete all -n $(NAMESPACE) -l template=koku-secret

oc-down:
	oc cluster down

oc-forward-ports: oc-stop-forwarding-ports
	oc port-forward $$(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=koku-pgsql) 15432:5432 >/dev/null 2>&1 &

oc-login-dev:
	oc login -u developer --insecure-skip-tls-verify=true localhost:8443

oc-make-migrations: oc-forward-ports
	sleep 1
	$(DJANGO_MANAGE) makemigrations api reporting reporting_common rates
	$(MAKE) oc-stop-forwarding-ports

oc-reinit: oc-delete-all oc-create-koku

oc-run-migrations: oc-forward-ports
	sleep 1
	$(DJANGO_MANAGE) migrate_schemas
	$(MAKE) oc-stop-forwarding-ports

oc-stop-forwarding-ports:
	kill -HUP $$(ps -eo pid,command | grep "oc port-forward" | grep -v grep | awk '{print $$1}')

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

docker-logs:
	docker-compose logs -f

docker-rabbit:
	docker-compose up -d rabbit

docker-shell:
	docker-compose run --service-ports koku-server

docker-test-all:
	docker-compose -f koku-test.yml up --build

docker-up:
	docker-compose up --build -d

docker-up-db:
	docker-compose up -d db

__oc-create-object:
	@if [ -f $(OC_PARAM_DIR)/$(OC_PARAMETER_FILE) ]; then \
		echo "A" && \
		[ "$$(oc get $(OC_OBJECT) 2>/dev/null)" == 'No resources found.' ] || \
		oc process -f $(OC_TEMPLATE_DIR)/$(OC_TEMPLATE_FILE) \
			--param-file=$(OC_PARAM_DIR)/$(OC_PARAMETER_FILE) \
		| oc create -n $(NAMESPACE) -f - ;\
	else \
		echo "B" && \
		[ "$$(oc get $(OC_OBJECT) 2>/dev/null)" == 'No resources found.' ] || \
		oc process -f $(OC_TEMPLATE_DIR)/$(OC_TEMPLATE_FILE) \
			$(foreach PARAM, $(OC_PARAMETERS), -p $(PARAM)) \
		| oc create -n $(NAMESPACE) -f - ;\
	fi

#
# Phony targets
#
.PHONY: docs __oc-create-object
