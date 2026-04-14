#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for OCP daily summary pod schema alignment."""
import re
from pathlib import Path
from unittest import TestCase

from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.self_hosted_models import OCPUsageLineItemDailySummaryStaging


class OCPDailySummarySchemaTest(TestCase):
    """Validate pod column support in OCP daily summary models and SQL."""

    def _assert_insert_columns_include_pod(self, sql):
        """Verify each INSERT column list includes pod to avoid SELECT/INSERT mismatches."""
        insert_matches = list(re.finditer(r"INSERT INTO .*?\((.*?)\)\s*(?:--|SELECT)", sql, re.DOTALL | re.IGNORECASE))
        self.assertGreater(len(insert_matches), 0)
        for match in insert_matches:
            columns = [column.strip().lower() for column in match.group(1).split(",")]
            self.assertIn("pod", columns)

    def test_ocp_usage_line_item_daily_summary_has_pod_field(self):
        """Ensure the tenant summary model preserves the pod dimension."""
        self.assertIn("pod", [field.name for field in OCPUsageLineItemDailySummary._meta.fields])

    def test_ocp_usage_line_item_daily_summary_staging_has_pod_field(self):
        """Ensure the self-hosted staging model preserves the pod dimension."""
        self.assertIn("pod", [field.name for field in OCPUsageLineItemDailySummaryStaging._meta.fields])

    def test_self_hosted_summary_sql_persists_pod(self):
        """Ensure the self-hosted SQL template inserts pod into summary tables."""
        sql = Path(
            "koku/masu/database/self_hosted_sql/openshift/reporting_ocpusagelineitem_daily_summary.sql"
        ).read_text()
        self.assertIn("    pod,\n", sql)
        self.assertIn("    pua.pod,\n", sql)
        self.assertIn("    sua.pod,\n", sql)
        self._assert_insert_columns_include_pod(sql)

    def test_trino_summary_sql_persists_pod(self):
        """Ensure the Trino SQL template inserts pod into summary tables."""
        sql = Path("koku/masu/database/trino_sql/openshift/reporting_ocpusagelineitem_daily_summary.sql").read_text()
        self.assertIn("    pod varchar,\n", sql)
        self.assertIn("    pua.pod,\n", sql)
        self.assertIn("    sua.pod,\n", sql)
        self._assert_insert_columns_include_pod(sql)
