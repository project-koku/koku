#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the running_celery_tasks endpoint view."""
import base64
import json
import os
from decimal import Decimal
from unittest.mock import Mock
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse

from api.common import RH_IDENTITY_HEADER
from api.iam.test.iam_test_case import IamTestCase
from koku.configurator import CONFIGURATOR
from masu.api.db_performance.db_performance import DBPerformanceStats
from masu.api.db_performance.dbp_views import APPLICATION_DBNAME
from masu.api.db_performance.dbp_views import get_database_list
from masu.api.db_performance.dbp_views import get_limit_offset
from masu.api.db_performance.dbp_views import get_menu
from masu.api.db_performance.dbp_views import get_parameter_bool
from masu.api.db_performance.dbp_views import get_parameter_list
from masu.api.db_performance.dbp_views import make_db_options
from masu.api.db_performance.dbp_views import make_pagination


TEST_CONFIGURATOR = type("TEST_CONFIGURATOR", CONFIGURATOR.__bases__, dict(CONFIGURATOR.__dict__))


def _get_database_name():
    return f"test_{CONFIGURATOR.get_database_name()}"


TEST_CONFIGURATOR.get_database_name = staticmethod(_get_database_name)


class _dikt(dict):
    def dict(self):
        return self


@override_settings(ROOT_URLCONF="masu.urls")
class TestDBPerformance(IamTestCase):
    """Test cases for the running_celery_tasks endpoint."""

    def _get_headers(self):
        return self.request_context["request"].META.copy()

    def _get_identity(self):
        _ident_raw = self.request_context["request"].META[RH_IDENTITY_HEADER]
        return json.loads(base64.b64decode(_ident_raw).decode("utf-8"))

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_dbsettings(self, mok_middl):
        """Test the db settings view."""
        response = self.client.get(reverse("db_settings"), **self._get_headers())
        html = response.content.decode("utf-8")
        self.assertIn('id="generic_table"', html)
        self.assertIn("Database Settings", html)
        self.assertIn("application_name", html)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_lockinfo(self, mok_middl):
        """Test the lock information view."""
        response = self.client.get(reverse("lock_info"), **self._get_headers())
        html = response.content.decode("utf-8")
        self.assertIn('id="term_action_table"', html)
        self.assertIn("Lock Information", html)

        mock_ret_val = [
            {
                "blocking_pid": 10,
                "blocking_user": "eek",
                "blckng_proc_curr_stmt": "select 1",
                "blocked_pid": 11,
                "blocked_user": "eek",
                "blocked_statement": "select 1",
            }
        ]
        with patch(
            "masu.api.db_performance.db_performance.DBPerformanceStats.get_lock_info", return_value=mock_ret_val
        ):
            response = self.client.get(reverse("lock_info"), **self._get_headers())
            html = response.content.decode("utf-8")
            self.assertIn("Lock Information", html)
            self.assertIn("<button", html)
            self.assertIn("blocked_pid", html)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_conn_activity(self, mok_middl):
        """Test the stat activity view."""
        with DBPerformanceStats("KOKU", TEST_CONFIGURATOR) as dbp:
            activity = dbp.get_activity(TEST_CONFIGURATOR.get_database_name())
        pid = activity[0]["backend_pid"]
        state = activity[0]["state"]
        with patch(
            "koku.configurator.CONFIGURATOR.get_database_name", return_value=TEST_CONFIGURATOR.get_database_name()
        ):
            response = self.client.get(reverse("conn_activity"), **self._get_headers())
            html = response.content.decode("utf-8")
            self.assertIn('id="term_action_table"', html)
            self.assertIn("Connection Activity", html)
            self.assertIn("backend_pid", html)

            response = self.client.get(reverse("conn_activity"), {"pid": pid}, **self._get_headers())
            html = response.content.decode("utf-8")
            self.assertIn('id="term_action_table"', html)
            self.assertIn("Connection Activity", html)
            self.assertIn("backend_pid", html)

            response = self.client.get(reverse("conn_activity"), {"pid": [pid]}, **self._get_headers())
            html = response.content.decode("utf-8")
            self.assertIn('id="term_action_table"', html)
            self.assertIn("Connection Activity", html)
            self.assertIn("backend_pid", html)

            response = self.client.get(reverse("conn_activity"), {"state": state}, **self._get_headers())
            html = response.content.decode("utf-8")
            self.assertIn('id="term_action_table"', html)
            self.assertIn("Connection Activity", html)
            self.assertIn("backend_pid", html)

            response = self.client.get(reverse("conn_activity"), {"state": [state]}, **self._get_headers())
            html = response.content.decode("utf-8")
            self.assertIn('id="term_action_table"', html)
            self.assertIn("Connection Activity", html)
            self.assertIn("backend_pid", html)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_stmt_stats(self, mok_middl):
        """Test the stat statements view."""
        response = self.client.get(reverse("stmt_stats"), **self._get_headers())
        html = response.content.decode("utf-8")
        self.assertIn('id="stmt_stats_table"', html)
        self.assertIn("Statement Statistics", html)
        self.assertTrue("calls" in html or "Result" in html)

        mock_ret_val = [
            {
                "min_exec_time": Decimal("100.003"),
                "max_exec_time": Decimal("10000.003"),
                "mean_exec_time": Decimal("4250.8882"),
                "query": "select 1",
            }
        ]
        with patch(
            "masu.api.db_performance.db_performance.DBPerformanceStats.get_statement_stats", return_value=mock_ret_val
        ):
            response = self.client.get(reverse("stmt_stats"), **self._get_headers())
            html = response.content.decode("utf-8")
            self.assertIn('id="stmt_stats_table"', html)
            self.assertIn("Statement Statistics", html)
            self.assertTrue("#d16969;" in html)
            self.assertTrue("#c7d169;" in html)
            self.assertTrue("#69d172;" in html)
            self.assertTrue("SELECT" in html)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_pg_ver(self, mok_middl):
        """Test the db version view."""
        response = self.client.get(reverse("db_version"), **self._get_headers())
        html = response.content.decode("utf-8")
        self.assertIn('id="generic_table"', html)
        self.assertIn("PostgreSQL Engine Version", html)
        self.assertIn("postgresql_version", html)

    @patch("koku.middleware.MASU", return_value=True)
    def test_explain(self, mok_middl):
        """Test the db version view."""
        headers = self._get_headers()
        response = self.client.get(reverse("explain_query"), **headers)
        html = response.content.decode("utf-8")
        self.assertIn('id="div-sql-statement"', html)
        self.assertIn("Explain Query", html)

        headers["HTTP_X_REQUESTED_WITH"] = "XMLHttpRequest"
        payload = json.dumps({"sql_statement": "select 1"})
        response = self.client.post(reverse("explain_query"), payload, "json", **headers)
        self.assertEqual(response.status_code, 200)

        payload = json.dumps({"sql_statement": "select 1;\nselect 2;"})
        response = self.client.post(reverse("explain_query"), payload, "json", **headers)
        self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("koku.configurator.CONFIGURATOR.get_database_name", return_value=TEST_CONFIGURATOR.get_database_name())
    def test_get_schema_sizes(self, mod_conf, mok_middl):
        headers = self._get_headers()
        response = self.client.get(reverse("schema_sizes"), **headers)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("schema_name", html)
        self.assertIn("schema_size_gb", html)
        self.assertNotIn("table_name", html)

        headers["HTTP_X_REQUESTED_WITH"] = "XMLHttpRequest"
        response = self.client.get(reverse("schema_sizes"), {"top": "5"}, **headers)
        html = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("schema_name", html)
        self.assertIn("schema_size_gb", html)
        self.assertIn("table_name", html)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_menu(self, mok_middl):
        """Test the db version view."""
        res = get_menu("eek")
        self.assertNotIn("current", res)
        self.assertIn("DB Engine Version", res)
        self.assertIn("DB Engine Settings", res)
        self.assertIn("Connection Activity", res)
        self.assertIn("Statement Statistics", res)
        self.assertIn("Lock Information", res)
        self.assertIn("Schema Sizes", res)
        self.assertIn("Explain Query", res)

        res = get_menu("conn_activity")
        conn_activity = False
        for line in res.split(os.linesep):
            if not conn_activity and "Connection Activity" in line:
                conn_activity = self.assertIn("current", line)
            else:
                self.assertNotIn("current", line)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_limit_offset(self, mok_middl):
        _default_limit = 100
        request = Mock()

        request.query_params = {}
        limit, offset = get_limit_offset(request)
        self.assertEqual(limit, _default_limit)
        self.assertIsNone(offset)

        request.query_params = {"limit": "eek"}
        limit, offset = get_limit_offset(request)
        self.assertEqual(limit, _default_limit)
        self.assertIsNone(offset)

        request.query_params = {"limit": "200"}
        limit, offset = get_limit_offset(request)
        self.assertEqual(limit, 200)
        self.assertIsNone(offset)

        request.query_params = {"offset": ""}
        limit, offset = get_limit_offset(request)
        self.assertEqual(limit, _default_limit)
        self.assertIsNone(offset)

        request.query_params = {"offset": "eek"}
        limit, offset = get_limit_offset(request)
        self.assertEqual(limit, _default_limit)
        self.assertIsNone(offset)

        request.query_params = {"offset": "100"}
        limit, offset = get_limit_offset(request)
        self.assertEqual(limit, _default_limit)
        self.assertEqual(offset, 100)

        request.query_params = {"limit": "250", "offset": "150"}
        limit, offset = get_limit_offset(request)
        self.assertEqual(limit, 250)
        self.assertEqual(offset, 150)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_parameter_list(self, mok_middl):
        class QP:
            def __init__(self, initvalues=[]):
                self._qp = initvalues
                self._qp_keys = {p[0] for p in self._qp}

            def getlist(self, param, default=None):
                return [p[1] for p in self._qp if p[0] == param] or default

            def __contains__(self, param):
                return param in self._qp_keys

        request = Mock()

        request.query_params = QP()
        x = get_parameter_list(request, "a_param", "a_silly_default")
        self.assertEqual(x, "a_silly_default")

        request.query_params = QP([["a_param", "a_value"]])
        x = get_parameter_list(request, "a_param")
        self.assertEqual(x, ["a_value"])

        request.query_params = QP([["a_param", "a_value,b_value"]])
        x = get_parameter_list(request, "a_param")
        self.assertEqual(x, ["a_value", "b_value"])

        request.query_params = QP([["a_param", "a_value|b_value"]])
        x = get_parameter_list(request, "a_param", sep="|")
        self.assertEqual(x, ["a_value", "b_value"])

        request.query_params = QP([["a_param", "d_value"], ["a_param", "e_value"]])
        x = get_parameter_list(request, "a_param")
        self.assertEqual(x, ["d_value", "e_value"])

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_parameter_bool(self, mok_middl):
        request = Mock()

        request.query_params = {}
        self.assertTrue(get_parameter_bool(request, "a_param", "a_silly_default"))

        self.assertFalse(get_parameter_bool(request, "a_param", 0))

        self.assertIsNone(get_parameter_bool(request, "a_param"))

        request.query_params = {"a_param": "nope"}
        self.assertFalse(get_parameter_bool(request, "a_param"))

        truthy = ("1", "y", "yes", "t", "true", "on")
        for p_val in truthy:
            request.query_params["a_param"] = p_val
            self.assertTrue(get_parameter_bool(request, "a_param"))

    @patch("koku.middleware.MASU", return_value=True)
    def test_make_pagination(self, mok_middl):
        request = Mock()
        data = ["a"] * 10
        request.query_params = _dikt(limit=10, offset=0)
        path = reverse("schema_sizes")

        # test full first page
        res = make_pagination(10, None, data, request, "schema_sizes")
        self.assertIn(path, res)
        self.assertEqual(res.count("<span"), 2)
        self.assertEqual(res.count("<a"), 1)
        self.assertIn("limit=20", res)
        self.assertIn("offset=10", res)

        # test middle of pages
        request.query_params["limit"] = 20
        request.query_params["offset"] = 10
        res = make_pagination(20, 10, data, request, "schema_sizes")
        self.assertIn(path, res)
        self.assertEqual(res.count("<span"), 1)
        self.assertEqual(res.count("<a"), 2)
        self.assertIn("limit=10", res)
        self.assertIn("offset=0", res)
        self.assertIn("limit=30", res)
        self.assertIn("offset=20", res)

        # test end of pages
        request.query_params["limit"] = 20
        request.query_params["offset"] = 10
        data = data[:2]
        res = make_pagination(20, 10, data, request, "schema_sizes")
        self.assertIn(path, res)
        self.assertEqual(res.count("<span"), 2)
        self.assertEqual(res.count("<a"), 1)
        self.assertIn("limit=10", res)
        self.assertIn("offset=0", res)

        # test no pagination
        request.query_params["limit"] = 10
        request.query_params["offset"] = 0
        res = make_pagination(10, 0, data, request, "schema_sizes")
        self.assertFalse(path in res)
        self.assertEqual(res.count("<span"), 3)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_database_list(self, mok_middl):
        with DBPerformanceStats("KOKU", TEST_CONFIGURATOR) as dbps:
            res = get_database_list(dbps)
            self.assertIn(APPLICATION_DBNAME, res[0])

    @patch("koku.middleware.MASU", return_value=True)
    def test_make_db_options(self, mok_middl):
        request = Mock()
        target_db = TEST_CONFIGURATOR.get_database_name()
        request.query_params = _dikt(dbname=target_db)

        with DBPerformanceStats("KOKU", TEST_CONFIGURATOR) as dbps:
            databases = get_database_list(dbps)
            res = make_db_options(databases, target_db, request, "schema_sizes")
            found = False
            for line in res.split(os.linesep):
                found = target_db in line
                if found:
                    self.assertIn("selected", line)
                    break
            self.assertTrue(found)
