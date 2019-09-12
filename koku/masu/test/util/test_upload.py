"""Upload utils tests."""
import calendar
from datetime import date
from unittest.mock import patch

from masu.celery.tasks import table_export_settings
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from masu.util.upload import get_upload_path, query_and_upload_to_s3


class TestUploadUtils(MasuTestCase):
    """Test cases for upload utils."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.creator = ReportObjectCreator(cls.schema, cls.column_map)

    def test_get_upload_path(self):
        """Test that the scheduled task calls the orchestrator."""

        report_date = date(2018, 4, 1)
        account = 'test_acct'
        provider_type = 'test'
        table_name = 'test_table'
        with self.settings(S3_BUCKET_PATH='bucket'):
            path = get_upload_path(account, provider_type, report_date, table_name)
            self.assertEquals('bucket/test_acct/test/2018/04/test_table.csv.gz', path)

    @patch('masu.util.upload.AwsS3Uploader')
    def test_query_and_upload_to_s3(self, mock_uploader):
        """Test that the scheduled task calls the orchestrator."""

        today = DateAccessor().today_with_timezone('UTC')
        curr_month_range = calendar.monthrange(today.year, today.month)
        curr_month_first_day = date(year=today.year, month=today.month, day=1)
        curr_month_last_day = date(year=today.year, month=today.month, day=curr_month_range[1])

        bill = self.creator.create_cost_entry_bill(
            provider_id=self.aws_provider.id,
            bill_date=today,
        )
        cost_entry = self.creator.create_cost_entry(bill, entry_datetime=today)
        product = self.creator.create_cost_entry_product()
        pricing = self.creator.create_cost_entry_pricing()
        reservation = self.creator.create_cost_entry_reservation()
        self.creator.create_cost_entry_line_item(
            bill, cost_entry, product, pricing, reservation
        )

        query_and_upload_to_s3('acct10001', table_export_settings[0], (curr_month_first_day, curr_month_last_day))
        mock_uploader.return_value.upload_file.assert_called()
