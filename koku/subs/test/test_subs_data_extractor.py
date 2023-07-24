import datetime
import uuid
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

from botocore.exceptions import EndpointConnectionError
from django_tenants.utils import schema_context

from api.utils import DateHelper
from reporting.models import SubsLastProcessed
from reporting.models import TenantAPIProvider
from subs.subs_data_extractor import SUBSDataExtractor
from subs.test import SUBSTestCase


class TestSUBSDataExtractor(SUBSTestCase):
    """Test class for the SUBSDataExtractor"""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.dh = DateHelper()
        cls.tracing_id = str(uuid.uuid4())
        cls.today = cls.dh.today
        cls.yesterday = cls.today - timedelta(days=1)
        with patch("subs.subs_data_extractor.get_subs_s3_client"):
            with patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query"):
                cls.extractor = SUBSDataExtractor(
                    cls.schema, cls.aws_provider_type, cls.aws_provider.uuid, cls.tracing_id
                )

    def test_subs_s3_path(self):
        """Test that the generated s3 path is expected"""
        expected = (
            f"{self.schema}/{self.aws_provider_type.removesuffix('-local')}/"
            f"source={self.aws_provider.uuid}/date={DateHelper().today.date()}"
        )
        actual = self.extractor.subs_s3_path
        self.assertEqual(expected, actual)

    def test_determine_latest_processed_time_for_provider_with_return_value(self):
        """Test determining the last processed time with a return value returns the expected value"""
        with schema_context(self.schema):
            year = "2023"
            month = "06"
            expected = datetime.datetime(2023, 6, 3, 15, tzinfo=datetime.timezone.utc)
            SubsLastProcessed.objects.create(
                source_uuid=TenantAPIProvider.objects.get(uuid=self.aws_provider.uuid),
                year=year,
                month=month,
                latest_processed_time=expected,
            ).save()
        actual = self.extractor.determine_latest_processed_time_for_provider(year, month)
        self.assertEqual(actual, expected)

    def test_determine_latest_processed_time_for_provider_without_return_value(self):
        """Test determining the last processed time with no return gives back None"""
        with schema_context(self.schema):
            year = "2023"
            month = "05"
            SubsLastProcessed.objects.create(
                source_uuid=TenantAPIProvider.objects.get(uuid=self.aws_provider.uuid), year=year, month=month
            ).save()
        actual = self.extractor.determine_latest_processed_time_for_provider(year, month)
        self.assertIsNone(actual)

    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query")
    def test_determine_end_time(self, mock_trino):
        self.extractor.determine_end_time("2023", "06")
        mock_trino.assert_called()

    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query")
    def test_determine_line_item_count(self, mock_trino):
        """Test determining the line item count for the subs query calls trino"""
        self.extractor.determine_line_item_count("fake where clause")
        mock_trino.assert_called_once()

    def test_determine_where_clause(self):
        """Test resulting where clause matches expected values"""
        year = "2023"
        month = "07"
        latest_processed_time = self.today
        end_time = self.today + timedelta(days=2)
        expected = (
            f"WHERE source='{self.aws_provider.uuid}' AND year='{year}' AND month='{month}' AND"
            " lineitem_productcode = 'AmazonEC2' AND lineitem_lineitemtype IN ('Usage', 'SavingsPlanCoveredUsage') AND"
            " product_vcpu IS NOT NULL AND strpos(resourcetags, 'com_redhat_rhel') > 0 AND"
            f" lineitem_usagestartdate > TIMESTAMP '{latest_processed_time}' AND"
            f" lineitem_usagestartdate <= TIMESTAMP '{end_time}'"
        )
        actual = self.extractor.determine_where_clause(latest_processed_time, end_time, year, month)
        self.assertEqual(expected, actual)

    def test_update_latest_processed_time(self):
        """Test updating the processed time calls trino"""
        year = "2023"
        month = "04"
        with schema_context(self.schema):
            SubsLastProcessed.objects.create(
                source_uuid=TenantAPIProvider.objects.get(uuid=self.aws_provider.uuid), year=year, month=month
            ).save()
        expected = datetime.datetime(2023, 6, 3, 15, tzinfo=datetime.timezone.utc)
        self.extractor.update_latest_processed_time(year, month, expected)
        with schema_context(self.schema):
            subs_record = SubsLastProcessed.objects.get(
                source_uuid=TenantAPIProvider.objects.get(uuid=self.aws_provider.uuid), year=year, month=month
            )
            self.assertEqual(subs_record.latest_processed_time, expected)

    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_end_time")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.update_latest_processed_time")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.copy_data_to_subs_s3_bucket")
    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query_with_description")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_line_item_count")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_where_clause")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_latest_processed_time_for_provider")
    def test_extract_data_to_s3(
        self, mock_latest_time, mock_where_clause, mock_li_count, mock_trino, mock_copy, mock_update, mock_end_time
    ):
        """Test the flow of extracting data to S3 calls the right functions"""
        mock_li_count.return_value = 10
        expected_key = "fake_key"
        mock_copy.return_value = expected_key
        mock_trino.return_value = (MagicMock(), MagicMock())
        upload_keys = self.extractor.extract_data_to_s3(self.yesterday, self.today)
        mock_latest_time.assert_called_once()
        mock_end_time.assert_called_once()
        mock_where_clause.assert_called_once()
        mock_li_count.assert_called_once()
        mock_trino.assert_called_once()
        mock_copy.assert_called_once()
        mock_update.assert_called_once()
        self.assertEqual([expected_key], upload_keys)

    def test_copy_data_to_subs_s3_bucket(self):
        """Test copy_data_to_subs_s3_bucket."""
        actual_key = self.extractor.copy_data_to_subs_s3_bucket(["data"], ["column"], "filename")
        self.assertEqual(f"{self.extractor.subs_s3_path}/filename", actual_key)

    def test_copy_data_to_subs_s3_bucket_conn_error(self):
        """Test that an error copying data results in no upload_key being returned"""
        self.extractor.s3_client.upload_fileobj.side_effect = EndpointConnectionError(endpoint_url="fakeurl")
        actual_key = self.extractor.copy_data_to_subs_s3_bucket(["data"], ["column"], "filename")
        self.assertEqual(None, actual_key)
