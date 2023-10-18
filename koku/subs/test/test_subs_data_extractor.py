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
            rid = "12345"
            base_time = datetime.datetime(2023, 6, 3, 15, tzinfo=datetime.timezone.utc)
            SubsLastProcessed.objects.create(
                source_uuid=TenantAPIProvider.objects.get(uuid=self.aws_provider.uuid),
                resource_id=rid,
                year=year,
                month=month,
                latest_processed_time=base_time,
            ).save()
        # we add 1 second to the latest processed time to ensure the records are new
        expected = base_time + timedelta(seconds=1)
        actual = self.extractor.determine_latest_processed_time_for_provider(rid, year, month)
        self.assertEqual(actual, expected)

    def test_determine_latest_processed_time_for_provider_without_return_value(self):
        """Test determining the last processed time with no return gives back None"""
        with schema_context(self.schema):
            year = "2023"
            month = "05"
            rid = "56789"
            SubsLastProcessed.objects.create(
                source_uuid=TenantAPIProvider.objects.get(uuid=self.aws_provider.uuid),
                resource_id=rid,
                year=year,
                month=month,
            ).save()
        actual = self.extractor.determine_latest_processed_time_for_provider(rid, year, month)
        self.assertIsNone(actual)

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
        rid = "45678"
        expected_sql_params = {
            "provider_uuid": self.aws_provider.uuid,
            "year": year,
            "month": month,
            "latest_processed_time": latest_processed_time,
            "end_time": end_time,
            "rid": rid,
        }
        expected_clause = (
            "WHERE source={{provider_uuid}} AND year={{year}} AND month={{month}} AND"
            " lineitem_productcode = 'AmazonEC2' AND lineitem_lineitemtype IN ('Usage', 'SavingsPlanCoveredUsage') AND"
            " product_vcpu != '' AND strpos(lower(resourcetags), 'com_redhat_rhel') > 0 AND"
            " lineitem_usagestartdate > {{latest_processed_time}} AND"
            " lineitem_usagestartdate <= {{end_time}} AND lineitem_resourceid = {{rid}}"
        )
        actual_clause, actual_params = self.extractor.determine_where_clause_and_params(
            latest_processed_time, end_time, year, month, rid
        )
        self.assertEqual(expected_clause, actual_clause)
        self.assertEqual(expected_sql_params, actual_params)

    @patch("subs.subs_data_extractor.SUBSDataExtractor.bulk_update_latest_processed_time")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.gather_and_upload_for_resource")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_start_time_for_resource")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.get_resource_ids_for_usage_account")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_ids_for_provider")
    def test_extract_data_to_s3(
        self,
        mock_ids,
        mock_resources,
        mock_start_time,
        mock_gather,
        mock_bulk_update,
    ):
        """Test the flow of extracting data to S3 calls the right functions"""
        expected_key = "fake_key"
        mock_gather.return_value = [expected_key]
        # there should be two calls to the gather function that returns a list of keys to be appended
        expected_upload_keys = [expected_key, expected_key]
        mock_ids.return_value = ["12345"]
        mock_resources.return_value = [("23456", MagicMock()), ("34567", MagicMock())]
        upload_keys = self.extractor.extract_data_to_s3(self.dh.month_start(self.yesterday))
        mock_ids.assert_called_once()
        mock_resources.assert_called_once()
        self.assertEqual(2, len(mock_start_time.mock_calls))
        self.assertEqual(2, len(mock_gather.mock_calls))
        mock_bulk_update.assert_called()
        self.assertEqual(expected_upload_keys, upload_keys)

    @patch("subs.subs_data_extractor.SUBSDataExtractor.bulk_update_latest_processed_time")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.gather_and_upload_for_resource")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_start_time_for_resource")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.get_resource_ids_for_usage_account")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_ids_for_provider")
    def test_extract_data_to_s3_no_usage_ids_found(
        self,
        mock_ids,
        mock_resources,
        mock_start_time,
        mock_gather,
        mock_bulk_update,
    ):
        """Test the flow of extracting data to S3 calls the right functions when no IDs are found"""
        mock_ids.return_value = []
        upload_keys = self.extractor.extract_data_to_s3(self.dh.month_start(self.yesterday))
        mock_ids.assert_called_once()
        mock_resources.assert_not_called()
        mock_start_time.assert_not_called()
        mock_gather.assert_not_called()
        mock_bulk_update.assert_not_called()
        self.assertEqual([], upload_keys)

    @patch("subs.subs_data_extractor.SUBSDataExtractor.bulk_update_latest_processed_time")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.gather_and_upload_for_resource")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_start_time_for_resource")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.get_resource_ids_for_usage_account")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_ids_for_provider")
    def test_extract_data_to_s3_no_resource_ids_found(
        self,
        mock_ids,
        mock_resources,
        mock_start_time,
        mock_gather,
        mock_bulk_update,
    ):
        """Test the flow of extracting data to S3 calls the right functions when no resource IDs are found"""
        expected_key = "fake_key"
        mock_gather.return_value = expected_key
        mock_ids.return_value = ["12345"]
        mock_resources.return_value = []
        upload_keys = self.extractor.extract_data_to_s3(self.dh.month_start(self.yesterday))
        mock_ids.assert_called_once()
        mock_resources.assert_called_once()
        mock_start_time.assert_not_called()
        mock_gather.assert_not_called()
        mock_bulk_update.assert_not_called()
        self.assertEqual([], upload_keys)

    @patch("subs.subs_data_extractor.SUBSDataExtractor.copy_data_to_subs_s3_bucket")
    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query_with_description")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_line_item_count")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_where_clause_and_params")
    def test_gather_and_upload_for_resource(self, mock_where_clause, mock_li_count, mock_trino, mock_copy):
        """Test gathering data and uploading it to S3 calls the right functions and returns the right value."""
        self.dh.month_start(self.yesterday)
        rid = "12345"
        year = "2023"
        month = "04"
        start_time = datetime.datetime(2023, 4, 3, tzinfo=datetime.timezone.utc)
        end_time = datetime.datetime(2023, 4, 5, tzinfo=datetime.timezone.utc)
        mock_li_count.return_value = 10
        expected_key = "fake_key"
        mock_copy.return_value = expected_key
        mock_trino.return_value = (MagicMock(), MagicMock())
        mock_where_clause.return_value = (MagicMock(), MagicMock())
        upload_keys = self.extractor.gather_and_upload_for_resource(rid, year, month, start_time, end_time)
        mock_where_clause.assert_called_once()
        mock_li_count.assert_called_once()
        mock_trino.assert_called_once()
        mock_copy.assert_called_once()
        self.assertEqual([expected_key], upload_keys)

    @patch("subs.subs_data_extractor.SUBSDataExtractor.copy_data_to_subs_s3_bucket")
    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query_with_description")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_line_item_count")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_where_clause_and_params")
    def test_gather_and_upload_for_resource_no_result(self, mock_where_clause, mock_li_count, mock_trino, mock_copy):
        """Test uploading does not attempt with empty values from trino query."""
        self.dh.month_start(self.yesterday)
        rid = "12345"
        year = "2023"
        month = "04"
        start_time = datetime.datetime(2023, 4, 3, tzinfo=datetime.timezone.utc)
        end_time = datetime.datetime(2023, 4, 5, tzinfo=datetime.timezone.utc)
        mock_li_count.return_value = 10
        expected_key = "fake_key"
        mock_copy.return_value = expected_key
        mock_trino.return_value = ([], [("fake_col1",), ("fake_col2",)])
        mock_where_clause.return_value = (MagicMock(), MagicMock())
        upload_keys = self.extractor.gather_and_upload_for_resource(rid, year, month, start_time, end_time)
        mock_where_clause.assert_called_once()
        mock_li_count.assert_called_once()
        mock_trino.assert_called_once()
        mock_copy.assert_not_called()
        self.assertEqual(upload_keys, [])

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

    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query")
    def test_get_resource_ids_for_usage_account(self, mock_trino):
        """Test that proper ids are returned from trino queries."""
        mock_trino.return_value = [("12345", "fake time")]
        year = "2023"
        month = "08"
        expected_ids = [("12345", "fake time")]
        actual_ids = self.extractor.get_resource_ids_for_usage_account("123", year, month)
        self.assertEqual(expected_ids, actual_ids)

    def test_bulk_update_latest_processed_time(self):
        """Test that timestamps for multiple resources are update in the DB when bulk updating processed times."""
        year = "2023"
        month = "04"
        rid1 = "1234"
        rid2 = "3456"
        expected_time = datetime.datetime(2023, 6, 3, 15, tzinfo=datetime.timezone.utc)
        resources = [(rid1, expected_time), (rid2, expected_time)]
        with schema_context(self.schema):
            SubsLastProcessed.objects.create(
                source_uuid_id=self.aws_provider.uuid, resource_id=rid1, year=year, month=month
            ).save()
            SubsLastProcessed.objects.create(
                source_uuid_id=self.aws_provider.uuid, resource_id=rid2, year=year, month=month
            ).save()
        self.extractor.bulk_update_latest_processed_time(resources, year, month)
        with schema_context(self.schema):
            subs_record_1 = SubsLastProcessed.objects.get(
                source_uuid_id=self.aws_provider.uuid, resource_id=rid1, year=year, month=month
            )
            subs_record_2 = SubsLastProcessed.objects.get(
                source_uuid_id=self.aws_provider.uuid, resource_id=rid2, year=year, month=month
            )
            self.assertEqual(subs_record_1.latest_processed_time, expected_time)
            self.assertEqual(subs_record_2.latest_processed_time, expected_time)

    def test_determine_start_time_for_resource(self):
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
                        actual = self.extractor.determine_start_time_for_resource(
                            rid="123456", year="2023", month="08", month_start=datetime.datetime(2023, 8, 1)
                        )
                        self.assertEqual(expected["expected_return"], actual)
