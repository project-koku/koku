#! /usr/bin/env python3
import logging
import os

import trino
from trino.exceptions import TrinoExternalError

logging.basicConfig(format="%(asctime)s: %(message)s", datefmt="%m/%d/%Y %I:%M:%S %p", level=logging.INFO)
PRESTO_HOST = os.environ.get("PRESTO_HOST", "localhost")
PRESTO_USER = os.environ.get("PRESTO_USER", "admin")
PRESTO_CATALOG = os.environ.get("PRESTO_CATALOG", "hive")
try:
    PRESTO_PORT = int(os.environ.get("PRESTO_PORT", "8080"))
except ValueError:
    PRESTO_PORT = 8080

CONNECT_PARAMS = {
    "host": PRESTO_HOST,
    "port": PRESTO_PORT,
    "user": PRESTO_USER,
    "catalog": PRESTO_CATALOG,
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


def main():
    logging.info("Running the hive migration for OCP/GCP node columns")

    logging.info("fetching schemas")
    schemas = get_schemas()
    logging.info("Running against the following schemas")
    logging.info(schemas)

    # tables_to_drop = ["gcp_openshift_daily"]
    # columns_to_drop = ["ocp_matched"]
    columns_to_add = {"node_capacity_cpu_core_hours": "double", "node_capacity_memory_gigabyte_hours": "double"}

    for schema in schemas:
        CONNECT_PARAMS["schema"] = schema
        logging.info(f"*** Adding column to tables for schema {schema} ***")
        add_columns_to_table(columns_to_add, "reporting_ocpgcpcostlineitem_project_daily_summary", CONNECT_PARAMS)
        add_columns_to_table(columns_to_add, "reporting_ocpgcpcostlineitem_project_daily_summary_temp", CONNECT_PARAMS)


if __name__ == "__main__":
    main()
