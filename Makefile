PYTHON	= $(shell which python)

TOPDIR  = $(shell pwd)
PYDIR	= saltcellar

help:
	@echo "Please use \`make <target>' where <target> is one of:"
	@echo "  clean                    to clean the project directory of any scratch files, bytecode, logs, etc."
	@echo "  help                     to show this message"
	@echo "  html                     to create html documentation for the project"
	@echo "  lint                     to run linting against the project"
	@echo "  reinitdb                 to drop and recreate the database"
	@echo "  run-migrations           to run migrations against database"
	@echo "  serve                    to run the Django server locally"
	@echo "  start-db                 to start the psql db in detached state"
	@echo "  stop-compose             to stop all containers"
	@echo "  unittest                 to run unittests"
	@echo "  user                     to create a Django super user"

clean:
	git clean -fdx -e .idea/ -e *env/

html:
	@cd docs; $(MAKE) html

lint:
	tox -elint

reinitdb: stop-compose remove-db start-db run-migrations

remove-db:
	rm -rf $(TOPDIR)/pg_data

run-migrations:
	sleep 1
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py migrate

serve:
	DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py runserver

start-db:
	docker-compose up -d db

stop-compose:
	docker-compose down

unittest:
	$(PYTHON) $(PYDIR)/manage.py test

user:
	$(PYTHON) $(PYDIR)/manage.py createsuperuser

.PHONY: docs
