# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0

"""Test the GCPCostModelCostUpdater utility object."""
from datetime import date
from datetime import datetime
from unittest.mock import patch, MagicMock

from django.utils import timezone

from api.utils import DateHelper
from masu.processor.gcp.gcp_cost_model_cost_updater import GCPCostModelCostUpdater
from masu.test import MasuTestCase
from reporting.provider.gcp.models import UI_SUMMARY_TABLES


class GCPCostModelCostUpdaterTest(MasuTestCase):
    """Test Cases for the GCPCostModelCostUpdater object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.dh = DateHelper()

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        self.provider = self.gcp_provider
        self.provider_uuid = self.gcp_provider_uuid
        self.schema = self.schema
        self.updater = GCPCostModelCostUpdater(schema=self.schema, provider=self.provider)

    @patch("masu.processor.gcp.gcp_cost_model_cost_updater.GCPReportDBAccessor")
    @patch.object(timezone, "now")
    @patch.object(DateHelper, "invoice_month_start")
    def test_update_summary_cost_model_costs(
        self,
        mock_invoice_month_start,
        mock_timezone_now,
        mock_accessor
    ):
        """Test that the summary cost model update process works correctly."""
        start_date = "2023-01-01"
        end_date = "2023-01-31"
        test_now = datetime(2023, 1, 15)

        mock_bill_1 = MagicMock()
        mock_bill_2 = MagicMock()
        mock_bills = [mock_bill_1, mock_bill_2]

        mock_accessor.return_value.__enter__.return_value.fetch_invoice_months_and_dates.return_value = [
            ("202301", date(2023, 1, 1), date(2023, 1, 31))
        ]
        mock_accessor.return_value.__enter__.return_value.bills_for_provider_uuid.return_value = mock_bills

        mock_invoice_month_start.return_value.date.return_value = date(2023, 1, 1)
        mock_timezone_now.return_value = test_now

        with patch.object(self.updater, "_update_markup_cost") as mock_update_markup_cost:
            self.updater.update_summary_cost_model_costs(start_date=start_date, end_date=end_date)

        mock_update_markup_cost.assert_called_once_with(start_date, end_date)

        mock_accessor.assert_called_once_with(self.schema)
        mock_accessor.return_value.__enter__.return_value.fetch_invoice_months_and_dates.assert_called_once_with(
            start_date, end_date
        )
        mock_accessor.return_value.__enter__.return_value.populate_ui_summary_tables.assert_called()
        mock_accessor.return_value.__enter__.return_value.bills_for_provider_uuid.assert_called()

        self.assertEqual(mock_bill_1.derived_cost_datetime, test_now)
        mock_bill_1.save.assert_called_once()
        self.assertEqual(mock_bill_2.derived_cost_datetime, test_now)
        mock_bill_2.save.assert_called_once()
