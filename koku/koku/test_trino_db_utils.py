import unittest
import uuid
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from jinjasql import JinjaSql
from trino.dbapi import Connection
from trino.exceptions import TrinoQueryError

from api.iam.test.iam_test_case import FakeTrinoConn
from api.iam.test.iam_test_case import FakeTrinoCur
from api.iam.test.iam_test_case import IamTestCase
from koku.trino_database import connect
from koku.trino_database import executescript
from koku.trino_database import TrinoStatementExecError


class TestTrinoDatabaseUtils(IamTestCase):
    @unittest.skipIf(getattr(settings, 'ONPREM', False), "Trino-specific test, skipped for ONPREM")
    def test_connect(self):
        """
        Test connection to trino returns trino.dbapi.Connection instance
        """
        conn = connect(schema=self.schema_name, catalog="hive")
        self.assertTrue(isinstance(conn, Connection))
        self.assertEqual(conn.schema, self.schema_name)
        self.assertEqual(conn.catalog, "hive")

    def test_executescript_jinja_conditionals(self):
        """
        Test that execute of a buffer with jinja conditionals.
        """
        sqlscript = """
{% if populate %}
SELECT * FROM hive.{{schema | sqlsafe}}.fake_table
{% endif %}
;
"""
        conn = FakeTrinoConn()
        params = {
            "schema": self.schema_name,
            "populate": False,
        }
        results = executescript(
            conn, sqlscript, params=params, preprocessor=JinjaSql(param_style="format").prepare_query
        )
        self.assertEqual(results, [])

    def test_executescript_empty_string(self):
        sqlscript = ""
        conn = FakeTrinoConn()
        params = {
            "schema": self.schema_name,
            "populate": False,
        }
        results = executescript(
            conn, sqlscript, params=params, preprocessor=JinjaSql(param_style="format").prepare_query
        )
        self.assertEqual(results, [])

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

select t_data
    from hive.{{schema | sqlsafe}}.__test_{{uuid | sqlsafe}}
where i_data = {{int_data}};

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

    @unittest.skipIf(getattr(settings, 'ONPREM', False), "Trino-specific test, skipped for ONPREM")
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
        self.assertTrue(logger.output)
        self.assertIn("TrinoQueryError", logger.output[0])

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

    @unittest.skipIf(getattr(settings, 'ONPREM', False), "Trino-specific test, skipped for ONPREM")
    def test_retry_logic_on_no_such_key_error(self):
        class FakeTrinoQueryError(Exception):
            def __init__(self, error):
                self.error = error
                self.message = error["message"]

        class FakeTrinoCur:
            def __init__(self, *args, **kwargs):
                self.execute_calls = 0

            def execute(self, *args, **kwargs):
                self.execute_calls += 1
                if self.execute_calls == 1:
                    raise FakeTrinoQueryError(
                        {
                            "errorName": "TRINO_NO_SUCH_KEY",
                            "errorType": "USER_ERROR",
                            "message": "NoSuchKey error occurred",
                            "query_id": "fake_query_id",
                        }
                    )
                return [["eek"]] * 6

            def fetchall(self):
                return [["eek"]] * 6

        class FakeTrinoConn:
            def __init__(self, *args, **kwargs):
                self.cur = FakeTrinoCur()

            def cursor(self):
                return self.cur

        sqlscript = "SELECT * FROM table"
        params = {
            "uuid": "some_uuid",
            "schema": "test_schema",
            "int_data": 255,
            "txt_data": "This is a test",
        }
        conn = FakeTrinoConn()

        with patch("time.sleep", return_value=None), self.assertRaises(FakeTrinoQueryError) as error_context:
            results = executescript(
                trino_conn=conn,
                sqlscript=sqlscript,
                params=params,
                preprocessor=None,
            )
            self.assertEqual(results, [["eek"]] * 6)

        self.assertIn("NoSuchKey error occurred", str(error_context.exception))
        self.assertEqual(conn.cur.execute_calls, 1)


@unittest.skipIf(getattr(settings, 'ONPREM', False), "Trino-specific test class, skipped for ONPREM")
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
