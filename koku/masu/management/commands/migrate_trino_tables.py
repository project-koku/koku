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
from koku.cache import build_trino_table_exists_key
from koku.cache import delete_value_from_cache
from reporting.models import TRINO_MANAGED_TABLES

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
    "managed_aws_openshift_daily_temp",
    "managed_aws_openshift_disk_capacities_temp",
    "managed_reporting_ocpawscostlineitem_project_daily_summary",
    "managed_reporting_ocpawscostlineitem_project_daily_summary_temp",
    "managed_azure_openshift_daily_temp",
    "managed_azure_openshift_disk_capacities_temp",
    "managed_reporting_ocpazurecostlineitem_project_daily_summary",
    "managed_reporting_ocpazurecostlineitem_project_daily_summary_temp",
    "managed_gcp_openshift_daily_temp",
    "managed_reporting_ocpgcpcostlineitem_project_daily_summary",
    "managed_reporting_ocpgcpcostlineitem_project_daily_summary_temp",
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


class Action(BaseModel):
    list_of_cols: ListAddColumns | ListDropColumns
    schemas: list[str] | None = Field(default_factory=list)
    find_query: str
    modify_query: str

    def model_post_init(self, *arg, **kwargs) -> None:
        if not self.schemas:
            try:
                self.schemas = self.get_schemas()
            except TrinoExternalError as exc:
                LOG.error(exc)

        return self.schemas

    def get_schemas(self) -> set[str]:
        LOG.info("Finding schemas...")
        result = set()
        for col in self.list_of_cols.list:
            schemas = run_trino_sql(textwrap.dedent(self.find_query.format(col=col)))
            schemas = [
                schema
                for listed_schema in schemas
                for schema in listed_schema
                if schema not in ["default", "information_schema"]
            ]
            result.update(schemas)

        return result

    def run(self) -> None:
        if not self.schemas:
            LOG.info("No schemas to update found")
            return

        log_start(self.schemas)
        schema_count = len(self.schemas)
        for count, schema in enumerate(self.schemas):
            LOG.info(f"Modifying tables for schema {schema} ({count + 1} / {schema_count})")
            for col in self.list_of_cols.list:
                try:
                    LOG.info(f"    {schema}: Altering table {col.table}...")
                    result = run_trino_sql(textwrap.dedent(self.modify_query.format(col=col)), schema)
                    LOG.info(f"    {schema}: Altered table {col.table} {result}")
                except Exception as e:
                    LOG.error(e)
                    return

        self.validate()
        LOG.info("Migration successful")

    def validate(self) -> None:
        LOG.info("Validating...")
        schemas = self.get_schemas()
        if schemas:
            LOG.error(f"Migration failed for the follow schemas: {schemas}")
            sys.exit(1)


class AddColumnAction(Action):
    @classmethod
    def build(cls, list_of_cols: ListAddColumns, schemas: list[str]):
        find_query = """
            SELECT t.table_schema
            FROM information_schema.tables AS t
            LEFT JOIN information_schema.columns AS c
            ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND c.column_name = '{col.column}'
            WHERE t.table_name = '{col.table}'
            AND c.column_name IS NULL
            AND t.table_schema NOT IN ('information_schema', 'sys', 'mysql', 'performance_schema')
            AND t.table_type = 'BASE TABLE'
        """
        return cls(
            list_of_cols=list_of_cols,
            schemas=schemas,
            find_query=find_query,
            modify_query="ALTER TABLE IF EXISTS {col.table} ADD COLUMN IF NOT EXISTS {col.column} {col.datatype}",
        )


class DropColumnAction(Action):
    @classmethod
    def build(cls, list_of_cols: ListDropColumns, schemas: list[str]):
        find_query = """
            SELECT t.table_schema
            FROM information_schema.tables AS t
            LEFT JOIN information_schema.columns AS c
            ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND c.column_name = '{col.column}'
            WHERE t.table_name = '{col.table}'
            AND c.column_name IS NOT NULL
            AND t.table_schema NOT IN ('information_schema', 'sys', 'mysql', 'performance_schema')
            AND t.table_type = 'BASE TABLE'
        """
        return cls(
            list_of_cols=list_of_cols,
            schemas=schemas,
            find_query=find_query,
            modify_query="ALTER TABLE IF EXISTS {col.table} DROP COLUMN IF EXISTS {col.column}",
        )


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
                "a json encoded string that contains an array of objects which must include `table` and `column` keys"
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
            action = AddColumnAction.build(list_of_cols=columns_to_add, schemas=options["schemas"])
            action.run()
        elif columns_to_drop := options["columns_to_drop"]:
            columns_to_drop = ListDropColumns(list=columns_to_drop)
            action = DropColumnAction.build(list_of_cols=columns_to_drop, schemas=options["schemas"])
            action.run()
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
    schemas = {
        schema
        for listed_schema in schemas
        for schema in listed_schema
        if schema not in ["default", "information_schema"]
    }
    if not schemas:
        LOG.info("No schema in DB to update")

    return sorted(schemas)


def run_trino_sql(sql, schema=None) -> list[list[int] | None]:
    retries = 8
    for n in range(1, retries + 1):
        attempt = n
        remaining_retries = retries - n
        # Exponential backoff with a little bit of randomness and a
        # minimum wait of 0.5 and max wait of 7
        wait = (min(2**n, 12) + secrets.randbelow(1000) / 1000) or 0.5
        try:
            with trino_db.connect(schema=schema) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    return cur.fetchall()
        except TrinoExternalError as err:
            if err.error_name == "HIVE_METASTORE_ERROR" and n < (retries):
                LOG.warning(
                    f"{err.message}. Attempt number {attempt} of {retries} failed. "
                    f"Trying {remaining_retries} more time{'s' if remaining_retries > 1 else ''} "
                    f"after waiting {wait:.2f}s."
                )
                time.sleep(wait)
            else:
                raise err
        except TrinoUserError as err:
            LOG.error(err.message)
            return []


def log_start(schemas: list[str]) -> str:
    message = f"Running against the following schemas: {', '.join(schemas)}"
    if (schema_count := len(schemas)) > 10:
        message = f"Running against {schema_count} schemas"

    LOG.info(message)


def drop_tables(tables, schemas) -> None:
    """drop specified tables"""
    if not schemas:
        schemas = get_all_schemas()

    if not set(tables).issubset(EXTERNAL_TABLES):
        LOG.error(f"Attempting to drop non-external table, revise the list of tables to drop. {tables}")
        sys.exit()

    log_start(schemas)
    schema_count = len(schemas)
    for count, schema in enumerate(schemas):
        prefix = f"    {schema}: "
        LOG.info(f"Dropping tables {tables} for {schema} ({count + 1} / {schema_count})")
        for table_name in tables:
            LOG.info(f"{prefix}Dropping table {table_name}")
            sql = f"DROP TABLE IF EXISTS {table_name}"
            try:
                result = run_trino_sql(sql, schema)
                LOG.info(f"{prefix}DROP TABLE result: {result}")
                key = build_trino_table_exists_key(schema, table_name)
                result = delete_value_from_cache(key)
                LOG.info(f"{prefix}delete cache key {key}: {result}")
            except Exception as e:
                LOG.error(e)


def drop_partitions_from_tables(list_of_partitions: ListDropPartitions, schemas: list) -> None:  # noqa: C901
    """drop specified partitions from tables"""
    if not schemas:
        schemas = get_all_schemas()

    log_start(schemas)
    for count, schema in enumerate(schemas):
        prefix = f"    {schema}: "
        schema_count = len(schemas)
        LOG.info(f"Looking for partitions to delete schema {schema} ({count + 1} / {schema_count})")
        for part in list_of_partitions.list:
            sql = f"SELECT count(DISTINCT {part.partition_column}) FROM {part.table}"
            try:
                result = run_trino_sql(sql, schema)
                try:
                    partition_count = result[0][0]
                except IndexError:
                    LOG.warning(f"{prefix}Unable to get partition count")
                    continue

                if not partition_count:
                    LOG.info(f"{prefix}No partitions to delete")
                    continue

                limit = 10000
                for i in range(0, partition_count, limit):
                    sql = f"SELECT DISTINCT {part.partition_column} FROM {part.table} OFFSET {i} LIMIT {limit}"
                    result = run_trino_sql(sql, schema)
                    partitions = [res[0] for res in result]

                    for partition in partitions:
                        LOG.info(f"{prefix}Deleting {part.table} partition {part.partition_column} = {partition}")
                        sql = f"DELETE FROM {part.table} WHERE {part.partition_column} = '{partition}'"
                        result = run_trino_sql(sql, schema)
                        LOG.info(f"{prefix}DELETE PARTITION result: {result}")
            except Exception as e:
                LOG.error(e)


def check_table_exists(schema, table):
    show_tables = f"SHOW TABLES LIKE '{table}'"
    return run_trino_sql(show_tables, schema)


def find_expired_partitions(schema, months, table, source_column_param):
    """Finds the expired partitions"""
    today = DateHelper().today
    middle_of_current_month = today.replace(day=15)
    num_of_days_to_expire_date = months * timedelta(days=30)
    middle_of_expire_date_month = middle_of_current_month - num_of_days_to_expire_date
    expiration_date = datetime(
        year=middle_of_expire_date_month.year,
        month=middle_of_expire_date_month.month,
        day=1,
        tzinfo=settings.UTC,
    )

    prefix = f"    {schema}: "
    LOG.info(f"{prefix}Report data expiration is {expiration_date.date()!s} for a {months} month retention policy")
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
    WHERE partitions.partition_date < DATE '{expiration_date.date()!s}'
    GROUP BY partitions.year, partitions.month, partitions.source
        """
    LOG.info(f"{prefix}Finding expired partitions for {table}")
    return run_trino_sql(textwrap.dedent(expired_partitions_query), schema)


def drop_expired_partitions(tables, schemas):
    """Drop expired partitions"""
    if not schemas:
        schemas = get_all_schemas()

    log_start(schemas)
    schema_count = len(schemas)
    for count, schema in enumerate(schemas):
        LOG.info(f"Checking partitions for {schema} ({count + 1} / {schema_count})")
        prefix = f"    {schema}: "
        for table in tables:
            if table in MANAGED_TABLES:
                months = 5
            else:
                LOG.info(f"{prefix}Only supported for managed tables at the moment")
                continue

            source_column_param = TRINO_MANAGED_TABLES[table]
            if not check_table_exists(schema, table):
                LOG.info(f"{prefix}{table} does not exist")
                continue

            expired_partitions = find_expired_partitions(schema, months, table, source_column_param)
            if not expired_partitions:
                LOG.info(f"{prefix}No expired partitions found for {table}")
                continue

            LOG.info(f"{prefix}Found {len(expired_partitions)}")
            for partition in expired_partitions:
                year, month, source = partition
                LOG.info(f"{prefix}Removing partition for {source} {year}-{month}...")
                # Using same query as what we use in db accessor
                delete_partition_query = f"""
                            DELETE FROM hive.{schema}.{table}
                            WHERE {source_column_param} = '{source}'
                            AND year = '{year}'
                            AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')
                            """
                result = run_trino_sql(textwrap.dedent(delete_partition_query), schema)
                LOG.info(f"{prefix}DELETE PARTITION result: {result}")
