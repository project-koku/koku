#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""command overrides."""
import logging

from tenant_schemas.management.commands import migrate_schemas
from tenant_schemas.migration_executors import get_executor
from tenant_schemas.utils import get_public_schema_name
from tenant_schemas.utils import get_tenant_model

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
                tenants = (
                    get_tenant_model()
                    .objects.exclude(schema_name=get_public_schema_name())
                    .values_list("schema_name", flat=True)
                )
                tenants = [tenant for tenant in tenants if schema_exists(tenant[0])]
            executor.run_migrations(tenants=tenants)
