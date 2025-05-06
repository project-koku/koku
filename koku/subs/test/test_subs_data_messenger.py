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
    @patch("subs.subs_data_messenger.csv.DictReader")
    @patch("subs.subs_data_messenger.SUBSDataMessenger.build_aws_subs_dict")
    def test_process_and_send_subs_message(self, mock_msg_builder, mock_reader, mock_remove):
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
                "subs_rhel_version": "479",
                "subs_addon_id": "204",
                "subs_conversion": "true",
            }
        ]
        mock_op = mock_open(read_data="x,y,z")
        with patch("builtins.open", mock_op):
            self.messenger.process_and_send_subs_message(upload_keys)
        mock_msg_builder.assert_called_once()

    @patch("subs.subs_data_messenger.os.remove")
    @patch("subs.subs_data_messenger.get_producer")
    @patch("subs.subs_data_messenger.csv.DictReader")
    @patch("subs.subs_data_messenger.SUBSDataMessenger.build_aws_subs_dict")
    def test_process_and_send_subs_message_exception(self, mock_msg_builder, mock_reader, mock_producer, mock_remove):
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
                "subs_vcpu": "a",
                "variant": "Server",
                "subs_usage": "Production",
                "subs_sla": "Premium",
                "subs_role": "Red Hat Enterprise Linux Server",
                "subs_rhel_version": "479",
                "subs_addon_id": "204",
                "subs_conversion": "true",
            }
        ]
        mock_op = mock_open(read_data="x,y,z")
        with patch("builtins.open", mock_op):
            self.messenger.process_and_send_subs_message(upload_keys)
        mock_msg_builder.assert_called_once()

    def test_build_base_subs_dict(self):
        """
        Test building the kafka message body
        """
        lineitem_resourceid = "i-55555556"
        lineitem_usagestartdate = "2023-07-01T01:00:00Z"
        lineitem_usageenddate = "2023-07-01T02:00:00Z"
        product_vcpu = "2"
        version = "479"
        converted = "true"
        usage = "Production"
        rol = "Red Hat Enterprise Linux Server"
        sla = "Premium"
        product_ids = ["479", "204"]
        addon = "204"
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
            "measurements": [{"value": product_vcpu, "metric_id": "vCPUs"}],
            "cloud_provider": "AWS",
            "hardware_type": "Cloud",
            "product_ids": product_ids,
            "role": rol,
            "sla": sla,
            "usage": usage,
            "billing_provider": "aws",
            "conversion": True,
        }
        with patch("subs.subs_data_messenger.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = static_uuid
            actual = self.messenger.build_base_subs_dict(
                lineitem_resourceid,
                lineitem_usagestartdate,
                lineitem_usageenddate,
                product_vcpu,
                version,
                sla,
                usage,
                rol,
                converted,
                addon,
            )
        self.assertEqual(expected_subs_dict, actual)

    def test_build_aws_subs_dict(self):
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
        addon = "204"
        version = "479"
        product_ids = ["479", "204"]
        converted = "true"
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
            "measurements": [{"value": product_vcpu, "metric_id": "vCPUs"}],
            "cloud_provider": "AWS",
            "hardware_type": "Cloud",
            "product_ids": product_ids,
            "role": rol,
            "sla": sla,
            "usage": usage,
            "billing_provider": "aws",
            "billing_account_id": lineitem_usageaccountid,
            "conversion": True,
        }
        with patch("subs.subs_data_messenger.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = static_uuid
            actual = self.messenger.build_aws_subs_dict(
                lineitem_resourceid,
                lineitem_usageaccountid,
                lineitem_usagestartdate,
                lineitem_usageenddate,
                product_vcpu,
                version,
                sla,
                usage,
                rol,
                converted,
                addon,
            )
        self.assertEqual(expected_subs_dict, actual)

    def test_build_base_subs_dict_sap_role(self):
        """
        Test building the kafka message body
        """
        lineitem_resourceid = "i-55555556"
        lineitem_usagestartdate = "2023-07-01T01:00:00Z"
        lineitem_usageenddate = "2023-07-01T02:00:00Z"
        product_vcpu = "2"
        usage = "Production"
        rol = "SAP"
        sla = "Premium"
        product_ids = ["241", "479", "204"]
        version = "479"
        addon = "204"
        converted = "true"
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
            "measurements": [{"value": product_vcpu, "metric_id": "vCPUs"}],
            "cloud_provider": "AWS",
            "hardware_type": "Cloud",
            "product_ids": product_ids,
            "sla": sla,
            "usage": usage,
            "billing_provider": "aws",
            "conversion": True,
        }
        with patch("subs.subs_data_messenger.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = static_uuid
            actual = self.messenger.build_base_subs_dict(
                lineitem_resourceid,
                lineitem_usagestartdate,
                lineitem_usageenddate,
                product_vcpu,
                version,
                sla,
                usage,
                rol,
                converted,
                addon,
            )
        self.assertEqual(expected_subs_dict, actual)

    def test_build_base_subs_dict_addon_els(self):
        """
        Test building the kafka message body
        """
        lineitem_resourceid = "i-55555556"
        lineitem_usagestartdate = "2023-07-01T01:00:00Z"
        lineitem_usageenddate = "2023-07-01T02:00:00Z"
        product_vcpu = "2"
        version = "479"
        converted = "false"
        usage = "Production"
        rol = "SAP"
        sla = "Premium"
        product_ids = ["241", "479", "204"]
        addon = "204"
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
            "measurements": [{"value": product_vcpu, "metric_id": "vCPUs"}],
            "cloud_provider": "AWS",
            "hardware_type": "Cloud",
            "product_ids": product_ids,
            "sla": sla,
            "usage": usage,
            "billing_provider": "aws",
            "conversion": False,
        }
        with patch("subs.subs_data_messenger.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = static_uuid
            actual = self.messenger.build_base_subs_dict(
                lineitem_resourceid,
                lineitem_usagestartdate,
                lineitem_usageenddate,
                product_vcpu,
                version,
                sla,
                usage,
                rol,
                converted,
                addon,
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
        version = "479"
        converted = "true"
        usage = "Production"
        rol = "Red Hat Enterprise Linux Server"
        sla = "Premium"
        product_ids = ["479", "204"]
        addon = "204"
        tenant_id = "my-fake-id"
        vm_name = "my-fake-vm"
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
            "measurements": [{"value": product_vcpu, "metric_id": "vCPUs"}],
            "cloud_provider": "AWS",
            "hardware_type": "Cloud",
            "product_ids": product_ids,
            "role": rol,
            "sla": sla,
            "usage": usage,
            "billing_provider": "aws",
            "azure_subscription_id": lineitem_usageaccountid,
            "azure_tenant_id": tenant_id,
            "conversion": True,
            "display_name": vm_name,
        }
        with patch("subs.subs_data_messenger.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = static_uuid
            actual = self.messenger.build_azure_subs_dict(
                lineitem_resourceid,
                lineitem_usageaccountid,
                lineitem_usagestartdate,
                lineitem_usageenddate,
                product_vcpu,
                version,
                sla,
                usage,
                rol,
                converted,
                addon,
                tenant_id,
                vm_name,
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
        version = "479"
        converted = "true"
        usage = "Production"
        rol = "SAP"
        sla = "Premium"
        addon = "204"
        product_ids = ["241", "479", "204"]
        tenant_id = "my-fake-id"
        vm_name = "my-fake-vm"
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
            "measurements": [{"value": product_vcpu, "metric_id": "vCPUs"}],
            "cloud_provider": "AWS",
            "hardware_type": "Cloud",
            "product_ids": product_ids,
            "sla": sla,
            "usage": usage,
            "billing_provider": "aws",
            "azure_subscription_id": lineitem_usageaccountid,
            "azure_tenant_id": tenant_id,
            "conversion": True,
            "display_name": vm_name,
        }
        with patch("subs.subs_data_messenger.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value = static_uuid
            actual = self.messenger.build_azure_subs_dict(
                lineitem_resourceid,
                lineitem_usageaccountid,
                lineitem_usagestartdate,
                lineitem_usageenddate,
                product_vcpu,
                version,
                sla,
                usage,
                rol,
                converted,
                addon,
                tenant_id,
                vm_name,
            )
        self.assertEqual(expected_subs_dict, actual)

    @patch("subs.subs_data_messenger.get_producer")
    def test_send_kafka_message(self, mock_producer):
        """Test that we would try to send a kafka message"""
        kafka_msg = {"instance_id": "test"}
        self.messenger.send_kafka_message(kafka_msg)
        mock_producer.assert_called()

    def test_determine_azure_instance_and_tenant_id_tag(self):
        """Test getting the azure instance id from the row provided by a tag returns as expected."""
        expected_instance = "waffle-house"
        self.azure_messenger.instance_map = {}
        instance_key = "fake-instance-key"
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
            "subs_addon": "false",
            "resourcegroup": "my-fake-rg",
            "subs_vmname": "my-fake-vm",
            "subs_instance": expected_instance,
            "source": self.azure_provider.uuid,
        }
        actual_instance, actual_tenant = self.azure_messenger.determine_azure_instance_and_tenant_id(
            my_row, instance_key
        )
        self.assertEqual(expected_instance, actual_instance)
        self.assertEqual(self.azure_tenant, actual_tenant)

    def test_determine_azure_instance_and_tenant_id_from_map(self):
        """Test getting the azure instance id from the instance map returns as expected."""
        expected_instance = "oh-yeah"
        expected_tenant = "my-tenant"
        instance_key = "i-55555556_extra_fake"
        self.azure_messenger.instance_map[instance_key] = (expected_instance, expected_tenant)
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
            "subs_addon": "false",
            "subs_instance": "fake",
            "subs_vmname": "extra_fake",
            "source": self.azure_provider.uuid,
        }
        actual_instance, actual_tenant = self.azure_messenger.determine_azure_instance_and_tenant_id(
            my_row, instance_key
        )
        self.assertEqual(expected_instance, actual_instance)
        self.assertEqual(expected_tenant, actual_tenant)

    def test_determine_azure_instance_and_tenant_id(self):
        """Test building the Azure instance id returns as expected."""
        subs_account = "9999999999999"
        resource_group = "my-fake-rg"
        vm_name = "my-fake-vm"
        instance_key = f"{subs_account}:{resource_group}:{vm_name}"
        expected_instance = instance_key
        self.messenger.instance_map = {}
        my_row = {
            "resourceid": "i-55555556",
            "subs_start_time": "2023-07-01T01:00:00Z",
            "subs_end_time": "2023-07-01T02:00:00Z",
            "subs_resource_id": "i-55555556",
            "subs_account": subs_account,
            "physical_cores": "1",
            "subs_vcpu": "2",
            "variant": "Server",
            "subs_usage": "Production",
            "subs_sla": "Premium",
            "subs_role": "Red Hat Enterprise Linux Server",
            "subs_product_ids": "479-70",
            "subs_addon": "false",
            "subs_instance": "",
            "source": self.azure_provider.uuid,
            "resourcegroup": resource_group,
            "subs_vmname": vm_name,
        }
        actual_instance, actual_tenant = self.messenger.determine_azure_instance_and_tenant_id(my_row, instance_key)
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
                "subs_rhel_version": "479",
                "subs_addon_id": "204",
                "subs_conversion": "true",
                "subs_instance": "",
                "source": self.azure_provider.uuid,
                "resourcegroup": "my-fake-rg",
                "subs_vmname": "my-fake-vm",
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
    def test_process_and_send_subs_message_azure_with_id_exception(
        self, mock_reader, mock_producer, mock_remove, mock_azure_id
    ):
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
                "subs_vcpu": "a",
                "variant": "Server",
                "subs_usage": "Production",
                "subs_sla": "Premium",
                "subs_role": "Red Hat Enterprise Linux Server",
                "subs_usage_quantity": "4",
                "subs_rhel_version": "479",
                "subs_addon_id": "204",
                "subs_conversion": "true",
                "subs_instance": "",
                "source": self.azure_provider.uuid,
                "resourcegroup": "my-fake-rg",
                "subs_vmname": "my-fake-vm",
            }
        ]
        mock_op = mock_open(read_data="x,y,z")
        with patch("builtins.open", mock_op):
            self.azure_messenger.process_and_send_subs_message(upload_keys)
        mock_azure_id.assert_called_once()

    @patch("subs.subs_data_messenger.SUBSDataMessenger.determine_azure_instance_and_tenant_id")
    @patch("subs.subs_data_messenger.os.remove")
    @patch("subs.subs_data_messenger.csv.DictReader")
    @patch("subs.subs_data_messenger.SUBSDataMessenger.build_azure_subs_dict")
    def test_process_and_send_subs_message_azure_time_already_processed(
        self, mock_msg_builder, mock_reader, mock_remove, mock_azure_id
    ):
        """Tests that the start for the range is updated."""
        mock_azure_id.return_value = ("expected", "expected")
        mock_msg_builder.return_value = {"fake": "msg"}
        upload_keys = ["fake_key"]
        instance = "expected"
        account = "9999999999999"
        vcpu = "2"
        rhel_version = "7"
        sla = "Premium"
        usage = "Production"
        role = "Red Hat Enterprise Linux Server"
        conversion = "true"
        addon_id = "ELS"
        tenant_id = "expected"
        expected_start = "2024-07-01T12:00:00+00:00"
        expected_end = "2024-07-01T13:00:00+00:00"
        vm_name = "my-fake-vm"
        resource_id = "i-55555556"
        rg = "my-fake-rg"
        instance_key = f"{account}:{rg}:{vm_name}"
        self.azure_messenger.date_map = {"2024-07-01T00:00:00Z": {instance_key: 12}}
        mock_reader.return_value = [
            {
                "resourceid": resource_id,
                "subs_start_time": "2024-07-01T00:00:00Z",
                "subs_end_time": "2024-07-02T00:00:00Z",
                "subs_resource_id": resource_id,
                "subs_account": account,
                "physical_cores": "1",
                "subs_vcpu": "2",
                "variant": "Server",
                "subs_usage": usage,
                "subs_usage_quantity": "1",
                "subs_sla": sla,
                "subs_role": role,
                "subs_rhel_version": rhel_version,
                "subs_addon_id": addon_id,
                "subs_instance": instance,
                "subs_conversion": conversion,
                "source": self.azure_provider.uuid,
                "resourcegroup": rg,
                "subs_vmname": vm_name,
            }
        ]
        mock_op = mock_open(read_data="x,y,z")
        with patch("builtins.open", mock_op):
            self.azure_messenger.process_and_send_subs_message(upload_keys)
        mock_azure_id.assert_called_once()
        mock_msg_builder.assert_called_with(
            instance,
            account,
            expected_start,
            expected_end,
            vcpu,
            rhel_version,
            sla,
            usage,
            role,
            conversion,
            addon_id,
            tenant_id,
            vm_name,
        )

    def test_determine_product_ids(self):
        """Test that different combinations of inputs result in expected product IDs"""
        mapping_to_expected = {
            ("69", "204", "Red Hat Enterprise Linux Compute Node"): ["76"],  # RHEL 7 HPC
            ("69", "204", "SAP"): ["146", "69", "204"],  # RHEL 7 ELS SAP
            ("69", "", "Workstation"): ["69"],  # RHEL 7 workstation
            ("479", "204", "Red Hat Enterprise Linux Compute Node"): ["479"],  # RHEL 8 HPC
            ("479", "204", "SAP"): ["241", "479", "204"],  # RHEL 8 ELS SAP
            ("479", "204", "Workstation"): ["479", "204"],  # RHEL 8 ELS
            ("479", "", "Workstation"): ["479"],  # RHEL 8 Workstation
        }
        for tup, expected in mapping_to_expected.items():
            with self.subTest(inputs=tup):
                version, addon, role = tup
                actual = self.messenger.determine_product_ids(version, addon, role)
                self.assertEqual(expected, actual)
