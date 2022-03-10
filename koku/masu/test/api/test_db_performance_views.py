#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the running_celery_tasks endpoint view."""
import logging
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse

from api.iam.test.iam_test_case import IamTestCase


LOG = logging.getLogger(__name__)


@override_settings(ROOT_URLCONF="masu.urls")
class TestDBPerformance(IamTestCase):
    """Test cases for the running_celery_tasks endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_dbsettings(self, mok_middl):
        response = self.client.get(reverse("db_settings"))
        html = response.content.decode("utf-8")
        self.assertIn('id="generic_table"', html)
        self.assertIn("Database Settings", html)
        self.assertIn("application_name", html)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_lockinfo(self, mok_middl):
        response = self.client.get(reverse("lock_info"))
        html = response.content.decode("utf-8")
        self.assertIn('id="generic_table"', html)
        self.assertIn("Lock Information", html)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_conn_activity(self, mok_middl):
        response = self.client.get(reverse("conn_activity"))
        html = response.content.decode("utf-8")
        self.assertIn('id="generic_table"', html)
        self.assertIn("Connection Activity", html)
        self.assertIn("backend_pid", html)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_stmt_stats(self, mok_middl):
        response = self.client.get(reverse("stmt_stats"))
        html = response.content.decode("utf-8")
        self.assertIn('id="generic_table"', html)
        self.assertIn("Statement Statistics", html)
        self.assertIn("calls", html)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_pg_ver(self, mok_middl):
        response = self.client.get(reverse("db_version"))
        html = response.content.decode("utf-8")
        self.assertIn('id="generic_table"', html)
        self.assertIn("PostgreSQL Engine Version", html)
        self.assertIn("postgresql_version", html)
