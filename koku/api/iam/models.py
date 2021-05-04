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
import json
import logging
import os
import pkgutil
from uuid import uuid4

from django.conf import settings
from django.db import connection as conn
from django.db import models
from tenant_schemas.models import TenantMixin
from tenant_schemas.signals import post_schema_sync
from tenant_schemas.utils import schema_exists

from koku.database import dbfunc_not_exists
from koku.migration_sql_helpers import apply_sql_file
from koku.migration_sql_helpers import find_db_functions_dir


LOG = logging.getLogger(__name__)


class CloneSchemaError(Exception):
    pass


class CloneSchemaFuncMissing(CloneSchemaError):
    pass


class CloneSchemaTemplateMissing(CloneSchemaError):
    pass


TENANT_SUPPORT = {}


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
        self.beta = False

    class Meta:
        ordering = ["username"]


class Tenant(TenantMixin):
    """The model used to create a tenant schema."""

    # Sometimes the Tenant model can seemingly return funky results,
    # so the template schema name is going to get more inline with the
    # customer account schema names
    _TEMPLATE_SCHEMA = getattr(settings, "TEMPLATE_SCHEMA", os.environ.get("TEMPLATE_SCHEMA", "template0"))
    _READ_SCHEMA_FUNC_FILENAME = os.path.join(find_db_functions_dir(), "read_schema.sql")
    _READ_SCHEMA_FUNC_SCHEMA = "public"
    _READ_SCHEMA_FUNC_NAME = "read_schema"
    _READ_SCHEMA_FUNC_SIG = (
        f"{_READ_SCHEMA_FUNC_SCHEMA}.{_READ_SCHEMA_FUNC_NAME}("
        "source_schema text, "
        "_verbose boolean DEFAULT false"
        ")"
    )
    _CREATE_SCHEMA_FUNC_FILENAME = os.path.join(find_db_functions_dir(), "create_schema.sql")
    _CREATE_SCHEMA_FUNC_SCHEMA = "public"
    _CREATE_SCHEMA_FUNC_NAME = "create_schema"
    _CREATE_SCHEMA_FUNC_SIG = (
        f"{_CREATE_SCHEMA_FUNC_SCHEMA}.{_CREATE_SCHEMA_FUNC_NAME}("
        "source_schema text, source_structure jsonb, "
        "new_schemata text[], "
        "copy_data boolean DEFAULT false, "
        "_verbose boolean DEFAULT false"
        ")"
    )

    _TEMPLATE_SOURCE_CATALOG = 0
    _TEMPLATE_SOURCE_FILE = 1

    # Override the mixin domain url to make it nullable, non-unique
    domain_url = None

    # Delete all schemas when a tenant is removed
    auto_drop_schema = True
    # auto_create_schema = False
    auto_create_schema = bool(settings.DEVELOPMENT)

    template_schema_source = _TEMPLATE_SOURCE_FILE

    def __repr__(self):
        return f'<Tenant("{self.schema_name}")>'

    def _check_clone_func(self):
        clone_func_state = TENANT_SUPPORT.get("clone_func_state")
        if clone_func_state is None:
            LOG.info("Checking state of functions from the DB")
            func_map = {
                self._READ_SCHEMA_FUNC_SCHEMA: {
                    self._READ_SCHEMA_FUNC_NAME: self._READ_SCHEMA_FUNC_SIG,
                    self._CREATE_SCHEMA_FUNC_NAME: self._CREATE_SCHEMA_FUNC_SIG,
                }
            }
            func_file_map = {
                self._READ_SCHEMA_FUNC_NAME: self._READ_SCHEMA_FUNC_FILENAME,
                self._CREATE_SCHEMA_FUNC_NAME: self._CREATE_SCHEMA_FUNC_FILENAME,
            }
            clone_func_state = dbfunc_not_exists(conn, func_map)
            if clone_func_state:
                missing_functions = [f"{s}.{f}" for s in clone_func_state for f in clone_func_state[s]]
                LOG.warning(f"Clone functions {', '.join(missing_functions)} are missing.")
                for schema in list(clone_func_state):
                    conn.cursor().execute(f"set search_path = {schema}, public;")
                    for func_name in list(clone_func_state[schema]):
                        LOG.info(f"Appliying clone function {func_name} to database.")
                        apply_sql_file(conn.schema_editor(), func_file_map[func_name], literal_placeholder=True)
                        del clone_func_state[schema][func_name]
                    del clone_func_state[schema]

            clone_func_state = not bool(clone_func_state)
            TENANT_SUPPORT["clone_func_state"] = clone_func_state

        LOG.info(f"{'Clone functions exist' if clone_func_state else 'Clone functions DO NOT EXIST'}")

        return clone_func_state

    def _verify_template(self):
        LOG.info(f'Verify that template schema "{self._TEMPLATE_SCHEMA}" exists')

        tenant_state = TENANT_SUPPORT.get("tenant_state", None)
        if tenant_state is None:
            LOG.info("Checking template state from the DB")
            # This is using the teanant table data as the source of truth which can be dangerous.
            # If this becomes unreliable, then the database itself should be the source of truth
            # and extra code must be written to handle the sync of the table data to the state of
            # the database.
            template_schema = self.__class__.objects.get_or_create(schema_name=self._TEMPLATE_SCHEMA)

            # Strict check here! Both the record and the schema *should* exist!
            tenant_state = bool(template_schema) and schema_exists(self._TEMPLATE_SCHEMA)
            TENANT_SUPPORT["tenant_state"] = tenant_state

        LOG.info(f"{'Template exists' if tenant_state else 'Template does not exist!'}")

        return tenant_state

    def _clone_schema_from_catalog(self):
        template_info = TENANT_SUPPORT.get("template_info", None)
        if template_info is None:
            LOG.info(f'Reading teamplate "{self._TEMPLATE_SCHEMA}" info from the DB')
            with conn.cursor() as cur:
                cur.execute("select public.read_schema(%s)", (self._TEMPLATE_SCHEMA,))
                template_info = cur.fetchone()

            if isinstance(template_info, dict):
                template_info = json.dumps(template_info)

            TENANT_SUPPORT["template_info"] = template_info
        else:
            LOG.info(f'Using cached template "{self._TEMPLATE_SCHEMA}" info')

        result = None
        # This db func will clone the schema objects
        # bypassing the time it takes to run migrations
        sql = """
select public.create_schema(%s::text, %s::jsonb, %s::text[], copy_data => true) as "clone_result";
"""
        LOG.info(f'Cloning template schema "{self._TEMPLATE_SCHEMA}" to "{self.schema_name}"')

        with conn.cursor() as cur:
            cur.execute(sql, (self._TEMPLATE_SCHEMA, template_info, [self.schema_name]))
            result = cur.fetchone()
            cur.execute("SET search_path = public;")

        result = result[0]
        created = [f'"{s[1:]}"' for s in result if s.startswith("+")] or ["none"]
        existing = [f'"{s[1:]}"' for s in result if s.startswith("!")] or ["none"]

        LOG.info(f"Schema create function created {', '.join(created)}")
        LOG.info(f"Schema create function skipped {', '.join(existing)}")

        return result[0] if result else False

    def _clone_schema_from_file(self):
        LOG.info("Loading create script from koku_tenant_create.sql file.")
        create_sql_buff = pkgutil.get_data("api.iam", "sql/koku_tenant_create.sql").decode("utf-8")
        LOG.info(f'Cloning template schema "{self._TEMPLATE_SCHEMA}" to "{self.schema_name}"')
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema_name}" AUTHORIZATION current_user ;')
            cur.execute(f'SET search_path = "{self.schema_name}", public ;')
            cur.execute(create_sql_buff)
            cur.execute("SET search_path = public ;")
        return True

    def _clone_schema(self):
        if self.template_schema_source == self._TEMPLATE_SOURCE_FILE:
            res = self._clone_schema_from_file()
        else:
            # Make sure all of our special pieces are in play
            ret = self._check_clone_func()
            if not ret:
                errmsg = "Missing clone_schema function even after re-applying the function SQL file."
                LOG.critical(errmsg)
                raise CloneSchemaFuncMissing(errmsg)

            ret = self._verify_template()
            if not ret:
                errmsg = f'Template schema "{self._TEMPLATE_SCHEMA}" does not exist'
                LOG.critical(errmsg)
                raise CloneSchemaTemplateMissing(errmsg)

            res = self._clone_schema_from_catalog()

        return res

    def create_schema(self, check_if_exists=True, **kwargs):
        """
        If schema is "public" or matches _TEMPLATE_SCHEMA, then use the superclass' create_schema() method.
        Else, verify the template and inputs and use the database clone function.
        """
        if self.schema_name in ("public", self._TEMPLATE_SCHEMA):
            LOG.info(f'Using superclass for "{self.schema_name}" schema creation')
            return super().create_schema(check_if_exists=True, **kwargs)

        if check_if_exists:
            # Check to see if the schema exists!
            LOG.info(f"Check if target schema {self.schema_name} already exists")
            if schema_exists(self.schema_name):
                LOG.warning(f'Schema "{self.schema_name}" already exists. Exit with False.')
                return False

        # Clone the schema. The database function will check
        # that the source schema exists and the destination schema does not.
        try:
            self._clone_schema()
        except Exception as dbe:
            LOG.error(
                f"""Exception {dbe.__class__.__name__} cloning"""
                + f""" "{self._TEMPLATE_SCHEMA}" to "{self.schema_name}": {str(dbe)}"""
            )
            raise dbe
        else:
            LOG.info(f'Successful clone of "{self._TEMPLATE_SCHEMA}" to "{self.schema_name}"')
            post_schema_sync.send(sender=TenantMixin, tenant=self)

        conn.set_schema_to_public()

        return True
