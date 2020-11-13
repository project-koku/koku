import datetime
import uuid

from jinjasql import JinjaSql
from prestodb.dbapi import Connection

from . import presto_database as kpdb
from api.iam.test.iam_test_case import FakePrestoConn
from api.iam.test.iam_test_case import IamTestCase


class TestPrestoDatabaseUtils(IamTestCase):
    def test_connect(self):
        """
        Test connection to presto returns presto.dbapi.Connection instance
        """
        conn = kpdb.connect(schema=self.schema_name, catalog="hive")
        self.assertTrue(isinstance(conn, Connection))
        self.assertEqual(conn.schema, self.schema_name)
        self.assertEqual(conn.catalog, "hive")

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

    def test_executescript(self):
        """
        Test execution of a buffer containing multiple statements
        """
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
        conn = FakePrestoConn()
        params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "schema": self.schema_name,
            "int_data": 255,
            "txt_data": "This is a test",
        }
        results = kpdb.executescript(conn, sqlscript, params=params, preprocessor=JinjaSql().prepare_query)
        self.assertEqual(results, [["eek"], ["eek"], ["eek"], ["eek"], ["eek"], ["eek"]])

    def test_executescript_err(self):
        """
        Test executescript will raise a preprocessor error
        """
        conn = FakePrestoConn()
        sqlscript = """
select * from eek where val1 in {{val_list}};
"""
        params = {"val_list": (1, 2, 3, 4, 5)}
        with self.assertRaises(kpdb.PreprocessStatementError):
            kpdb.executescript(conn, sqlscript, params=params, preprocessor=JinjaSql().prepare_query)

    def test_executescript_no_preprocess(self):
        """
        Test executescript will raise a preprocessor error
        """
        sqlscript = """
select x from y;
select a from b;
"""
        conn = FakePrestoConn()
        res = kpdb.executescript(conn, sqlscript)
        self.assertEqual(res, [["eek"], ["eek"]])
