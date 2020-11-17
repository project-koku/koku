import uuid
from datetime import datetime

from django.db import connection as conn
from pytz import UTC

from . import database as kdb
from api.iam.test.iam_test_case import IamTestCase


class TestPrestoDeleteLogTrigger(IamTestCase):
    def test_presto_delete_log_table_exists(self):
        """
        Ensure that the table and trigger exists
        """
        with conn.cursor() as cur:
            cur.execute(
                """
select count(*) as ct
  from pg_class
 where relnamespace = 'acct10001'::regnamespace
   and relname = 'presto_delete_wrapper_log';
"""
            )
            self.assertTrue(bool(cur.fetchone()[0]))

            cur.execute(
                """
select count(*) as ct
  from pg_trigger
 where tgname = 'tr_presto_before_insert'
   and tgrelid = 'acct10001.presto_delete_wrapper_log'::regclass;
"""
            )
            self.assertTrue(bool(cur.fetchone()[0]))

    def test_presto_delete_log_func_exists(self):
        """
        Ensure that the presto delete wrapper trigger function exists
        """
        func_schema = "public"
        func_name = "tr_presto_delete_wrapper_log_action"
        func_sig = f"{func_schema}.{func_name}()"
        self.assertTrue(kdb.dbfunc_exists(conn, func_schema, func_name, func_sig))

    def test_delete_log_action(self):
        """
        Test that the trigger action will delete the specified records from the specified table
        """
        # create test table with 20 rows
        with conn.cursor() as cur:
            cur.execute(
                """
create table acct10001.test_presto_delete as
select id::int, 'eek'::text "data"
  from generate_series(1, 20) id;
"""
            )
            cur.execute("""select count(*) as ct from acct10001.test_presto_delete;""")
            initial_row_count = cur.fetchone()[0]
        self.assertEqual(initial_row_count, 20)

        # delete 4 rows
        # Out of range value on purpose
        id = uuid.uuid4()
        action_ts = datetime.now().replace(tzinfo=UTC)
        target_table = "test_presto_delete"
        where_clause = "where id in (1, 4, 7, 19, 77)"
        with conn.cursor() as cur:
            cur.execute(
                """
insert into acct10001.presto_delete_wrapper_log(id, action_ts, table_name, where_clause)
values(%s, %s, %s, %s);
""",
                (id, action_ts, target_table, where_clause),
            )

            cur.execute("""select result_rows from acct10001.presto_delete_wrapper_log where id = %s;""", (id,))
            result_rows = cur.fetchone()[0]
            cur.execute("""select count(*) as ct from acct10001.test_presto_delete;""")
            row_count = cur.fetchone()[0]
            self.assertEqual(result_rows, 4)
            self.assertEqual(row_count, (initial_row_count - result_rows))
