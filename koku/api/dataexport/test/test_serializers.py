"""Tests for data export serializers."""
from base64 import b64encode
from json import dumps as json_dumps
from unittest.mock import Mock
from unittest.mock import patch

import faker

from api.common import RH_IDENTITY_HEADER
from api.dataexport.models import DataExportRequest
from api.dataexport.serializers import DataExportRequestSerializer
from api.iam.models import User
from masu.test import MasuTestCase

_faker = faker.Faker()


class DataExportRequestSerializerTest(MasuTestCase):
    """
    Test the Data Export Request Serializer.

    Inherit from MasuTestCase to get the customer and schema set up.
    """

    def setUp(self):
        """Set up the shared variables required for this test."""
        super().setUp()
        username = _faker.user_name()
        email = _faker.email()
        user = User.objects.create(username=username, email=email)

        identity = {
            "identity": {
                "account_number": "10001",
                "type": "User",
                "user": {"username": username, "email": email, "is_org_admin": False},
            },
            "entitlements": {"cost_management": {"is_entitled": True}},
        }
        json_identity = json_dumps(identity)
        mock_header = b64encode(json_identity.encode("utf-8")).decode("utf-8")

        mock_request = Mock()
        mock_request.user = user
        mock_request.META = {RH_IDENTITY_HEADER: mock_header}

        self.context = {"request": mock_request}

    @patch("api.dataexport.serializers.transaction.on_commit")
    @patch("api.dataexport.serializers.sync_data_to_customer")
    def test_sync_data_to_customer_called(self, mock_sync_data_to_customer, mock_commit):
        """Test that creating a DataExportRequest kicks off a sync_data_to_customer task."""
        mock_commit.side_effect = mock_sync_data_to_customer.delay()
        validated_data = {"bucket_name": "fake-bucket", "start_date": "2019-11-01", "end_date": "2019-12-01"}
        serializer = DataExportRequestSerializer(context=self.context)
        result = serializer.create(validated_data)
        self.assertIsInstance(result, DataExportRequest)
        mock_sync_data_to_customer.delay.assert_called()
