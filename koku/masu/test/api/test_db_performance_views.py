#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the running_celery_tasks endpoint view."""
import base64
import json
import logging
from decimal import Decimal
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse

from api.common import RH_IDENTITY_HEADER
from api.iam.test.iam_test_case import IamTestCase


LOG = logging.getLogger(__name__)


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
        response = self.client.get(reverse("conn_activity"), **self._get_headers())
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
        self.assertIn("Explain SQL Statement", html)

        headers["HTTP_X_REQUESTED_WITH"] = "XMLHttpRequest"
        payload = json.dumps({"sql_statement": "select 1"})
        response = self.client.post(reverse("explain_query"), payload, "json", **headers)
        self.assertEqual(response.status_code, 200)

        payload = json.dumps({"sql_statement": "select 1;\nselect 2;"})
        response = self.client.post(reverse("explain_query"), payload, "json", **headers)
        self.assertEqual(response.status_code, 200)
