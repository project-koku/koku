#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json
import uuid
from unittest.mock import mock_open
from unittest.mock import patch

from subs.subs_data_messenger import SUBSDataMessenger
from subs.test import SUBSTestCase


class TestSUBSDataMessenger(SUBSTestCase):
    """Test class for the SUBSDataMessenger"""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.context = {"some": "context"}
        cls.tracing_id = "trace_me"
        with patch("subs.subs_data_messenger.get_s3_resource"):
            cls.messenger = SUBSDataMessenger(cls.context, cls.schema, cls.tracing_id)

    @patch("subs.subs_data_messenger.os.remove")
    @patch("subs.subs_data_messenger.get_producer")
    @patch("subs.subs_data_messenger.csv.DictReader")
    @patch("subs.subs_data_messenger.SUBSDataMessenger.build_subs_msg")
    def test_process_and_send_subs_message(self, mock_msg_builder, mock_reader, mock_producer, mock_remove):
        """Tests that the proper functions are called when running process_and_send_subs_message"""
        upload_keys = ["fake_key"]
        mock_reader.return_value = [
            {
                "lineitem_usagestartdate": "2023-07-01T01:00:00Z",
                "lineitem_usageenddate": "2023-07-01T02:00:00Z",
                "lineitem_resourceid": "i-55555556",
                "lineitem_usageaccountid": "9999999999999",
                "physical_cores": "1",
                "product_vcpu": "2",
                "variant": "Server",
                "subs_usage": "Production",
                "subs_sla": "Premium",
                "subs_role": "Red Hat Enterprise Linux Server",
                "subs_product_ids": "479-70",
            }
        ]
        mock_op = mock_open(read_data="x,y,z")
        with patch("builtins.open", mock_op):
            self.messenger.process_and_send_subs_message(upload_keys)
        mock_msg_builder.assert_called_once()
        mock_producer.assert_called_once()

    def test_build_subs_msg(self):
        """
        Test building the kafka message body
        """
        lineitem_resourceid = "i-55555556"
        lineitem_usagestartdate = "2023-07-01T01:00:00Z"
        lineitem_usageenddate = "2023-07-01T02:00:00Z"
        lineitem_usageaccountid = "9999999999999"
        product_vcpu = "2"
        usage = "Production"
        rol = "Red Hat Enterprise Linux Server"
        sla = "Premium"
        product_ids = ["479", "70"]
        static_uuid = uuid.uuid4()
        expected_subs_json = {
            "event_id": str(static_uuid),
            "event_source": "cost-management",
            "event_type": "Snapshot",
            "account_number": self.acct,
            "org_id": self.org_id,
            "service_type": "RHEL System",
            "instance_id": lineitem_resourceid,
            "timestamp": lineitem_usagestartdate,
            "expiration": lineitem_usageenddate,
            "measurements": [{"value": product_vcpu, "uom": "vCPUs"}],
            "cloud_provider": "AWS",
            "hardware_type": "Cloud",
            "product_ids": product_ids,
            "role": rol,
            "sla": sla,
            "usage": usage,
            "billing_provider": "aws",
            "billing_account_id": lineitem_usageaccountid,
        }
        expected = bytes(json.dumps(expected_subs_json), "utf-8")
        with patch("subs.subs_data_messenger.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = static_uuid
            actual = self.messenger.build_subs_msg(
                lineitem_resourceid,
                lineitem_usageaccountid,
                lineitem_usagestartdate,
                lineitem_usageenddate,
                product_vcpu,
                sla,
                usage,
                rol,
                product_ids,
            )
        self.assertEqual(expected, actual)

    @patch("subs.subs_data_messenger.get_producer")
    def test_send_kafka_message(self, mock_producer):
        """Test that we would try to send a kafka message"""
        kafka_msg = {"test"}
        self.messenger.send_kafka_message(kafka_msg)
        mock_producer.assert_called()
