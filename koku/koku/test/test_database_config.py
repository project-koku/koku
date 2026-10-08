#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the PostgreSQL session options in the database config."""
import os
from unittest.mock import patch

from django.test import SimpleTestCase

from koku import database


class DatabaseSessionOptionsTest(SimpleTestCase):
    """Session options come from optional environment variables."""

    def test_no_options_by_default(self):
        """Without the variables the server defaults apply."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_STATEMENT_TIMEOUT_MS", None)
            os.environ.pop("DATABASE_CLIENT_CONNECTION_CHECK_INTERVAL_MS", None)
            self.assertEqual(database._session_options(), "")
            self.assertNotIn("options", database.config()["OPTIONS"])

    def test_both_options(self):
        """Both settings are passed to PostgreSQL as -c options."""
        env = {"DATABASE_STATEMENT_TIMEOUT_MS": "30000", "DATABASE_CLIENT_CONNECTION_CHECK_INTERVAL_MS": "5000"}
        with patch.dict(os.environ, env):
            options = database.config()["OPTIONS"]
        self.assertEqual(options["options"], "-c statement_timeout=30000 -c client_connection_check_interval=5000")
        self.assertIn("application_name", options)

    def test_zero_disables_a_setting(self):
        """A value of 0 leaves that setting out."""
        env = {"DATABASE_STATEMENT_TIMEOUT_MS": "30000", "DATABASE_CLIENT_CONNECTION_CHECK_INTERVAL_MS": "0"}
        with patch.dict(os.environ, env):
            self.assertEqual(database._session_options(), "-c statement_timeout=30000")
