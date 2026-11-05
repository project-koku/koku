#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for drop_stale_clones, the only part of the stale test DB check that destroys anything.

It runs DROP DATABASE, so these tests pin which databases it may drop. They also exercise
fixture_state and fixture_data_is_stale through real databases.
"""
from datetime import date

from django.db import connections
from django.test import TestCase

from koku.koku_test_runner import _connect
from koku.koku_test_runner import drop_stale_clones
from koku.koku_test_runner import KokuTestRunner

SCHEMA = KokuTestRunner.schema


class DropStaleClonesTest(TestCase):
    """drop_stale_clones drops parallel clones (<test DB>_<n>) that are stale, or all of them."""

    def setUp(self):
        self.connection = connections["default"]
        self.test_db = self.connection.settings_dict["NAME"]
        self.clone = f"{self.test_db}_97"
        self.today = date(2026, 11, 4)

    def tearDown(self):
        self._admin(f'DROP DATABASE IF EXISTS "{self.clone}"')

    def _admin(self, statement, dbname=None):
        admin = _connect(self.connection, dbname or self.test_db)
        admin.autocommit = True
        try:
            with admin.cursor() as cursor:
                cursor.execute(statement)
                return cursor.fetchall() if cursor.description else None
        finally:
            admin.close()

    def _clone_exists(self):
        return bool(self._admin(f"SELECT 1 FROM pg_database WHERE datname = '{self.clone}'"))

    def _create_clone(self, newest_report_period=None):
        self._admin(f'CREATE DATABASE "{self.clone}"')
        if newest_report_period:
            self._admin(f"CREATE SCHEMA {SCHEMA}", self.clone)
            self._admin(
                f"CREATE TABLE {SCHEMA}.reporting_ocpusagereportperiod (report_period_start timestamptz)", self.clone
            )
            self._admin(
                f"INSERT INTO {SCHEMA}.reporting_ocpusagereportperiod VALUES ('{newest_report_period}T00:00:00Z')",
                self.clone,
            )

    def test_stale_clone_is_dropped(self):
        self._create_clone(newest_report_period="2026-10-01")
        drop_stale_clones(self.connection, self.test_db, SCHEMA, self.today, drop_all=False)
        self.assertFalse(self._clone_exists())

    def test_fresh_clone_is_kept(self):
        self._create_clone(newest_report_period="2026-11-01")
        drop_stale_clones(self.connection, self.test_db, SCHEMA, self.today, drop_all=False)
        self.assertTrue(self._clone_exists())

    def test_clone_without_fixtures_is_dropped(self):
        """Django would reuse an incomplete clone under KEEPDB, so it is dropped."""
        self._create_clone()
        drop_stale_clones(self.connection, self.test_db, SCHEMA, self.today, drop_all=False)
        self.assertFalse(self._clone_exists())

    def test_drop_all_drops_fresh_clones(self):
        self._create_clone(newest_report_period="2026-11-01")
        drop_stale_clones(self.connection, self.test_db, SCHEMA, self.today, drop_all=True)
        self.assertFalse(self._clone_exists())
