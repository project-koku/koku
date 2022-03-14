#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.db import connection

from api.iam.test.iam_test_case import IamTestCase
from koku.configurator import CONFIGURATOR
from masu.api.db_performance.db_performance import DBPerformanceStats
from masu.api.db_performance.db_performance import SERVER_VERSION
from masu.test.api.db_perf_test_common import verify_pg_stat_statements


class TestDBPerformanceClass(IamTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        conn = connection.connection
        with conn.cursor() as cur:
            cur.execute("create extension if not exists pg_stat_statements;;")

    def test_separate_connection(self):
        """Test that the DBPerformanceStats class uses a separate connetion"""
        with DBPerformanceStats("KOKU", CONFIGURATOR) as dbp:
            self.assertNotEqual(dbp.conn, connection.connection)
            _conn = dbp.conn
        self.assertTrue(_conn.closed)

    def test_del_closes_connection(self):
        """Test that instance delete closes the connection"""
        dbp = DBPerformanceStats("KOKU", CONFIGURATOR)
        _conn = dbp.conn
        self.assertFalse(_conn.closed)
        del dbp
        self.assertTrue(_conn.closed)

    def test_get_db_version(self):
        """Test that the db engine version can be retrieved."""
        with DBPerformanceStats("KOKU", CONFIGURATOR) as dbp:
            ver = dbp.get_pg_engine_version()
            self.assertEqual(ver, SERVER_VERSION)
            self.assertTrue(all(isinstance(v, int) for v in ver))

    def test_get_dbsettings(self):
        """Test that the current settings are retrieved from the databsae."""
        with DBPerformanceStats("KOKU", CONFIGURATOR) as dbp:
            settings = dbp.get_pg_settings()
            self.assertTrue(len(settings) > 0)
            self.assertIn("application_name", (s["name"] for s in settings))

            expected_nsmes = {"application_name", "search_path"}
            settings = dbp.get_pg_settings(setting_names=list(expected_nsmes))
            self.assertEqual({s["name"] for s in settings}, expected_nsmes)

    def test_handle_limit(self):
        """Test handle limit clause."""
        with DBPerformanceStats("KOKU", CONFIGURATOR) as dbp:
            params = {}
            res = dbp._handle_limit(None, params)
            self.assertEqual(res, "")
            self.assertEqual(params, {})

            res = dbp._handle_limit(10, params)
            self.assertEqual(res.strip(), "limit %(limit)s")
            self.assertEqual(params, {"limit": 10})

    def test_handle_offset(self):
        """Test handle offset clause."""
        with DBPerformanceStats("KOKU", CONFIGURATOR) as dbp:
            params = {}
            res = dbp._handle_offset(None, params)
            self.assertEqual(res, "")
            self.assertEqual(params, {})

            res = dbp._handle_offset(10, params)
            self.assertEqual(res.strip(), "offset %(offset)s")
            self.assertEqual(params, {"offset": 10})

    def test_handle_lockinfo(self):
        with DBPerformanceStats("KOKU", CONFIGURATOR) as dbp:
            lockinfo = dbp.get_lock_info()
            self.assertNotEqual(lockinfo, [])  # This should always return a list of at least one element

    def test_get_conn_activity(self):
        """Test that the correct connection activty is returned."""
        with DBPerformanceStats("KOKU", CONFIGURATOR) as dbp:
            dbpid = dbp.conn.get_backend_pid()
            activity = dbp.get_activity()
            self.assertTrue(all(a["backend_pid"] != dbpid for a in activity))

            activity = dbp.get_activity(include_self=True)
            self.assertTrue(any(a["backend_pid"] == dbpid for a in activity))

            activity = dbp.get_activity(include_self=True, pid=[dbpid])
            self.assertTrue(all(a["backend_pid"] == dbpid for a in activity))

            activity = dbp.get_activity(state=["COMPLETELY INVALID STATE HERE!"])
            self.assertEqual(activity, [])

    def test_get_stmt_stats(self):
        """Test that statement statistics are returned."""
        verify_pg_stat_statements()
        with DBPerformanceStats("KOKU", CONFIGURATOR) as dbp:
            stats = dbp.get_statement_stats()
            self.assertTrue(0 < len(stats) <= 100)
            self.assertIn("calls", stats[0])
