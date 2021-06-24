#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Django database settings."""
import json
import logging
import os

import django
from django.conf import settings
from django.db import connections
from django.db import DEFAULT_DB_ALIAS
from django.db import models
from django.db import OperationalError
from django.db import transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models import DecimalField
from django.db.models.aggregates import Func
from django.db.models.fields.json import KeyTextTransform
from django.db.models.sql.compiler import SQLDeleteCompiler
from sqlparse import format as format_sql

from .configurator import CONFIGURATOR
from .env import ENVIRONMENT
from .migration_sql_helpers import apply_sql_file
from .migration_sql_helpers import find_db_functions_dir


LOG = logging.getLogger(__name__)

engines = {
    "sqlite": "django.db.backends.sqlite3",
    "postgresql": "tenant_schemas.postgresql_backend",
    "mysql": "django.db.backends.mysql",
}


DB_MODELS = {}


def _cert_config(db_config, database_cert):
    """Add certificate configuration as needed."""
    if database_cert:
        cert_file = CONFIGURATOR.get_database_ca_file()
        db_options = {"OPTIONS": {"sslmode": "verify-full", "sslrootcert": cert_file}}
        db_config.update(db_options)
    return db_config


def config():
    """Database config."""
    service_name = ENVIRONMENT.get_value("DATABASE_SERVICE_NAME", default="").upper().replace("-", "_")
    if service_name:
        engine = engines.get(ENVIRONMENT.get_value("DATABASE_ENGINE"), engines["postgresql"])
    else:
        engine = engines["postgresql"]

    name = CONFIGURATOR.get_database_name()

    if not name and engine == engines["sqlite"]:
        name = os.path.join(settings.BASE_DIR, "db.sqlite3")

    db_config = {
        "ENGINE": engine,
        "NAME": name,
        "USER": CONFIGURATOR.get_database_user(),
        "PASSWORD": CONFIGURATOR.get_database_password(),
        "HOST": CONFIGURATOR.get_database_host(),
        "PORT": CONFIGURATOR.get_database_port(),
    }

    database_cert = CONFIGURATOR.get_database_ca()
    return _cert_config(db_config, database_cert)


def dbfunc_exists(connection, function_schema, function_name, function_signature):
    """
    Test that the migration check database function exists by
    checking the existence of the function signature.
    """
    sql = """
select p.pronamespace::regnamespace::text || '.' || p.proname ||
       '(' || pg_get_function_arguments(p.oid) || ')' as funcsig
  from pg_proc p
 where pronamespace = %s::regnamespace
   and proname = %s;
"""
    with connection.cursor() as cur:
        cur.execute(sql, (function_schema, function_name))
        res = cur.fetchone()

    return bool(res) and res[0] == function_signature


def install_migrations_dbfunc(connection):
    """
    Install the migration check database function
    """
    db_funcs_dir = find_db_functions_dir()
    migration_check_sql = os.path.join(db_funcs_dir, "app_needs_migrations_func.sql")
    LOG.info("Installing migration check db function")
    apply_sql_file(connection.schema_editor(), migration_check_sql, True)


def verify_migrations_dbfunc(connection):
    func_sig = "public.migrations_complete(leaf_migrations jsonb, _verbose boolean DEFAULT false)"
    if not dbfunc_exists(connection, "public", "migrations_complete", func_sig):
        install_migrations_dbfunc(connection)


def check_migrations_dbfunc(connection, targets):
    """
    Check the state of the migrations using the migrations_complete
    database function.
    The database function returns true if the migrations NEED to be run else false.
    """
    LOG.info("Checking app migrations via database function")
    with connection.cursor() as cur:
        cur.execute("SELECT public.migrations_complete(%s::jsonb);", (json.dumps(dict(targets)),))
        res = cur.fetchone()
        ret = bool(res) and res[0]

    LOG.info(f"Migrations should {'not ' if ret else ''}be run.")
    return ret


def check_migrations():
    """
    Check the status of database migrations.
    The koku API server is responsible for running all database migrations.  This method
    will return the state of the database and whether or not all migrations have been completed.
    Hat tip to the Stack Overflow contributor: https://stackoverflow.com/a/31847406
    Returns:
        Boolean - True if database is available and migrations have completed.  False otherwise.
    """
    try:
        connection = connections[DEFAULT_DB_ALIAS]
        connection.prepare_database()
        targets = MigrationLoader(None).graph.leaf_nodes()
        with transaction.atomic():
            verify_migrations_dbfunc(connection)
            res = check_migrations_dbfunc(connection, targets)
        return res
    except OperationalError:
        return False


class JSONBBuildObject(Func):
    """Expose the Postgres jsonb_build_object function for use by ORM."""

    function = "jsonb_build_object"


class KeyDecimalTransform(KeyTextTransform):
    """Return a decimal for our numeric JSON."""

    output_field = DecimalField()

    def as_postgresql(self, compiler, connection):
        sqlpart, params = super().as_postgresql(compiler, connection)
        return sqlpart + "::numeric", params


def get_delete_sql(query):
    return SQLDeleteCompiler(query.query, transaction.get_connection(), query.db).as_sql()


def get_update_sql(query, **updatespec):
    assert query.query.can_filter()
    query.for_write = True
    q = query.query.chain(models.sql.UpdateQuery)
    q.add_update_values(updatespec)
    q._annotations = None

    return q.get_compiler(query.db).as_sql()


def execute_compiled_sql(sql, params=None):
    rows_affected = 0
    with transaction.get_connection().cursor() as cur:
        params = params or None
        LOG.debug(format_sql(cur.mogrify(sql, params).decode("utf-8"), reindent_aligned=True))
        cur.execute(sql, params)
        rows_affected = cur.rowcount

    return rows_affected


def execute_delete_sql(query):
    """Execute sql directly, returns cursor."""
    sql, params = get_delete_sql(query)
    return execute_compiled_sql(sql, params=params)


def execute_update_sql(query, **updatespec):
    """Execute sql directly, returns cursor."""
    sql, params = get_update_sql(query, **updatespec)
    return execute_compiled_sql(sql, params=params)


def cascade_delete(from_model, instance_pk_query, skip_relations=[], base_model=None, level=0):
    """
    Performs a cascading delete by walking the Django model relations and executing compiled SQL
    to perform the on_delete actions instead or running the collector.
    Parameters:
        from_model (models.Model) : A model class that is the relation root
        instance_pk_query (QuerySet) : A query for the records to delete and cascade from
        base_model (None; Model) : The root model class, If null, this will be set for you.
        level (int) : Recursion depth. This is used in logging only. Do not set.
        skip_relations (Iterable of Models) : Relations to skip over in case they are handled explicitly elsewhere
    """
    if base_model is None:
        base_model = from_model
    instance_pk_query = instance_pk_query.values_list("pk").order_by()
    LOG.info(f"Level {level} Delete Cascade for {base_model.__name__}: Checking relations for {from_model.__name__}")
    for model_relation in from_model._meta.related_objects:
        related_model = model_relation.related_model
        if related_model in skip_relations:
            LOG.info(f"SKIPPING RELATION {related_model.__name__} from caller directive")
            continue

        if model_relation.on_delete.__name__ == "SET_NULL":
            filterspec = {f"{model_relation.remote_field.column}__in": models.Subquery(instance_pk_query)}
            updatespec = {f"{model_relation.remote_field.column}": None}
            LOG.info(
                f"    Executing SET NULL constraint action on {related_model.__name__}"
                f" relation of {from_model.__name__}"
            )
            rec_count = execute_update_sql(related_model.objects.filter(**filterspec), **updatespec)
            LOG.info(f"    Updated {rec_count} records in {related_model.__name__}")
        elif model_relation.on_delete.__name__ == "CASCADE":
            filterspec = {f"{model_relation.remote_field.column}__in": models.Subquery(instance_pk_query)}
            related_pk_values = related_model.objects.filter(**filterspec).values_list(related_model._meta.pk.name)
            LOG.info(f"    Cascading delete to relations of {related_model.__name__}")
            cascade_delete(
                related_model, related_pk_values, base_model=base_model, level=level + 1, skip_relations=skip_relations
            )

    LOG.info(f"Level {level}: delete records from {from_model.__name__}")
    if level == 0:
        del_query = instance_pk_query
    else:
        filterspec = {f"{from_model._meta.pk.name}__in": models.Subquery(instance_pk_query)}
        del_query = from_model.objects.filter(**filterspec)

    rec_count = execute_delete_sql(del_query)
    LOG.info(f"Deleted {rec_count} records from {from_model.__name__}")


def _load_db_models():
    """Initialize the global dict that will hold the table_name/model_name -> Model map"""
    qualified_only = set()
    for app, _models in django.apps.apps.all_models.items():
        for lmodel_name, model in _models.items():
            qualified_model_name = f"{app}.{lmodel_name}"
            if lmodel_name in DB_MODELS:
                qualified_only.add(lmodel_name)
                del DB_MODELS[lmodel_name]

            DB_MODELS[qualified_model_name] = model
            DB_MODELS[model._meta.db_table] = model
            if lmodel_name not in qualified_only:
                DB_MODELS[lmodel_name] = model


def get_model(model_or_table_name):
    """Get a model class from the model name or table name"""
    if not DB_MODELS:
        _load_db_models()
    return DB_MODELS[model_or_table_name.lower()]
