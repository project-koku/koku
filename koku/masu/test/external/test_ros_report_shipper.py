#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json
from unittest import TestCase
from unittest.mock import patch

from botocore.exceptions import EndpointConnectionError

from api.utils import DateHelper
from masu.external.ros_report_shipper import ROSReportShipper


class TestROSReportShipper(TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.schema_name = "org1234567"
        cls.b64_identity = "identity"
        cls.source_id = 4
        cls.provider_uuid = "1b09c37c-a0ca-4ad0-ac08-8db88e55e08f"
        cls.request_id = "4"
        cls.cluster_id = "ros-ocp-cluster-test"
        cls.account_id = "1234"
        cls.org_id = "5678"
        test_report_meta = {
            "cluster_id": cls.cluster_id,
            "manifest_id": "300",
            "source_id": cls.source_id,
            "provider_uuid": cls.provider_uuid,
            "request_id": cls.request_id,
            "schema_name": cls.schema_name,
        }
        test_context = {
            "account": cls.account_id,
            "org_id": cls.org_id,
        }
        with patch("masu.external.ros_report_shipper.get_ros_s3_client"):
            cls.ros_shipper = ROSReportShipper(
                test_report_meta,
                cls.b64_identity,
                test_context,
            )

    def test_ros_s3_path(self):
        """tests that the generated s3 path is expected"""
        expected = f"{self.schema_name}/source={self.provider_uuid}/date={DateHelper().today.date()}"
        actual = self.ros_shipper.ros_s3_path
        self.assertEqual(expected, actual)

    @patch("masu.external.ros_report_shipper.UNLEASH_CLIENT.is_enabled", return_value=True)
    @patch("masu.external.ros_report_shipper.ROSReportShipper.copy_local_report_file_to_ros_s3_bucket")
    @patch("masu.external.ros_report_shipper.ROSReportShipper.build_ros_msg")
    @patch("masu.external.ros_report_shipper.ROSReportShipper.send_kafka_message")
    def test_process_manifest_reports(self, mock_kafka_msg, mock_ros_msg, mock_report_copy, *args):
        """Tests that process_manifest_reports flows as expected under normal circumstances."""
        self.ros_shipper.process_manifest_reports([("report1", "path1")])
        mock_report_copy.assert_called_once()
        mock_ros_msg.assert_called_once()
        mock_kafka_msg.assert_called_once()

    @patch("masu.external.ros_report_shipper.UNLEASH_CLIENT.is_enabled", return_value=False)
    @patch("masu.external.ros_report_shipper.ROSReportShipper.copy_local_report_file_to_ros_s3_bucket")
    @patch("masu.external.ros_report_shipper.ROSReportShipper.build_ros_msg")
    @patch("masu.external.ros_report_shipper.ROSReportShipper.send_kafka_message")
    def test_process_manifest_reports_unleash_gate(self, mock_kafka_msg, mock_ros_msg, mock_report_copy, *args):
        """Tests that process_manifest_reports flows as expected with unleash gating."""
        self.ros_shipper.process_manifest_reports([("report1", "path1")])
        mock_report_copy.assert_called_once()
        mock_ros_msg.assert_not_called()
        mock_kafka_msg.assert_not_called()

    @patch("masu.external.ros_report_shipper.UNLEASH_CLIENT.is_enabled", return_value=True)
    @patch("masu.external.ros_report_shipper.ROSReportShipper.copy_local_report_file_to_ros_s3_bucket")
    @patch("masu.external.ros_report_shipper.ROSReportShipper.build_ros_msg")
    @patch("masu.external.ros_report_shipper.ROSReportShipper.send_kafka_message")
    def test_process_manifest_reports_no_reports_uploaded(self, mock_kafka_msg, mock_ros_msg, mock_report_copy, *args):
        """Tests that we do not send a kafka message if there were no reports successfully uploaded to s3"""
        mock_report_copy.return_value = None
        self.ros_shipper.process_manifest_reports([("report1", "path1")])
        mock_report_copy.assert_called_once()
        mock_ros_msg.assert_not_called()
        mock_kafka_msg.assert_not_called()

    @patch("masu.external.ros_report_shipper.generate_s3_object_url")
    def test_copy_data_to_ros_s3_bucket(self, mock_url):
        """Test copy_data_to_ros_s3_bucket."""
        self.ros_shipper.copy_data_to_ros_s3_bucket("filename", "data")
        mock_url.assert_called_once_with(self.ros_shipper.s3_client, f"{self.ros_shipper.ros_s3_path}/filename")

    def test_copy_data_to_ros_s3_bucket_conn_error(self):
        """Test that an error copying data results in no url being returned"""
        self.ros_shipper.s3_client.upload_fileobj.side_effect = EndpointConnectionError(endpoint_url="fakeurl")
        new_upload = self.ros_shipper.copy_data_to_ros_s3_bucket("filename", "data")
        self.assertEqual(None, new_upload)

    @patch("masu.external.ros_report_shipper.get_producer")
    def test_send_kafka_message(self, mock_producer):
        """Test that we would try to send a kafka message"""
        kafka_msg = {"test"}
        self.ros_shipper.send_kafka_message(kafka_msg)
        mock_producer.assert_called()

    def test_build_ros_msg(self):
        """Test that the built ros msg looks like the expected message"""
        expected_json = {
            "request_id": self.request_id,
            "b64_identity": self.b64_identity,
            "metadata": {
                "account": self.account_id,
                "org_id": self.org_id,
                "source_id": self.source_id,
                "provider_uuid": self.provider_uuid,
                "cluster_uuid": self.cluster_id,
                "cluster_alias": "my-source-name",
            },
            "files": ["report1_url"],
            "object_keys": ["path1"],
        }
        expected_msg = bytes(json.dumps(expected_json), "utf-8")
        with patch("masu.external.ros_report_shipper.ProviderDBAccessor.get_provider_name") as mock_providerdba:
            mock_providerdba.return_value = "my-source-name"
            actual = self.ros_shipper.build_ros_msg(["report1_url"], ["path1"])
        self.assertEqual(actual, expected_msg)
