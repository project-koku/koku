"""Collection of tests for customer-initiated data export requests API."""
from datetime import date

import faker
from django.test import TestCase

from api.dataexport.models import DataExportRequest
from api.iam.models import User

fake = faker.Faker()


class DataExportRequestTest(TestCase):
    """DataExportRequest test case."""

    def test_str_empty_instance(self):
        """Test str representation of a new empty instance."""
        data_export_request = DataExportRequest()
        the_str = str(data_export_request)
        self.assertTrue(the_str.startswith("DataExportRequest"))

    def test_str_fully_populated_instance(self):
        """Test str representation of a fully populated instance."""
        user = User.objects.create(username=fake.name())
        data_export_request = DataExportRequest.objects.create(
            start_date=date(2019, 1, 1), end_date=date(2019, 2, 1), created_by=user, bucket_name="my-test-bucket"
        )
        data_export_request.refresh_from_db()
        the_str = str(data_export_request)
        self.assertTrue(the_str.startswith("DataExportRequest"))
        self.assertIn(data_export_request.status, the_str)
        self.assertIn(str(data_export_request.uuid), the_str)
        self.assertIn(data_export_request.bucket_name, the_str)
        self.assertIn("2019-01-01", the_str)
        self.assertIn("2019-02-01", the_str)
