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

"""Test the AWSReportDBAccessor utility object."""
from unittest.mock import patch

import psycopg2

from masu.database import AWS_CUR_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.aws.aws_report_charge_updater import (
    AWSReportChargeUpdater,
    AWSReportChargeUpdaterError,
)
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class AWSReportChargeUpdaterTest(MasuTestCase):
    """Test Cases for the AWSReportChargeUpdater object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        with ReportingCommonDBAccessor() as report_common_db:
            cls.column_map = report_common_db.column_map

        cls.accessor = AWSReportDBAccessor('acct10001', cls.column_map)

        cls.report_schema = cls.accessor.report_schema

        cls.all_tables = list(AWS_CUR_TABLE_MAP.values())

        cls.creator = ReportObjectCreator(cls.schema, cls.column_map)

        cls.date_accessor = DateAccessor()
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up each test."""
        super().setUp()

        billing_start = self.date_accessor.today_with_timezone('UTC').replace(day=1)
        self.manifest_dict = {
            'assembly_id': '1234',
            'billing_period_start_datetime': billing_start,
            'num_total_files': 2,
            'provider_uuid': self.aws_provider_uuid,
        }

        with ProviderDBAccessor(self.aws_provider_uuid) as provider_accessor:
            self.provider = provider_accessor.get_provider()

        self.updater = AWSReportChargeUpdater(
            schema=self.schema,
            provider=self.provider,
        )
        today = DateAccessor().today_with_timezone('UTC')
        bill = self.creator.create_cost_entry_bill(provider_uuid=self.provider.uuid, bill_date=today)
        cost_entry = self.creator.create_cost_entry(bill, today)
        product = self.creator.create_cost_entry_product()
        pricing = self.creator.create_cost_entry_pricing()
        reservation = self.creator.create_cost_entry_reservation()
        self.creator.create_cost_entry_line_item(
            bill, cost_entry, product, pricing, reservation
        )

        self.manifest = self.manifest_accessor.add(**self.manifest_dict)

    @patch('masu.database.cost_model_db_accessor.CostModelDBAccessor.get_markup')
    def test_update_summary_charge_info(self, mock_markup):
        """Test to verify AWS derived cost summary is calculated."""
        markup = {'value': 10, 'unit': 'percent'}
        mock_markup.return_value = markup
        start_date = self.date_accessor.today_with_timezone('UTC')
        bill_date = start_date.replace(day=1).date()

        self.updater.update_summary_charge_info()
        with AWSReportDBAccessor('acct10001', self.column_map) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.derived_cost_datetime)
