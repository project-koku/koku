#
# Copyright 2018 Red Hat, Inc.
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
"""Models for identity and access management."""
import logging
import os
from uuid import uuid4

from django.db import models
from django.db import transaction
from tenant_schemas.models import TenantMixin
from tenant_schemas.postgresql_backend.base import _check_schema_name
from tenant_schemas.utils import schema_exists


LOG = logging.getLogger(__name__)


class CloneSchemaError(Exception):
    pass


class Customer(models.Model):
    """A Koku Customer.

    A customer is an organization of N-number of users

    """

    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True, null=False)
    account_id = models.CharField(max_length=150, blank=False, null=True, unique=True)
    schema_name = models.TextField(unique=True, null=False, default="public")

    class Meta:
        ordering = ["schema_name"]


class User(models.Model):
    """A Koku User."""

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True, null=False)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, null=True)
    customer = models.ForeignKey("Customer", null=True, on_delete=models.CASCADE)

    def __init__(self, *args, **kwargs):
        """Initialize non-persisted user properties."""
        super().__init__(*args, **kwargs)
        self.admin = False
        self.access = {}
        self.identity_header = None

    class Meta:
        ordering = ["username"]


class Tenant(TenantMixin):
    """The model used to create a tenant schema."""

    _TEMPLATE_SCHEMA = os.environ.get("TEMPLATE_SCHEMA", "template0")

    # Override the mixin domain url to make it nullable, non-unique
    domain_url = None

    # Delete all schemas when a tenant is removed
    auto_drop_schema = True

    def _check_clone_func(self):
        func_sig = (
            "public.clone_schema(source_schema text, dest_schema text, "
            "copy_data boolean DEFAULT false, "
            "_verbose boolean DEFAULT false)"
        )
        sql = """
select pronamespace::regnamespace::text || '.' || proname || '(' || pg_get_function_arguments(oid) || ')'
  from pg_proc
 where pronamespace = 'public'::regnamespace
   and proname = 'clone_schema';
"""
        conn = transaction.get_connection()
        cur = conn.cursor()
        cur.execute(sql)
        result = cur.fetchone()
        cur.close()
        if (not result) or (result[0] != func_sig):
            raise CloneSchemaError('Database Function "public.clone_schema" not found')

    def _verify_template(self, verbosity=1):
        LOG.info(f'Verify that template schema "{self._TEMPLATE_SCHEMA}" exists')
        _schema = self.schema_name
        self.schema_name = self._TEMPLATE_SCHEMA
        ret = super().create_schema(check_if_exists=True, sync_schema=True, verbosity=verbosity)
        self.schema_name = _schema
        return ret

    def create_schema(self, check_if_exists=True, sync_schema=True, verbosity=1):
        if self.schema_name == "public":
            LOG.info("Using superclass for public schema creation")
            return super().create_schema(check_if_exists=True, sync_schema=sync_schema, verbosity=verbosity)

        # Verify name structure
        _check_schema_name(self.schema_name)

        # Make sure all of our special pieces are in play
        self._check_clone_func()
        ret = self._verify_template(verbosity=verbosity)
        if self.schema_name == self._TEMPLATE_SCHEMA:
            return ret

        # ignoring check_if_exists flag -- ALWAYS CHECK!
        if schema_exists(self.schema_name):
            return False

        # Clone the schema
        conn = transaction.get_connection()
        with transaction.atomic():
            cur = conn.cursor()

            # This db func will clone the schema objects
            # bypassing the time it takes to run migrations
            sql = """
select public.clone_schema(%s, %s, copy_data => true) as "clone_result";
"""
            LOG.info(f"Cloning template schema {self._TEMPLATE_SCHEMA} to {self.schema_name} with data")
            cur.execute(sql, [self._TEMPLATE_SCHEMA, self.schema_name])
            result = cur.fetchone()
            cur.close()

            result = result[0] if result else False
            if not result:
                # Error creating schema
                conn.rollback()
                LOG.error(f"Error cloning template schema {self._TEMPLATE_SCHEMA}")
                raise CloneSchemaError(f'Schema "{self.schema_name} creation has failed! Check DB logs!')
            else:
                LOG.info(f"Successful clone of {self._TEMPLATE_SCHEMA} to {self.schema_name}")

            conn.set_schema_to_public()

        return result
