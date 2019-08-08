#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Test the OCP util."""
import os
from uuid import UUID

from unittest.mock import patch

import tempfile
import shutil

from masu.util.ocp import common as utils
from masu.exceptions import MasuProviderError
from masu.config import Config
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.test.database.helpers import ReportObjectCreator
from masu.exceptions import MasuConfigurationError, MasuProviderError

from masu.test import MasuTestCase


class OCPUtilTests(MasuTestCase):
    """Test the OCP utility functions."""

    def setUp(self):
        super().setUp()
        self.common_accessor = ReportingCommonDBAccessor()
        self.column_map = self.common_accessor.column_map
        self.accessor = OCPReportDBAccessor(
            schema=self.schema, column_map=self.column_map
        )
        self.provider_accessor = ProviderDBAccessor(
            provider_uuid=self.ocp_test_provider_uuid
        )
        self.report_schema = self.accessor.report_schema
        self.creator = ReportObjectCreator(self.schema, self.column_map)
        self.all_tables = list(OCP_REPORT_TABLE_MAP.values())

        self.provider_id = self.provider_accessor.get_provider().id
        reporting_period = self.creator.create_ocp_report_period(
            provider_id=self.provider_id
        )
        report = self.creator.create_ocp_report(
            reporting_period, reporting_period.report_period_start
        )
        self.creator.create_ocp_usage_line_item(reporting_period, report)
        self.creator.create_ocp_storage_line_item(reporting_period, report)

    def test_get_cluster_id_from_provider(self):
        """Test that the cluster ID is returned from OCP provider."""
        cluster_id = utils.get_cluster_id_from_provider(self.ocp_test_provider_uuid)
        self.assertIsNotNone(cluster_id)

    def test_get_cluster_id_from_non_ocp_provider(self):
        """Test that None is returned when getting cluster ID on non-OCP provider."""
        cluster_id = utils.get_cluster_id_from_provider(self.aws_test_provider_uuid)
        self.assertIsNone(cluster_id)

    def test_get_provider_uuid_from_cluster_id(self):
        """Test that the provider uuid is returned for a cluster ID."""
        cluster_id = self.ocp_provider_resource_name
        provider_uuid = utils.get_provider_uuid_from_cluster_id(cluster_id)
        try:
            UUID(provider_uuid)
        except ValueError:
            self.fail('{} is not a valid uuid.'.format(str(provider_uuid)))

    def test_get_provider_uuid_from_invalid_cluster_id(self):
        """Test that the provider uuid is not returned for an invalid cluster ID."""
        cluster_id = 'bad_cluster_id'
        provider_uuid = utils.get_provider_uuid_from_cluster_id(cluster_id)
        self.assertIsNone(provider_uuid)

    def test_poll_ingest_override_for_provider(self):
        """Test that OCP polling override returns True if insights local path exists."""
        fake_dir = tempfile.mkdtemp()
        with patch.object(Config, 'INSIGHTS_LOCAL_REPORT_DIR', fake_dir):
            cluster_id = utils.get_cluster_id_from_provider(self.ocp_test_provider_uuid)
            expected_path = '{}/{}/'.format(
                Config.INSIGHTS_LOCAL_REPORT_DIR, cluster_id
            )
            os.makedirs(expected_path, exist_ok=True)
            self.assertTrue(
                utils.poll_ingest_override_for_provider(self.ocp_test_provider_uuid)
            )
        shutil.rmtree(fake_dir)
