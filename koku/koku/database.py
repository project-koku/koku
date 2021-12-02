#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Django database settings."""
import json
import logging
import os
import pkgutil
import re
import threading
import types

import django
from django.conf import settings
from django.db import connections
from django.db import DEFAULT_DB_ALIAS
from django.db import IntegrityError
from django.db import models
from django.db import OperationalError
from django.db import transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models import DecimalField
from django.db.models import ForeignKey
from django.db.models.aggregates import Func
from django.db.models.fields.json import KeyTextTransform
from django.db.models.sql.compiler import SQLDeleteCompiler
from django.db.utils import ProgrammingError
from jinjasql import JinjaSql
from sqlparse import format as format_sql
from sqlparse import split as sql_split

from .configurator import CONFIGURATOR
from .env import ENVIRONMENT
from .migration_sql_helpers import apply_sql_file
from .migration_sql_helpers import find_db_functions_dir


LOG = logging.getLogger(__name__)


class FKViolation:
    """Detect Foreign Key violation verbage from an IntegritiyError or other more generic exception"""

    FK_VIOLATION_REGEX_STR = (
        r'(.+?) on table "(.+?)" violates foreign key constraint .+?'
        + r'DETAIL:\s*(.+?) is not present in table "(.+?)".*\n'
    )
    FK_VIOLATION_REGEX = re.compile(FK_VIOLATION_REGEX_STR, flags=re.DOTALL)

    def __init__(self, _exception):
        """Accepts Exception or str"""
        res = self.FK_VIOLATION_REGEX.findall(_exception if isinstance(_exception, str) else str(_exception))
        self.__is_fk_violation = bool(res)
        if not self.__is_fk_violation:
            res = [(None,) * 4]
        self.action, self.target_table, self.detected_key_values, self.reference_table = res[0]

    @property
    def is_fk_violation(self):
        """Returns bool reflecting fk violation or not based on the regex search of the exception error"""
        return self.__is_fk_violation

    def __bool__(self):
        return self.__is_fk_violation

    def __repr__(self):
        return str(self)

    def __str__(self):
        if self.__is_fk_violation:
            msg = (
                f'{self.action} on table "{self.target_table}" violates foreign key.\n'
                + f'DETAILS: {self.detected_key_values} is not present in table "{self.reference_table}"'
            )
        else:
            msg = ""

        return msg


engines = {
    "sqlite": "django.db.backends.sqlite3",
    "postgresql": "tenant_schemas.postgresql_backend",
    "mysql": "django.db.backends.mysql",
}


PARTITIONED_MODEL_NAMES = [
    "AWSCostEntryLineItemDailySummary",
    "AzureCostEntryLineItemDailySummary",
    "GCPCostEntryLineItemDailySummary",
    "OCPUsageLineItemDailySummary",
    "OCPAllCostLineItemDailySummaryP",
    "OCPAllCostLineItemProjectDailySummaryP",
    "OCPAllCostSummaryPT",
    "OCPAllCostSummaryByAccountPT",
    "OCPAllCostSummaryByServicePT",
    "OCPAllCostSummaryByRegionPT",
    "OCPAllComputeSummaryPT",
    "OCPAllDatabaseSummaryPT",
    "OCPAllNetworkSummaryPT",
    "OCPAllStorageSummaryPT",
    "AWSCostSummaryP",
    "AWSCostSummaryByServiceP",
    "AWSCostSummaryByAccountP",
    "AWSCostSummaryByRegionP",
    "AWSComputeSummaryP",
    "AWSComputeSummaryByServiceP",
    "AWSComputeSummaryByAccountP",
    "AWSComputeSummaryByRegionP",
    "AWSStorageSummaryP",
    "AWSStorageSummaryByServiceP",
    "AWSStorageSummaryByAccountP",
    "AWSStorageSummaryByRegionP",
    "AWSNetworkSummaryP",
    "AWSDatabaseSummaryP",
    "OCPCostSummaryP",
    "OCPCostSummaryByProjectP",
    "OCPCostSummaryByNodeP",
    "OCPPodSummaryP",
    "OCPPodSummaryByProjectP",
    "OCPVolumeSummaryP",
    "OCPVolumeSummaryByProjectP",
    "OCPAWSComputeSummaryP",
    "OCPAWSCostSummaryP",
    "OCPAWSCostSummaryByAccountP",
    "OCPAWSCostSummaryByServiceP",
    "OCPAWSCostSummaryByRegionP",
    "OCPAWSStorageSummaryP",
    "OCPAWSNetworkSummaryP",
    "OCPAWSDatabaseSummaryP",
    "OCPGCPCostLineItemDailySummaryP",
    "OCPGCPCostLineItemProjectDailySummaryP",
    "OCPGCPCostSummaryByAccountP",
    "OCPGCPCostSummaryByGCPProjectP",
    "OCPGCPCostSummaryByRegionP",
    "OCPGCPCostSummaryByServiceP",
    "OCPGCPCostSummaryP",
    "OCPGCPComputeSummaryP",
    "OCPGCPDatabaseSummaryP",
    "OCPGCPNetworkSummaryP",
    "OCPGCPStorageSummaryP",
    "AzureCostSummaryP",
    "AzureCostSummaryByAccountP",
    "AzureCostSummaryByLocationP",
    "AzureCostSummaryByServiceP",
    "AzureComputeSummaryP",
    "AzureStorageSummaryP",
    "AzureNetworkSummaryP",
    "AzureDatabaseSummaryP",
    "GCPCostSummaryP",
    "GCPCostSummaryByAccountP",
    "GCPCostSummaryByProjectP",
    "GCPCostSummaryByRegionP",
    "GCPCostSummaryByServiceP",
    "GCPComputeSummaryP",
    "GCPComputeSummaryByProjectP",
    "GCPComputeSummaryByServiceP",
    "GCPComputeSummaryByAccountP",
    "GCPComputeSummaryByRegionP",
    "GCPStorageSummaryP",
    "GCPStorageSummaryByProjectP",
    "GCPStorageSummaryByServiceP",
    "GCPStorageSummaryByAccountP",
    "GCPStorageSummaryByRegionP",
    "GCPNetworkSummaryP",
    "GCPDatabaseSummaryP",
    "OCPAzureCostSummaryP",
    "OCPAzureCostSummaryByAccountP",
    "OCPAzureCostSummaryByLocationP",
    "OCPAzureCostSummaryByServiceP",
    "OCPAzureComputeSummaryP",
    "OCPAzureStorageSummaryP",
    "OCPAzureNetworkSummaryP",
    "OCPAzureDatabaseSummaryP",
]
DB_MODELS_LOCK = threading.Lock()
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
    except (IntegrityError, OperationalError):
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
    try:
        return execute_compiled_sql(sql, params=params)
    except Exception as e:
        LOG.debug(f"The following exception occurred {e}")
        return 0


def execute_update_sql(query, **updatespec):
    """Execute sql directly, returns cursor."""
    sql, params = get_update_sql(query, **updatespec)
    return execute_compiled_sql(sql, params=params)


def set_constraints_immediate():
    with transaction.get_connection().cursor() as cur:
        LOG.debug("Setting constaints to execute immediately")
        cur.execute("set constraints all immediate;")


def cascade_delete(from_model, instance_pk_query, skip_relations=None, base_model=None, level=0):
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

    if skip_relations is None:
        skip_relations = []

    # Skip the low-level data.
    skip_relations.extend(
        (
            get_model("reporting_awscostentrylineitem"),
            get_model("reporting_gcpcostentrylineitem"),
            get_model("reporting_ocpusagelineitem"),
            get_model("reporting_ocpnodelabellineitem"),
            get_model("reporting_ocpstoragelineitem"),
        )
    )

    instance_pk_query = instance_pk_query.values_list("pk").order_by()
    LOG.debug(f"Level {level} Delete Cascade for {base_model.__name__}: Checking relations for {from_model.__name__}")
    for model_relation in from_model._meta.related_objects:
        related_model = model_relation.related_model
        if related_model in skip_relations:
            LOG.debug(f"SKIPPING RELATION {related_model.__name__} by directive")
            continue

        if model_relation.on_delete.__name__ == "SET_NULL":
            filterspec = {f"{model_relation.remote_field.column}__in": models.Subquery(instance_pk_query)}
            updatespec = {f"{model_relation.remote_field.column}": None}
            LOG.debug(
                f"    Executing SET NULL constraint action on {related_model.__name__}"
                f" relation of {from_model.__name__}"
            )
            with transaction.atomic():
                set_constraints_immediate()
                rec_count = execute_update_sql(related_model.objects.filter(**filterspec), **updatespec)
                LOG.debug(f"    Updated {rec_count} records in {related_model.__name__}")
        elif model_relation.on_delete.__name__ == "CASCADE":
            filterspec = {f"{model_relation.remote_field.column}__in": models.Subquery(instance_pk_query)}
            related_pk_values = related_model.objects.filter(**filterspec).values_list(related_model._meta.pk.name)
            LOG.debug(f"    Cascading delete to relations of {related_model.__name__}")
            cascade_delete(
                related_model, related_pk_values, base_model=base_model, level=level + 1, skip_relations=skip_relations
            )

    LOG.debug(f"Level {level}: delete records from {from_model.__name__}")
    if level == 0:
        del_query = instance_pk_query
    else:
        filterspec = {f"{from_model._meta.pk.name}__in": models.Subquery(instance_pk_query)}
        del_query = from_model.objects.filter(**filterspec)

    with transaction.atomic():
        set_constraints_immediate()
        rec_count = execute_delete_sql(del_query)
        LOG.debug(f"Deleted {rec_count} records from {from_model.__name__}")


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
    with DB_MODELS_LOCK:
        if not DB_MODELS:
            _load_db_models()
    return DB_MODELS[model_or_table_name.lower()]


def _count_fk_fields(model):
    num_fk = 0
    for f in model._meta.fields:
        num_fk += int(isinstance(f, ForeignKey))
    return num_fk


def p_table_sql(self, model):
    # Use default model class for the original django SQL generation
    sql, params = self.o_table_sql(model)

    # Based on model name match, get the defined model from the app
    # For some reason, this differs from the model class passed into this method
    # from the django migration processing
    if model.__name__ in PARTITIONED_MODEL_NAMES:
        pmodel = get_model(model.__name__)
    else:
        pmodel = None

    # If there was a partition name match and the class has the required attribute,
    # use this information to add the partition clause to the create table sql
    # Otherwise, return the original sql and params
    if pmodel is not None and hasattr(pmodel, "PartitionInfo"):
        LOG.info(f"*** Creating PARTITIONED TABLE {pmodel._meta.db_table}")
        partition_cols = pmodel.PartitionInfo.partition_cols
        sparams = {
            "partition_type": pmodel.PartitionInfo.partition_type.upper(),
            "partition_cols": ", ".join(f'"{c}"' for c in partition_cols),
        }

        # The primary key will be overridden here
        # Partitioned tables require that the partition column(s) be part of the primary key
        p_sql = self.sql_partitioned_table % sparams
        sql = sql.replace("PRIMARY KEY", "") + p_sql

        pk_cols = partition_cols[:]
        try:
            mod_pk = pmodel._meta.pk.get_attname()
        except Exception:
            pass
        else:
            pk_cols.append(mod_pk)

        sparams = {
            "table_name": f'"{pmodel._meta.db_table}"',
            "constraint_name": f'"{pmodel._meta.db_table}_pk"',
            "constraint_cols": ", ".join(f'"{c}"' for c in pk_cols),
        }
        pk_constraint = self.sql_partitioned_pk % sparams

        num_fk = _count_fk_fields(pmodel)
        if num_fk:
            self.deferred_sql.insert(-num_fk - 1, pk_constraint)
        else:
            self.deferred_sql.append(pk_constraint)

        # Add a deferred sql statement to create the default partition
        sparams = {
            "default_partition_name": f"{pmodel._meta.db_table}_default",
            "partitioned_table_name": pmodel._meta.db_table,
            "partition_type": pmodel.PartitionInfo.partition_type.lower(),
            "partition_col": ",".join(partition_cols),
            "partition_parameters": '{"default": true}',
        }
        with self.connection.cursor() as cur:
            self.deferred_sql.append(cur.mogrify(self.sql_partition_default, sparams).decode("utf-8"))
    else:
        LOG.info(f"Creating TABLE {model._meta.db_table}")

    return sql, params


def p_delete_model(self, model):
    if model.__name__ in PARTITIONED_MODEL_NAMES:
        pmodel = get_model(model.__name__)
    else:
        pmodel = None

    if pmodel is not None and hasattr(pmodel, "PartitionInfo"):
        sparams = {"partitioned_table_name": pmodel._meta.db_table}
        with self.connection.cursor() as cur:
            drop_partitions_sql = cur.mogrify(self.sql_drop_partitions, sparams).decode("utf-8")
        self.execute(drop_partitions_sql)

    self.o_delete_model(model)


def set_partitioned_schema_editor(schema_editor):
    """
    Add attributes and override method of given schema_editor to allow partition table sql statements
    to be emitted.
    """
    # Add SQL templates, if not already present
    if not hasattr(schema_editor, "sql_partitioned_table"):
        setattr(schema_editor, "sql_partitioned_table", " PARTITION BY %(partition_type)s (%(partition_cols)s) ")

    if not hasattr(schema_editor, "sql_partitioned_pk"):
        setattr(
            schema_editor,
            "sql_partitioned_pk",
            "ALTER TABLE %(table_name)s ADD CONSTRAINT %(constraint_name)s PRIMARY KEY (%(constraint_cols)s)",
        )

    # Special sql template to be added to the deferred sql to create the default partition
    # This REQUIRES that the partitioned_tables table is present as well as the trigger and trigger
    # function exists for partition management via this tracking table.
    if not hasattr(schema_editor, "sql_partition_default"):
        default_partition_sql = """
INSERT INTO partitioned_tables (
    schema_name,
    table_name,
    partition_of_table_name,
    partition_type,
    partition_col,
    partition_parameters,
    active
)
VALUES
(
    current_schema,
    %(default_partition_name)s,
    %(partitioned_table_name)s,
    %(partition_type)s,
    %(partition_col)s,
    %(partition_parameters)s::jsonb,
    true
)
"""
        setattr(schema_editor, "sql_partition_default", default_partition_sql)

    # Template to drop partitions by using the partition manager trigger function set
    # on the table
    if not hasattr(schema_editor, "sql_drop_partitions"):
        drop_partitions_sql = """
DELETE
  FROM partitioned_tables
 WHERE schema_name = current_schema
   AND partition_of_table_name = %(partitioned_table_name)s
"""
        setattr(schema_editor, "sql_drop_partitions", drop_partitions_sql)

    # Backup original method to emit create table sql and replace with the new method
    if not hasattr(schema_editor, "o_table_sql"):
        setattr(schema_editor, "o_table_sql", schema_editor.table_sql)
        setattr(schema_editor, "table_sql", types.MethodType(p_table_sql, schema_editor))

    if not hasattr(schema_editor, "o_delete_model"):
        setattr(schema_editor, "o_delete_model", schema_editor.delete_model)
        setattr(schema_editor, "delete_model", types.MethodType(p_delete_model, schema_editor))


def set_partition_mode(apps, schema_editor):
    set_partitioned_schema_editor(schema_editor)


def unset_partitioned_schema_editor(schema_editor):
    # Delete partition template attributes, if present
    if not hasattr(schema_editor, "sql_partitioned_table"):
        delattr(schema_editor, "sql_partitioned_table")

    if not hasattr(schema_editor, "sql_partitioned_pk"):
        delattr(schema_editor, "sql_partitioned_pk")

    if not hasattr(schema_editor, "sql_partition_default"):
        delattr(schema_editor, "sql_partition_default")

    if not hasattr(schema_editor, "sql_drop_partitions"):
        delattr(schema_editor, "sql_drop_partitions")

    # Restore original functionality for create table sql emit
    if not hasattr(schema_editor, "o_table_sql"):
        setattr(schema_editor, "table_sql", schema_editor.o_table_sql)
        delattr(schema_editor, "o_table_sql")

    # Restore original functionality for delete_model method
    if not hasattr(schema_editor, "o_delete_model"):
        setattr(schema_editor, "table_sql", schema_editor.o_delete_model)
        delattr(schema_editor, "o_delete_model")


def unset_partition_mode(apps, schema_editor):
    unset_partitioned_schema_editor(schema_editor)


class SQLScriptAtomicExecutorMixin:
    """This mixin accetps a jinja_sql sql script and parameters (dict) and process each statement
    in the script individually for better logging within PostgreSQL"""

    DEFAULT_SQL_RENDERER = JinjaSql()
    DEFAULT_SQL_RENDERER_METHOD = DEFAULT_SQL_RENDERER.prepare_query

    def _execute_processing_script(
        self, base_module, script_file_path, sql_params, sql_renderer=DEFAULT_SQL_RENDERER_METHOD
    ):
        conn = transaction.get_connection()
        sql = pkgutil.get_data(base_module, script_file_path).decode("utf-8")
        for sql_stmt in sql_split(sql):
            sql_stmt = sql_stmt.strip()
            if sql_stmt:
                sql_stmt, params = sql_renderer(sql_stmt, sql_params)
                with conn.cursor() as cur:
                    try:
                        cur.execute(sql_stmt, params)
                    except (ProgrammingError, IndexError) as exc:
                        if isinstance(sql_stmt, bytes):
                            sql_stmt = sql_stmt.decode("utf-8")
                        msg = [
                            f"ERROR in SQL statement: '{exc}'",
                            f"Script file {os.path.join(base_module.replace('.', os.path.sep), script_file_path)}",
                            f"STATEMENT: {sql_stmt}",
                            f"PARAMS: {params}",
                            f"INPUT_PARAMS: {sql_params}",
                        ]
                        LOG.error(os.linesep.join(msg))
                        raise exc
