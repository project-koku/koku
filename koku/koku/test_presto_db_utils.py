import datetime
import uuid

import jinjasql
from requests.exceptions import HTTPError

from . import presto_database as kpdb
from api.iam.test.iam_test_case import IamTestCase


class TestPrestoDatabaseUtils(IamTestCase):
    def test_bad_conninfo(self):
        """
        Test to make sure that bad presto connection args will throw an exception
        """
        conn = kpdb.connect(port=19999, host="no/host/here!", schema="eek")
        cur = conn.cursor()
        with self.assertRaises(HTTPError):
            cur.execute("show tables")

    def test_connect(self):
        """
        Test connection to presto
        """
        conn = kpdb.connect(schema=self.schema_name)
        cur = conn.cursor()
        exc = None
        try:
            cur.execute("show tables")
        except Exception as e:
            exc = e

        self.assertIsNone(exc)

    def test_sql_mogrify(self):
        """
        Test that sql_mogrify renders a syntactically correct SQL statement
        """

        class SQLTest:
            def __init__(self, sql_test, params, sql_verify):
                self.sql_test = sql_test
                self.params = params
                self.sql_verify = sql_verify
                self.sql_result = None

        tests = [
            SQLTest("""select * from public.api_tenant""", None, """select * from public.api_tenant"""),
            SQLTest(
                """select * from public.api_tenant where schema_name = %s""",
                ["public"],
                """select * from public.api_tenant where schema_name = 'public'""",
            ),
            SQLTest(
                """select * from eek where date_col = %(date_val)s and bool_col = %(bool_val)s""",
                {"date_val": datetime.date(2020, 4, 30), "bool_val": False},
                """select * from eek where date_col = '2020-04-30' and bool_col = False""",
            ),
            SQLTest("""select * from eek where col1 in %s""", [(11,)], """select * from eek where col1 in (11)"""),
            SQLTest(
                """select * from eek where col1 in %s""",
                [("11", "12")],
                """select * from eek where col1 in ('11', '12')""",
            ),
        ]

        for test in tests:
            test.sql_result = kpdb.sql_mogrify(test.sql_test, test.params)
            self.assertEqual(test.sql_verify, test.sql_result)

    def test_execute(self):
        conn = kpdb.connect(schema=self.schema_name)
        exc = None
        try:
            res = kpdb.execute(conn, """show tables""")
        except Exception as e:
            exc = e
        self.assertIsNone(exc)
        self.assertTrue(isinstance(res, list))

    def test_executescript(self):
        sqlscript = """
drop table if exists hive.{{schema | sqlsafe}}.__test_{{uuid | sqlsafe}};
create table hive.{{schema | sqlsafe}}.__test_{{uuid | sqlsafe}}
(
    id varchar,
    i_data integer,
    t_data varchar
);

insert into hive.{{schema | sqlsafe}}.__test_{{uuid | sqlsafe}} (id, i_data, t_data)
values (cast(uuid() as varchar), 10, 'default');

insert into hive.{{schema | sqlsafe}}.__test_{{uuid | sqlsafe}} (id, i_data, t_data)
values (cast(uuid() as varchar), {{int_data}}, {{txt_data}});

select t_data from hive.{{schema | sqlsafe}}.__test_{{uuid | sqlsafe}} where i_data = {{int_data}};

drop table if exists hive.{{schema | sqlsafe}}.__test_{{uuid | sqlsafe}};
"""
        conn = kpdb.connect(schema=self.schema_name)
        params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "schema": self.schema_name,
            "int_data": 255,
            "txt_data": "This is a test",
        }
        results = kpdb.executescript(conn, sqlscript, params=params, preprocessor=jinjasql.JinjaSql().prepare_query)
        self.assertEqual(results, [[True], [True], [1], [1], ["This is a test"], [True]])
