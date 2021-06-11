#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AzureCostModelCostUpdater object."""
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.azure.azure_cost_model_cost_updater import AzureCostModelCostUpdater
from masu.test import MasuTestCase


class AzureCostModelCostUpdaterTest(MasuTestCase):
    """Test Cases for the AzureCostModelCostUpdater object."""

    def test_azure_update_summary_cost_model_costs(self):
        """Test to verify Azure derived cost summary is calculated."""
        updater = AzureCostModelCostUpdater(schema=self.schema, provider=self.azure_provider)
        start_date = DateAccessor().today_with_timezone("UTC")
        bill_date = start_date.replace(day=1).date()

        updater.update_summary_cost_model_costs()

        with AzureReportDBAccessor(self.schema) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.derived_cost_datetime)
