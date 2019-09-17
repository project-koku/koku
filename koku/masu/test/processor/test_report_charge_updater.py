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

from masu.processor.aws.aws_report_charge_updater import AWSReportChargeUpdater
from masu.processor.azure.azure_report_charge_updater import AzureReportChargeUpdater
from masu.processor.ocp.ocp_report_charge_updater import OCPReportChargeUpdater
from masu.processor.report_charge_updater import (
    ReportChargeUpdater,
    ReportChargeUpdaterError,
)
from masu.test import MasuTestCase


class ReportChargeUpdaterTest(MasuTestCase):
    """Test class for the report summary updater."""

    @patch(
        'masu.processor.report_charge_updater.OCPReportChargeUpdater.update_summary_charge_info'
    )
    def test_ocp_route(self, mock_update):
        """Test that OCP charge updating works as expected."""
        updater = ReportChargeUpdater(self.schema, self.ocp_test_provider_uuid)
        self.assertIsInstance(updater._updater, OCPReportChargeUpdater)
        updater.update_charge_info()
        mock_update.assert_called()

    @patch(
        'masu.processor.report_charge_updater.AzureReportChargeUpdater.update_summary_charge_info'
    )
    def test_azure_local_route(self, mock_update):
        """Test that AZURE-local charge updating works as expected."""
        updater = ReportChargeUpdater(self.schema, self.azure_test_provider_uuid)
        self.assertIsInstance(updater._updater, AzureReportChargeUpdater)
        updater.update_charge_info()
        mock_update.assert_called()

    @patch(
        'masu.processor.report_charge_updater.AWSReportChargeUpdater.update_summary_charge_info'
    )
    def test_aws_route(self, mock_update):
        """Test that AWS charge updating works as expected."""
        updater = ReportChargeUpdater(self.schema, self.aws_test_provider_uuid)
        self.assertIsInstance(updater._updater, AWSReportChargeUpdater)
        updater.update_charge_info()
        mock_update.assert_called()

    @patch(
        'masu.processor.report_charge_updater.AzureReportChargeUpdater.update_summary_charge_info'
    )
    def test_azure_route(self, mock_update):
        """Test that Azure charge updating works as expected."""
        updater = ReportChargeUpdater(self.schema, self.azure_test_provider_uuid)
        self.assertIsInstance(updater._updater, AzureReportChargeUpdater)
        updater.update_charge_info()
        mock_update.assert_called()

    @patch('masu.processor.report_charge_updater.OCPReportChargeUpdater.__init__')
    def test_init_fail(self, mock_updater):
        """Test that an unimplemented provider throws an error."""
        mock_updater.side_effect = Exception('general error')

        with self.assertRaises(ReportChargeUpdaterError):
            ReportChargeUpdater(self.schema, self.ocp_test_provider_uuid)
