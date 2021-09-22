import logging
import prestodb

LOG = logging.getLogger(__name__)

def check_schema(schema, presto_cursor):
    schema_check_sql = f"SHOW SCHEMAS LIKE '{schema}'"
    schema = presto_cursor.execute(schema_check_sql, "default")
    LOG.info("Checking for schema")
    if schema:
        return True
    return False

def get_schemas(presto_cursor):
    schemas_sql = "SELECT schema_name FROM information_schema.schemata"
    presto_cursor.execute(schemas_sql)
    schemas = presto_cursor.fetchall()
    schemas = [schema for listed_schema in schemas for schema in listed_schema if schema not in ['default', 'information_schema']]
    return schemas

table_names = ["aws_line_items", "aws_line_items_daily", "aws_openshift_daily"]
presto_conn = False
try:
    presto_conn = prestodb.dbapi.connect(host="localhost", port=8080, user="admin", catalog="hive", schema="default")
    presto_cur = presto_conn.cursor()
    schemas = get_schemas(presto_cur)
    presto_conn.close()
    for schema in schemas: 
        presto_conn = prestodb.dbapi.connect(host="localhost", port=8080, user="admin", catalog="hive", schema=schema)
        presto_cur = presto_conn.cursor()
        if check_schema(schema, presto_cur):
            for table_name in table_names:
                try:
                    print(f"Dropping table {table_name} from {schema}.")
                    presto_cur.execute(f"""
                        DROP TABLE IF EXISTS {table_name}
                    """, None)
                    print("Success")
                    result = presto_cur.fetchall()
                    print(result)
                except Exception as e:
                    print(e)
finally:
    if presto_conn:
        presto_conn.close()
