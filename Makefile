PYTHON	= $(shell which python)

TOPDIR  = $(shell pwd)
PYDIR	= koku
APIDOC = apidoc

OC_SOURCE	= registry.access.redhat.com/openshift3/ose
OC_VERSION	= v3.9
OC_DATA_DIR	= ${HOME}/.oc/openshift.local.data

PGSQL_VERSION   = 9.6

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
  run-migrations           run migrations against database
  serve                    run the Django server locally
  serve-with-oc            run Django server locally against an Openshift DB
  start-db                 start the psql db in detached state
  stop-compose             stop all containers
  unittest                 run unittests
  user                     create a Django super user

--- Commands using Docker Compose ---
  docker-up                 run django and database
  docker-down               shut down service containers
  docker-shell              run django and db containers with shell access to server (for pdb)
  docker-logs               connect to console logs for all services
  docker-test-all           run unittests

--- Commands using an OpenShift Cluster ---
  oc-clean                 stop openshift cluster & remove local config data
  oc-create-all            run all application services in openshift cluster
  oc-create-db             create a Postgres DB in an initialized openshift cluster
  oc-create-koku           create the Koku app in an initialized openshift cluster
  oc-create-tags           create image stream tags
  oc-create-test-db-file   create a Postgres DB dump file for Masu
  oc-delete-all            delete Openshift objects without a cluster restart
  oc-down                  stop app & openshift cluster
  oc-forward-ports         port forward the DB to localhost
  oc-login-dev             login to an openshift cluster as 'developer'
  oc-reinit                remove existing app and restart app in initialized openshift cluster
  oc-run-migrations        run Django migrations in the Openshift DB
  oc-stop-forwarding-ports stop port forwarding the DB to localhost
  oc-up                    initialize an openshift cluster
  oc-up-all                run app in openshift cluster
  oc-up-db                 run Postgres in an openshift cluster
endef
export HELP_TEXT

help:
	@echo "$$HELP_TEXT"

clean:
	git clean -fdx -e .idea/ -e *env/

html:
	@cd docs; $(MAKE) html

lint:
	tox -elint

reinitdb: stop-compose remove-db start-db
	sleep 5
	make run-migrations
	make create-test-db-file

remove-db:
	$(PREFIX) rm -rf $(TOPDIR)/pg_data

make-migrations:
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py makemigrations api reporting reporting_common rates

run-migrations:
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py migrate_schemas

create-test-db-file: run-migrations
	sleep 1
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py runserver > /dev/null 2>&1 &
	sleep 5
	$(PYTHON) $(TOPDIR)/scripts/create_test_customer.py --bypass-api
	pg_dump -d $(DATABASE_NAME) -h $(POSTGRES_SQL_SERVICE_HOST) -p $(POSTGRES_SQL_SERVICE_PORT) -U $(DATABASE_USER) > test.sql
	kill -HUP $$(ps -eo pid,command | grep "manage.py runserver" | grep -v grep | awk '{print $$1}')

gen-apidoc:
	rm -fr $(PYDIR)/staticfiles/
	rm -fr $(APIDOC)
	apidoc -i $(PYDIR) -o $(APIDOC)
	cp docs/source/specs/openapi.json $(APIDOC)/

collect-static:
	$(PYTHON) $(PYDIR)/manage.py collectstatic --no-input

requirements:
	pipenv lock
	pipenv lock -r > docs/rtd_requirements.txt

serve:
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py runserver

serve-with-oc: oc-forward-ports
	sleep 3
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py runserver
	make oc-stop-forwarding-ports

start-db:
	docker-compose up -d db

stop-compose:
	docker-compose down

unittest:
	$(PYTHON) $(PYDIR)/manage.py test $(PYDIR) -v 2

user:
	$(PYTHON) $(PYDIR)/manage.py createsuperuser

oc-clean: oc-down
	$(PREFIX) rm -rf $(OC_DATA_DIR)

oc-create-tags:
	oc get istag postgresql:$(PGSQL_VERSION) || oc create istag postgresql:$(PGSQL_VERSION) --from-image=centos/postgresql-96-centos7

oc-create-redis-tags:
	oc get istag redis:5.0.4 || oc create istag redis:5.0.4 --from-image=redis

oc-create-db:
	oc process openshift//postgresql-persistent \
		-p NAMESPACE=myproject \
		-p POSTGRESQL_USER=kokuadmin \
		-p POSTGRESQL_PASSWORD=admin123 \
		-p POSTGRESQL_DATABASE=koku \
		-p POSTGRESQL_VERSION=$(PGSQL_VERSION) \
		-p DATABASE_SERVICE_NAME=koku-pgsql \
	| oc create -f -

oc-create-all: oc-create-tags oc-create-koku

oc-create-koku:
	openshift/init-app.sh -n myproject -b `git rev-parse --abbrev-ref HEAD`

oc-create-test-db-file: oc-run-migrations
	sleep 1
	make oc-forward-ports
	sleep 1
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py runserver > /dev/null 2>&1 &
	sleep 5
	$(PYTHON) $(TOPDIR)/scripts/create_test_customer.py --bypass-api
	pg_dump -d $(DATABASE_NAME) -h $(POSTGRES_SQL_SERVICE_HOST) -p $(POSTGRES_SQL_SERVICE_PORT) -U $(DATABASE_USER) > test.sql
	kill -HUP $$(ps -eo pid,command | grep "manage.py runserver" | grep -v grep | awk '{print $$1}')
	make oc-stop-forwarding-ports

oc-delete-all:
	oc delete is --all && \
	oc delete dc --all && \
	oc delete bc --all && \
	oc delete svc --all && \
	oc delete pvc --all && \
	oc delete routes --all && \
	oc delete statefulsets --all && \
	oc delete configmap/koku-env \
		secret/koku-secret \
		secret/koku-pgsql \

oc-down:
	oc cluster down

oc-forward-ports:
	-make oc-stop-forwarding-ports 2>/dev/null
	oc port-forward $$(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=koku-pgsql) 15432:5432 >/dev/null 2>&1 &

oc-login-dev:
	oc login -u developer --insecure-skip-tls-verify=true localhost:8443

oc-make-migrations: oc-forward-ports
	sleep 3
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py makemigrations api reporting reporting_common rates
	make oc-stop-forwarding-ports

oc-reinit: oc-delete-all oc-create-koku

oc-run-migrations: oc-forward-ports
	sleep 3
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py migrate_schemas
	make oc-stop-forwarding-ports

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

docker-up:
	docker-compose up --build -d

docker-logs:
	docker-compose logs -f

docker-shell:
	docker-compose run --service-ports koku-server

docker-test-all:
	docker-compose -f koku-test.yml up --build

docker-down:
	docker-compose down

.PHONY: docs
