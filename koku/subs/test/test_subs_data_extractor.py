import datetime
import uuid
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

from botocore.exceptions import EndpointConnectionError
from django_tenants.utils import schema_context

from api.utils import DateHelper
from reporting.models import SubsLastProcessed
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
        azure_context = {
            "schema": cls.schema,
            "provider_type": cls.azure_provider_type,
            "provider_uuid": cls.azure_provider.uuid,
        }
        with patch("subs.subs_data_extractor.get_s3_resource"):
            with patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query"):
                cls.extractor = SUBSDataExtractor(cls.tracing_id, context)
                cls.azure_extractor = SUBSDataExtractor(cls.tracing_id, azure_context)

    def test_subs_s3_path(self):
        """Test that the generated s3 path is expected"""
        expected = (
            f"{self.schema}/{self.aws_provider_type.removesuffix('-local')}/"
            f"source={self.aws_provider.uuid}/date={DateHelper().today.date()}"
        )
        actual = self.extractor.subs_s3_path
        self.assertEqual(expected, actual)

    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query")
    def test_determine_row_count(self, mock_trino):
        """Test determining the line item count for the subs query calls trino"""
        self.extractor.determine_row_count({"fake": "params"})
        mock_trino.assert_called_once()

    @patch("subs.subs_data_extractor.SUBSDataExtractor.bulk_update_latest_processed_time")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.gather_and_upload_for_resource_batch")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.get_resource_ids_for_usage_account")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_ids_for_provider")
    def test_extract_data_to_s3(
        self,
        mock_ids,
        mock_resources,
        mock_gather,
        mock_bulk_update,
    ):
        """Test the flow of extracting data to S3 calls the right functions"""
        expected_key = "fake_key"
        mock_gather.return_value = [expected_key]
        expected_upload_keys = [expected_key]
        mock_ids.return_value = ["12345"]
        mock_resources.return_value = [("23456", MagicMock()), ("34567", MagicMock())]
        upload_keys = self.extractor.extract_data_to_s3(self.dh.month_start(self.yesterday))
        mock_ids.assert_called_once()
        mock_resources.assert_called_once()
        mock_gather.assert_called_once()
        mock_bulk_update.assert_called()
        self.assertEqual(expected_upload_keys, upload_keys)

    @patch("subs.subs_data_extractor.SUBSDataExtractor.bulk_update_latest_processed_time")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.gather_and_upload_for_resource_batch")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.get_resource_ids_for_usage_account")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_ids_for_provider")
    def test_extract_data_to_s3_azure(
        self,
        mock_ids,
        mock_resources,
        mock_gather,
        mock_bulk_update,
    ):
        """Test the flow of extracting data to S3 calls the right functions"""
        expected_key = "fake_key"
        mock_gather.return_value = [expected_key]
        expected_upload_keys = [expected_key]
        mock_ids.return_value = ["12345"]
        mock_resources.return_value = [("23456", "fake:key", MagicMock()), ("34567", "bigfake:key", MagicMock())]
        upload_keys = self.azure_extractor.extract_data_to_s3(self.dh.month_start(self.yesterday))
        mock_ids.assert_called_once()
        mock_resources.assert_called_once()
        mock_gather.assert_called_once()
        mock_bulk_update.assert_called()
        self.assertEqual(expected_upload_keys, upload_keys)

    @patch("subs.subs_data_extractor.SUBSDataExtractor.bulk_update_latest_processed_time")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.gather_and_upload_for_resource_batch")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.get_resource_ids_for_usage_account")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_ids_for_provider")
    def test_extract_data_to_s3_no_usage_ids_found(
        self,
        mock_ids,
        mock_resources,
        mock_gather,
        mock_bulk_update,
    ):
        """Test the flow of extracting data to S3 calls the right functions when no IDs are found"""
        mock_ids.return_value = []
        upload_keys = self.extractor.extract_data_to_s3(self.dh.month_start(self.yesterday))
        mock_ids.assert_called_once()
        mock_resources.assert_not_called()
        mock_gather.assert_not_called()
        mock_bulk_update.assert_not_called()
        self.assertEqual([], upload_keys)

    @patch("subs.subs_data_extractor.SUBSDataExtractor.bulk_update_latest_processed_time")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.gather_and_upload_for_resource_batch")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.get_resource_ids_for_usage_account")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_ids_for_provider")
    def test_extract_data_to_s3_no_resource_ids_found(
        self,
        mock_ids,
        mock_resources,
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
        mock_gather.assert_not_called()
        mock_bulk_update.assert_not_called()
        self.assertEqual([], upload_keys)

    @patch("subs.subs_data_extractor.SUBSDataExtractor.copy_data_to_subs_s3_bucket")
    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query_with_description")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_row_count")
    def test_gather_and_upload_for_resource_batch(self, mock_row_count, mock_trino, mock_copy):
        """Test gathering data and uploading it to S3 calls the right functions and returns the right value."""
        self.dh.month_start(self.yesterday)
        rid = "12345"
        year = "2023"
        month = "04"
        rid_2 = "23456"
        start_time = datetime.datetime(2023, 4, 3, tzinfo=datetime.timezone.utc)
        end_time = datetime.datetime(2023, 4, 5, tzinfo=datetime.timezone.utc)
        batch = [
            {"rid": rid, "start": start_time, "end": end_time},
            {"rid": rid_2, "start": start_time, "end": end_time},
        ]
        mock_row_count.return_value = 10
        expected_key = "fake_key"
        base_filename = "fake_filename"
        mock_copy.return_value = expected_key
        mock_trino.return_value = (MagicMock(), MagicMock())
        upload_keys = self.extractor.gather_and_upload_for_resource_batch(
            year, month, batch, base_filename, "fake_usage_account"
        )
        mock_row_count.assert_called_once()
        mock_trino.assert_called_once()
        mock_copy.assert_called_once()
        expected_result = [expected_key]
        self.assertEqual(expected_result, upload_keys)

    @patch("subs.subs_data_extractor.SUBSDataExtractor.copy_data_to_subs_s3_bucket")
    @patch("subs.subs_data_extractor.SUBSDataExtractor._execute_trino_raw_sql_query_with_description")
    @patch("subs.subs_data_extractor.SUBSDataExtractor.determine_row_count")
    def test_gather_and_upload_for_resource_batch_no_result(self, mock_row_count, mock_trino, mock_copy):
        """Test uploading does not attempt with empty values from trino query."""
        self.dh.month_start(self.yesterday)
        rid = "12345"
        year = "2023"
        month = "04"
        rid_2 = "23456"
        start_time = datetime.datetime(2023, 4, 3, tzinfo=datetime.timezone.utc)
        end_time = datetime.datetime(2023, 4, 5, tzinfo=datetime.timezone.utc)
        batch = [
            {"rid": rid, "start": start_time, "end": end_time},
            {"rid": rid_2, "start": start_time, "end": end_time},
        ]
        mock_row_count.return_value = 10
        expected_key = "fake_key"
        base_filename = "fake_filename"
        mock_copy.return_value = expected_key
        mock_trino.return_value = ([], [("fake_col1",), ("fake_col2",)])
        upload_keys = self.extractor.gather_and_upload_for_resource_batch(
            year, month, batch, base_filename, "fake_usage_account"
        )
        mock_row_count.assert_called_once()
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

    def test_bulk_update_latest_processed_time_azure(self):
        """Test that timestamps for multiple resources are update in the DB when bulk updating processed times."""
        year = "2023"
        month = "04"
        rid1 = "54321"
        rid2 = "98765"
        instance_key_one = "my:fake:key"
        instance_key_two = "my:second:key"
        expected_time = datetime.datetime(2023, 6, 3, 15, tzinfo=datetime.timezone.utc)
        resources = [(rid1, instance_key_one, expected_time), (rid2, instance_key_two, expected_time)]
        with schema_context(self.schema):
            SubsLastProcessed.objects.create(
                source_uuid_id=self.azure_provider.uuid, resource_id=instance_key_one, year=year, month=month
            ).save()
            SubsLastProcessed.objects.create(
                source_uuid_id=self.azure_provider.uuid, resource_id=instance_key_two, year=year, month=month
            ).save()
        self.azure_extractor.bulk_update_latest_processed_time(resources, year, month)
        with schema_context(self.schema):
            subs_record_1 = SubsLastProcessed.objects.get(
                source_uuid_id=self.azure_provider.uuid, resource_id=instance_key_one, year=year, month=month
            )
            subs_record_2 = SubsLastProcessed.objects.get(
                source_uuid_id=self.azure_provider.uuid, resource_id=instance_key_two, year=year, month=month
            )
            self.assertEqual(subs_record_1.latest_processed_time, expected_time)
            self.assertEqual(subs_record_2.latest_processed_time, expected_time)

    def test_provider_creation_time(self):
        """Test provider processing time for different provider types."""
        aws_expected = self.aws_provider.created_timestamp.replace(
            microsecond=0, second=0, minute=0, hour=0
        ) - timedelta(days=1)
        azure_expected = self.azure_provider.created_timestamp.replace(
            microsecond=0, second=0, minute=0, hour=0
        ) - timedelta(days=2)
        self.assertEqual(aws_expected, self.extractor.creation_processing_time)
        self.assertEqual(azure_expected, self.azure_extractor.creation_processing_time)

    def test_get_latest_processed_dict_for_provider(self):
        """Test that one second is appropriately added to last processed time."""
        year = "2023"
        month = "06"
        rid = "fake_rid"
        base_time = datetime.datetime(2023, 6, 3, 15, tzinfo=datetime.timezone.utc)
        with schema_context(self.schema):
            SubsLastProcessed.objects.create(
                source_uuid_id=self.aws_provider.uuid,
                resource_id=rid,
                year=year,
                month=month,
                latest_processed_time=base_time,
            ).save()
        lpt_dict = self.extractor.get_latest_processed_dict_for_provider("2023", "06")
        actual_time = lpt_dict.get(rid)
        # One second should be added to the stored time to avoid processing overlaps
        self.assertEqual(base_time + timedelta(seconds=1), actual_time)
