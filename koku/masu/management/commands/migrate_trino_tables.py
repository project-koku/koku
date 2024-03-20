import argparse
import json
import logging
import os

from django.core.management.base import BaseCommand
from pydantic import BaseModel
from trino.exceptions import TrinoExternalError
from trino.exceptions import TrinoUserError

import koku.trino_database as trino_db

LOG = logging.getLogger(__name__)
# External tables can be dropped as the data in S3 will persist
EXTERNAL_TABLES = {
    "aws_line_items",
    "aws_line_items_daily",
    "aws_openshift_daily",
    "azure_line_items",
    "azure_openshift_daily",
    "gcp_line_items",
    "gcp_line_items_daily",
    "gcp_openshift_daily",
    "oci_cost_line_items",
    "oci_cost_line_items_daily",
    "oci_usage_line_items",
    "oci_usage_line_items_daily",
    "openshift_namespace_labels_line_items",
    "openshift_namespace_labels_line_items_daily",
    "openshift_node_labels_line_items",
    "openshift_node_labels_line_items_daily",
    "openshift_pod_usage_line_items",
    "openshift_pod_usage_line_items_daily",
    "openshift_storage_usage_line_items",
    "openshift_storage_usage_line_items_daily",
}

# Managed tables should be altered not dropped as we will lose all of the data
MANAGED_TABLES = {
    "aws_openshift_daily_resource_matched_temp",
    "aws_openshift_daily_tag_matched_temp",
    "azure_openshift_daily_resource_matched_temp",
    "azure_openshift_daily_tag_matched_temp",
    "gcp_openshift_daily_resource_matched_temp",
    "gcp_openshift_daily_tag_matched_temp",
    "reporting_ocpawscostlineitem_project_daily_summary",
    "reporting_ocpawscostlineitem_project_daily_summary_temp",
    "reporting_ocpazurecostlineitem_project_daily_summary",
    "reporting_ocpazurecostlineitem_project_daily_summary_temp",
    "reporting_ocpgcpcostlineitem_project_daily_summary",
    "reporting_ocpgcpcostlineitem_project_daily_summary_temp",
    "reporting_ocpusagelineitem_daily_summary",
}
MIGRATIONS_PATH = os.path.join(os.path.dirname(__file__), "trino_migrations")
ADD_COLUMNS_JSON = os.path.join(MIGRATIONS_PATH, "add_columns.json")
DROP_COLUMNS_JSON = os.path.join(MIGRATIONS_PATH, "drop_columns.json")
DROP_PARTITIONS_JSON = os.path.join(MIGRATIONS_PATH, "drop_partitions.json")


class CommaSeparatedArgs(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values.split(","))


class AddColumn(BaseModel):
    table: str
    column: str
    datatype: str


class DropColumn(BaseModel):
    table: str
    column: str


class DropPartition(BaseModel):
    table: str
    partition_column: str


class ListAddColumns(BaseModel):
    list: list[AddColumn]


class ListDropColumns(BaseModel):
    list: list[DropColumn]


class ListDropPartitions(BaseModel):
    list: list[DropPartition]


class Command(BaseCommand):

    help = ""

    def add_arguments(self, parser: argparse.ArgumentParser):
        parser.add_argument(
            "--schemas",
            action=CommaSeparatedArgs,
            default=[],
        )
        parser.add_argument(
            "--drop-tables",
            action=CommaSeparatedArgs,
            default=[],
            help="a comma separated list of tables to drop",
            dest="tables_to_drop",
        )
        parser.add_argument(
            "--drop-columns",
            action="store_true",
            default=False,
            help="read the drop_columns.json to drop columns from specified tables",
            dest="columns_to_drop",
        )
        parser.add_argument(
            "--drop-partitions",
            action="store_true",
            default=False,
            help="read the drop_partitions.json to drop partitions from specified tables",
            dest="partitions_to_drop",
        )
        parser.add_argument(
            "--add-columns",
            action="store_true",
            default=False,
            help="read the add_columns.json to add columns to specified tables",
            dest="columns_to_add",
        )

    def handle(self, *args, **options):
        schemas = options["schemas"]
        if not schemas:
            LOG.info("fetching schemas")
            schemas = get_schemas()
        LOG.info("Running against the following schemas")
        LOG.info(schemas)

        if columns_to_add := options["columns_to_add"]:
            columns_to_add = get_json_data(ADD_COLUMNS_JSON, ListAddColumns)
        if columns_to_drop := options["columns_to_drop"]:
            columns_to_drop = get_json_data(DROP_COLUMNS_JSON, ListDropColumns)
        if partitions_to_drop := options["partitions_to_drop"]:
            partitions_to_drop = get_json_data(DROP_PARTITIONS_JSON, ListDropPartitions)
        tables_to_drop = options["tables_to_drop"]

        for schema in schemas:
            if tables_to_drop:
                LOG.info(f"*** Dropping tables {options['tables_to_drop']} for schema {schema} ***")
                drop_tables(tables_to_drop, schema)
            if columns_to_add:
                LOG.info(f"*** Adding column to tables for schema {schema} ***")
                add_columns_to_tables(columns_to_add, schema)
            if columns_to_drop:
                LOG.info(f"*** Dropping column from tables for schema {schema} ***")
                drop_columns_from_tables(columns_to_drop, schema)
            if partitions_to_drop:
                LOG.info(f"*** Dropping partition from tables for schema {schema} ***")
                drop_partitions_from_tables(partitions_to_drop, schema)


def get_json_data(filename, cls):
    """Read json file into the given pydantic model."""
    with open(filename) as f:
        return cls(list=json.load(f))


def get_schemas():
    sql = "SELECT schema_name FROM information_schema.schemata"
    schemas = run_trino_sql(sql)
    schemas = [
        schema
        for listed_schema in schemas
        for schema in listed_schema
        if schema not in ["default", "information_schema"]
    ]
    return schemas


def run_trino_sql(sql, schema=None):
    retries = 5
    for i in range(retries):
        try:
            with trino_db.connect(schema=schema) as conn:
                cur = conn.cursor()
                cur.execute(sql)
                return cur.fetchall()
        except TrinoExternalError as err:
            if err.error_name == "HIVE_METASTORE_ERROR" and i < (retries - 1):
                continue
            else:
                raise err
        except TrinoUserError as err:
            LOG.info(err.message)
            return


def drop_tables(tables, schema):
    if not set(tables).issubset(EXTERNAL_TABLES):
        raise ValueError("Attempting to drop non-external table, revise the list of tables to drop.", tables)
    for table_name in tables:
        LOG.info(f"dropping table {table_name}")
        sql = f"DROP TABLE IF EXISTS {table_name}"
        try:
            result = run_trino_sql(sql, schema)
            LOG.info(f"DROP TABLE result: {result}")
        except Exception as e:
            LOG.info(e)


def add_columns_to_tables(list_of_cols: ListAddColumns, schema: str):
    """add specified columns with datatypes to the tables"""
    for col in list_of_cols.list:
        LOG.info(f"adding column {col.column} of type {col.datatype} to table {col.table}")
        sql = f"ALTER TABLE {col.table} ADD COLUMN IF NOT EXISTS {col.column} {col.datatype}"
        try:
            result = run_trino_sql(sql, schema)
            LOG.info(f"ALTER TABLE result: {result}")
        except Exception as e:
            LOG.info(e)


def drop_columns_from_tables(list_of_cols: ListDropColumns, schema: str):
    """Given a list of columns, drop from table."""
    for col in list_of_cols.list:
        LOG.info(f"dropping column {col.column} from table {col.table}")
        sql = f"ALTER TABLE IF EXISTS {col.table} DROP COLUMN IF EXISTS {col.column}"
        try:
            result = run_trino_sql(sql, schema)
            LOG.info(f"ALTER TABLE result: {result}")
        except Exception as e:
            LOG.info(e)


def drop_partitions_from_tables(list_of_partitions: ListDropPartitions, schema: str):
    for part in list_of_partitions.list:
        sql = f"SELECT count(DISTINCT {part.partition_column}) FROM {part.table}"
        try:
            result = run_trino_sql(sql, schema)
            partition_count = result[0][0]
            limit = 10000
            for i in range(0, partition_count, limit):
                sql = f"SELECT DISTINCT {part.partition_column} FROM {part.table} OFFSET {i} LIMIT {limit}"
                result = run_trino_sql(sql, schema)
                partitions = [res[0] for res in result]

                for partition in partitions:
                    LOG.info(f"*** Deleting {part.table} partition {part.partition_column} = {partition} ***")
                    sql = f"DELETE FROM {part.table} WHERE {part.partition_column} = '{partition}'"
                    result = run_trino_sql(sql, schema)
                    LOG.info(f"DELETE PARTITION result: {result}")
        except Exception as e:
            LOG.info(e)
