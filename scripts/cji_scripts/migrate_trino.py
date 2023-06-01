#! /usr/bin/env python3
import logging
import os

import trino
from trino.exceptions import TrinoExternalError


logging.basicConfig(format="%(asctime)s: %(message)s", datefmt="%m/%d/%Y %I:%M:%S %p", level=logging.INFO)

TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
TRINO_USER = os.environ.get("TRINO_USER", "admin")
TRINO_CATALOG = os.environ.get("TRINO_CATALOG", "hive")
try:
    TRINO_PORT = int(os.environ.get("TRINO_PORT", "8080"))
except ValueError:
    TRINO_PORT = 8080

# After the TRINO_* params land in app-interface, these CONNECT_PARAMS can be switched to TRINO_*
CONNECT_PARAMS = {
    "host": TRINO_HOST,
    "port": TRINO_PORT,
    "user": TRINO_USER,
    "catalog": TRINO_CATALOG,
    "schema": "default",
}


def get_schemas():
    sql = "SELECT schema_name FROM information_schema.schemata"
    schemas = run_trino_sql(sql, CONNECT_PARAMS)
    schemas = [
        schema
        for listed_schema in schemas
        for schema in listed_schema
        if schema not in ["default", "information_schema"]
    ]
    return schemas


def run_trino_sql(sql, conn_params):
    retries = 5
    for i in range(retries):
        try:
            with trino.dbapi.connect(**conn_params) as conn:
                cur = conn.cursor()
                cur.execute(sql)
                result = cur.fetchall()
                return result
        except TrinoExternalError as err:
            if err.error_name == "HIVE_METASTORE_ERROR" and i < (retries - 1):
                continue
            else:
                raise err


def drop_tables(tables, conn_params):
    for table_name in tables:
        logging.info(f"dropping table {table_name}")
        sql = f"DROP TABLE IF EXISTS {table_name}"
        try:
            result = run_trino_sql(sql, conn_params)
            logging.info("Drop table result: ")
            logging.info(result)
        except Exception as e:
            logging.info(e)


def add_columns_to_table(column_map, table, conn_params):
    """Given a map of column name: type, add columns to table."""
    for column, type in column_map.items():
        logging.info(f"adding column {column} of type {type} to table {table}")
        sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {type}"
        try:
            result = run_trino_sql(sql, conn_params)
            logging.info("ALTER TABLE result: ")
            logging.info(result)
        except Exception as e:
            logging.info(e)


def drop_columns_from_table(columns, table, conn_params):
    """Given a list of columns, drop from table."""
    for column in columns:
        logging.info(f"Dropping column {column} from table {table}")
        sql = f"ALTER TABLE IF EXISTS {table} DROP COLUMN IF EXISTS {column}"
        try:
            result = run_trino_sql(sql, conn_params)
            logging.info("ALTER TABLE result: ")
            logging.info(result)
        except Exception as e:
            logging.info(e)


def drop_table_by_partition(table, partition_column, conn_params):
    sql = f"SELECT count(DISTINCT {partition_column}) FROM {table}"
    try:
        result = run_trino_sql(sql, conn_params)
        partition_count = result[0][0]
        limit = 10000
        for i in range(0, partition_count, limit):
            sql = f"SELECT DISTINCT {partition_column} FROM {table} OFFSET {i} LIMIT {limit}"
            result = run_trino_sql(sql, conn_params)
            partitions = [res[0] for res in result]

            for partition in partitions:
                logging.info(f"*** Deleting {table} partition {partition_column} = {partition} ***")
                sql = f"DELETE FROM {table} WHERE {partition_column} = '{partition}'"
                result = run_trino_sql(sql, conn_params)
                logging.info("DELETE PARTITION result: ")
                logging.info(result)
    except Exception as e:
        logging.info(e)


def main():
    logging.info("fetching schemas")
    schemas = get_schemas()
    logging.info("Running against the following schemas")
    logging.info(schemas)

    tables_to_drop = [
        "aws_openshift_daily",
    ]
    # columns_to_drop = ["ocp_matched"]
    # columns_to_add = {
    #     "calculated_amortized_cost": "double",
    #     "markup_cost_amortized": "double",
    # }

    for schema in schemas:
        CONNECT_PARAMS["schema"] = schema
        # logging.info(f"*** Adding column to tables for schema {schema} ***")
        # add_columns_to_table(columns_to_add, "reporting_ocpawscostlineitem_project_daily_summary", CONNECT_PARAMS)
        logging.info(f"*** Dropping tables {tables_to_drop} for schema {schema} ***")
        drop_tables(tables_to_drop, CONNECT_PARAMS)


if __name__ == "__main__":
    main()
