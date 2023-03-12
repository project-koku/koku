import uuid

from jinjasql import JinjaSql
from trino.dbapi import Connection

from . import trino_database as trino_db
from api.iam.test.iam_test_case import FakePrestoConn
from api.iam.test.iam_test_case import FakePrestoCur
from api.iam.test.iam_test_case import IamTestCase


class TestPrestoDatabaseUtils(IamTestCase):
    def test_connect(self):
        """
        Test connection to presto returns presto.dbapi.Connection instance
        """
        conn = trino_db.connect(schema=self.schema_name, catalog="hive")
        self.assertTrue(isinstance(conn, Connection))
        self.assertEqual(conn.schema, self.schema_name)
        self.assertEqual(conn.catalog, "hive")

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
        results = trino_db.executescript(conn, sqlscript, params=params, preprocessor=JinjaSql().prepare_query)
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
        with self.assertRaises(trino_db.PreprocessStatementError):
            trino_db.executescript(conn, sqlscript, params=params, preprocessor=JinjaSql().prepare_query)

    def test_executescript_no_preprocess(self):
        """
        Test executescript will raise a preprocessor error
        """
        sqlscript = """
select x from y;
select a from b;
"""
        conn = FakePrestoConn()
        res = trino_db.executescript(conn, sqlscript)
        self.assertEqual(res, [["eek"], ["eek"]])

    def test_preprocessor_err(self):
        def t_preprocessor(*args):
            raise TypeError("This is a test")

        sqlscript = """
select x from y;
select a from b;
"""
        params = {"eek": 1}
        conn = FakePrestoConn()
        with self.assertRaises(trino_db.PreprocessStatementError):
            trino_db.executescript(conn, sqlscript, params=params, preprocessor=t_preprocessor)

    def test_executescript_error(self):
        def t_exec_error(*args, **kwargs):
            raise ValueError("Nope!")

        class FakerFakePrestoCur(FakePrestoCur):
            def execute(*args, **kwargs):
                t_exec_error(*args, **kwargs)

        class FakerFakePrestoConn(FakePrestoConn):
            def cursor(self):
                return FakerFakePrestoCur()

        sqlscript = """
select x from y;
select a from b;
"""
        with self.assertRaises(trino_db.TrinoStatementExecError):
            conn = FakerFakePrestoConn()
            trino_db.executescript(conn, sqlscript)
