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
        context = {
            "schema": cls.schema,
            "provider_type": cls.aws_provider_type,
            "provider_uuid": cls.aws_provider.uuid,
        }
        with patch("subs.subs_data_extractor.get_s3_resource"):
            with patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query"):
                cls.extractor = SUBSDataExtractor(cls.tracing_id, context)

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
            base_time = datetime.datetime(2023, 6, 3, 15, tzinfo=datetime.timezone.utc)
            SubsLastProcessed.objects.create(
                source_uuid=TenantAPIProvider.objects.get(uuid=self.aws_provider.uuid),
                year=year,
                month=month,
                latest_processed_time=base_time,
            ).save()
        # we add 1 second to the latest processed time to ensure the records are new
        expected = base_time + timedelta(seconds=1)
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
        self.extractor.determine_line_item_count("fake where clause", {"fake": "params"})
        mock_trino.assert_called_once()

    def test_determine_where_clause_and_params(self):
        """Test resulting where clause and params matches expected values"""
        year = "2023"
        month = "07"
        latest_processed_time = self.today
        end_time = self.today + timedelta(days=2)
        ids = ["12345"]
        expected_sql_params = {
            "provider_uuid": self.aws_provider.uuid,
            "year": year,
            "month": month,
            "latest_processed_time": latest_processed_time,
            "end_time": end_time,
            "ids": ids,
        }
        expected_clause = (
            "WHERE source={{provider_uuid}} AND year={{year}} AND month={{month}} AND"
            " lineitem_productcode = 'AmazonEC2' AND lineitem_lineitemtype IN ('Usage', 'SavingsPlanCoveredUsage') AND"
            " product_vcpu IS NOT NULL AND strpos(lower(resourcetags), 'com_redhat_rhel') > 0 AND"
            " lineitem_usagestartdate > {{latest_processed_time}} AND"
            " lineitem_usagestartdate <= {{end_time}}"
            " AND lineitem_usageaccountid IN {{ids | inclause}}"
        )
        actual_clause, actual_params = self.extractor.determine_where_clause_and_params(
            latest_processed_time, end_time, year, month, ids
        )
        self.assertEqual(expected_clause, actual_clause)
        self.assertEqual(expected_sql_params, actual_params)

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
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_where_clause_and_params")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_ids_for_provider")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_start_time")
    def test_extract_data_to_s3(
        self,
        mock_start_time,
        mock_ids,
        mock_where_clause,
        mock_li_count,
        mock_trino,
        mock_copy,
        mock_update,
        mock_end_time,
    ):
        """Test the flow of extracting data to S3 calls the right functions"""
        mock_li_count.return_value = 10
        expected_key = "fake_key"
        mock_ids.return_value = ["12345"]
        mock_copy.return_value = expected_key
        mock_trino.return_value = (MagicMock(), MagicMock())
        mock_where_clause.return_value = (MagicMock(), MagicMock())
        upload_keys = self.extractor.extract_data_to_s3(self.dh.month_start(self.yesterday))
        mock_start_time.assert_called_once()
        mock_end_time.assert_called_once()
        mock_where_clause.assert_called_once()
        mock_li_count.assert_called_once()
        mock_trino.assert_called_once()
        mock_copy.assert_called_once()
        mock_update.assert_called_once()
        self.assertEqual([expected_key], upload_keys)

    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_end_time")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.update_latest_processed_time")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.copy_data_to_subs_s3_bucket")
    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query_with_description")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_line_item_count")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_where_clause_and_params")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_ids_for_provider")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_start_time")
    def test_extract_data_to_s3_no_ids_found(
        self,
        mock_start_time,
        mock_ids,
        mock_where_clause,
        mock_li_count,
        mock_trino,
        mock_copy,
        mock_update,
        mock_end_time,
    ):
        """Test the flow of extracting data to S3 calls the right functions when no IDs are found"""
        mock_li_count.return_value = 10
        expected_key = "fake_key"
        mock_ids.return_value = []
        mock_copy.return_value = expected_key
        mock_trino.return_value = (MagicMock(), MagicMock())
        mock_where_clause.return_value = (MagicMock(), MagicMock())
        upload_keys = self.extractor.extract_data_to_s3(self.dh.month_start(self.yesterday))
        mock_start_time.assert_called_once()
        mock_end_time.assert_called_once()
        mock_where_clause.assert_not_called()
        mock_li_count.assert_not_called()
        mock_trino.assert_not_called()
        mock_copy.assert_not_called()
        mock_update.assert_called_once()
        self.assertEqual([], upload_keys)

    def test_copy_data_to_subs_s3_bucket(self):
        """Test copy_data_to_subs_s3_bucket."""
        actual_key = self.extractor.copy_data_to_subs_s3_bucket(["data"], ["column"], "filename")
        self.assertEqual(f"{self.extractor.subs_s3_path}/filename", actual_key)

    def test_copy_data_to_subs_s3_bucket_conn_error(self):
        """Test that an error copying data results in no upload_key being returned"""
        self.extractor.s3_resource.Object.side_effect = EndpointConnectionError(endpoint_url="fakeurl")
        actual_key = self.extractor.copy_data_to_subs_s3_bucket(["data"], ["column"], "filename")
        self.assertIsNone(actual_key)

    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query")
    def test_determine_ids_for_provider(self, mock_trino):
        """Test that proper IDs are returned for a given provider."""
        mock_trino.return_value = [["12345"]]
        year = "2023"
        month = "08"
        expected_ids = ["12345"]
        actual_ids = self.extractor.determine_ids_for_provider(year, month)
        self.assertEqual(expected_ids, actual_ids)

    def test_determine_start_time(self):
        """Test that determing the start time for different scenarios evaluates correctly."""
        test_table = {
            "no_base_prov_created_same_month": {
                "latest": None,
                "prov_created": datetime.datetime(2023, 8, 7),
                "expected_return": datetime.datetime(2023, 8, 6, 0),
            },
            "no_base_prov_created_prev_month": {
                "latest": None,
                "prov_created": datetime.datetime(2023, 7, 7),
                "expected_return": datetime.datetime(2023, 8, 1, 0),
            },
            "base_prov_created_before": {
                "latest": datetime.datetime(2023, 8, 10, 12),
                "prov_created": datetime.datetime(2023, 8, 7),
                "expected_return": datetime.datetime(2023, 8, 10, 12),
            },
            "base_prov_created_after": {
                "latest": datetime.datetime(2023, 8, 10, 12),
                "prov_created": datetime.datetime(2023, 8, 15),
                "expected_return": datetime.datetime(2023, 8, 14, 0),
            },
        }
        for test_case, expected in test_table.items():
            with self.subTest(case=test_case):
                with patch(
                    "subs.subs_data_extractor.SUBSDataExtractor.determine_latest_processed_time_for_provider"
                ) as mock_latest:
                    with patch("subs.subs_data_extractor.Provider.objects") as mock_prov:
                        mock_prov.get.return_value.created_timestamp = expected["prov_created"]
                        mock_latest.return_value = expected["latest"]
                        actual = self.extractor.determine_start_time(
                            year="2023", month="08", month_start=datetime.datetime(2023, 8, 1)
                        )
                        self.assertEqual(expected["expected_return"], actual)
