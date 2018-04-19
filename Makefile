PYTHON	= $(shell which python)

TOPDIR  = $(shell pwd)
PYDIR	= saltcellar

clean:
	git clean -fdx -e .idea/ -e *env/

help:
	@echo "Please use \`make <target>' where <target> is one of:"
	@echo "  clean                    to clean the project directory of any scratch files, bytecode, logs, etc."
	@echo "  help                     to show this message"
	@echo "  html                     to create html documentation for the project"
	@echo "  lint                     to run linting against the project"
	@echo "  reinitdb                 to drop and recreate the database"
	@echo "  run-migrations           to run migrations against database"
	@echo "  serve                    to run the Django server locally"
	@echo "  unittest                 to run unittests"
	@echo "  user                     to create a Django super user"

html:
	@cd docs; $(MAKE) html

lint:
	tox -eflake8

reinitdb: remove-db run-migrations

remove-db:
	rm -rf $(TOPDIR)/db.sqlite3

run-migrations:
	sleep 1
	$(PYTHON) manage.py migrate

serve:
	$(PYTHON) manage.py runserver

unittest:
	$(PYTHON) manage.py test

user:
	$(PYTHON) manage.py createsuperuser

.PHONY: docs
