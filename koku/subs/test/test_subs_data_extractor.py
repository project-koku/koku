import uuid
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

from botocore.exceptions import EndpointConnectionError

from api.utils import DateHelper
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
        cls.dh = DateHelper()
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

    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query")
    def test_create_subs_table(self, mock_trino):
        """Test creating the subs table calls trino."""
        self.extractor.create_subs_table()
        mock_trino.assert_called_once()

    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query")
    def test_determine_latest_processed_time_for_provider_with_return_value(self, mock_trino):
        """Test determining the last processed time with a return value returns the expected value"""
        expected = self.today
        mock_trino.return_value = [[expected]]
        actual = self.extractor.determine_latest_processed_time_for_provider("2023", "02")
        self.assertEqual(expected, actual)

    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query")
    def test_determine_latest_processed_time_for_provider_without_return_value(self, mock_trino):
        """Test determining the last processed time with no return gives back None"""
        mock_trino.return_value = []
        actual = self.extractor.determine_latest_processed_time_for_provider("2023", "07")
        self.assertIsNone(actual)

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
        expected = (
            f"WHERE source='{self.aws_provider.uuid}' AND year='{year}' AND month='{month}' AND"
            " lineitem_productcode = 'AmazonEC2' AND lineitem_lineitemtype = 'Usage' AND"
            " product_vcpu IS NOT NULL AND strpos(resourcetags, 'com_redhat_rhel') > 0 AND"
            f" lineitem_usagestartdate > TIMESTAMP '{latest_processed_time}'"
        )
        actual = self.extractor.determine_where_clause(latest_processed_time, year, month)
        self.assertEqual(expected, actual)

    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query")
    def test_update_latest_processed_time(self, mock_trino):
        """Test updating the processed time calls trino"""
        self.extractor.update_latest_processed_time("2023", "07")
        mock_trino.assert_called()

    @patch("subs.subs_data_extractor.SUBSDataExtractor.update_latest_processed_time")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.copy_data_to_subs_s3_bucket")
    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query_with_description")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_line_item_count")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_where_clause")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_latest_processed_time_for_provider")
    def test_extract_data_to_s3(
        self, mock_latest_time, mock_where_clause, mock_li_count, mock_trino, mock_copy, mock_update
    ):
        """Test the flow of extracting data to S3 calls the right functions"""
        mock_li_count.return_value = 10
        expected_key = "fake_key"
        mock_copy.return_value = expected_key
        mock_trino.return_value = (MagicMock(), MagicMock())
        upload_keys = self.extractor.extract_data_to_s3(self.yesterday, self.today)
        mock_latest_time.assert_called_once()
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
