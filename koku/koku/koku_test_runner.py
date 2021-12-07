#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
# flake8: noqa
"""Koku Test Runner."""
import logging
import os
import sys

from django.conf import settings
from django.db import connections
from django.test.runner import DiscoverRunner
from django.test.utils import get_unique_databases_and_mirrors
from scripts.insert_org_tree import UploadAwsTree
from tenant_schemas.utils import tenant_context

from api.models import Customer
from api.models import Tenant
from api.report.test.utils import NiseDataLoader
from koku.env import ENVIRONMENT
from reporting.models import OCPEnabledTagKeys

GITHUB_ACTIONS = ENVIRONMENT.bool("GITHUB_ACTIONS", default=False)
LOG = logging.getLogger(__name__)
OCP_ENABLED_TAGS = ["app", "storageclass", "environment", "version"]

if GITHUB_ACTIONS:
    sys.stdout = open(os.devnull, "w")


class KokuTestRunner(DiscoverRunner):
    """Koku Test Runner for Unit Tests."""

    account = "10001"
    schema = f"acct{account}"
    settings.HOSTNAME = "koku-worker-10-abcdef"

    def setup_databases(self, **kwargs):
        """Set up database tenant schema."""
        self.keepdb = settings.KEEPDB
        main_db = setup_databases(
            self.verbosity, self.interactive, self.keepdb, self.debug_sql, self.parallel, **kwargs
        )

        return main_db


def setup_databases(verbosity, interactive, keepdb=False, debug_sql=False, parallel=0, aliases=None, **kwargs):
    """Create the test databases.

    This function is a copy of the Django setup_databases with one addition.
    A Tenant object is created and saved when setting up the database.
    """
    test_databases, mirrored_aliases = get_unique_databases_and_mirrors(aliases)

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
                    autoclobber=not interactive,
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
                            account_id=KokuTestRunner.account, schema_name=KokuTestRunner.schema
                        )
                        with tenant_context(tenant):
                            for tag_key in OCP_ENABLED_TAGS:
                                OCPEnabledTagKeys.objects.get_or_create(key=tag_key)
                        data_loader = NiseDataLoader(KokuTestRunner.schema)
                        # Obtain the day_list from yaml
                        read_yaml = UploadAwsTree(None, None, None, None)
                        tree_yaml = read_yaml.import_yaml(yaml_file_path="scripts/aws_org_tree.yml")
                        day_list = tree_yaml["account_structure"]["days"]
                        # Load data
                        data_loader = NiseDataLoader(KokuTestRunner.schema)
                        data_loader.load_openshift_data(customer, "ocp_aws_static_data.yml", "OCP-on-AWS")
                        data_loader.load_aws_data(customer, "aws_static_data.yml", day_list=day_list)
                        data_loader.load_openshift_data(customer, "ocp_azure_static_data.yml", "OCP-on-Azure")
                        data_loader.load_azure_data(customer, "azure_static_data.yml")
                        data_loader.load_gcp_data(customer, "gcp_static_data.yml")
                        for account in [("10002", "acct10002"), ("12345", "acct12345")]:
                            tenant = Tenant.objects.get_or_create(schema_name=account[1])[0]
                            tenant.save()
                            tenant.create_schema()
                            Customer.objects.get_or_create(account_id=account[0], schema_name=account[1])
                except Exception as err:
                    LOG.error(err)
                    raise err

                if parallel > 1:
                    for index in range(parallel):
                        connection.creation.clone_test_db(suffix=str(index + 1), verbosity=verbosity, keepdb=keepdb)
            # Configure all other connections as mirrors of the first one
            else:
                connections[alias].creation.set_as_test_mirror(connections[first_alias].settings_dict)

    # Configure the test mirrors.
    for alias, mirror_alias in mirrored_aliases.items():
        connections[alias].creation.set_as_test_mirror(connections[mirror_alias].settings_dict)

    if debug_sql:
        for alias in connections:
            connections[alias].force_debug_cursor = True

    return old_names
