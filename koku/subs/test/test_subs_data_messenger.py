#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json
import uuid
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
        with patch("subs.subs_data_messenger.get_subs_s3_client"):
            cls.messenger = SUBSDataMessenger(cls.context, cls.schema, cls.tracing_id)

    @patch("subs.subs_data_messenger.get_producer")
    @patch("subs.subs_data_messenger.csv.DictReader")
    @patch("subs.subs_data_messenger.StringIO")
    @patch("subs.subs_data_messenger.SUBSDataMessenger.build_subs_msg")
    def test_process_and_send_subs_message(self, mock_msg_builder, mock_stringio, mock_reader, mock_producer):
        """Tests that the proper functions are called when running process_and_send_subs_message"""
        upload_keys = ["fake_key"]
        mock_reader.return_value = [
            {
                "tstamp": "2023-07-01T01:00:00Z/2023-07-01T02:00:00Z",
                "instance_id": "i-55555556",
                "billing_account_id": "9999999999999",
                "physical_cores": "1",
                "cpu_count": "2",
                "variant": "Server",
                "usage": "Production",
                "sla": "Premium",
            }
        ]
        self.messenger.process_and_send_subs_message(upload_keys)
        mock_msg_builder.assert_called_once()
        mock_producer.assert_called_once()

    def test_build_subs_msg(self):
        """
        Test building the kafka message body

        sample_row = {'tstamp': '2023-07-01T01:00:00Z/2023-07-01T02:00:00Z', 'instance_id': 'i-55555556',
        'billing_account_id': '9999999999999', 'physical_cores': '1', 'cpu_count': '2',
        'variant': 'Server', 'usage': 'Production', 'sla': 'Premium'}
        """
        instance_id = "i-55555556"
        tstamp = "2023-07-01T01:00:00Z/2023-07-01T02:00:00Z"
        billing_account_id = "9999999999999"
        cpu_count = "2"
        usage = "Production"
        sla = "Premium"

        static_uuid = uuid.uuid4()
        expected_subs_json = {
            "event_id": str(static_uuid),
            "event_source": "cost-management",
            "event_type": "Snapshot",
            "account_number": self.acct,
            "org_id": self.org_id,
            "service_type": "RHEL System",
            "instance_id": instance_id,
            "timestamp": tstamp,
            "expiration": "date-time-offset",
            "display_name": "system name",
            # "inventory_id": "string", # likely wont have
            # "insights_id": "string", # likely wont have
            # "subscription_manager_id": "string", # likely wont have
            # "correlation_ids": ["id"],
            "measurements": [{"value": cpu_count, "uom": "Cores"}],
            "cloud_provider": "AWS",
            "hardware_type": "Cloud",
            # "hypervisor_uuid": "string", # wont have
            # "product_ids": ["69"],
            "role": "Red Hat Enterprise Linux Server",
            "sla": sla,
            "usage": usage,
            "uom": "Cores",
            "billing_provider": "aws",
            "billing_account_id": billing_account_id,
        }
        expected = bytes(json.dumps(expected_subs_json), "utf-8")
        with patch("subs.subs_data_messenger.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = static_uuid
            actual = self.messenger.build_subs_msg(instance_id, tstamp, cpu_count, sla, usage, billing_account_id)
        self.assertEqual(expected, actual)

    @patch("subs.subs_data_messenger.get_producer")
    def test_send_kafka_message(self, mock_producer):
        """Test that we would try to send a kafka message"""
        kafka_msg = {"test"}
        self.messenger.send_kafka_message(kafka_msg)
        mock_producer.assert_called()
