#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import uuid
from collections import defaultdict
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
        cls.context = {"some": "context", "provider_type": "AWS-local"}
        cls.azure_context = {"some": "context", "provider_type": "Azure-local"}
        cls.tracing_id = "trace_me"
        with patch("subs.subs_data_messenger.get_s3_resource"):
            cls.messenger = SUBSDataMessenger(cls.context, cls.schema, cls.tracing_id)
            cls.azure_messenger = SUBSDataMessenger(cls.azure_context, cls.schema, cls.tracing_id)

    @patch("subs.subs_data_messenger.os.remove")
    @patch("subs.subs_data_messenger.get_producer")
    @patch("subs.subs_data_messenger.csv.DictReader")
    @patch("subs.subs_data_messenger.SUBSDataMessenger.build_subs_dict")
    def test_process_and_send_subs_message(self, mock_msg_builder, mock_reader, mock_producer, mock_remove):
        """Tests that the proper functions are called when running process_and_send_subs_message"""
        upload_keys = ["fake_key"]
        mock_msg_builder.return_value = defaultdict(str)
        mock_reader.return_value = [
            {
                "subs_start_time": "2023-07-01T01:00:00Z",
                "subs_end_time": "2023-07-01T02:00:00Z",
                "subs_resource_id": "i-55555556",
                "subs_account": "9999999999999",
                "physical_cores": "1",
                "subs_vcpu": "2",
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

    def test_build_subs_dict(self):
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
        expected_subs_dict = {
            "event_id": str(static_uuid),
            "event_source": "cost-management",
            "event_type": "snapshot",
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
        with patch("subs.subs_data_messenger.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = static_uuid
            actual = self.messenger.build_subs_dict(
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
        self.assertEqual(expected_subs_dict, actual)

    def test_build_subs_dict_sap_role(self):
        """
        Test building the kafka message body
        """
        lineitem_resourceid = "i-55555556"
        lineitem_usagestartdate = "2023-07-01T01:00:00Z"
        lineitem_usageenddate = "2023-07-01T02:00:00Z"
        lineitem_usageaccountid = "9999999999999"
        product_vcpu = "2"
        usage = "Production"
        rol = "SAP"
        sla = "Premium"
        product_ids = ["479", "70"]
        static_uuid = uuid.uuid4()
        expected_subs_dict = {
            "event_id": str(static_uuid),
            "event_source": "cost-management",
            "event_type": "snapshot",
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
            "sla": sla,
            "usage": usage,
            "billing_provider": "aws",
            "billing_account_id": lineitem_usageaccountid,
        }
        with patch("subs.subs_data_messenger.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = static_uuid
            actual = self.messenger.build_subs_dict(
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
        self.assertEqual(expected_subs_dict, actual)

    def test_build_azure_subs_dict(self):
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
        tenant_id = "my-fake-id"
        static_uuid = uuid.uuid4()
        expected_subs_dict = {
            "event_id": str(static_uuid),
            "event_source": "cost-management",
            "event_type": "snapshot",
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
            "azure_subscription_id": lineitem_usageaccountid,
            "azure_tenant_id": tenant_id,
        }
        with patch("subs.subs_data_messenger.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = static_uuid
            actual = self.messenger.build_azure_subs_dict(
                lineitem_resourceid,
                lineitem_usageaccountid,
                lineitem_usagestartdate,
                lineitem_usageenddate,
                product_vcpu,
                sla,
                usage,
                rol,
                product_ids,
                tenant_id,
            )
        self.assertEqual(expected_subs_dict, actual)

    def test_build_azure_subs_dict_sap_role(self):
        """
        Test building the kafka message body
        """
        lineitem_resourceid = "i-55555556"
        lineitem_usagestartdate = "2023-07-01T01:00:00Z"
        lineitem_usageenddate = "2023-07-01T02:00:00Z"
        lineitem_usageaccountid = "9999999999999"
        product_vcpu = "2"
        usage = "Production"
        rol = "SAP"
        sla = "Premium"
        product_ids = ["479", "70"]
        tenant_id = "my-fake-id"
        static_uuid = uuid.uuid4()
        expected_subs_dict = {
            "event_id": str(static_uuid),
            "event_source": "cost-management",
            "event_type": "snapshot",
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
            "sla": sla,
            "usage": usage,
            "billing_provider": "aws",
            "azure_subscription_id": lineitem_usageaccountid,
            "azure_tenant_id": tenant_id,
        }
        with patch("subs.subs_data_messenger.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = static_uuid
            actual = self.messenger.build_azure_subs_dict(
                lineitem_resourceid,
                lineitem_usageaccountid,
                lineitem_usagestartdate,
                lineitem_usageenddate,
                product_vcpu,
                sla,
                usage,
                rol,
                product_ids,
                tenant_id,
            )
        self.assertEqual(expected_subs_dict, actual)

    @patch("subs.subs_data_messenger.get_producer")
    def test_send_kafka_message(self, mock_producer):
        """Test that we would try to send a kafka message"""
        kafka_msg = {"test"}
        self.messenger.send_kafka_message(kafka_msg)
        mock_producer.assert_called()

    def test_determine_azure_instance_and_tenant_id_tag(self):
        """Test getting the azure instance id from the row provided by a tag returns as expected."""
        expected_instance = "waffle-house"
        self.azure_messenger.instance_map = {}
        my_row = {
            "resourceid": "i-55555556",
            "subs_start_time": "2023-07-01T01:00:00Z",
            "subs_end_time": "2023-07-01T02:00:00Z",
            "subs_resource_id": "i-55555556",
            "subs_account": "9999999999999",
            "physical_cores": "1",
            "subs_vcpu": "2",
            "variant": "Server",
            "subs_usage": "Production",
            "subs_sla": "Premium",
            "subs_role": "Red Hat Enterprise Linux Server",
            "subs_product_ids": "479-70",
            "subs_instance": expected_instance,
            "source": self.azure_provider.uuid,
        }
        actual_instance, actual_tenant = self.azure_messenger.determine_azure_instance_and_tenant_id(my_row)
        self.assertEqual(expected_instance, actual_instance)
        self.assertEqual(self.azure_tenant, actual_tenant)

    def test_determine_azure_instance_and_tenant_id_local_prov(self):
        """Test that a local provider does not reach out to Azure."""
        self.azure_messenger.instance_map = {}
        expected_instance = ""
        my_row = {
            "resourceid": "i-55555556",
            "subs_start_time": "2023-07-01T01:00:00Z",
            "subs_end_time": "2023-07-01T02:00:00Z",
            "subs_resource_id": "i-55555556",
            "subs_account": "9999999999999",
            "physical_cores": "1",
            "subs_vcpu": "2",
            "variant": "Server",
            "subs_usage": "Production",
            "subs_sla": "Premium",
            "subs_role": "Red Hat Enterprise Linux Server",
            "subs_product_ids": "479-70",
            "subs_instance": "",
            "source": self.azure_provider.uuid,
        }
        actual_instance, actual_tenant = self.azure_messenger.determine_azure_instance_and_tenant_id(my_row)
        self.assertEqual(expected_instance, actual_instance)
        self.assertEqual(self.azure_tenant, actual_tenant)

    def test_determine_azure_instance_and_tenant_id_from_map(self):
        """Test getting the azure instance id from the instance map returns as expected."""
        expected_instance = "oh-yeah"
        expected_tenant = "my-tenant"
        self.azure_messenger.instance_map["i-55555556"] = (expected_instance, expected_tenant)
        my_row = {
            "resourceid": "i-55555556",
            "subs_start_time": "2023-07-01T01:00:00Z",
            "subs_end_time": "2023-07-01T02:00:00Z",
            "subs_resource_id": "i-55555556",
            "subs_account": "9999999999999",
            "physical_cores": "1",
            "subs_vcpu": "2",
            "variant": "Server",
            "subs_usage": "Production",
            "subs_sla": "Premium",
            "subs_role": "Red Hat Enterprise Linux Server",
            "subs_product_ids": "479-70",
            "subs_instance": "fake",
            "source": self.azure_provider.uuid,
        }
        actual_instance, actual_tenant = self.azure_messenger.determine_azure_instance_and_tenant_id(my_row)
        self.assertEqual(expected_instance, actual_instance)
        self.assertEqual(expected_tenant, actual_tenant)

    def test_determine_azure_instance_and_tenant_id(self):
        """Test getting the azure instance id from mock Azure Compute Client returns as expected."""
        expected_instance = "my-fake-id"
        self.messenger.instance_map = {}
        my_row = {
            "resourceid": "i-55555556",
            "subs_start_time": "2023-07-01T01:00:00Z",
            "subs_end_time": "2023-07-01T02:00:00Z",
            "subs_resource_id": "i-55555556",
            "subs_account": "9999999999999",
            "physical_cores": "1",
            "subs_vcpu": "2",
            "variant": "Server",
            "subs_usage": "Production",
            "subs_sla": "Premium",
            "subs_role": "Red Hat Enterprise Linux Server",
            "subs_product_ids": "479-70",
            "subs_instance": "",
            "source": self.azure_provider.uuid,
            "resourcegroup": "my-fake-rg",
        }
        with patch("subs.subs_data_messenger.AzureClientFactory") as mock_factory:
            mock_factory.return_value.compute_client.virtual_machines.get.return_value.vm_id = expected_instance
            actual_instance, actual_tenant = self.messenger.determine_azure_instance_and_tenant_id(my_row)
        self.assertEqual(expected_instance, actual_instance)
        self.assertEqual(self.azure_tenant, actual_tenant)

    @patch("subs.subs_data_messenger.SUBSDataMessenger.determine_azure_instance_and_tenant_id")
    @patch("subs.subs_data_messenger.os.remove")
    @patch("subs.subs_data_messenger.get_producer")
    @patch("subs.subs_data_messenger.csv.DictReader")
    def test_process_and_send_subs_message_azure_with_id(self, mock_reader, mock_producer, mock_remove, mock_azure_id):
        """Tests that the proper functions are called when running process_and_send_subs_message with Azure provider."""
        upload_keys = ["fake_key"]
        self.azure_messenger.date_map = defaultdict(list)
        mock_azure_id.return_value = ("string1", "string2")
        mock_reader.return_value = [
            {
                "resourceid": "i-55555556",
                "subs_start_time": "2023-07-01T01:00:00Z",
                "subs_end_time": "2023-07-01T02:00:00Z",
                "subs_resource_id": "i-55555556",
                "subs_account": "9999999999999",
                "physical_cores": "1",
                "subs_vcpu": "2",
                "variant": "Server",
                "subs_usage": "Production",
                "subs_sla": "Premium",
                "subs_role": "Red Hat Enterprise Linux Server",
                "subs_usage_quantity": "4",
                "subs_product_ids": "479-70",
                "subs_instance": "",
                "source": self.azure_provider.uuid,
                "resourcegroup": "my-fake-rg",
            }
        ]
        mock_op = mock_open(read_data="x,y,z")
        with patch("builtins.open", mock_op):
            self.azure_messenger.process_and_send_subs_message(upload_keys)
        mock_azure_id.assert_called_once()
        self.assertEqual(mock_producer.call_count, 4)

    @patch("subs.subs_data_messenger.SUBSDataMessenger.determine_azure_instance_and_tenant_id")
    @patch("subs.subs_data_messenger.os.remove")
    @patch("subs.subs_data_messenger.get_producer")
    @patch("subs.subs_data_messenger.csv.DictReader")
    @patch("subs.subs_data_messenger.SUBSDataMessenger.build_subs_dict")
    def test_process_and_send_subs_message_azure_time_already_processed(
        self, mock_msg_builder, mock_reader, mock_producer, mock_remove, mock_azure_id
    ):
        """Tests that the functions are not called for a provider that has already processed."""
        upload_keys = ["fake_key"]
        self.azure_messenger.date_map["2023-07-01T01:00:00Z"] = "i-55555556"
        mock_reader.return_value = [
            {
                "resourceid": "i-55555556",
                "subs_start_time": "2023-07-01T01:00:00Z",
                "subs_end_time": "2023-07-01T02:00:00Z",
                "subs_resource_id": "i-55555556",
                "subs_account": "9999999999999",
                "physical_cores": "1",
                "subs_vcpu": "2",
                "variant": "Server",
                "subs_usage": "Production",
                "subs_sla": "Premium",
                "subs_role": "Red Hat Enterprise Linux Server",
                "subs_product_ids": "479-70",
                "subs_instance": "",
                "source": self.azure_provider.uuid,
                "resourcegroup": "my-fake-rg",
            }
        ]
        mock_op = mock_open(read_data="x,y,z")
        with patch("builtins.open", mock_op):
            self.azure_messenger.process_and_send_subs_message(upload_keys)
        mock_azure_id.assert_not_called()
        mock_msg_builder.assert_not_called()
        mock_producer.assert_not_called()
