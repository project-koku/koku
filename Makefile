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
SCRIPTDIR = $(TOPDIR)/dev/scripts
KOKU_SERVER = $(shell echo "${KOKU_API_HOST:-localhost}")
KOKU_SERVER_PORT = $(shell echo "${KOKU_API_PORT:-8000}")
MASU_SERVER = $(shell echo "${MASU_SERVICE_HOST:-localhost}")
MASU_SERVER_PORT = $(shell echo "${MASU_SERVICE_PORT:-5042}")
DOCKER := $(shell which docker 2>/dev/null || which podman 2>/dev/null)
DOCKER_BUILDKIT = 1
scale = 1

# Prefer Docker Compose v2
DOCKER_COMPOSE_CHECK := $(shell $(DOCKER) compose version >/dev/null 2>&1 ; echo $$?)
DOCKER_COMPOSE_BIN = $(DOCKER) compose
ifneq ($(DOCKER_COMPOSE_CHECK), 0)
	DOCKER_COMPOSE_BIN = $(DOCKER)-compose
endif

# Use ARM images on ARM systems
DOCKER_COMPOSE = $(DOCKER_COMPOSE_BIN)
ifeq (arm, $(findstring arm, $(shell uname -m)))
	DOCKER_COMPOSE = $(DOCKER_COMPOSE_BIN) -f docker-compose.yml -f docker-compose.arm.yml
endif

# Testing directories
TESTINGDIR = $(TOPDIR)/testing
PROVIDER_TEMP_DIR = $(TESTINGDIR)/data
OCP_PROVIDER_TEMP_DIR = $(PROVIDER_TEMP_DIR)/insights_local

# How to execute Django's manage.py
DJANGO_MANAGE = DJANGO_READ_DOT_ENV_FILE=True $(PYTHON) $(PYDIR)/manage.py

# Platform differences
#
# - Use 'sudo' on Linux
# - Don't use 'sudo' on MacOS
#
OS := $(shell uname)
ifeq ($(OS),Darwin)
	PREFIX	=
	SED_IN_PLACE = sed -i ""
else
	PREFIX	= sudo
	SED_IN_PLACE = sed -i
endif

help:
	@echo "Please use \`make <target>' where <target> is one of:"
	@echo ""
	@echo "--- General Commands ---"
	@echo "  clean                                 clean the project directory of any scratch files, bytecode, logs, etc"
	@echo "  help                                  show this message"
	@echo "  lint                                  run pre-commit against the project"
	@echo "  get-release-commit                    show the latest commit that is safe to release"
	@echo ""
	@echo "--- Commands using local services ---"
	@echo "  delete-testing                        Delete stale files/subdirectories from the testing directory."
	@echo "  delete-trino                          Delete stale files/subdirectories from the trino data directory."
	@echo "  delete-trino-data                     Delete old trino data from .trino/parquet_data/koku-bucket/."
	@echo "  delete-redis-cache                    Flushes cache keys inside of the redis container."
	@echo "  create-test-customer                  create a test customer and tenant in the database"
	@echo "  create-test-customer-no-sources       create a test customer and tenant in the database without test sources"
	@echo "  create-large-ocp-source-config-file   create a config file for nise to generate a large data sample"
	@echo "                                          @param output_file_name - file name for output"
	@echo "                                          @param generator_config_file - (optional, default=default) config file for the generator"
	@echo "                                          @param generator_template_file - (optional) jinja2 template to render output"
	@echo "                                          @param generator_flags - (optional) additional cli flags and args"
	@echo "  delete-test-sources                   Call the source DELETE API for each source in the database"
	@echo "  delete-cost-models                    Call the cost-model DELETE API for each cost-model in the database"
	@echo "  delete-test-customer-data             Delete all sources and cost-models in the database"
	@echo "  large-ocp-source-testing              create a test OCP source "large_ocp_1" with a larger volume of data"
	@echo "                                          @param nise_config_dir - directory of nise config files to use"
	@echo "  load-test-customer-data               load test data for the default sources created in create-test-customer"
	@echo "                                          @param  test_source - load a specific source's data (aws, azure, gcp, onprem, all(default))"
	@echo "                                          @param start - (optional) start date ex. 2019-08-02"
	@echo "                                          @param end - (optional) end date ex. 2019-12-5"
	@echo "  load-aws-org-unit-tree                inserts aws org tree into model and runs nise command to populate cost"
	@echo "                                          @param tree_yml - (optional) Tree yaml file. Default: 'dev/scripts/aws_org_tree.yml'."
	@echo "                                          @param schema - (optional) schema name. Default: 'org1234567'."
	@echo "                                          @param nise_yml - (optional) Nise yaml file. Defaults to nise static yaml."
	@echo "                                          @param start_date - (optional) Date delta zero in the aws_org_tree.yml"
	@echo "  backup-local-db-dir                   make a backup copy PostgreSQL database directory (pg_data.bak)"
	@echo "  restore-local-db-dir                  overwrite the local PostgreSQL database directory with pg_data.bak"
	@echo "  collect-static                        collect static files to host"
	@echo "  make-migrations                       make migrations for the database"
	@echo "  requirements                          generate Pipfile.lock"
	@echo "  clowdapp                              generates a new clowdapp.yaml"
	@echo "  delete-db                             delete local directory $(TOPDIR)/pg_data"
	@echo "  delete-test-db                        delete the django test db"
	@echo "  reset-db-statistics                   clear the pg_stat_statements statistics"
	@echo "  run-migrations                        run migrations against database"
	@echo "                                          @param applabel - (optional) Use specified application"
	@echo "                                          @param migration - (optional) Migrate to this migration"
	@echo "                                          SPECIFY BOTH PARAMETERS OR NEITHER"
	@echo "  serve                                 run the Django app on localhost"
	@echo "  shell                                 run the Django interactive shell"
	@echo "  shell-schema                          run the Django interactive shell with the specified schema"
	@echo "                                          @param schema - (optional) schema name. Default: 'org1234567'."
	@echo "  superuser                             create a Django super user"
	@echo "  unittest                              run unittests"
	@echo "  local-upload-data                     upload data to Ingress if it is up and running locally"
	@echo "  unleash-export                        export feature-flags to file"
	@echo "  unleash-import                        import feature-flags from file"
	@echo "  unleash-import-drop                   import feature-flags from file AND wipe current database"
	@echo "  scan_project                          run security scan"
	@echo ""
	@echo "--- Commands using Docker Compose ---"
	@echo "  docker-up                            run docker compose up --build -d"
	@echo "  docker-up-no-build                   run docker compose up -d"
	@echo "  docker-up-koku                       run docker compose up -d koku-server"
	@echo "                                         @param build : set to '--build' to build the container"
	@echo "  docker-up-db                         run database only"
	@echo "  docker-up-db-monitor                 run the database monitoring via grafana"
	@echo "                                         url:      localhost:3001"
	@echo "                                         user:     admin"
	@echo "                                         password: admin12"
	@echo "  docker-up-min                        run database, koku/masu servers and worker"
	@echo "  docker-down                          shut down all containers"
	@echo "  docker-up-min-trino                 start minimum targets for Trino usage"
	@echo "  docker-up-min-trino-no-build        start minimum targets for Trino usage without building koku base"
	@echo "  docker-trino-down-all               Tear down Trino and Koku containers"
	@echo "  docker-reinitdb                      drop and recreate the database"
	@echo "  docker-reinitdb-with-sources         drop and recreate the database with fake sources"
	@echo "  docker-reinitdb-with-sources-lite    drop and recreate the database with fake sources without restarting everything"

	@echo "  docker-shell                         run Django and database containers with shell access to server (for pdb)"
	@echo "  docker-logs                          connect to console logs for all services"
	@echo "  docker-iqe-local-hccm                create container based off local hccm plugin. Requires env 'HCCM_PLUGIN_PATH'"
	@echo "                                          @param iqe_cmd - (optional) Command to run. Defaults to 'bash'."
	@echo "  docker-iqe-smoke-tests              run smoke tests"
	@echo "  docker-iqe-smoke-tests-trino        run smoke tests without reininting the db and clearing testing"

	@echo "  docker-iqe-api-tests                 run api tests"
	@echo "  docker-iqe-vortex-tests              run vortex tests"
	@echo ""
	@echo "--- Create Sources ---"
	@echo "  ocp-source-from-yaml                  Create ocp source using a yaml file."
	@echo "      cluster_id=<cluster_name>           @param - Required. The name of your cluster (ex. my-ocp-cluster-0)"
	@echo "      srf_yaml=<filename>                 @param - Required. Path of static-report-file yaml (ex. '/ocp_static_report.yml')"
	@echo "      ocp_name=<source_name>              @param - Required. The name of the source. (ex. 'OCPsource')"
	@echo "  aws-source                            Create aws source using environment variables"
	@echo "      aws_name=<source_name>              @param - Required. Name of the source"
	@echo "      bucket=<bucket_name>                @param - Required. Name of the bucket"
	@echo "  gcp-source                            Create gcp source using environment variables"
	@echo "      gcp_name=<source_name>              @param - Required. Name of the source"

### General Commands ###

clean:
	git clean -fdx -e .idea/ -e *env/ -e .env

lint:
	pre-commit run --all-files

delete-testing:
	$(PREFIX) $(PYTHON) $(SCRIPTDIR)/clear_testing.py -p $(TOPDIR)/testing

delete-trino:
	$(PREFIX) rm -fr ./.trino/

delete-trino-data:
	$(PREFIX) rm -fr ./.trino/parquet_data/koku-bucket/**

delete-redis-cache:
	$(DOCKER) exec -it koku_redis redis-cli -n 1 flushall

create-test-customer: run-migrations docker-up-koku
	$(PYTHON) $(SCRIPTDIR)/create_test_customer.py || echo "WARNING: create_test_customer failed unexpectedly!"

create-test-customer-no-sources: run-migrations docker-up-koku
	$(PYTHON) $(SCRIPTDIR)/create_test_customer.py --no-sources --bypass-api || echo "WARNING: create_test_customer failed unexpectedly!"

delete-test-sources:
	$(PYTHON) $(SCRIPTDIR)/delete_test_sources.py

delete-cost-models:
	$(PYTHON) $(SCRIPTDIR)/delete_cost_models.py

delete-test-customer-data: delete-test-sources delete-cost-models

test_source=all
load-test-customer-data:
	$(SCRIPTDIR)/load_test_customer_data.sh $(test_source) $(start) $(end)
	make load-aws-org-unit-tree

load-aws-org-unit-tree:
	@if [ $(shell $(PYTHON) -c 'import sys; print(sys.version_info[0])') = '3' ] ; then \
		$(PYTHON) $(SCRIPTDIR)/insert_org_tree.py tree_yml=$(tree_yml) schema=$(schema) nise_yml=$(nise_yml) start_date=$(start_date) ; \
	else \
		echo "This make target requires python3." ; \
	fi

run-api-test:
	$(PYTHON) $(SCRIPTDIR)/report_api_test.py || echo "WARNING: run-api-test failed unexpectedly!"

collect-static:
	$(DJANGO_MANAGE) collectstatic --no-input

make-migrations:
	$(DJANGO_MANAGE) makemigrations api reporting reporting_common cost_models

delete-db:
	$(PREFIX) rm -rf $(TOPDIR)/pg_data

delete-test-db:
	@PGPASSWORD=$$DATABASE_PASSWORD psql -h $$POSTGRES_SQL_SERVICE_HOST \
                                         -p $$POSTGRES_SQL_SERVICE_PORT \
                                         -d $$DATABASE_NAME \
                                         -U $$DATABASE_USER \
                                         -c "DROP DATABASE test_$$DATABASE_NAME;" >/dev/null
	@echo "Test DB (test_$$DATABASE_NAME) has been deleted."

reset-db-statistics:
	@PGPASSWORD=$$DATABASE_PASSWORD psql -h $$POSTGRES_SQL_SERVICE_HOST \
                                         -p $$POSTGRES_SQL_SERVICE_PORT \
                                         -d $$DATABASE_NAME \
                                         -U $$DATABASE_USER \
                                         -c "select pg_stat_statements_reset();" >/dev/null
	@echo "Statistics have been reset"

requirements:
	pipenv lock

run-migrations:
	scripts/run_migrations.sh $(applabel) $(migration)

serve:
	$(DJANGO_MANAGE) runserver

shell:
	$(DJANGO_MANAGE) shell

shell-schema: schema := org1234567
shell-schema:
	$(DJANGO_MANAGE) tenant_command shell --schema=$(schema)

unittest:
	$(DJANGO_MANAGE) test $(PYDIR) -v 2

superuser:
	$(DJANGO_MANAGE) createsuperuser

unleash-export:
	curl -X GET -H "Authorization: Basic YWRtaW46" \
	"http://localhost:4242/api/admin/state/export?format=json&featureToggles=1&strategies=0&tags=0&projects=0&download=1" \
	-s | python -m json.tool > .unleash/flags.json

unleash-import:
	curl -X POST -H "Content-Type: application/json" -H "Authorization: Basic YWRtaW46" \
	-s -d @.unleash/flags.json http://localhost:4242/api/admin/state/import

unleash-import-drop:
	curl -X POST -H "Content-Type: application/json" -H "Authorization: Basic YWRtaW46" \
	-s -d @.unleash/flags.json http://localhost:4242/api/admin/state/import?drop=true

scan_project:
	./sonarqube.sh

clowdapp: kustomize
	$(KUSTOMIZE) build deploy/kustomize > deploy/clowdapp.yaml

kustomize:
ifeq (, $(shell which kustomize))
	@{ \
	set -e ;\
	curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash;\
	mv kustomize $(TESTINGDIR);\
	}
KUSTOMIZE=$(TESTINGDIR)/kustomize
else
KUSTOMIZE=$(shell which kustomize)
endif

###############################
### Docker compose Commands ###
###############################

docker-down:
	$(DOCKER_COMPOSE) down -v --remove-orphans
	$(PREFIX) make delete-testing
	$(PREFIX) make delete-trino-data

docker-down-db:
	$(DOCKER_COMPOSE) rm -s -v -f unleash
	$(DOCKER_COMPOSE) rm -s -v -f db

docker-logs:
	$(DOCKER_COMPOSE) logs -f koku-server koku-worker masu-server

docker-trino-logs:
	$(DOCKER_COMPOSE) logs -f trino

docker-reinitdb: docker-down-db delete-db docker-up-db run-migrations docker-restart-koku create-test-customer-no-sources
	@echo "Local database re-initialized with a test customer."

docker-reinitdb-with-sources: docker-down-db delete-db docker-up-db run-migrations docker-restart-koku create-test-customer
	@echo "Local database re-initialized with a test customer and sources."

docker-reinitdb-with-sources-lite: docker-down-db delete-db docker-up-db run-migrations create-test-customer
	@echo "Local database re-initialized with a test customer and sources."

docker-shell:
	$(DOCKER_COMPOSE) run --service-ports koku-server

docker-restart-koku:
	@if [ -n "$$($(DOCKER) ps -q -f name=koku_server)" ] ; then \
         $(DOCKER_COMPOSE) restart koku-server masu-server koku-worker koku-beat koku-listener ; \
         make _koku-wait ; \
         echo " koku is available" ; \
     else \
         make docker-up-koku ; \
     fi

docker-up-koku:
	@if [ -z "$$($(DOCKER) ps -q -f name=koku_server)" ] ; then \
         echo "Starting koku_server ..." ; \
         $(DOCKER_COMPOSE) up $(build) -d koku-server ; \
         make _koku-wait ; \
     fi
	@echo " koku is available!"

_koku-wait:
	@echo "Waiting on koku status: "
	@until ./dev/scripts/check_for_koku_server.sh $${KOKU_API_HOST:-localhost} $${API_PATH_PREFIX:-/api/cost-management} $${KOKU_API_PORT:-8000} >/dev/null 2>&1 ; do \
         printf "." ; \
         sleep 1 ; \
     done

docker-build:
	$(DOCKER_COMPOSE) build koku-base

docker-up: docker-build
	$(DOCKER_COMPOSE) up -d --scale koku-worker=$(scale)

docker-up-no-build: docker-up-db
	$(DOCKER_COMPOSE) up -d --scale koku-worker=$(scale)

# basic dev environment targets
docker-up-min: docker-build docker-up-min-no-build

docker-up-min-no-build: docker-up-db
	$(DOCKER_COMPOSE) up -d --scale koku-worker=$(scale) redis koku-server masu-server koku-worker trino hive-metastore

# basic dev environment targets with koku-listener for local Sources Kafka testing
docker-up-min-with-listener: docker-up-min
	$(DOCKER_COMPOSE) up -d --scale koku-worker=$(scale) koku-listener

docker-up-min-no-build-with-listener: docker-up-min-no-build
	$(DOCKER_COMPOSE) up -d --scale koku-worker=$(scale) koku-listener

docker-up-db:
	$(DOCKER_COMPOSE) up -d db
	@until pg_isready -h $${POSTGRES_SQL_SERVICE_HOST:-localhost} -p $${POSTGRES_SQL_SERVICE_PORT:-15432} >/dev/null ; do \
	    printf '.'; \
	    sleep 0.5 ; \
    done
	@echo ' PostgreSQL is available!'
	$(DOCKER_COMPOSE) up -d unleash

docker-up-db-monitor:
	$(DOCKER_COMPOSE) up --build -d grafana
	@echo "Monitor is up at localhost:3001  User=admin  Password=admin12"

_set-test-dir-permissions:
	@$(PREFIX) chmod -R o+rw,g+rw ./testing
	@$(PREFIX) find ./testing -type d -exec chmod o+x,g+x {} \;

docker-iqe-local-hccm: docker-reinitdb _set-test-dir-permissions delete-testing
	./testing/run_local_hccm.sh $(iqe_cmd)

docker-iqe-smoke-tests: docker-reinitdb _set-test-dir-permissions delete-testing
	./testing/run_smoke_tests.sh

docker-iqe-smoke-tests-trino:
	./testing/run_smoke_tests.sh

docker-iqe-api-tests: docker-reinitdb _set-test-dir-permissions delete-testing
	./testing/run_api_tests.sh

docker-iqe-vortex-tests: docker-reinitdb _set-test-dir-permissions delete-testing
	./testing/run_vortex_api_tests.sh

docker-trino-setup: delete-trino
	mkdir -p -m a+rwx ./.trino
	@[[ ! -d ./.trino/parquet_data ]] && mkdir -p -m a+rwx ./.trino/parquet_data || chmod a+rwx ./.trino/parquet_data

docker-trino-up: docker-trino-setup
	$(DOCKER_COMPOSE) up --build -d trino hive-metastore

docker-trino-up-no-build: docker-trino-setup
	$(DOCKER_COMPOSE) up -d trino hive-metastore

docker-trino-ps:
	$(DOCKER_COMPOSE) ps trino hive-metastore

docker-trino-down:
	$(DOCKER_COMPOSE) down -v --remove-orphans
	make delete-trino

docker-trino-down-all: docker-trino-down docker-down

docker-up-min-trino: docker-up-min docker-trino-up

docker-up-min-trino-no-build: docker-up-min-no-build docker-trino-up-no-build


### Source targets ###
ocp-source-from-yaml:
#parameter validation
ifndef cluster_id
	$(error param cluster_id is not set)
endif
ifndef srf_yaml
	$(error param srf_yaml is not set)
endif
ifndef ocp_name
	$(error param ocp_name is not set)
endif
	(command -v nise > /dev/null 2>&1) || (echo 'nise is not installed, please install nise.' && exit 1 )
	mkdir -p testing/data/insights_local
	nise report ocp --ocp-cluster-id $(cluster_id) --insights-upload testing/data/insights_local --static-report-file $(srf_yaml)
	curl -d '{"name": "$(ocp_name)", "source_type": "OCP", "authentication": {"credentials": {"cluster_id": "$(cluster_id)"}}}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8000/api/cost-management/v1/sources/
# From here you can hit the http://127.0.0.1:5042/api/cost-management/v1/download/ endpoint to start running masu.
# After masu has run these endpoints should have data in them: (v1/reports/openshift/memory, v1/reports/openshift/compute/, v1/reports/openshift/volumes/)

aws-source:
ifndef aws_name
	$(error param aws_name is not set)
endif
ifndef bucket
	$(error param bucket is not set)
endif
	(printenv AWS_RESOURCE_NAME > /dev/null 2>&1) || (echo 'AWS_RESOURCE_NAME is not set in .env' && exit 1)
	curl -d '{"name": "$(aws_name)", "source_type": "AWS", "authentication": {"credentials": {"role_arn":"${AWS_RESOURCE_NAME}"}}, "billing_source": {"data_source": {"bucket": "$(bucket)"}}}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8000/api/cost-management/v1/sources/

gcp-source:
ifndef gcp_name
	$(error param gcp_name is not set)
endif
# Required environment variables are: [GCP_DATASET, GCP_TABLE_ID, GCP_PROJECT_ID]
	(printenv GCP_DATASET > /dev/null 2>&1) || (echo 'GCP_DATASET is not set in .env' && exit 1)
	(printenv GCP_TABLE_ID > /dev/null 2>&1) || (echo 'GCP_TABLE_ID is not set in .env' && exit 1)
	(printenv GCP_PROJECT_ID > /dev/null 2>&1) || (echo 'GCP_PROJECT_ID is not set in .env' && exit 1)
	curl -d '{"name": "$(gcp_name)", "source_type": "GCP", "authentication": {"credentials": {"project_id":"${GCP_PROJECT_ID}"}}, "billing_source": {"data_source": {"table_id": "${GCP_TABLE_ID}", "dataset": "${GCP_DATASET}"}}}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8000/api/cost-management/v1/sources/

oci-source:
ifndef oci_name
	$(error param oci_name is not set)
endif
ifndef bucket
	$(error param bucket is not set)
endif
ifndef namespace
	$(error param namespace is not set)
endif
ifndef region
	$(error param region is not set)
endif
# Required environment variables: [OCI_CLI_USER, OCI_CLI_KEY_FILE, OCI_CLI_FINGERPRINT, OCI_CLI_TENANCY]
	(printenv OCI_CLI_USER > /dev/null 2>&1) || (echo 'OCI_CLI_USER is not set in .env' && exit 1)
	(printenv OCI_CLI_KEY_FILE > /dev/null 2>&1) || (echo 'OCI_CLI_KEY_FILE is not set in .env' && exit 1)
	(printenv OCI_CLI_FINGERPRINT > /dev/null 2>&1) || (echo 'OCI_CLI_FINGERPRINT is not set in .env' && exit 1)
	(printenv OCI_CLI_TENANCY > /dev/null 2>&1) || (echo 'OCI_CLI_TENANCY is not set in .env' && exit 1)
	curl -d '{"name": "$(oci_name)", "source_type": "OCI", "authentication": {"credentials": []}, "billing_source": {"data_source": {"bucket": "$(bucket)", "bucket_namespace": "$(namespace)", "bucket_region": "$(region)"}}}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8000/api/cost-management/v1/sources/


###################################################
#  This section is for larger data volume testing
###################################################

create-large-ocp-source-config-file:
ifndef output_file_name
	$(error param output_file_name is not set)
endif
ifdef generator_template_file
	@nise yaml ocp -c $(or $(generator_config_file), default) -t $(generator_template_file) -o $(output_file_name) $(generator_flags)
else
	@nise yaml ocp -c $(or $(generator_config_file), default) -o $(output_file_name) $(generator_flags)
endif


create-large-ocp-source-testing-files:
ifndef nise_config_dir
	$(error param nise_config_dir is not set)
endif
	make purge-large-testing-ocp-files
	@for FILE in $(foreach f, $(wildcard $(nise_config_dir)/*.yml), $(f)) ; \
    do \
        make ocp-source-from-yaml cluster_id=large_ocp_1 srf_yaml=$$FILE ocp_name=large_ocp_1 ; \
	done

import-large-ocp-source-testing-costmodel:
	curl --header 'Content-Type: application/json' \
	     --request POST \
	     --data '{"name": "Cost Management OpenShift Cost Model", "description": "A cost model of on-premises OpenShift clusters.", "source_type": "OCP", "source_uuids": $(shell make -s find-large-testing-source-uuid), "rates": [{"metric": {"name": "cpu_core_usage_per_hour"}, "tiered_rates": [{"unit": "USD", "value": 0.007, "usage_start": null, "usage_end": null}]}, {"metric": {"name": "node_cost_per_month"}, "tiered_rates": [{"unit": "USD", "value": 0.2, "usage_start": null, "usage_end": null}]}, {"metric": {"name": "cpu_core_request_per_hour"}, "tiered_rates": [{"unit": "USD", "value": 0.2, "usage_start": null, "usage_end": null}]}, {"metric": {"name": "memory_gb_usage_per_hour"}, "tiered_rates": [{"unit": "USD", "value": 0.009, "usage_start": null, "usage_end": null}]}, {"metric": {"name": "memory_gb_request_per_hour"}, "tiered_rates": [{"unit": "USD", "value": 0.05, "usage_start": null, "usage_end": null}]}, {"metric": {"name": "storage_gb_usage_per_month"}, "tiered_rates": [{"unit": "USD", "value": 0.01, "usage_start": null, "usage_end": null}]}, {"metric": {"name": "storage_gb_request_per_month"}, "tiered_rates": [{"unit": "USD", "value": 0.01, "usage_start": null, "usage_end": null}]}]}' \
	     http://$(KOKU_SERVER):$(KOKU_SERVER_PORT)/api/cost-management/v1/cost-models/

import-large-ocp-source-testing-data:
	curl --request GET http://$(MASU_SERVER):$(MASU_SERVER_PORT)/api/cost-management/v1/download/

# Create a large volume of data for a test OCP source
# Will create the files, add the cost model and process the data
large-ocp-source-testing:
ifndef nise_config_dir
	$(error param nise_config_dir is not set)
endif
	make create-large-ocp-source-testing-files nise_config_dir="$(nise_config_dir)"
	make import-large-ocp-source-testing-costmodel
	make import-large-ocp-source-testing-data

# Delete the testing large ocp source local files
purge-large-testing-ocp-files:
	rm -rf $(OCP_PROVIDER_TEMP_DIR)/large_ocp_1

# Delete *ALL* local testing files
purge-all-testing-ocp-files:
	rm -rf $(OCP_PROVIDER_TEMP_DIR)/*

# currently locked to the large ocp source
find-large-testing-source-uuid:
	@curl "http://$(KOKU_SERVER):$(KOKU_SERVER_PORT)/api/cost-management/v1/sources/?name=large_ocp_1" | python3 -c "import sys, json; data_list=json.load(sys.stdin)['data']; print([data['uuid'] for data in data_list if data['type']=='OCP']);" | tr "'" '"'


# Dump local database
dump-local-db:
ifndef dump_outfile
	$(error param dump_outfile not set)
endif
	@if [ ! -x "$(shell which pg_dump)" ]; then \
        echo "ERROR :: Cannot find 'pg_dump' program" >&2 ; \
        false ; \
    else \
	    PGPASSWORD=$$DATABASE_PASSWORD pg_dump -h $$POSTGRES_SQL_SERVICE_HOST \
                                               -p $$POSTGRES_SQL_SERVICE_PORT \
                                               -d $$DATABASE_NAME \
                                               -U $$DATABASE_USER \
                                               --clean --if-exists --verbose \
                                               --file=$(dump_outfile) ; \
    fi


# Restore local database
load-local-db:
ifndef dump_outfile
	$(error param dump_outfile not set)
endif
	@if [ ! -x "$(shell which psql)" ]; then \
	    echo "ERROR :: Cannot find 'psql' program" >&2 ; \
		false ; \
	else \
	    PGPASSWORD=$$DATABASE_PASSWORD psql -h $$POSTGRES_SQL_SERVICE_HOST \
                                            -p $$POSTGRES_SQL_SERVICE_PORT \
                                            -d $$DATABASE_NAME \
                                            -U $$DATABASE_USER \
                                            --file=$(dump_outfile) ; \
	fi


backup-local-db-dir:
	$(DOCKER_COMPOSE) stop db
	@cd $(TOPDIR)
	@echo "Copying pg_data to pg_data.bak..."
	@$(PREFIX) cp -rp ./pg_data ./pg_data.bak
	@cd - >/dev/null
	$(DOCKER_COMPOSE) start db

local-upload-data:
	curl -vvvv -F "upload=@$(file);type=application/vnd.redhat.hccm.$(basename $(basename $(notdir $(file))))+tgz" \
		-H "x-rh-identity: eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzNDUiLCAiaW50ZXJuYWwiOiB7Im9yZ19pZCI6ICI1NDMyMSJ9fX0=" \
		-H "x-rh-request_id: testtesttest" \
		localhost:8080/api/ingress/v1/upload


restore-local-db-dir:
	@cd $(TOPDIR)
	@if [ -d ./pg_data.bak ] ; then \
	    $(DOCKER_COMPOSE) stop db ; \
	    echo "Removing pg_data..." ; \
	    $(PREFIX) rm -rf ./pg_data ; \
	    echo "Renaming pg_data.bak to pg_data..." ; \
	    $(PREFIX) mv -f ./pg_data.bak ./pg_data ; \
	    $(DOCKER_COMPOSE) start db ; \
	    echo "NOTE :: Migrations may need to be run." ; \
	else \
	    echo "NOTE :: There is no pg_data.bak dir to restore from." ; \
	fi
	@cd - >/dev/null


get-release-commit:
	@$(PYTHON) $(SCRIPTDIR)/get-release-commit.py
