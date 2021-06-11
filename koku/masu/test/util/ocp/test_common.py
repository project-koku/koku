#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP util."""
import os
import shutil
import tempfile
from unittest.mock import patch
from uuid import UUID

import pandas as pd

from masu.config import Config
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from masu.util.ocp import common as utils


class OCPUtilTests(MasuTestCase):
    """Test the OCP utility functions."""

    def setUp(self):
        """Shared variables used by ocp common tests."""
        super().setUp()
        self.accessor = OCPReportDBAccessor(schema=self.schema)
        self.provider_accessor = ProviderDBAccessor(provider_uuid=self.ocp_test_provider_uuid)
        self.report_schema = self.accessor.report_schema
        self.creator = ReportObjectCreator(self.schema)
        self.all_tables = list(OCP_REPORT_TABLE_MAP.values())

        self.provider_uuid = self.provider_accessor.get_provider().uuid
        reporting_period = self.creator.create_ocp_report_period(provider_uuid=self.provider_uuid)
        report = self.creator.create_ocp_report(reporting_period, reporting_period.report_period_start)
        self.creator.create_ocp_usage_line_item(reporting_period, report)
        self.creator.create_ocp_storage_line_item(reporting_period, report)
        self.creator.create_ocp_node_label_line_item(reporting_period, report)

    def test_get_cluster_id_from_provider(self):
        """Test that the cluster ID is returned from OCP provider."""
        cluster_id = utils.get_cluster_id_from_provider(self.ocp_test_provider_uuid)
        self.assertIsNotNone(cluster_id)

    def test_get_cluster_id_from_non_ocp_provider(self):
        """Test that None is returned when getting cluster ID on non-OCP provider."""
        cluster_id = utils.get_cluster_id_from_provider(self.aws_provider_uuid)
        self.assertIsNone(cluster_id)

    def test_get_cluster_alias_from_cluster_id(self):
        """Test that the cluster alias is returned from cluster_id."""
        cluster_id = self.ocp_cluster_id
        cluster_alias = utils.get_cluster_alias_from_cluster_id(cluster_id)
        self.assertIsNotNone(cluster_alias)

    def test_get_provider_uuid_from_cluster_id(self):
        """Test that the provider uuid is returned for a cluster ID."""
        cluster_id = self.ocp_cluster_id
        provider_uuid = utils.get_provider_uuid_from_cluster_id(cluster_id)
        try:
            UUID(provider_uuid)
        except ValueError:
            self.fail("{} is not a valid uuid.".format(str(provider_uuid)))

    def test_get_provider_uuid_from_invalid_cluster_id(self):
        """Test that the provider uuid is not returned for an invalid cluster ID."""
        cluster_id = "bad_cluster_id"
        provider_uuid = utils.get_provider_uuid_from_cluster_id(cluster_id)
        self.assertIsNone(provider_uuid)

    def test_poll_ingest_override_for_provider(self):
        """Test that OCP polling override returns True if insights local path exists."""
        fake_dir = tempfile.mkdtemp()
        with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
            cluster_id = utils.get_cluster_id_from_provider(self.ocp_test_provider_uuid)
            expected_path = f"{Config.INSIGHTS_LOCAL_REPORT_DIR}/{cluster_id}/"
            os.makedirs(expected_path, exist_ok=True)
            self.assertTrue(utils.poll_ingest_override_for_provider(self.ocp_test_provider_uuid))
        shutil.rmtree(fake_dir)

    def test_process_openshift_datetime(self):
        """Test process_openshift_datetime method with good and bad values."""
        expected_dt_str = "2020-07-01 00:00:00"
        expected = pd.to_datetime(expected_dt_str)
        dt = utils.process_openshift_datetime("2020-07-01 00:00:00 +0000 UTC")
        self.assertEqual(expected, dt)
