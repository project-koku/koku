#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for identity and access management."""
import logging
import os
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import connection as conn
from django.db import models
from django.db import transaction
from django_tenants.models import DomainMixin
from django_tenants.models import TenantMixin
from django_tenants.postgresql_backend.base import is_valid_schema_name
from django_tenants.utils import schema_exists

from koku.database import dbfunc_exists
from koku.migration_sql_helpers import apply_sql_file
from koku.migration_sql_helpers import find_db_functions_dir

LOG = logging.getLogger(__name__)


class CloneSchemaError(Exception):
    pass


class CloneSchemaFuncMissing(CloneSchemaError):
    pass


class CloneSchemaTemplateMissing(CloneSchemaError):
    pass


class Customer(models.Model):
    """A Koku Customer.

    A customer is an organization of N-number of users

    """

    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True, null=False)
    account_id = models.CharField(max_length=150, blank=False, null=True, unique=True)
    org_id = models.CharField(max_length=36, blank=False, null=True, unique=True)
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
    _TEMPLATE_SCHEMA = os.environ.get("TEMPLATE_SCHEMA", "template0")
    _CLONE_SCHEMA_FUNC_FILENAME = os.path.join(find_db_functions_dir(), "clone_schema.sql")
    _CLONE_SCHEMA_FUNC_SCHEMA = "public"
    _CLONE_SCHEMA_FUNC_NAME = "clone_schema"
    _CLONE_SCHEMA_FUNC_SIG = (
        f"{_CLONE_SCHEMA_FUNC_SCHEMA}.{_CLONE_SCHEMA_FUNC_NAME}("
        "source_schema text, dest_schema text, "
        "copy_data boolean DEFAULT false, "
        "_verbose boolean DEFAULT false"
        ")"
    )

    # Override the mixin domain url to make it nullable, non-unique
    domain_url = None

    # Delete all schemas when a tenant is removed
    auto_drop_schema = True
    auto_create_schema = False

    def _check_clone_func(self):
        LOG.info(f'Verify that clone function "{self._CLONE_SCHEMA_FUNC_NAME}" exists')
        res = dbfunc_exists(
            conn, self._CLONE_SCHEMA_FUNC_SCHEMA, self._CLONE_SCHEMA_FUNC_NAME, self._CLONE_SCHEMA_FUNC_SIG
        )
        if not res:
            LOG.warning(f'Clone function "{self._CLONE_SCHEMA_FUNC_NAME}" does not exist')
            LOG.info(f'Creating clone function "{self._CLONE_SCHEMA_FUNC_NAME}"')
            apply_sql_file(conn.schema_editor(), self._CLONE_SCHEMA_FUNC_FILENAME, literal_placeholder=True)
            res = dbfunc_exists(
                conn, self._CLONE_SCHEMA_FUNC_SCHEMA, self._CLONE_SCHEMA_FUNC_NAME, self._CLONE_SCHEMA_FUNC_SIG
            )
        else:
            LOG.info(f'Clone function "{self._CLONE_SCHEMA_FUNC_NAME}" exists. Not creating.')

        return res

    def _verify_template(self, verbosity=1):
        LOG.info(f'Verify that template schema "{self._TEMPLATE_SCHEMA}" exists')
        # This is using the tenant table data as the source of truth which can be dangerous.
        # If this becomes unreliable, then the database itself should be the source of truth
        # and extra code must be written to handle the sync of the table data to the state of
        # the database.
        template_schema, _ = self.__class__.objects.get_or_create(schema_name=self._TEMPLATE_SCHEMA)
        try:
            template_schema.create_schema()
        except Exception as ex:
            LOG.error(f"Caught exception {ex.__class__.__name__} during template schema create: {str(ex)}")
            raise ex

        # Strict check here! Both the record and the schema *should* exist!
        res = bool(template_schema) and schema_exists(self._TEMPLATE_SCHEMA)
        return res

    def _clone_schema(self):
        result = None
        # This db func will clone the schema objects
        # bypassing the time it takes to run migrations
        sql = """
select public.clone_schema(%s, %s, copy_data => true) as "clone_result";
"""
        LOG.info(f'Cloning template schema "{self._TEMPLATE_SCHEMA}" to "{self.schema_name}"')
        LOG.info("Reading catalog for template data")

        with conn.cursor() as cur:
            cur.execute(sql, [self._TEMPLATE_SCHEMA, self.schema_name])
            result = cur.fetchone()
            cur.execute("SET search_path = public;")

        return result[0] if result else False

    def create_schema(self, check_if_exists=True, sync_schema=True, verbosity=1):
        """
        If schema is "public" or matches _TEMPLATE_SCHEMA, then use the superclass' create_schema() method.
        Else, verify the template and inputs and use the database clone function.
        """
        if self.schema_name in ("public", self._TEMPLATE_SCHEMA):
            LOG.info(f'Using superclass for "{self.schema_name}" schema creation')
            return super().create_schema(check_if_exists=True, sync_schema=sync_schema, verbosity=verbosity)

        db_exc = None
        # Verify name structure
        if not is_valid_schema_name(self.schema_name):
            exc = ValidationError(f'Invalid schema name: "{self.schema_name}"')
            LOG.error(f"{exc.__class__.__name__}:: {''.join(exc)}")
            raise exc

        with transaction.atomic():
            # Make sure all of our special pieces are in play
            ret = self._check_clone_func()
            if not ret:
                errmsg = "Missing clone_schema function even after re-applying the function SQL file."
                LOG.critical(errmsg)
                raise CloneSchemaFuncMissing(errmsg)

            ret = self._verify_template(verbosity=verbosity)
            if not ret:
                errmsg = f'Template schema "{self._TEMPLATE_SCHEMA}" does not exist'
                LOG.critical(errmsg)
                raise CloneSchemaTemplateMissing(errmsg)

            # Always check to see if the schema exists!
            LOG.info(f"Check if target schema {self.schema_name} already exists")
            if schema_exists(self.schema_name):
                LOG.warning(f'Schema "{self.schema_name}" already exists. Exit with False.')
                return False

            # Clone the schema. The database function will check
            # that the source schema exists and the destination schema does not.
            try:
                self._clone_schema()
            except Exception as dbe:
                db_exc = dbe
                LOG.error(
                    f"""Exception {dbe.__class__.__name__} cloning"""
                    + f""" "{self._TEMPLATE_SCHEMA}" to "{self.schema_name}": {str(dbe)}"""
                )
                LOG.info("Setting transaction to exit with ROLLBACK")
                transaction.set_rollback(True)  # Set this transaction context to issue a rollback on exit
            else:
                LOG.info(f'Successful clone of "{self._TEMPLATE_SCHEMA}" to "{self.schema_name}"')

        # Set schema to public (even if there was an exception)
        with transaction.atomic():
            LOG.info("Reset DB search path to public")
            conn.set_schema_to_public()

        if db_exc:
            raise db_exc

        return True


class Domain(DomainMixin):
    """Domain model to map domain to tenant.
    Fields inherited:
        domain = models.Charfied
        is_primary = models.BooleanField(default=True)
        tenant = models.ForeignKey(Tenant)
    """

    pass
