#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import argparse
import json
import logging
import re
import secrets
import sys
import textwrap
import time
import typing as t
from datetime import datetime
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from pydantic import BaseModel
from pydantic import Field
from trino.exceptions import TrinoExternalError
from trino.exceptions import TrinoUserError

import koku.trino_database as trino_db
from api.utils import DateHelper

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

manage_table_mapping = {
    "aws_openshift_daily_resource_matched_temp": "ocp_source",
    "aws_openshift_daily_tag_matched_temp": "ocp_source",
    "azure_openshift_daily_resource_matched_temp": "ocp_source",
    "azure_openshift_daily_tag_matched_temp": "ocp_source",
    "gcp_openshift_daily_resource_matched_temp": "ocp_source",
    "gcp_openshift_daily_tag_matched_temp": "ocp_source",
    "reporting_ocpawscostlineitem_project_daily_summary": "ocp_source",
    "reporting_ocpawscostlineitem_project_daily_summary_temp": "ocp_source",
    "reporting_ocpazurecostlineitem_project_daily_summary": "ocp_source",
    "reporting_ocpazurecostlineitem_project_daily_summary_temp": "ocp_source",
    "reporting_ocpgcpcostlineitem_project_daily_summary": "ocp_source",
    "reporting_ocpgcpcostlineitem_project_daily_summary_temp": "ocp_source",
    "reporting_ocpusagelineitem_daily_summary": "source",
}

VALID_CHARACTERS = re.compile(r"^[\w.-]+$")


class CommaSeparatedArgs(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None) -> None:
        vals = values.split(",")
        if not all(VALID_CHARACTERS.match(v) for v in vals):
            raise ValueError(f"String should match pattern '{VALID_CHARACTERS.pattern}': {vals}")
        setattr(namespace, self.dest, vals)


class JSONArgs(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None) -> None:
        setattr(namespace, self.dest, json.loads(values))


class AddColumn(BaseModel):
    table: str = Field(pattern=VALID_CHARACTERS)
    column: str = Field(pattern=VALID_CHARACTERS)
    datatype: str = Field(pattern=VALID_CHARACTERS)


class DropColumn(BaseModel):
    table: str = Field(pattern=VALID_CHARACTERS)
    column: str = Field(pattern=VALID_CHARACTERS)


class DropPartition(BaseModel):
    table: str = Field(pattern=VALID_CHARACTERS)
    partition_column: str = Field(pattern=VALID_CHARACTERS)


class ListAddColumns(BaseModel):
    list: list[AddColumn]


class ListDropColumns(BaseModel):
    list: list[DropColumn]


class ListDropPartitions(BaseModel):
    list: list[DropPartition]


class AddColumnAction(BaseModel):
    list_of_cols: ListAddColumns
    schemas: t.Optional[list[str]] = None
    sql: t.Optional[
        str
    ] = """
        SELECT t.table_schema
        FROM information_schema.tables AS t
        LEFT JOIN information_schema.columns AS c
        ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND c.column_name = '{col.column}'
        WHERE t.table_name = '{col.table}'
        AND c.column_name IS NULL
        AND t.table_schema NOT IN ('information_schema', 'sys', 'mysql', 'performance_schema')
        AND t.table_type = 'BASE TABLE'
        """

    def model_post_init(self, *arg, **kwargs) -> None:
        # FIXME: Maybe make this a cached property
        if not self.schemas:
            try:
                self.schemas = self.get_schemas()
                return
            except TrinoExternalError as exc:
                LOG.error(exc)

        self.schemas = []

    def get_schemas(self) -> list[str]:
        """Grabs all schema where the column is not added to the table."""
        LOG.info("finding all schemas missing column")
        schema_list = []
        for col in self.list_of_cols.list:
            schemas = run_trino_sql(textwrap.dedent(self.sql.format(col=col)))
            schemas = [
                schema
                for listed_schema in schemas
                for schema in listed_schema
                if schema not in ["default", "information_schema"]
            ]
            schema_list.extend(schemas)

        return schema_list

    def run(self) -> None:
        """Add specified columns with datatypes to the tables"""
        if not self.schemas:
            LOG.info("No schemas to update found")
            return

        LOG.info(f"running against the following schemas: {self.schemas}")
        for schema in self.schemas:
            LOG.info(f"*** adding column to tables for schema {schema} ***")
            for col in self.list_of_cols.list:
                LOG.info(f"adding column {col.column} of type {col.datatype} to table {col.table}")
                sql = f"ALTER TABLE IF EXISTS {col.table} ADD COLUMN IF NOT EXISTS {col.column} {col.datatype}"
                try:
                    result = run_trino_sql(sql, schema)
                    LOG.info(f"ALTER TABLE result: {result}")
                except Exception as e:
                    LOG.error(e)
                    return

        self.validate()
        LOG.info("Migration successful")

    def validate(self) -> None:
        schemas = self.get_schemas()
        LOG.info("Validating...")
        if schemas:
            LOG.error(f"Not all columns were successfully added to the follow schemas: {schemas}")
            sys.exit(1)


class Command(BaseCommand):

    help = ""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        exclusive_group = parser.add_mutually_exclusive_group()
        parser.add_argument(
            "--schemas",
            action=CommaSeparatedArgs,
            help="a comma separated list of schemas to run the provided command against. default is all schema in db",
            default=[],
        )
        exclusive_group.add_argument(
            "--drop-tables",
            action=CommaSeparatedArgs,
            default=[],
            help="a comma separated list of tables to drop",
            dest="tables_to_drop",
        )
        exclusive_group.add_argument(
            "--drop-columns",
            action=JSONArgs,
            help=(
                "a json encoded string that contains an array of "
                "objects which must include `table` and `column` keys"
            ),
            dest="columns_to_drop",
        )
        exclusive_group.add_argument(
            "--drop-partitions",
            action=JSONArgs,
            help=(
                "a json encoded string that contains an array of "
                "objects which must include `table` and `partition_column` keys"
            ),
            dest="partitions_to_drop",
        )
        exclusive_group.add_argument(
            "--add-columns",
            action=JSONArgs,
            help=(
                "a json encoded string that contains an array of "
                "objects which must include `table`, `column`, and `datatype` keys"
            ),
            dest="columns_to_add",
        )
        exclusive_group.add_argument(
            "--remove-expired-partitions", action=CommaSeparatedArgs, default=[], dest="remove_expired_partitions"
        )
        parser.add_argument(
            "--rerun",
            action="store_true",
            help="a flag to indicate we should find schemas missing the migration",
            dest="rerun",
        )

    def handle(self, *args, **options) -> None:
        if columns_to_add := options["columns_to_add"]:
            columns_to_add = ListAddColumns(list=columns_to_add)
            action = AddColumnAction(list_of_cols=columns_to_add, schemas=options["schemas"])
            action.run()
        elif columns_to_drop := options["columns_to_drop"]:
            columns_to_drop = ListDropColumns(list=columns_to_drop)
            drop_columns_from_tables(columns_to_drop, options["schemas"])
        elif partitions_to_drop := options["partitions_to_drop"]:
            partitions_to_drop = ListDropPartitions(list=partitions_to_drop)
            drop_partitions_from_tables(partitions_to_drop, options["schemas"])
        elif tables_to_drop := options["tables_to_drop"]:
            drop_tables(tables_to_drop, options["schemas"])
        elif expired_partition_tables := options["remove_expired_partitions"]:
            drop_expired_partitions(expired_partition_tables, options["schemas"])


def get_all_schemas() -> list[str]:
    sql = "SELECT schema_name FROM information_schema.schemata"
    schemas = run_trino_sql(sql)
    schemas = [
        schema
        for listed_schema in schemas
        for schema in listed_schema
        if schema not in ["default", "information_schema"]
    ]
    if not schemas:
        LOG.info("no schema in db to update")

    return schemas


def get_schema_containing_column(list_of_cols: ListDropColumns) -> list[str]:
    """Grabs all schema where the column still exists in the table."""
    LOG.info("finding all schemas containing column")
    schema_list = []
    for col in list_of_cols.list:
        sql = f"""
        SELECT t.table_schema
        FROM information_schema.tables AS t
        LEFT JOIN information_schema.columns AS c
        ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND c.column_name = '{col.column}'
        WHERE t.table_name = '{col.table}'
        AND c.column_name IS NOT NULL
        AND t.table_schema NOT IN ('information_schema', 'sys', 'mysql', 'performance_schema')
        AND t.table_type = 'BASE TABLE'
        """
        schemas = run_trino_sql(textwrap.dedent(sql))
        schemas = [
            schema
            for listed_schema in schemas
            for schema in listed_schema
            if schema not in ["default", "information_schema"]
        ]
        schema_list.extend(schemas)

    if not schemas:
        LOG.info("no schema in db to update")

    return schema_list


def run_trino_sql(sql, schema=None) -> t.Optional[str]:
    retries = 5
    for n in range(1, retries + 1):
        attempt = n
        remaining_retries = retries - n
        # Exponential backoff with a little bit of randomness and a
        # minimum wait of 0.5 and max wait of 7
        wait = (min(2**n, 7) + secrets.randbelow(1000) / 1000) or 0.5
        try:
            with trino_db.connect(schema=schema) as conn:
                cur = conn.cursor()
                cur.execute(sql)
                return cur.fetchall()
        except TrinoExternalError as err:
            if err.error_name == "HIVE_METASTORE_ERROR" and n < (retries):
                LOG.warn(
                    f"{err.message}. Attempt number {attempt} of {retries} failed. "
                    f"Trying {remaining_retries} more time{'s' if remaining_retries > 1 else ''} "
                    f"after waiting {wait:.2f}s."
                )
                time.sleep(wait)
            else:
                raise err
        except TrinoUserError as err:
            LOG.error(err.message)
            return schema


def drop_tables(tables, schemas) -> None:
    """drop specified tables"""
    if not schemas:
        schemas = get_all_schemas()
    if not set(tables).issubset(EXTERNAL_TABLES):
        raise ValueError("Attempting to drop non-external table, revise the list of tables to drop.", tables)
    LOG.info(f"running against the following schemas: {schemas}")
    for schema in schemas:
        LOG.info(f"*** dropping tables {tables} for schema {schema} ***")
        for table_name in tables:
            LOG.info(f"dropping table {table_name}")
            sql = f"DROP TABLE IF EXISTS {table_name}"
            try:
                result = run_trino_sql(sql, schema)
                LOG.info(f"DROP TABLE result: {result}")
            except Exception as e:
                LOG.error(e)


def drop_columns_from_tables(list_of_cols: ListDropColumns, schemas: list) -> None:
    """drop specified columns from tables"""
    if not schemas:
        try:
            schemas = get_schema_containing_column(list_of_cols)
        except TrinoExternalError as exc:
            LOG.error(exc)

    LOG.info(f"running against the following schemas: {schemas}")
    for schema in schemas:
        LOG.info(f"*** dropping column from tables for schema {schema} ***")
        for col in list_of_cols.list:
            LOG.info(f"dropping column {col.column} from table {col.table}")
            sql = f"ALTER TABLE IF EXISTS {col.table} DROP COLUMN IF EXISTS {col.column}"
            try:
                result = run_trino_sql(sql, schema)
                LOG.info(f"ALTER TABLE result: {result}")
            except Exception as e:
                LOG.error(e)


def drop_partitions_from_tables(list_of_partitions: ListDropPartitions, schemas: list) -> None:
    """drop specified partitions from tables"""
    if not schemas:
        schemas = get_all_schemas()
    LOG.info(f"running against the following schemas: {schemas}")
    for schema in schemas:
        LOG.info(f"*** dropping partition from tables for schema {schema} ***")
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
                LOG.error(e)

def check_table_exists(schema, table):
    show_tables = f"SHOW TABLES LIKE '{table}'"
    return run_trino_sql(show_tables, schema)


def find_expired_partitions(schema, months, table, source_column_param):
    """Finds the expired partitions"""
    expiration_msg = "Report data expiration is {} for a {} month retention policy"
    today = DateHelper().today
    LOG.info("Current date time is %s", today)
    middle_of_current_month = today.replace(day=15)
    num_of_days_to_expire_date = months * timedelta(days=30)
    middle_of_expire_date_month = middle_of_current_month - num_of_days_to_expire_date
    expiration_date = datetime(
        year=middle_of_expire_date_month.year,
        month=middle_of_expire_date_month.month,
        day=1,
        tzinfo=settings.UTC,
    )
    expiration_date_param = str(expiration_date.date())
    msg = expiration_msg.format(expiration_date_param, months)
    LOG.info(msg)
    expired_partitions_query = f"""
        SELECT partitions.year, partitions.month, partitions.source
    FROM (
        SELECT year as year,
            month as month,
            day as day,
            cast(date_parse(concat(year, '-', month, '-', day), '%Y-%m-%d') as date) as partition_date,
            {source_column_param} as source
        FROM  "{table}$partitions"
    ) as partitions
    WHERE partitions.partition_date < DATE '{expiration_date_param}'
    GROUP BY partitions.year, partitions.month, partitions.source
        """
    LOG.info(f"Finding expired partitions for {schema} {table}")
    return run_trino_sql(expired_partitions_query, schema)


def drop_expired_partitions(tables, schemas):
    """Drop expired partitions"""
    if not schemas:
        schemas = get_all_schemas()
    LOG.info(f"running against the following schemas: {schemas}")
    for schema in schemas:
        for table in tables:
            if table in MANAGED_TABLES:
                months = 5
            else:
                LOG.info("Only supported for managed tables at the moment")
                return
            source_column_param = manage_table_mapping[table]
            if not check_table_exists(schema, table):
                LOG.info(f"{table} does not exist for {schema}")
                return
            continue
            expired_partitions = find_expired_partitions(schema, months, table, source_column_param)
            if not expired_partitions:
                LOG.info(f"No expired partitions found for {table} {schema}")
                return
            continue
            LOG.info(f"Found {len(expired_partitions)}")
            for partition in expired_partitions:
                year, month, source = partition
                LOG.info(f"Removing partition for {source} {year}-{month}")
                # Using same query as what we use in db accessor
                delete_partition_query = f"""
                            DELETE FROM hive.{schema}.{table}
                            WHERE {source_column_param} = '{source}'
                            AND year = '{year}'
                            AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')
                            """
                result = run_trino_sql(delete_partition_query, schema)
                LOG.info(f"DELETE PARTITION result: {result}")
