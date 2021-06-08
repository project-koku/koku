#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""command overrides."""
import logging

from tenant_schemas.management.commands import migrate_schemas
from tenant_schemas.migration_executors import get_executor
from tenant_schemas.utils import get_public_schema_name
from tenant_schemas.utils import get_tenant_model
from tenant_schemas.utils import schema_exists

LOG = logging.getLogger(__name__)


class Command(migrate_schemas.Command):
    """Override the migrate_schemas command from django-tenant-schemas.
    This override is here to workaround a dead upstream.
    This enables django-tenant_schemas to work with Django 3.1.x
    """

    requires_system_checks = []

    def handle(self, *args, **options):
        super(migrate_schemas.Command, self).handle(*args, **options)
        self.PUBLIC_SCHEMA_NAME = get_public_schema_name()

        executor = get_executor(codename=self.executor)(self.args, self.options)

        if self.sync_public and not self.schema_name:
            self.schema_name = self.PUBLIC_SCHEMA_NAME

        if self.sync_public:
            executor.run_migrations(tenants=[self.schema_name])
        if self.sync_tenant:
            if self.schema_name and self.schema_name != self.PUBLIC_SCHEMA_NAME:
                if not schema_exists(self.schema_name):
                    msg = f"Schema {self.schema_name} does not exist, skipping."
                    LOG.info(msg)
                else:
                    tenants = [self.schema_name]
            else:
                from django.db.models.expressions import RawSQL

                tenant_model = get_tenant_model()
                tenants = list(
                    tenant_model.objects.filter(
                        schema_name__in=RawSQL(
                            """
                                SELECT nspname::text
                                FROM pg_catalog.pg_namespace
                                WHERE nspname = %s
                                    OR nspname ~ '^acct'
                            """,
                            (tenant_model._TEMPLATE_SCHEMA,),
                        )
                    ).values_list("schema_name", flat=True)
                )
            executor.run_migrations(tenants=tenants)
