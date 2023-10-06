#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportParquetSummaryUpdater."""
from unittest.mock import patch

from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.ocp.ocp_report_parquet_summary_updater import OCPReportParquetSummaryUpdater
from masu.test import MasuTestCase
from masu.util.ocp.common import get_cluster_alias_from_cluster_id
from masu.util.ocp.common import get_cluster_id_from_provider


class OCPReportParquetSummaryUpdaterTest(MasuTestCase):
    """Test cases for the OCPReportParquetSummaryUpdater."""

    def test_valid_initialization(self):
        """Test the valid initialization of OCPReportParquetSummaryUpdater."""

        cluster_id = get_cluster_id_from_provider(self.ocp_provider_uuid)
        cluster_alias = get_cluster_alias_from_cluster_id(cluster_id)

        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(1)
        updater = OCPReportParquetSummaryUpdater(self.schema_name, self.ocp_provider, manifest)

        self.assertEqual(updater._cluster_id, cluster_id)
        self.assertEqual(updater._cluster_alias, cluster_alias)
        self.assertEqual(updater._schema, self.schema_name)
        self.assertEqual(updater._provider, self.ocp_provider)
        self.assertEqual(updater._manifest, manifest)

    @patch("masu.processor.ocp.ocp_report_parquet_summary_updater.get_cluster_id_from_provider")
    def test_missing_cluster_id_raises_error(self, mock_get_cluster_id):
        """Test the initialization of OCPReportParquetSummaryUpdater with no cluster_id."""

        mock_get_cluster_id.return_value = None
        with self.assertRaises(ValueError) as context:
            OCPReportParquetSummaryUpdater(self.schema_name, self.ocp_provider, "test_manifest")

        expected_error_msg = f"Missing cluster_id for provider: {self.ocp_provider.uuid}"
        self.assertEqual(str(context.exception), expected_error_msg)
