"""Upload utils tests."""
import uuid
from datetime import date

from django.test import TestCase

from masu.util.upload import get_upload_path


class TestUploadUtils(TestCase):
    """Test cases for upload utils."""

    def test_get_upload_path(self):
        """Assert get_upload_path produces an appropriate S3 path for the month."""
        report_date = date(2018, 4, 1)
        schema_name = "test_acct"
        provider_type = "test_type"
        provider_uuid = uuid.UUID("de4db3ef-a185-4bad-b33f-d15ea5edc0de", version=4)
        table_name = "test_table"
        with self.settings(S3_BUCKET_PATH="bucket"):
            path = get_upload_path(schema_name, provider_type, provider_uuid, report_date, table_name)
            self.assertEqual(
                "bucket/test_acct/test_type/de4db3ef-a185-4bad-b33f-d15ea5edc0de/2018/04/00/test_table.csv.gz", path
            )

    def test_get_upload_path_daily(self):
        """Assert get_upload_path produces an appropriate S3 path including day of month."""
        report_date = date(2018, 4, 1)
        schema_name = "test_acct"
        provider_type = "test_type"
        provider_uuid = uuid.UUID("de4db3ef-a185-4bad-b33f-d15ea5edc0de", version=4)
        table_name = "test_table"
        with self.settings(S3_BUCKET_PATH="bucket"):
            path = get_upload_path(schema_name, provider_type, provider_uuid, report_date, table_name, daily=True)
            self.assertEqual(
                "bucket/test_acct/test_type/de4db3ef-a185-4bad-b33f-d15ea5edc0de/2018/04/01/test_table.csv.gz", path
            )
