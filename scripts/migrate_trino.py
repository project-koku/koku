#! /usr/bin/env python3.8
import logging
import os

import trino

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
    with trino.dbapi.connect(**conn_params) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
    return result


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


def add_columns_to_table(columns, table, conn_params):
    for column in columns:
        logging.info(f"adding column {column} to table {table}")
        sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} double"
        try:
            result = run_trino_sql(sql, conn_params)
            logging.info("ALTER TABLE result: ")
            logging.info(result)
        except Exception as e:
            logging.info(e)


def drop_columns_from_table(columns, table, conn_params):
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
    logging.info("Running the hive migration for cost model effective cost")

    logging.info("fetching schemas")
    schemas = get_schemas()
    logging.info("Running against the following schemas")
    logging.info(schemas)

    # tables_to_drop = []
    # columns_to_add = []
    columns_to_drop = ["project_rank", "data_source_rank"]

    for schema in schemas:
        CONNECT_PARAMS["schema"] = schema
        # logging.info(f"*** dropping tables for schema {schema} ***")
        # drop_tables(tables_to_drop, CONNECT_PARAMS)
        logging.info(f"*** Dropping columns for schema {schema} ***")
        drop_columns_from_table(
            columns_to_drop, "reporting_ocpawscostlineitem_project_daily_summary_temp", CONNECT_PARAMS
        )
        drop_columns_from_table(columns_to_drop, "reporting_ocpawscostlineitem_project_daily_summary", CONNECT_PARAMS)
        drop_columns_from_table(
            columns_to_drop, "reporting_ocpazurecostlineitem_project_daily_summary_temp", CONNECT_PARAMS
        )
        drop_columns_from_table(
            columns_to_drop, "reporting_ocpazurecostlineitem_project_daily_summary", CONNECT_PARAMS
        )
        drop_columns_from_table(
            columns_to_drop, "reporting_ocpgcpcostlineitem_project_daily_summary_temp", CONNECT_PARAMS
        )
        drop_columns_from_table(columns_to_drop, "reporting_ocpgcpcostlineitem_project_daily_summary", CONNECT_PARAMS)


if __name__ == "__main__":
    main()
