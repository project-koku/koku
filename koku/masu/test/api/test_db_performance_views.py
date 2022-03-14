#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the running_celery_tasks endpoint view."""
import base64
import json
import logging
from unittest import skip
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse

from api.common import RH_IDENTITY_HEADER
from api.iam.test.iam_test_case import IamTestCase
from masu.test.api.db_perf_test_common import verify_pg_stat_statements


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

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_conn_activity(self, mok_middl):
        """Test the stat activity view."""
        response = self.client.get(reverse("conn_activity"), **self._get_headers())
        html = response.content.decode("utf-8")
        self.assertIn('id="term_action_table"', html)
        self.assertIn("Connection Activity", html)
        self.assertIn("backend_pid", html)

    @skip("Lingering issue with pg_stat_statement_extension in jenkins env")
    @patch("koku.middleware.MASU", return_value=True)
    def test_get_stmt_stats(self, mok_middl):
        """Test the stat statements view."""
        verify_pg_stat_statements()
        response = self.client.get(reverse("stmt_stats"), **self._get_headers())
        html = response.content.decode("utf-8")
        self.assertIn('id="stmt_stats_table"', html)
        self.assertIn("Statement Statistics", html)
        self.assertIn("calls", html)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_pg_ver(self, mok_middl):
        """Test the db version view."""
        response = self.client.get(reverse("db_version"), **self._get_headers())
        html = response.content.decode("utf-8")
        self.assertIn('id="generic_table"', html)
        self.assertIn("PostgreSQL Engine Version", html)
        self.assertIn("postgresql_version", html)
