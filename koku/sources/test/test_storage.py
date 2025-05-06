#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Sources Storage access layer."""
from base64 import b64decode
from json import loads as json_loads
from unittest.mock import Mock
from unittest.mock import patch

from django.db import InterfaceError
from django.test import TestCase
from faker import Faker

from api.iam.models import Customer
from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from api.provider.models import Sources
from sources import storage
from sources.config import Config

faker = Faker()


class MockDetails:
    """Mock details object."""

    def __init__(self, name, source_uuid, source_type, endpoint_id, auth_header=Config.SOURCES_FAKE_HEADER):
        """Init mock details."""
        self.name = name
        self.source_uuid = source_uuid
        self.source_type = source_type
        self.endpoint_id = endpoint_id
        self.auth_header = auth_header


class MockProvider:
    """Mock Provider Class."""

    def __init__(
        self, source_id, name, source_type, auth, billing_source, auth_header, offset, pending_delete, koku_uuid=None
    ):
        """Init mock provider."""
        self.source_id = source_id
        self.name = name
        self.source_type = source_type
        self.authentication = auth
        self.billing_source = billing_source
        self.auth_header = auth_header
        self.offset = offset
        self.pending_delete = pending_delete
        self.koku_uuid = koku_uuid
        self.status = {}


class SourcesStorageTest(TestCase):
    """Test cases for Sources Storage."""

    def setUp(self):
        """Test case setup."""
        self.test_source_id = 1
        self.test_offset = 2
        self.test_header = Config.SOURCES_FAKE_HEADER
        self.test_obj = Sources(source_id=self.test_source_id, auth_header=self.test_header, offset=self.test_offset)
        decoded_rh_auth = b64decode(self.test_header)
        json_rh_auth = json_loads(decoded_rh_auth)
        self.account_id = json_rh_auth.get("identity", {}).get("account_number")
        self.org_id = json_rh_auth.get("identity", {}).get("org_id")

        self.test_obj.save()

    def test_is_known_source(self):
        """Tests is_known_source method."""
        self.assertTrue(storage.is_known_source(self.test_source_id))
        self.assertFalse(storage.is_known_source(self.test_source_id + 1))

    @patch("sources.storage.Sources.objects")
    def test_is_known_souce_db_down(self, mock_objects):
        """Test InterfaceError in is_known_souce."""
        mock_objects.get.side_effect = InterfaceError("test_exception")
        with self.assertRaises(InterfaceError):
            storage.is_known_source(self.test_source_id)

    @patch("sources.storage.Sources.objects")
    def test_get_source_db_down(self, mock_objects):
        """Tests creating a source db record with invalid auth_header."""
        mock_objects.get.side_effect = InterfaceError("test_exception")
        with self.assertRaises(InterfaceError):
            test_source_id = 2
            storage.get_source(test_source_id, "error", Mock)

    def test_create_source_event(self):
        """Tests that a source can be created."""
        test_source_id = 2
        test_offset = 3
        storage.create_source_event(
            test_source_id, self.account_id, self.org_id, Config.SOURCES_FAKE_HEADER, test_offset
        )
        db_obj = Sources.objects.get(source_id=test_source_id)
        self.assertEqual(db_obj.source_id, test_source_id)
        self.assertEqual(db_obj.auth_header, Config.SOURCES_FAKE_HEADER)
        self.assertEqual(db_obj.offset, test_offset)
        self.assertEqual(db_obj.account_id, self.account_id)

    def test_create_source_event_out_of_order(self):
        """Tests that a source entry is cleaned up when following an out of order destroy."""
        test_source_id = 3
        test_offset = 4
        test_obj = Sources(source_id=test_source_id, offset=3, out_of_order_delete=True)
        test_obj.save()

        storage.create_source_event(
            test_source_id, self.account_id, self.org_id, Config.SOURCES_FAKE_HEADER, test_offset
        )
        self.assertFalse(Sources.objects.filter(source_id=test_source_id).exists())

    def test_create_source_event_out_of_order_unexpected_entry(self):
        """Tests that a source entry is not cleaned up when unexpected entry is found."""
        test_source_id = 3
        test_offset = 4
        test_obj = Sources(source_id=test_source_id, offset=3)
        test_obj.save()

        storage.create_source_event(
            test_source_id, self.account_id, self.org_id, Config.SOURCES_FAKE_HEADER, test_offset
        )
        self.assertTrue(Sources.objects.filter(source_id=test_source_id).exists())

    def test_create_source_event_db_down(self):
        """Tests creating a source db record with invalid auth_header."""
        test_source_id = 2
        ocp_obj = Sources(source_id=test_source_id, offset=3, out_of_order_delete=True, pending_delete=False)
        ocp_obj.save()
        with patch.object(Sources, "delete") as mock_object:
            mock_object.side_effect = InterfaceError("Error")
            with self.assertRaises(InterfaceError):
                test_offset = 3
                storage.create_source_event(
                    test_source_id, self.account_id, self.org_id, Config.SOURCES_FAKE_HEADER, test_offset
                )

    def test_destroy_source_event(self):
        """Tests that a source can be destroyed."""
        test_uuid = faker.uuid4()
        self.assertIsNotNone(self.test_obj)
        storage.add_provider_koku_uuid(self.test_source_id, test_uuid)
        response = storage.destroy_source_event(self.test_source_id)
        self.assertFalse(Sources.objects.filter(source_id=self.test_source_id).exists())
        self.assertEqual(response, test_uuid)

    def test_destroy_source_event_not_found(self):
        """Tests when destroying a non-existent source."""
        response = storage.destroy_source_event(self.test_source_id + 1)
        self.assertIsNone(response)

    def test_destroy_source_event_db_down(self):
        """Tests when destroying a source when DB is down."""
        with patch("sources.storage.Sources.objects") as mock_objects:
            mock_objects.get.side_effect = InterfaceError("Test exception")
            with self.assertRaises(InterfaceError):
                storage.destroy_source_event(self.test_source_id)

    def test_add_provider_sources_details(self):
        """Tests that adding information retrieved from the sources network API is successful."""
        test_header = "different-header"
        test_source = Sources.objects.get(source_id=self.test_source_id)
        self.assertIsNone(test_source.name)
        self.assertEqual(test_source.source_type, "")
        self.assertEqual(test_source.authentication, {})
        self.assertNotEqual(test_source.auth_header, test_header)

        test_name = "My Source Name"
        source_type = Provider.PROVIDER_AWS
        endpoint_id = 1
        source_uuid = faker.uuid4()
        mock_details = MockDetails(test_name, source_uuid, source_type, endpoint_id, test_header)
        storage.add_provider_sources_details(mock_details, self.test_source_id)

        test_source = Sources.objects.get(source_id=self.test_source_id)
        self.assertEqual(test_source.name, test_name)
        self.assertEqual(test_source.source_type, source_type)
        self.assertEqual(str(test_source.source_uuid), source_uuid)
        self.assertEqual(test_source.auth_header, test_header)

    def test_add_provider_sources_details_not_found(self):
        """Tests that adding information retrieved from the sources network API is not successful."""
        try:
            test_name = "My Source Name"
            source_type = Provider.PROVIDER_AWS
            mock_details = MockDetails(test_name, faker.uuid4(), source_type, 1)
            storage.add_provider_sources_details(mock_details, self.test_source_id + 1)
        except Exception as error:
            self.fail(str(error))

    def test_add_provider_koku_uuid(self):
        """Tests that add a koku provider uuid to a source."""
        test_uuid = faker.uuid4()
        storage.add_provider_koku_uuid(self.test_source_id, test_uuid)
        self.assertEqual(Sources.objects.get(source_id=self.test_source_id).koku_uuid, test_uuid)

    def test_add_provider_uuid_does_not_exist(self):
        """Tests that add a koku provider uuid to a non-existent source."""
        test_uuid = faker.uuid4()
        try:
            storage.add_provider_koku_uuid(self.test_source_id + 1, test_uuid)
        except Exception as error:
            self.fail(str(error))

    def test_add_source_pause(self):
        """Tests add a pause to a source."""
        for test in {True, False}:
            with self.subTest(test=test):
                test_source = Sources.objects.get(source_id=self.test_source_id)
                self.assertFalse(test_source.paused)
                storage.add_source_pause(self.test_source_id, test)
                self.assertEqual(Sources.objects.get(source_id=self.test_source_id).paused, test)

    def test_add_source_pause_does_not_exist(self):
        """Tests add a pause to a source that does not exist."""
        for test in {True, False}:
            with self.subTest(test=test):
                try:
                    storage.add_source_pause(self.test_source_id + 1, test)
                except Exception as error:
                    self.fail(str(error))

    def test_screen_and_build_provider_sync_create_event(self):
        """Tests that provider create events are generated."""
        test_matrix = [
            {
                "provider": MockProvider(
                    source_id=1,
                    name="AWS Provider",
                    source_type=Provider.PROVIDER_AWS,
                    auth={"role_arn": "arn:fake"},
                    billing_source={"bucket": "testbucket"},
                    auth_header="authheader",
                    offset=1,
                    pending_delete=False,
                ),
                "expected_response": {"operation": "create", "offset": 1},
            },
            {
                "provider": MockProvider(
                    source_id=1,
                    name="AWS Provider",
                    source_type=Provider.PROVIDER_AWS,
                    auth={"role_arn": "arn:fake"},
                    billing_source=None,
                    auth_header="authheader",
                    offset=1,
                    pending_delete=False,
                ),
                "expected_response": {},
            },
            {
                "provider": MockProvider(
                    source_id=2,
                    name="OCP Provider",
                    source_type=Provider.PROVIDER_OCP,
                    auth={"role_arn": "my-cluster-id"},
                    billing_source={"bucket": ""},
                    auth_header="authheader",
                    offset=2,
                    pending_delete=False,
                ),
                "expected_response": {"operation": "create", "offset": 2},
            },
            {
                "provider": MockProvider(
                    source_id=2,
                    name="OCP Provider",
                    source_type=Provider.PROVIDER_OCP,
                    auth={"cluster_id": "my-cluster-id"},
                    billing_source={},
                    auth_header="authheader",
                    offset=2,
                    pending_delete=True,
                ),
                "expected_response": {},
            },
            {
                "provider": MockProvider(
                    source_id=2,
                    name=None,
                    source_type=Provider.PROVIDER_OCP,
                    auth={"cluster_id": "my-cluster-id"},
                    billing_source={},
                    auth_header="authheader",
                    offset=2,
                    pending_delete=False,
                ),
                "expected_response": {},
            },
            {
                "provider": MockProvider(
                    source_id=3,
                    name="Azure Provider",
                    source_type=Provider.PROVIDER_AZURE,
                    auth={
                        "credentials": {
                            "client_id": "test_client_id",
                            "tenant_id": "test_tenant_id",
                            "client_secret": "test_client_secret",
                            "subscription_id": "test_subscription_id",
                        }
                    },
                    billing_source={
                        "data_source": {
                            "resource_group": "test_resource_group",
                            "storage_account": "test_storage_account",
                        }
                    },
                    auth_header="authheader",
                    offset=3,
                    pending_delete=False,
                ),
                "expected_response": {"operation": "create", "offset": 3},
            },
            {
                "provider": MockProvider(
                    source_id=3,
                    name="GCP Provider",
                    source_type=Provider.PROVIDER_GCP,
                    auth={"project_id": "test-project"},
                    billing_source={"data_source": {"dataset": "test-dataset", "table_id": "test-tableid"}},
                    auth_header="authheader",
                    offset=3,
                    pending_delete=False,
                ),
                "expected_response": {"operation": "create", "offset": 3},
            },
            {
                "provider": MockProvider(
                    source_id=3,
                    name="GCP Provider",
                    source_type=Provider.PROVIDER_GCP,
                    auth={"project_id": "test-project"},
                    billing_source={"data_source": {}},
                    auth_header="authheader",
                    offset=1,
                    pending_delete=False,
                ),
                "expected_response": {},
            },
        ]
        for test in test_matrix:
            response = storage.screen_and_build_provider_sync_create_event(test.get("provider"))

            if response:
                self.assertEqual(response.get("operation"), test.get("expected_response").get("operation"))
                self.assertEqual(response.get("offset"), test.get("expected_response").get("offset"))
            else:
                self.assertEqual(response, {})

    def test_get_source_type(self):
        """Test to source type from source."""
        test_source_id = 3

        ocp_obj = Sources(
            source_id=test_source_id,
            auth_header=self.test_header,
            offset=3,
            source_type=Provider.PROVIDER_OCP,
            name="Test OCP Source",
            authentication={"role_arn": "arn:test"},
            billing_source={"bucket": "test-bucket"},
        )
        ocp_obj.save()

        response = storage.get_source_type(test_source_id)
        self.assertEqual(response, Provider.PROVIDER_OCP)
        self.assertEqual(storage.get_source_type(test_source_id + 1), None)

    def test_add_provider_sources_auth_info(self):
        """Test to add authentication to a source."""
        test_source_id = 3
        test_authentication = {"role_arn": "arn:test"}
        aws_obj = Sources(
            source_id=test_source_id,
            auth_header=self.test_header,
            offset=3,
            source_type=Provider.PROVIDER_AWS,
            name="Test AWS Source",
            billing_source={"bucket": "test-bucket"},
        )
        aws_obj.save()

        result = storage.add_provider_sources_auth_info(test_source_id, test_authentication)
        self.assertTrue(result)
        response = Sources.objects.filter(source_id=test_source_id).first()
        self.assertEqual(response.authentication, test_authentication)

    def test_add_provider_sources_auth_info_with_sub_id(self):
        """Test to add authentication to a source with subscription_id."""
        test_source_id = 3
        test_authentication = {"credentials": {"client_id": "new-client-id"}}
        orig_authentication = {"credentials": {"subscription_id": "orig-sub-id", "client_id": "test-client-id"}}
        azure_obj = Sources(
            source_id=test_source_id,
            auth_header=self.test_header,
            offset=3,
            source_type=Provider.PROVIDER_AZURE,
            name="Test AZURE Source",
            authentication=orig_authentication,
        )
        azure_obj.save()
        response = Sources.objects.filter(source_id=test_source_id).first()
        self.assertDictEqual(response.authentication, orig_authentication)

        result = storage.add_provider_sources_auth_info(test_source_id, test_authentication)
        self.assertTrue(result)
        response = Sources.objects.filter(source_id=test_source_id).first()
        self.assertDictEqual(response.authentication, test_authentication)

    def test_add_provider_sources_billing_info(self):
        """Test to add billing_source to a source."""
        test_source_id = 3
        test_billing = {"bucket": "bucket"}
        aws_obj = Sources(
            source_id=test_source_id,
            auth_header=self.test_header,
            offset=3,
            source_type=Provider.PROVIDER_AWS,
            name="Test AWS Source",
            authentication={"role_arn": "arn:test"},
        )
        aws_obj.save()

        result = storage.add_provider_sources_billing_info(test_source_id, test_billing)
        self.assertTrue(result)
        response = Sources.objects.filter(source_id=test_source_id).first()
        self.assertEqual(response.billing_source, test_billing)

    def test_add_provider_sources_billing_info_no_source(self):
        """Test to add billing_source to a non-existent source."""
        test_source_id = 3
        test_billing = {"bucket": "bucket"}

        result = storage.add_provider_sources_billing_info(test_source_id, test_billing)
        self.assertIsNone(result)

    def test_enqueue_source_delete(self):
        """Test for enqueuing source delete."""
        test_source_id = 3
        test_offset = 3

        account_name = "Test Provider"
        provider_uuid = faker.uuid4()
        ocp_provider = Provider.objects.create(
            uuid=provider_uuid,
            name=account_name,
            type=Provider.PROVIDER_OCP,
            authentication=ProviderAuthentication.objects.create(credentials={"cluster_id": "my-cluster'"}).save(),
            billing_source=ProviderBillingSource.objects.create(data_source={}),
            customer=Customer.objects.create(account_id="123", schema_name="myschema").save(),
            setup_complete=False,
        )
        ocp_provider.save()

        ocp_obj = Sources(
            source_id=test_source_id,
            auth_header=self.test_header,
            offset=test_offset,
            source_type=Provider.PROVIDER_OCP,
            name=account_name,
            koku_uuid=ocp_provider.uuid,
        )
        ocp_obj.save()

        storage.enqueue_source_delete(test_source_id, test_offset)
        source_response = Sources.objects.get(source_id=test_source_id)
        self.assertTrue(source_response.pending_delete)

        provider_response = Provider.objects.get(uuid=provider_uuid)
        self.assertTrue(provider_response.active)

    def test_enqueue_source_delete_db_down(self):
        """Tests enqueues source_delete with database error."""
        test_source_id = 2
        ocp_obj = Sources(source_id=test_source_id, offset=3, out_of_order_delete=False, pending_delete=False)
        ocp_obj.save()
        with patch.object(Sources, "save") as mock_object:
            mock_object.side_effect = InterfaceError("Error")
            with self.assertRaises(InterfaceError):
                test_offset = 3
                storage.enqueue_source_delete(test_source_id, Config.SOURCES_FAKE_HEADER, test_offset)

    def test_enqueue_source_delete_in_pending(self):
        """Test for enqueuing source delete while pending delete."""
        test_source_id = 3
        test_offset = 4
        aws_obj = Sources(
            source_id=test_source_id,
            auth_header=self.test_header,
            offset=test_offset,
            source_type=Provider.PROVIDER_AWS,
            name="Test AWS Source",
            billing_source={"bucket": "test-bucket"},
            pending_delete=True,
        )
        aws_obj.save()

        storage.enqueue_source_delete(test_source_id, test_offset)
        response = Sources.objects.get(source_id=test_source_id)
        self.assertTrue(response.pending_delete)

    def test_enqueue_source_delete_out_of_order(self):
        """Test for enqueuing source delete before receving create."""
        test_source_id = 3
        test_offset = 4

        storage.enqueue_source_delete(test_source_id, test_offset, allow_out_of_order=True)
        response = Sources.objects.get(source_id=test_source_id)
        self.assertTrue(response.out_of_order_delete)

    def test_enqueue_source_delete_out_of_order_source_destroy(self):
        """Test for enqueuing source delete before receving create for Source.destroy."""
        test_source_id = 3
        test_offset = 4

        storage.enqueue_source_delete(test_source_id, test_offset, allow_out_of_order=False)
        self.assertFalse(Sources.objects.filter(source_id=test_source_id).exists())

    def test_enqueue_source_create_or_update(self):
        """Test for enqueuing source updating."""
        test_matrix = [
            {"koku_uuid": None, "pending_delete": False, "pending_update": False, "expected_pending_update": False},
            {"koku_uuid": None, "pending_delete": True, "pending_update": False, "expected_pending_update": False},
            {
                "koku_uuid": faker.uuid4(),
                "pending_delete": True,
                "pending_update": False,
                "expected_pending_update": False,
            },
            {
                "koku_uuid": faker.uuid4(),
                "pending_delete": False,
                "pending_update": False,
                "expected_pending_update": True,
            },
            {
                "koku_uuid": faker.uuid4(),
                "pending_delete": False,
                "pending_update": True,
                "expected_pending_update": True,
            },
        ]
        test_source_id = 3
        for test in test_matrix:
            aws_obj = Sources(
                source_id=test_source_id,
                auth_header=self.test_header,
                koku_uuid=test.get("koku_uuid"),
                pending_delete=test.get("pending_delete"),
                pending_update=test.get("pending_update"),
                offset=3,
                source_type=Provider.PROVIDER_AWS,
                name="Test AWS Source",
                billing_source={"bucket": "test-bucket"},
            )
            aws_obj.save()

            storage.enqueue_source_create_or_update(test_source_id)
            response = Sources.objects.get(source_id=test_source_id)
            self.assertEqual(test.get("expected_pending_update"), response.pending_update)

    def test_enqueue_source_update_unknown_source(self):
        """Test to enqueue a source update for an unknown source."""
        self.test_obj.koku_uuid = faker.uuid4()
        storage.enqueue_source_create_or_update(self.test_source_id + 1)
        self.assertFalse(self.test_obj.pending_update)

    def test_clear_update_flag(self):
        """Test for clearing source update flag."""
        test_matrix = [
            {"koku_uuid": None, "pending_update": False, "expected_pending_update": False},
            {"koku_uuid": faker.uuid4(), "pending_update": False, "expected_pending_update": False},
            {"koku_uuid": faker.uuid4(), "pending_update": True, "expected_pending_update": False},
        ]
        for test_source_id, test in enumerate(test_matrix, start=3):
            aws_obj = Sources(
                source_id=test_source_id,
                auth_header=self.test_header,
                koku_uuid=test.get("koku_uuid"),
                pending_update=test.get("pending_update"),
                offset=3,
                source_type=Provider.PROVIDER_AWS,
                name="Test AWS Source",
                billing_source={"bucket": "test-bucket"},
            )
            aws_obj.save()

            storage.clear_update_flag(test_source_id)
            response = Sources.objects.get(source_id=test_source_id)
            self.assertEqual(test.get("expected_pending_update"), response.pending_update)

    def test_clear_update_flag_unknown_id(self):
        """Test to clear update flag for an unknown id."""
        self.test_obj.pending_update = True
        self.test_obj.save()
        storage.clear_update_flag(self.test_source_id + 1)
        self.assertTrue(self.test_obj.pending_update)

    def test_load_providers_to_update(self):
        """Test loading pending update events."""
        test_matrix = [
            {"koku_uuid": faker.uuid4(), "pending_update": False, "pending_delete": False, "expected_list_length": 0},
            {"koku_uuid": faker.uuid4(), "pending_update": True, "pending_delete": False, "expected_list_length": 1},
            {"koku_uuid": None, "pending_update": True, "pending_delete": False, "expected_list_length": 0},
        ]

        for test_source_id, test in enumerate(test_matrix, start=3):
            aws_obj = Sources(
                source_id=test_source_id,
                auth_header=self.test_header,
                koku_uuid=test.get("koku_uuid"),
                pending_update=test.get("pending_update"),
                pending_delete=test.get("pending_delete"),
                offset=3,
                source_type=Provider.PROVIDER_AWS,
                name="Test AWS Source",
                billing_source={"bucket": "test-bucket"},
            )
            aws_obj.save()

            response = storage.load_providers_to_update()
            self.assertEqual(len(response), test.get("expected_list_length"))
            aws_obj.delete()

    def test_save_status(self):
        """Test to verify source status is saved."""
        test_source_id = 3
        status = "unavailable"
        user_facing_string = "Missing credential and billing source"
        mock_status = {"availability_status": status, "availability_status_error": user_facing_string}
        azure_obj = Sources(
            source_id=test_source_id,
            auth_header=self.test_header,
            offset=3,
            source_type=Provider.PROVIDER_AZURE,
            name="Test AZURE Source",
        )
        azure_obj.save()

        return_code = storage.save_status(test_source_id, mock_status)
        db_obj = Sources.objects.get(source_id=test_source_id)
        self.assertEqual(db_obj.status, mock_status)
        self.assertTrue(return_code)

        # Save again and verify return_code is False
        return_code = storage.save_status(test_source_id, mock_status)
        db_obj = Sources.objects.get(source_id=test_source_id)
        self.assertEqual(db_obj.status, mock_status)
        self.assertFalse(return_code)
