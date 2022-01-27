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


def check_schema(schema, trino_cursor):
    schema_check_sql = f"SHOW SCHEMAS LIKE '{schema}'"
    schema = trino_cursor.execute(schema_check_sql)
    logging.info("Checking for schema")
    if schema:
        return True
    return False


def get_schemas(trino_cursor):
    schemas_sql = "SELECT schema_name FROM information_schema.schemata"
    trino_cursor.execute(schemas_sql)
    schemas = trino_cursor.fetchall()
    schemas = [
        schema
        for listed_schema in schemas
        for schema in listed_schema
        if schema not in ["default", "information_schema"]
    ]
    return schemas


table_names = ["openshift_pod_usage_line_items_daily", "reporting_ocpawscostlineitem_project_daily_summary_temp"]
trino_conn = False
logging.info("Running the hive migration for cost model effective cost")
try:
    trino_conn = trino.dbapi.connect(
        host=PRESTO_HOST, port=PRESTO_PORT, user=PRESTO_USER, catalog=PRESTO_CATALOG, schema="default"
    )
    trino_cur = trino_conn.cursor()
    schemas = get_schemas(trino_cur)
    logging.info("Running against the following schemas")
    logging.info(schemas)
    trino_conn.close()
    for schema in schemas:
        trino_conn = trino.dbapi.connect(
            host=PRESTO_HOST, port=PRESTO_PORT, user=PRESTO_USER, catalog=PRESTO_CATALOG, schema=schema
        )
        trino_cur = trino_conn.cursor()
        if check_schema(schema, trino_cur):
            for table_name in table_names:
                try:
                    logging.info(f"Dropping table {table_name} from {schema}.")
                    trino_cur.execute(
                        f"""
                        DROP TABLE IF EXISTS {table_name}
                    """
                    )
                    result = trino_cur.fetchall()
                    logging.info("Drop table result: ")
                    logging.info(result)
                except Exception as e:
                    logging.info(e)
            try:
                table_name = "reporting_ocpusagelineitem_daily_summary"
                columns = ["pod_effective_usage_memory_gigabyte_hours", "pod_effective_usage_cpu_core_hours"]

                logging.info(f"Altering table {table_name} from {schema}.")
                for column in columns:
                    trino_cur.execute(
                        f"""
                        ALTER TABLE {table_name} ADD COLUMN {column} double
                    """
                    )
                    result = trino_cur.fetchall()
                    logging.info("Drop table result: ")
                    logging.info(result)
            except Exception as e:
                logging.info(e)
finally:
    if trino_conn:
        trino_conn.close()
