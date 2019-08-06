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

"""Test the ReportChargeUpdater object."""

from unittest.mock import patch

from masu.external import (
    AMAZON_WEB_SERVICES,
    OPENSHIFT_CONTAINER_PLATFORM,
    OCP_LOCAL_SERVICE_PROVIDER,
)
from masu.processor.aws.aws_report_charge_updater import AWSReportChargeUpdater
from masu.processor.ocp.ocp_report_charge_updater import OCPReportChargeUpdater
from masu.processor.report_charge_updater import (
    ReportChargeUpdater,
    ReportChargeUpdaterError,
)
from masu.test import MasuTestCase


class ReportChargeUpdaterTest(MasuTestCase):
    """Test class for the report summary updater."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.schema = 'acct10001'

    @patch(
        'masu.processor.report_charge_updater.OCPReportChargeUpdater.update_summary_charge_info'
    )
    def test_ocp_route(self, mock_update):
        """Test that OCP charge updating works as expected."""
        provider_ocp_uuid = '3c6e687e-1a09-4a05-970c-2ccf44b0952e'
        updater = ReportChargeUpdater(self.schema, provider_ocp_uuid)
        self.assertIsInstance(updater._updater, OCPReportChargeUpdater)
        updater.update_charge_info()
        mock_update.assert_called()

    @patch(
        'masu.processor.report_charge_updater.OCPReportChargeUpdater.update_summary_charge_info'
    )
    def test_ocp_local_route(self, mock_update):
        """Test that OCP-local charge updating works as expected."""
        provider_ocp_uuid = '3c6e687e-1a09-4a05-970c-2ccf44b0952e'
        updater = ReportChargeUpdater(self.schema, provider_ocp_uuid)
        self.assertIsInstance(updater._updater, OCPReportChargeUpdater)
        updater.update_charge_info()
        mock_update.assert_called()

    @patch(
        'masu.processor.report_charge_updater.AWSReportChargeUpdater.update_summary_charge_info'
    )
    def test_aws_route(self, mock_update):
        """Test that AWS charge updating works as expected."""
        provider_aws_uuid = '6e212746-484a-40cd-bba0-09a19d132d64'
        updater = ReportChargeUpdater(self.schema, provider_aws_uuid)
        self.assertIsInstance(updater._updater, AWSReportChargeUpdater)
        updater.update_charge_info()
        mock_update.assert_called()

    @patch('masu.processor.report_charge_updater.OCPReportChargeUpdater.__init__')
    def test_init_fail(self, mock_updater):
        """Test that an unimplemented provider throws an error."""
        mock_updater.side_effect = Exception('general error')
        provider_ocp_uuid = '3c6e687e-1a09-4a05-970c-2ccf44b0952e'

        with self.assertRaises(ReportChargeUpdaterError):
            ReportChargeUpdater(self.schema, provider_ocp_uuid)
