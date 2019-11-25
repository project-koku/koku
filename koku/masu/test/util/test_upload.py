"""Upload utils tests."""
import calendar
import uuid
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytz
from django.test import TestCase

from masu.celery.tasks import table_export_settings
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from masu.util.upload import get_upload_path, query_and_upload_to_s3


class TestUploadUtils(TestCase):
    """Test cases for upload utils."""

    def test_get_upload_path(self):
        """Assert get_upload_path produces an appropriate S3 path for the month."""
        report_date = date(2018, 4, 1)
        schema_name = 'test_acct'
        provider_type = 'test_type'
        provider_uuid = uuid.UUID('de4db3ef-a185-4bad-b33f-d15ea5edc0de', version=4)
        table_name = 'test_table'
        with self.settings(S3_BUCKET_PATH='bucket'):
            path = get_upload_path(
                schema_name, provider_type, provider_uuid, report_date, table_name
            )
            self.assertEquals(
                'bucket/test_acct/test_type/de4db3ef-a185-4bad-b33f-d15ea5edc0de/2018/04/00/test_table.csv.gz',
                path,
            )

    def test_get_upload_path_daily(self):
        """Assert get_upload_path produces an appropriate S3 path including day of month."""
        report_date = date(2018, 4, 1)
        schema_name = 'test_acct'
        provider_type = 'test_type'
        provider_uuid = uuid.UUID('de4db3ef-a185-4bad-b33f-d15ea5edc0de', version=4)
        table_name = 'test_table'
        with self.settings(S3_BUCKET_PATH='bucket'):
            path = get_upload_path(
                schema_name, provider_type, provider_uuid, report_date, table_name, daily=True,
            )
            self.assertEquals(
                'bucket/test_acct/test_type/de4db3ef-a185-4bad-b33f-d15ea5edc0de/2018/04/01/test_table.csv.gz',
                path,
            )


class TestUploadUtilsWithData(MasuTestCase):
    """Test cases for upload utils that need some data."""

    def setUp(self):
        """Set up initial data for tests."""
        super(TestUploadUtilsWithData, self).setUp()

        with ReportingCommonDBAccessor(self.schema) as common_accessor:
            self.column_map = common_accessor.column_map
        self.creator = ReportObjectCreator(self.schema, self.column_map)

        timezone = pytz.timezone('UTC')
        # Arbitrary date as "today" so we don't drift around with `now`.
        self.today = datetime(2019, 11, 5, 0, 0, 0, tzinfo=timezone)

        self.today_date = date(year=self.today.year, month=self.today.month, day=self.today.day)
        self.create_some_data_for_date(self.today)

        self.yesterday = self.today - timedelta(days=1)
        self.yesterday_date = date(
            year=self.yesterday.year, month=self.yesterday.month, day=self.yesterday.day
        )
        self.create_some_data_for_date(self.yesterday)

        self.future = self.today + timedelta(days=900)
        self.future_date = date(year=self.future.year, month=self.future.month, day=self.future.day)

    def create_some_data_for_date(self, the_datetime):
        """Create some dummy data for the given datetime."""
        product = self.creator.create_cost_entry_product()
        pricing = self.creator.create_cost_entry_pricing()
        reservation = self.creator.create_cost_entry_reservation()

        bill = self.creator.create_cost_entry_bill(
            provider_uuid=self.aws_provider_uuid, bill_date=the_datetime
        )
        cost_entry = self.creator.create_cost_entry(bill, entry_datetime=the_datetime)
        self.creator.create_cost_entry_line_item(bill, cost_entry, product, pricing, reservation)

        # The daily summary lines are aligned with midnight of each day.
        the_date = the_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        self.creator.create_awscostentrylineitem_daily_summary(
            self.customer.account_id, self.schema, bill, the_date
        )

    def get_table_export_setting_by_name(self, name):
        """Get specific TableExportSetting for testing."""
        return [s for s in table_export_settings if s.output_name == name].pop()

    @patch('masu.util.upload.AwsS3Uploader')
    def test_query_and_upload_to_s3(self, mock_uploader):
        """
        Assert query_and_upload_to_s3 uploads to S3 for each query.

        We only have test data reliably set for AWS, but this function should
        still execute *all* of the table_export_settings queries, effectively
        providing a syntax check on the SQL even if no results are found.
        """
        today = self.today
        _, last_day_of_month = calendar.monthrange(today.year, today.month)
        curr_month_first_day = date(year=today.year, month=today.month, day=1)
        curr_month_last_day = date(year=today.year, month=today.month, day=last_day_of_month)

        date_range = (curr_month_first_day, curr_month_last_day)
        for table_export_setting in table_export_settings:
            mock_uploader.reset_mock()
            query_and_upload_to_s3(
                self.schema, self.aws_provider_uuid, table_export_setting, date_range
            )
            if table_export_setting.provider == 'aws':
                if table_export_setting.iterate_daily:
                    # There are always TWO days of AWS test data.
                    calls = mock_uploader.return_value.upload_file.call_args_list
                    self.assertEqual(len(calls), 2)
                else:
                    # There is always only ONE month of AWS test data.
                    mock_uploader.return_value.upload_file.assert_called_once()
            else:
                # We ONLY have test data currently for AWS.
                mock_uploader.return_value.upload_file.assert_not_called()

    @patch('masu.util.upload.AwsS3Uploader')
    def test_query_and_upload_skips_if_no_data(self, mock_uploader):
        """Assert query_and_upload_to_s3 uploads nothing if no data is found."""
        date_range = (self.future_date, self.future_date)
        table_export_setting = self.get_table_export_setting_by_name(
            'reporting_awscostentrylineitem'
        )
        query_and_upload_to_s3(
            self.schema, self.aws_provider_uuid, table_export_setting, date_range
        )
        mock_uploader.return_value.upload_file.assert_not_called()

    @patch('masu.util.upload.AwsS3Uploader')
    def test_query_and_upload_to_s3_multiple_days_multiple_rows(self, mock_uploader):
        """Assert query_and_upload_to_s3 for multiple days uploads multiple files."""
        date_range = (self.yesterday_date, self.today_date)
        table_export_setting = self.get_table_export_setting_by_name(
            'reporting_awscostentrylineitem_daily_summary'
        )
        query_and_upload_to_s3(
            self.schema, self.aws_provider_uuid, table_export_setting, date_range
        )
        # expect one upload call for yesterday and one for today
        self.assertEqual(mock_uploader.return_value.upload_file.call_count, 2)
