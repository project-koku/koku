PYTHON	= $(shell which python)

TOPDIR  = $(shell pwd)
PYDIR	= koku
APIDOC = apidoc

OC_SOURCE	= registry.access.redhat.com/openshift3/ose
OC_VERSION	= v3.7
OC_DATA_DIR	= ${HOME}/.oc/openshift.local.data

OS := $(shell uname)
ifeq ($(OS),Darwin)
	PREFIX	=
else
	PREFIX	= sudo
endif

help:
	@echo "Please use \`make <target>' where <target> is one of:"
	@echo "  clean                    to clean the project directory of any scratch files, bytecode, logs, etc."
	@echo "  help                     to show this message"
	@echo "  html                     to create html documentation for the project"
	@echo "  lint                     to run linting against the project"
	@echo "  reinitdb                 to drop and recreate the database"
	@echo "  make-migrations          to make migrations for the database"
	@echo "  run-migrations           to run migrations against database"
	@echo "  gen-apidoc               to create api documentation"
	@echo "  collect-static           to collect static files to host"
	@echo "  requirements             to generate Pipfile.lock and RTD requirements"
	@echo "  serve                    to run the Django server locally"
	@echo "  start-db                 to start the psql db in detached state"
	@echo "  stop-compose             to stop all containers"
	@echo "  unittest                 to run unittests"
	@echo "  user                     to create a Django super user"
	@echo "  oc-up                    to initialize an openshift cluster"
	@echo "  oc-up-all                to run app in openshift cluster"
	@echo "  oc-up-db                 to run Postgres in an openshift cluster"
	@echo "  oc-init                  to start app in initialized openshift cluster"
	@echo "  oc-reinit                to remove existing app and restart app in initialized openshift cluster"
	@echo "  oc-create-db             to create a Postgres DB in an initialized openshift cluster"
	@echo "  oc-forward-ports         to port forward the DB to localhost"
	@echo "  oc-stop-forwarding-ports to stop port forwarding the DB to localhost"
	@echo "  oc-run-migrations  	  to run Django migrations in the Openshift DB"
	@echo "  oc-serve 			 	  to run Django server locally against an Openshift DB"
	@echo "  oc-down                  to stop app & openshift cluster"
	@echo "  oc-clean                 to stop openshift cluster & remove local config data"

clean:
	git clean -fdx -e .idea/ -e *env/

html:
	@cd docs; $(MAKE) html

lint:
	tox -elint

reinitdb: stop-compose remove-db start-db run-migrations

remove-db:
	$(PREFIX) rm -rf $(TOPDIR)/pg_data

make-migrations:
	sleep 1
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py makemigrations api reporting reporting_common

run-migrations:
	sleep 1
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py migrate_schemas

gen-apidoc:
	rm -fr $(PYDIR)/staticfiles/
	apidoc -i $(PYDIR) -o $(APIDOC)

collect-static:
	$(PYTHON) $(PYDIR)/manage.py collectstatic --no-input

requirements:
	pipenv lock
	pipenv lock -r > docs/rtd_requirements.txt

serve:
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py runserver

start-db:
	docker-compose up -d db

stop-compose:
	docker-compose down

unittest:
	$(PYTHON) $(PYDIR)/manage.py test $(PYDIR) -v 2

user:
	$(PYTHON) $(PYDIR)/manage.py createsuperuser

oc-up:
	oc cluster up \
		--image=$(OC_SOURCE) \
		--version=$(OC_VERSION) \
		--host-data-dir=$(OC_DATA_DIR) \
		--use-existing-config=true
	sleep 60

oc-init:
	openshift/init-app.sh -n myproject -b `git rev-parse --abbrev-ref HEAD`

oc-up-all: oc-up oc-init

oc-up-db: oc-up oc-create-db

oc-reinit:
	oc login -u developer
	oc delete all -l app=koku && oc delete configmap/koku-env secret/koku-secret secret/koku-pgsql pvc/koku-pgsql
	sleep 10
	make oc-init

oc-down:
	oc cluster down

oc-clean: oc-down
	$(PREFIX) rm -rf $(OC_DATA_DIR)

oc-create-db:
	oc login -u developer
	oc create istag postgresql:9.6 --from-image=centos/postgresql-96-centos7
	oc process openshift//postgresql-persistent \
		-p NAMESPACE=myproject \
		-p POSTGRESQL_USER=kokuadmin \
		-p POSTGRESQL_PASSWORD=admin123 \
		-p POSTGRESQL_DATABASE=koku \
		-p POSTGRESQL_VERSION=9.6 \
		-p DATABASE_SERVICE_NAME=koku-pgsql \
	| oc create -f -

oc-forward-ports:
	-make oc-stop-forwarding-ports 2>/dev/null
	oc port-forward $$(oc get pods -o jsonpath='{.items[*].metadata.name}' -l name=koku-pgsql) 15432:5432 >/dev/null 2>&1 &

oc-stop-forwarding-ports:
	kill -HUP $$(ps -eo pid,command | grep "oc port-forward" | grep -v grep | awk '{print $$1}')

oc-make-migrations: oc-forward-ports
	sleep 3
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py makemigrations api reporting reporting_common
	make oc-stop-forwarding-ports

oc-run-migrations: oc-forward-ports
	sleep 3
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py migrate_schemas --shared
	make oc-stop-forwarding-ports

oc-serve: oc-forward-ports
	sleep 3
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py runserver
	make oc-stop-forwarding-ports

.PHONY: docs
