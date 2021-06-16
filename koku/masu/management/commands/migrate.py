#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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
