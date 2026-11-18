#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
# flake8: noqa
"""Koku Test Runner."""
import datetime
import logging
import os
import re
import sys

import psycopg2
from dev.scripts.insert_org_tree import UploadAwsTree
from django.conf import settings
from django.db import connections
from django.test.runner import DiscoverRunner
from django.test.runner import ParallelTestSuite
from django.test.utils import get_unique_databases_and_mirrors
from psycopg2 import sql as psycopg2_sql

from api.models import Customer
from api.models import Provider
from api.models import Tenant
from api.report.test.util.model_bakery_loader import ModelBakeryDataLoader
from koku.env import ENVIRONMENT
from koku.parallel_test_worker import init_worker as _koku_parallel_init_worker


OCP_ON_AWS_CLUSTER_ID = "OCP-on-AWS"
OCP_ON_AZURE_CLUSTER_ID = "OCP-on-Azure"
OCP_ON_GCP_CLUSTER_ID = "OCP-on-GCP"
OCP_ON_PREM_CLUSTER_ID = "OCP-on-Prem"

GITHUB_ACTIONS = ENVIRONMENT.bool("GITHUB_ACTIONS", default=False)
LOG = logging.getLogger(__name__)

if GITHUB_ACTIONS:
    sys.stdout = open(os.devnull, "w")


class KokuParallelTestSuite(ParallelTestSuite):
    """Parallel test suite with per-worker Masu temp directories."""

    init_worker = _koku_parallel_init_worker


class KokuTestRunner(DiscoverRunner):
    """Koku Test Runner for Unit Tests."""

    parallel_test_suite = KokuParallelTestSuite

    account = "10001"
    org_id = "1234567"
    schema = f"org{org_id}"
    settings.HOSTNAME = "koku-worker-10-abcdef"

    def setup_databases(self, **kwargs):
        """Set up database tenant schema."""
        self.keepdb = settings.KEEPDB
        return setup_databases(self.verbosity, self.interactive, self.keepdb, self.debug_sql, self.parallel, **kwargs)


def fixture_data_is_stale(newest_report_period_start, today):
    """Return True if kept fixture data predates the current month.

    The fixture loader creates last month and the current month, dated relative to the day the test
    DB is built, and only when it is built. A kept DB (KEEPDB) built in an earlier month lacks the
    current month, and every test that expects it fails. No report period at all also means stale.
    """
    if newest_report_period_start is None:
        return True
    return newest_report_period_start < today.replace(day=1)


def _connect(connection, dbname):
    """Connect to dbname with the parameters Django uses for this alias (TLS options included)."""
    params = connection.get_connection_params()
    params["dbname"] = dbname
    return psycopg2.connect(**params)


def fixture_state(connection, dbname, schema):
    """Return (db_exists, newest OCP report period start as a UTC date or None) of a test DB.

    (False, None) when the DB does not exist yet; Django and setup_databases create it.
    (True, None) when it exists without fixture data: no fixture table or an empty one, e.g. after
    an earlier setup failed halfway. Django keeps an existing DB under KEEPDB and setup skips
    loading for an existing tenant, so such a DB must be rebuilt.
    """
    try:
        test_db = _connect(connection, dbname)
    except psycopg2.OperationalError as error:
        LOG.info(f"No kept test DB {dbname} to check for stale fixture data: {error}")
        return False, None
    try:
        with test_db.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s)", [f"{schema}.reporting_ocpusagereportperiod"])
            if cursor.fetchone()[0] is None:
                return True, None
            cursor.execute(
                f"SELECT max(report_period_start AT TIME ZONE 'UTC')::date FROM {schema}.reporting_ocpusagereportperiod"
            )
            return True, cursor.fetchone()[0]
    finally:
        test_db.close()


def drop_stale_clones(connection, test_db_name, schema, today, drop_all):
    """Drop the parallel test DB clones (<test DB>_<n>) that are stale or incomplete, or all of them.

    Under KEEPDB, Django reuses existing clones and recreates missing ones from the primary test DB,
    so a dropped clone comes back as a fresh copy on the next parallel run. drop_all is set when the
    primary test DB is being rebuilt; otherwise each clone is checked like the primary.
    """
    maintenance = _connect(connection, connection.settings_dict["NAME"])
    maintenance.autocommit = True
    try:
        with maintenance.cursor() as cursor:
            cursor.execute(
                "SELECT datname FROM pg_database WHERE datname ~ %s ORDER BY datname",
                [f"^{re.escape(test_db_name)}_[0-9]+$"],
            )
            for (clone,) in cursor.fetchall():
                if not drop_all:
                    _, newest = fixture_state(connection, clone, schema)
                    if not fixture_data_is_stale(newest, today):
                        continue
                print(f"Dropping stale parallel test DB clone {clone}.", file=sys.stderr)
                cursor.execute(psycopg2_sql.SQL("DROP DATABASE {}").format(psycopg2_sql.Identifier(clone)))
    finally:
        maintenance.close()


def check_kept_test_dbs(keepdb, today):
    """Decide whether a kept test DB is reused; drop stale parallel clones.

    Returns (keepdb, stale_rebuild): keepdb becomes False when the kept primary test DB has stale or
    missing fixture data, and stale_rebuild tells setup_databases to rebuild it without prompting.
    """
    if not keepdb:
        return keepdb, False
    default = connections["default"]
    test_db_name = default.creation._get_test_db_name()
    db_exists, newest = fixture_state(default, test_db_name, KokuTestRunner.schema)
    stale_rebuild = db_exists and fixture_data_is_stale(newest, today)
    if stale_rebuild:
        print(
            f"Kept test DB is stale (newest fixture report period {newest or 'none'}, current month "
            f"{today:%Y-%m}): recreating it and its fixture data.",
            file=sys.stderr,
        )
    drop_stale_clones(default, test_db_name, KokuTestRunner.schema, today, drop_all=stale_rebuild)
    return not stale_rebuild, stale_rebuild


def setup_databases(verbosity, interactive, keepdb=False, debug_sql=False, parallel=0, aliases=None, **kwargs):
    """Create the test databases.

    This function is a copy of the Django setup_databases with one addition.
    A Tenant object is created and saved when setting up the database.
    A kept test DB whose fixture data predates the current month (or is missing) is recreated,
    and stale parallel clones are dropped.
    """
    test_databases, mirrored_aliases = get_unique_databases_and_mirrors(aliases)

    keepdb, stale_rebuild = check_kept_test_dbs(keepdb, datetime.datetime.now(datetime.timezone.utc).date())

    old_names = []

    for db_name, aliases in test_databases.values():
        first_alias = None
        for alias in aliases:
            connection = connections[alias]
            old_names.append((connection, db_name, first_alias is None))

            # Actually create the database for the first connection
            if first_alias is None:
                first_alias = alias
                test_db_name = connection.creation.create_test_db(
                    verbosity=verbosity,
                    # A stale kept DB is rebuilt without asking; other rebuilds keep Django's prompt.
                    autoclobber=not interactive or stale_rebuild,
                    keepdb=keepdb,
                    serialize=connection.settings_dict.get("TEST", {}).get("SERIALIZE", True),
                )

                try:
                    tenant, created = Tenant.objects.get_or_create(schema_name=Tenant._TEMPLATE_SCHEMA)
                    if created:
                        tenant.save()
                        tenant.create_schema()
                    tenant, created = Tenant.objects.get_or_create(schema_name=KokuTestRunner.schema)
                    if created:
                        tenant.save()
                        tenant.create_schema()
                        customer, __ = Customer.objects.get_or_create(
                            account_id=KokuTestRunner.account,
                            org_id=KokuTestRunner.org_id,
                            schema_name=KokuTestRunner.schema,
                        )
                        ##############################################################
                        # Obtain the day_list from yaml
                        read_yaml = UploadAwsTree(None, None, None, None)
                        tree_yaml = read_yaml.import_yaml(yaml_file_path="dev/scripts/aws_org_tree.yml")
                        day_list = tree_yaml["account_structure"]["days"]
                        bakery_data_loader = ModelBakeryDataLoader(KokuTestRunner.schema, customer)

                        ocp_on_aws_ocp_provider, ocp_on_aws_report_periods = bakery_data_loader.load_openshift_data(
                            OCP_ON_AWS_CLUSTER_ID, on_cloud=True
                        )

                        (
                            ocp_on_azure_ocp_provider,
                            ocp_on_azure_report_periods,
                        ) = bakery_data_loader.load_openshift_data(OCP_ON_AZURE_CLUSTER_ID, on_cloud=True)

                        ocp_on_gcp_ocp_provider, ocp_on_gcp_report_periods = bakery_data_loader.load_openshift_data(
                            OCP_ON_GCP_CLUSTER_ID, on_cloud=True
                        )

                        bakery_data_loader.load_openshift_data(OCP_ON_PREM_CLUSTER_ID, on_cloud=False)

                        aws_bills = bakery_data_loader.load_aws_data(
                            linked_openshift_provider=ocp_on_aws_ocp_provider, day_list=day_list
                        )

                        azure_bills = bakery_data_loader.load_azure_data(
                            linked_openshift_provider=ocp_on_azure_ocp_provider
                        )
                        gcp_bills = bakery_data_loader.load_gcp_data(linked_openshift_provider=ocp_on_gcp_ocp_provider)

                        bakery_data_loader.load_openshift_on_cloud_data(
                            Provider.PROVIDER_AWS_LOCAL, OCP_ON_AWS_CLUSTER_ID, aws_bills, ocp_on_aws_report_periods
                        )
                        bakery_data_loader.load_openshift_on_cloud_data(
                            Provider.PROVIDER_AZURE_LOCAL,
                            OCP_ON_AZURE_CLUSTER_ID,
                            azure_bills,
                            ocp_on_azure_report_periods,
                        )
                        bakery_data_loader.load_openshift_on_cloud_data(
                            Provider.PROVIDER_GCP_LOCAL, OCP_ON_GCP_CLUSTER_ID, gcp_bills, ocp_on_gcp_report_periods
                        )

                        for account in [("10002", "org2222222", "2222222"), ("12345", "org3333333", "3333333")]:
                            tenant = Tenant.objects.get_or_create(schema_name=account[1])[0]
                            tenant.save()
                            tenant.create_schema()
                            Customer.objects.get_or_create(
                                account_id=account[0], org_id=account[2], schema_name=account[1]
                            )
                except Exception as err:
                    LOG.error(err)
                    raise err

                if parallel > 1:
                    for index in range(parallel):
                        connection.creation.clone_test_db(suffix=str(index + 1), verbosity=verbosity, keepdb=keepdb)
            else:
                connection.creation.set_as_test_mirror(connections[first_alias].settings_dict)

    # Configure the test mirrors.
    for alias, mirror_alias in mirrored_aliases.items():
        connections[alias].creation.set_as_test_mirror(connections[mirror_alias].settings_dict)

    if debug_sql:
        for alias in connections:
            connections[alias].force_debug_cursor = True

    return old_names
