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


def check_schema(schema, presto_cursor):
    schema_check_sql = f"SHOW SCHEMAS LIKE '{schema}'"
    schema = presto_cursor.execute(schema_check_sql, "default")
    logging.info("Checking for schema")
    if schema:
        return True
    return False


def get_schemas(presto_cursor):
    schemas_sql = "SELECT schema_name FROM information_schema.schemata"
    presto_cursor.execute(schemas_sql)
    schemas = presto_cursor.fetchall()
    schemas = [
        schema
        for listed_schema in schemas
        for schema in listed_schema
        if schema not in ["default", "information_schema"]
    ]
    return schemas


table_names = ["aws_line_items", "aws_line_items_daily", "aws_openshift_daily"]
presto_conn = False
logging.info("Running the hive migration for aws savings plan")
try:
    presto_conn = trino.dbapi.connect(
        host=PRESTO_HOST, port=PRESTO_PORT, user=PRESTO_USER, catalog=PRESTO_CATALOG, schema="default"
    )
    presto_cur = presto_conn.cursor()
    schemas = get_schemas(presto_cur)
    logging.info("Running against the following schemas")
    logging.info(schemas)
    presto_conn.close()
    for schema in schemas:
        presto_conn = trino.dbapi.connect(
            host=PRESTO_HOST, port=PRESTO_PORT, user=PRESTO_USER, catalog=PRESTO_CATALOG, schema=schema
        )
        presto_cur = presto_conn.cursor()
        if check_schema(schema, presto_cur):
            for table_name in table_names:
                try:
                    logging.info(f"Dropping table {table_name} from {schema}.")
                    presto_cur.execute(
                        f"""
                        DROP TABLE IF EXISTS {table_name}
                    """,
                        None,
                    )
                except Exception as e:
                    logging.info(e)
finally:
    if presto_conn:
        presto_conn.close()
