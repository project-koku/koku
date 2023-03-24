import json
from unittest.mock import patch

from botocore.exceptions import ClientError
from django.test import TestCase

from api.utils import DateHelper
from masu.external.ros_report_shipper import ROSReportShipper


class TestROSReportShipper(TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.schema_name = "org1234567"
        cls.b64_identity = "identity"
        cls.provider_uuid = "1b09c37c-a0ca-4ad0-ac08-8db88e55e08f"
        cls.request_id = "4"
        cls.cluster_id = "ros-ocp-cluster-test"
        cls.account_id = "1234"
        cls.org_id = "5678"
        cls.ros_shipper = ROSReportShipper(
            cls.account_id,
            cls.b64_identity,
            cls.cluster_id,
            "300",
            cls.org_id,
            cls.provider_uuid,
            cls.request_id,
            cls.schema_name,
        )

    def test_ros_s3_path(self):
        expected = f"{self.schema_name}/source={self.provider_uuid}/{DateHelper().today.date()}"
        actual = self.ros_shipper.ros_s3_path
        self.assertEqual(expected, actual)

    @patch("masu.external.ros_report_shipper.ROSReportShipper.copy_local_report_file_to_ros_s3_bucket")
    @patch("masu.external.ros_report_shipper.ROSReportShipper.build_ros_json")
    @patch("masu.external.ros_report_shipper.ROSReportShipper.send_kafka_confirmation")
    def test_process_manifest_reports(self, mock_kafka_conf, mock_ros_json, mock_report_copy):
        self.ros_shipper.process_manifest_reports([("report1", "path1")])
        mock_report_copy.assert_called_once()
        mock_ros_json.assert_called_once()
        mock_kafka_conf.assert_called_once()

    def test_copy_data_to_ros_s3_bucket(self):
        """Test copy_data_to_s3_bucket."""
        with patch("masu.external.ros_report_shipper.get_ros_s3_resource") as mock_s3:
            upload = self.ros_shipper.copy_data_to_ros_s3_bucket("filename", "data")
            self.assertEqual(f"{self.ros_shipper.ros_s3_path}/filename", upload)

        with patch("masu.external.ros_report_shipper.get_ros_s3_resource") as mock_s3:
            mock_s3.side_effect = ClientError({}, "Error")
            new_upload = self.ros_shipper.copy_data_to_ros_s3_bucket("filename", "data")
            self.assertEqual(None, new_upload)

    @patch("masu.external.ros_report_shipper.get_producer")
    def test_send_kafka_confirmation(self, mock_producer):
        kafka_msg = {"test"}
        self.ros_shipper.send_kafka_confirmation(kafka_msg)
        mock_producer.assert_called()

    def test_build_ros_json(self):
        expected_json = {
            "request_id": self.request_id,
            "b64_identity": self.b64_identity,
            "metadata": {
                "account": self.account_id,
                "org_id": self.org_id,
                "source_id": self.provider_uuid,
                "cluster_uuid": self.cluster_id,
                "cluster_alias": "my-source-name",
            },
            "files": ["report1"],
        }
        expected_msg = bytes(json.dumps(expected_json), "utf-8")
        with patch("masu.external.ros_report_shipper.ProviderDBAccessor.get_provider_name") as mock_providerdba:
            mock_providerdba.return_value = "my-source-name"
            actual = self.ros_shipper.build_ros_json(["report1"])
        self.assertEqual(actual, expected_msg)
