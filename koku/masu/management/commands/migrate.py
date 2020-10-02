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
from tenant_schemas.management.commands import migrate
from tenant_schemas.utils import django_is_in_test_mode

from .migrate_schemas import Command as MigrateSchemasCommand


class Command(migrate.Command):
    """Override the migrate command from django-tenant-schemas.

    This override is here to workaround a dead upstream.
    This enables django-tenant_schemas to work with Django 3.1.x
    """

    requires_system_checks = []


if django_is_in_test_mode():
    Command = MigrateSchemasCommand  # noqa: F811
