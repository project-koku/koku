PYTHON	= $(shell which python)

TOPDIR  = $(shell pwd)
PYDIR	= koku
APIDOC = $(TOPDIR)/apidoc

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
	@echo "  serve                    to run the Django server locally"
	@echo "  start-db                 to start the psql db in detached state"
	@echo "  stop-compose             to stop all containers"
	@echo "  unittest                 to run unittests"
	@echo "  user                     to create a Django super user"
	@echo "  oc-up                    run app in openshift cluster"
	@echo "  oc-down                  stop app & openshift cluster"
	@echo "  oc-clean                 stop openshift cluster & remove local config data"

clean:
	git clean -fdx -e .idea/ -e *env/

html:
	@cd docs; $(MAKE) html

lint:
	tox -elint

reinitdb: stop-compose remove-db start-db run-migrations

remove-db:
	rm -rf $(TOPDIR)/pg_data

make-migrations:
	sleep 1
	DJANGO_READ_DOT_ENV_FILE=True$(PYTHON) $(PYDIR)/manage.py makemigrations api

run-migrations:
	sleep 1
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py migrate

gen-apidoc:
	rm -fr $(PYDIR)/staticfiles/
	apidoc -i $(PYDIR) -o $(APIDOC)

collect-static:
	$(PYTHON) $(PYDIR)/manage.py collectstatic --no-input

serve:
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py runserver

start-db:
	docker-compose up -d db

stop-compose:
	docker-compose down

unittest:
	$(PYTHON) $(PYDIR)/manage.py test $(PYDIR)

user:
	$(PYTHON) $(PYDIR)/manage.py createsuperuser

oc-up:
	oc cluster up \
		--image=$(OC_SOURCE) \
		--version=$(OC_VERSION) \
		--host-data-dir=$(OC_DATA_DIR) \
		--use-existing-config=true
	./init-app.sh -n myproject -b `git rev-parse --abbrev-ref HEAD`

oc-down:
	oc cluster down

oc-clean: oc-down
	$(PREFIX) rm -rf $(OC_DATA_DIR)

.PHONY: docs
