import uuid

from django.test import TestCase
from jinjasql import JinjaSql
from trino.dbapi import Connection
from trino.exceptions import TrinoQueryError

from api.iam.test.iam_test_case import FakeTrinoConn
from api.iam.test.iam_test_case import FakeTrinoCur
from api.iam.test.iam_test_case import IamTestCase
from koku.trino_database import connect
from koku.trino_database import executescript
from koku.trino_database import PreprocessStatementError
from koku.trino_database import TrinoStatementExecError


class TestTrinoDatabaseUtils(IamTestCase):
    def test_connect(self):
        """
        Test connection to trino returns trino.dbapi.Connection instance
        """
        conn = connect(schema=self.schema_name, catalog="hive")
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
        conn = FakeTrinoConn()
        params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "schema": self.schema_name,
            "int_data": 255,
            "txt_data": "This is a test",
        }
        results = executescript(
            conn, sqlscript, params=params, preprocessor=JinjaSql(param_style="format").prepare_query
        )
        self.assertEqual(results, [["eek"], ["eek"], ["eek"], ["eek"], ["eek"], ["eek"]])

    def test_executescript_no_preprocessor_error(self):
        """
        Test executescript will not raise a preprocessor error
        """
        sqlscript = """
select x from y;
select a from b;
"""
        conn = FakeTrinoConn()
        res = executescript(conn, sqlscript)
        self.assertEqual(res, [["eek"], ["eek"]])

    def test_executescript_trino_error(self):
        """
        Test that executescirpt will raise a TrinoStatementExecError
        """

        class FakeTrinoConn:
            @property
            def cursor(self):
                raise TrinoQueryError(
                    {
                        "errorName": "REMOTE_TASK_ERROR",
                        "errorType": "INTERNAL_ERROR",
                        "message": "Expected response code",
                    }
                )

        with (
            self.assertRaisesRegex(TrinoStatementExecError, "type=INTERNAL_ERROR"),
            self.assertLogs("koku.trino_database", level="WARN") as logger,
        ):
            executescript(FakeTrinoConn(), "SELECT x from y")

        self.assertIn("WARNING:koku.trino_database:Trino Query Error", logger.output[0])

    def test_preprocessor_error(self):
        def t_preprocessor(*args):
            raise TypeError("This is a test")

        sqlscript = """
select x from y;
select a from b;
"""
        params = {"eek": 1}
        conn = FakeTrinoConn()
        with self.assertRaises(PreprocessStatementError):
            executescript(conn, sqlscript, params=params, preprocessor=t_preprocessor)

    def test_executescript_error(self):
        def t_exec_error(*args, **kwargs):
            raise ValueError("Nope!")

        class FakerFakeTrinoCur(FakeTrinoCur):
            def execute(*args, **kwargs):
                t_exec_error(*args, **kwargs)

        class FakerFakeTrinoConn(FakeTrinoConn):
            def cursor(self):
                return FakerFakeTrinoCur()

        sqlscript = """
select x from y;
select a from b;
"""
        with self.assertRaises(ValueError):
            conn = FakerFakeTrinoConn()
            executescript(conn, sqlscript)


class TestTrinoStatementExecError(TestCase):
    def test_trino_statement_exec_error(self):
        """Test TestTrinoStatementExecError behavior"""

        trino_query_error = TrinoQueryError(
            {
                "errorName": "REMOTE_TASK_ERROR",
                "errorCode": 99,
                "errorType": "INTERNAL_ERROR",
                "failureInfo": {"type": "CLOUD_TROUBLES"},
                "message": "Expected response code",
                "errorLocation": {"lineNumber": 42, "columnNumber": 24},
            },
            query_id="20231220_165606_25626_c7r5y",
        )

        trino_statement_error = TrinoStatementExecError("SELECT x from y", 1, {}, trino_query_error)

        expected_str = (
            "Trino Query Error (TrinoQueryError) : TrinoQueryError(type=INTERNAL_ERROR, name=REMOTE_TASK_ERROR, "
            'message="Expected response code", query_id=20231220_165606_25626_c7r5y) statement number 1\n'
            "Statement: SELECT x from y\n"
            "Parameters: {}"
        )
        expected_repr = (
            "TrinoStatementExecError("
            "type=INTERNAL_ERROR, "
            "name=REMOTE_TASK_ERROR, "
            "message=Expected response code, "
            "query_id=20231220_165606_25626_c7r5y)"
        )
        self.assertEqual(str(trino_statement_error), expected_str)
        self.assertEqual(repr(trino_statement_error), expected_repr)
        self.assertEqual(trino_statement_error.error_code, 99)
        self.assertEqual(trino_statement_error.error_exception, "CLOUD_TROUBLES")
        self.assertEqual(trino_statement_error.failure_info, {"type": "CLOUD_TROUBLES"})
