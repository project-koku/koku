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

from django.core.exceptions import PermissionDenied
from django.test.utils import override_settings
from django.urls import reverse

from api.common import RH_IDENTITY_HEADER
from api.iam.test.iam_test_case import IamTestCase
from masu.api.db_performance.dbp_views import get_identity
from masu.api.db_performance.dbp_views import get_identity_username
from masu.api.db_performance.dbp_views import validate_identity


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
        self.assertIn('id="generic_table"', html)
        self.assertIn("Lock Information", html)

        # response = self.client.get(reverse('lock_info'), {"terminate": "enable"}, **self._get_headers())
        # self.assertIn('id="term_action_table"', html)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_conn_activity(self, mok_middl):
        """Test the stat activity view."""
        response = self.client.get(reverse("conn_activity"), **self._get_headers())
        html = response.content.decode("utf-8")
        self.assertIn('id="generic_table"', html)
        self.assertIn("Connection Activity", html)
        self.assertIn("backend_pid", html)

        # response = self.client.get(reverse('conn_activity'), {"terminate": "enable"}, **self._get_headers())
        # self.assertIn('id="term_action_table"', html)
        # self.assertIn('id="cancel-', html)
        # self.assertIn('id="terminate-', html)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_stmt_stats(self, mok_middl):
        """Test the stat statements view."""
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

    @patch("koku.middleware.MASU", return_value=True)
    def test_cancel_conn(self, mok_middl):
        """Test the cancel backend interface."""
        _headers = self._get_headers()
        response = self.client.get(reverse("db_cancel_connection"), **_headers)
        data = json.loads(response.content)
        self.assertEqual(data, {})

        # _headers["PARAM_DB_CONNID"] = -199
        # response = self.client.get(reverse("db_cancel_connection"), **_headers)
        # data = json.loads(response.content)
        # self.assertEqual(data, [{"pid": -199, "cancel": False}])

    @patch("koku.middleware.MASU", return_value=True)
    def test_terminate_conn(self, mok_middl):
        """Test the terminate backend interface."""
        _headers = self._get_headers()
        response = self.client.get(reverse("db_terminate_connection"), **_headers)
        data = json.loads(response.content)
        self.assertEqual(data, {})

        # _headers["PARAM_DB_CONNID"] = -199
        # response = self.client.get(reverse("db_terminate_connection"), **_headers)
        # data = json.loads(response.content)
        # self.assertEqual(data, [{"pid": -199, "terminate": False}])

    @skip("Lingering issue with pg_stat_statement_extension in jenkins env")
    @patch("koku.middleware.MASU", return_value=True)
    def test_reset_stats(self, mok_middl):
        """Test the statement stats reset interface."""
        response = self.client.get(reverse("clear_statement_statistics"), **self._get_headers())
        data = json.loads(response.content)
        self.assertEqual(data, [{"pg_stat_statements_reset": True}])

    def test_validate_identity(self):
        """Test validity checks of RH identity header"""
        _identity = self._get_identity()
        exc = None
        try:
            validate_identity(_identity)
        except Exception as e:
            exc = e
        self.assertEqual(exc, None)

        with self.assertRaises(PermissionDenied):
            validate_identity({})

        _missing_username = _identity.copy()
        _missing_username["identity"]["user"]["username"] = ""
        with self.assertRaises(PermissionDenied):
            validate_identity(_missing_username)

        _missing_email = _identity.copy()
        _missing_email["identity"]["user"]["email"] = ""
        with self.assertRaises(PermissionDenied):
            validate_identity(_missing_email)

        _bad_type = _identity.copy()
        _bad_type["identity"]["type"] = "eek"
        with self.assertRaises(PermissionDenied):
            validate_identity(_bad_type)

        _missing_user = _identity.copy()
        _missing_user["identity"]["user"] = None
        with self.assertRaises(PermissionDenied):
            validate_identity(_missing_user)

        _not_entitled = _identity.copy()
        _not_entitled["entitlements"]["cost_management"]["is_entitled"] = False
        with self.assertRaises(PermissionDenied):
            validate_identity(_not_entitled)

        _not_entitled_at_all = _identity.copy()
        _not_entitled_at_all["entitlements"] = {}
        with self.assertRaises(PermissionDenied):
            validate_identity(_not_entitled_at_all)

    def test_get_identity(self):
        """Test retrieval and parse of RH identity header"""
        self.assertEqual(get_identity(self.request_context["request"]), self._get_identity())

    def test_get_identity_username(self):
        """Test retrieval and parse of RH identity header"""
        _identity = self._get_identity()
        expected = f'{_identity["identity"]["user"]["username"]} ({_identity["identity"]["user"]["email"]})'
        _username = get_identity_username(self.request_context["request"])
        self.assertEqual(_username, expected)
