#
# Copyright 2019 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the Sources Storage access layer."""
from base64 import b64decode
from json import loads as json_loads
from unittest.mock import Mock
from unittest.mock import patch

from django.db import InterfaceError
from django.test import TestCase
from faker import Faker

from api.provider.models import Provider
from api.provider.models import Sources
from sources import storage
from sources.config import Config

faker = Faker()


class MockDetails:
    """Mock details object."""

    def __init__(self, name, source_uuid, source_type, endpoint_id):
        """Init mock details."""
        self.name = name
        self.source_uuid = source_uuid
        self.source_type = source_type
        self.endpoint_id = endpoint_id


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
        test_source_id = 2
        with self.assertRaises(InterfaceError):
            storage.get_source(test_source_id, "error", Mock)

    def test_create_source_event(self):
        """Tests that a source can be created."""
        test_source_id = 2
        test_offset = 3
        storage.create_source_event(test_source_id, Config.SOURCES_FAKE_HEADER, test_offset)
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

        storage.create_source_event(test_source_id, Config.SOURCES_FAKE_HEADER, test_offset)
        self.assertFalse(Sources.objects.filter(source_id=test_source_id).exists())

    def test_create_source_event_out_of_order_unexpected_entry(self):
        """Tests that a source entry is not cleaned up when unexpected entry is found."""
        test_source_id = 3
        test_offset = 4
        test_obj = Sources(source_id=test_source_id, offset=3)
        test_obj.save()

        storage.create_source_event(test_source_id, Config.SOURCES_FAKE_HEADER, test_offset)
        self.assertTrue(Sources.objects.filter(source_id=test_source_id).exists())

    def test_create_source_event_invalid_auth_header(self):
        """Tests creating a source db record with invalid auth_header."""
        test_source_id = 2
        test_offset = 3
        storage.create_source_event(test_source_id, "bad", test_offset)
        with self.assertRaises(Sources.DoesNotExist):
            Sources.objects.get(source_id=test_source_id)

    def test_create_source_event_db_down(self):
        """Tests creating a source db record with invalid auth_header."""
        test_source_id = 2
        test_offset = 3
        ocp_obj = Sources(source_id=test_source_id, offset=3, out_of_order_delete=True, pending_delete=False)
        ocp_obj.save()
        with patch.object(Sources, "delete") as mock_object:
            mock_object.side_effect = InterfaceError("Error")
            with self.assertRaises(InterfaceError):
                storage.create_source_event(test_source_id, Config.SOURCES_FAKE_HEADER, test_offset)

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

    def test_add_provider_network_info(self):
        """Tests that adding information retrieved from the sources network API is successful."""
        test_source = Sources.objects.get(source_id=self.test_source_id)
        self.assertIsNone(test_source.name)
        self.assertEqual(test_source.source_type, "")
        self.assertEqual(test_source.authentication, {})

        test_name = "My Source Name"
        source_type = Provider.PROVIDER_AWS
        endpoint_id = 1
        source_uuid = faker.uuid4()
        mock_details = MockDetails(test_name, source_uuid, source_type, endpoint_id)
        storage.add_provider_sources_network_info(mock_details, self.test_source_id)

        test_source = Sources.objects.get(source_id=self.test_source_id)
        self.assertEqual(test_source.name, test_name)
        self.assertEqual(test_source.source_type, source_type)
        self.assertEqual(str(test_source.source_uuid), source_uuid)

    def test_add_provider_network_info_not_found(self):
        """Tests that adding information retrieved from the sources network API is not successful."""
        try:
            test_name = "My Source Name"
            source_type = Provider.PROVIDER_AWS
            mock_details = MockDetails(test_name, faker.uuid4(), source_type, 1)
            storage.add_provider_sources_network_info(mock_details, self.test_source_id + 1)
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

    def test_screen_and_build_provider_sync_create_event(self):
        """Tests that provider create events are generated."""
        test_matrix = [
            {
                "provider": MockProvider(
                    1,
                    "AWS Provider",
                    Provider.PROVIDER_AWS,
                    {"role_arn": "arn:fake"},
                    {"bucket": "testbucket"},
                    "authheader",
                    1,
                    False,
                ),
                "expected_response": {"operation": "create", "offset": 1},
            },
            {
                "provider": MockProvider(
                    1, "AWS Provider", Provider.PROVIDER_AWS, {"role_arn": "arn:fake"}, None, "authheader", 1, False
                ),
                "expected_response": {},
            },
            {
                "provider": MockProvider(
                    2,
                    "OCP Provider",
                    Provider.PROVIDER_OCP,
                    {"role_arn": "my-cluster-id"},
                    {"bucket": ""},
                    "authheader",
                    2,
                    False,
                ),
                "expected_response": {"operation": "create", "offset": 2},
            },
            {
                "provider": MockProvider(
                    2,
                    "OCP Provider",
                    Provider.PROVIDER_OCP,
                    {"cluster_id": "my-cluster-id"},
                    {},
                    "authheader",
                    2,
                    True,
                ),
                "expected_response": {},
            },
            {
                "provider": MockProvider(
                    2, None, Provider.PROVIDER_OCP, {"cluster_id": "my-cluster-id"}, {}, "authheader", 2, False
                ),
                "expected_response": {},
            },
            {
                "provider": MockProvider(
                    3,
                    "Azure Provider",
                    Provider.PROVIDER_AZURE,
                    {
                        "credentials": {
                            "client_id": "test_client_id",
                            "tenant_id": "test_tenant_id",
                            "client_secret": "test_client_secret",
                            "subscription_id": "test_subscription_id",
                        }
                    },
                    {
                        "data_source": {
                            "resource_group": "test_resource_group",
                            "storage_account": "test_storage_account",
                        }
                    },
                    "authheader",
                    3,
                    False,
                ),
                "expected_response": {"operation": "create", "offset": 3},
            },
            {
                "provider": MockProvider(
                    3,
                    "GCP Provider",
                    Provider.PROVIDER_GCP,
                    {"project_id": "test-project"},
                    {"data_source": {"dataset": "test-dataset", "table_id": "test-tableid"}},
                    "authheader",
                    3,
                    False,
                ),
                "expected_response": {"operation": "create", "offset": 3},
            },
            {
                "provider": MockProvider(
                    3,
                    "GCP Provider",
                    Provider.PROVIDER_GCP,
                    {"project_id": "test-project"},
                    {"data_source": {}},
                    "authheader",
                    1,
                    False,
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
        self.assertEquals(response, Provider.PROVIDER_OCP)
        self.assertEquals(storage.get_source_type(test_source_id + 1), None)

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

        storage.add_provider_sources_auth_info(test_source_id, test_authentication)
        response = Sources.objects.filter(source_id=test_source_id).first()
        self.assertEquals(response.authentication, test_authentication)

    def test_add_provider_sources_auth_info_with_sub_id(self):
        """Test to add authentication to a source with subscription_id."""
        test_source_id = 3
        test_authentication = {"credentials": {"client_id": "new-client-id"}}
        azure_obj = Sources(
            source_id=test_source_id,
            auth_header=self.test_header,
            offset=3,
            source_type=Provider.PROVIDER_AZURE,
            name="Test AZURE Source",
            authentication={"credentials": {"subscription_id": "orig-sub-id", "client_id": "test-client-id"}},
        )
        azure_obj.save()

        storage.add_provider_sources_auth_info(test_source_id, test_authentication)
        response = Sources.objects.filter(source_id=test_source_id).first()
        self.assertEquals(response.authentication.get("credentials").get("subscription_id"), "orig-sub-id")
        self.assertEquals(response.authentication.get("credentials").get("client_id"), "new-client-id")

    def test_enqueue_source_delete(self):
        """Test for enqueuing source delete."""
        test_source_id = 3
        test_offset = 3
        aws_obj = Sources(
            source_id=test_source_id,
            auth_header=self.test_header,
            offset=test_offset,
            source_type=Provider.PROVIDER_AWS,
            name="Test AWS Source",
            billing_source={"bucket": "test-bucket"},
        )
        aws_obj.save()

        storage.enqueue_source_delete(test_source_id, test_offset)
        response = Sources.objects.get(source_id=test_source_id)
        self.assertTrue(response.pending_delete)

    def test_enqueue_source_delete_db_down(self):
        """Tests enqueues source_delete with database error."""
        test_source_id = 2
        test_offset = 3
        ocp_obj = Sources(source_id=test_source_id, offset=3, out_of_order_delete=False, pending_delete=False)
        ocp_obj.save()
        with patch.object(Sources, "save") as mock_object:
            mock_object.side_effect = InterfaceError("Error")
            with self.assertRaises(InterfaceError):
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

    def test_enqueue_source_update(self):
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

            storage.enqueue_source_update(test_source_id)
            response = Sources.objects.get(source_id=test_source_id)
            self.assertEquals(test.get("expected_pending_update"), response.pending_update)
            test_source_id += 1

    def test_enqueue_source_update_unknown_source(self):
        """Test to enqueue a source update for an unknown source."""
        self.test_obj.koku_uuid = faker.uuid4()
        storage.enqueue_source_update(self.test_source_id + 1)
        self.assertFalse(self.test_obj.pending_update)

    def test_clear_update_flag(self):
        """Test for clearing source update flag."""
        test_matrix = [
            {"koku_uuid": None, "pending_update": False, "expected_pending_update": False},
            {"koku_uuid": faker.uuid4(), "pending_update": False, "expected_pending_update": False},
            {"koku_uuid": faker.uuid4(), "pending_update": True, "expected_pending_update": False},
        ]
        test_source_id = 3
        for test in test_matrix:
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
            self.assertEquals(test.get("expected_pending_update"), response.pending_update)
            test_source_id += 1

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

        test_source_id = 3
        for test in test_matrix:
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
            self.assertEquals(len(response), test.get("expected_list_length"))
            test_source_id += 1
            aws_obj.delete()

    def test_validate_billing_source(self):
        """Test to validate that the billing source dictionary is valid."""
        test_matrix = [
            {"provider_type": Provider.PROVIDER_AWS, "billing_source": {"bucket": "test-bucket"}, "exception": False},
            {
                "provider_type": Provider.PROVIDER_AWS,
                "billing_source": {"data_source": {"bucket": "test-bucket"}},
                "exception": False,
            },
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "billing_source": {"data_source": {"resource_group": "foo", "storage_account": "bar"}},
                "exception": False,
            },
            {
                "provider_type": Provider.PROVIDER_AWS,
                "billing_source": {"data_source": {"nobucket": "test-bucket"}},
                "exception": True,
            },
            {"provider_type": Provider.PROVIDER_AWS, "billing_source": {"nobucket": "test-bucket"}, "exception": True},
            {"provider_type": Provider.PROVIDER_AWS, "billing_source": {"data_source": {}}, "exception": True},
            {"provider_type": Provider.PROVIDER_AWS, "billing_source": {}, "exception": True},
            {"provider_type": Provider.PROVIDER_AZURE, "billing_source": {}, "exception": True},
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "billing_source": {"nodata_source": {"resource_group": "foo", "storage_account": "bar"}},
                "exception": True,
            },
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "billing_source": {"data_source": {"noresource_group": "foo", "storage_account": "bar"}},
                "exception": True,
            },
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "billing_source": {"data_source": {"resource_group": "foo", "nostorage_account": "bar"}},
                "exception": True,
            },
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "billing_source": {"data_source": {"resource_group": "foo"}},
                "exception": True,
            },
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "billing_source": {"data_source": {"storage_account": "bar"}},
                "exception": True,
            },
            {
                "provider_type": Provider.PROVIDER_GCP,
                "billing_source": {"data_source": {"dataset": "test_dataset", "table_id": "test_table_id"}},
                "exception": False,
            },
            {
                "provider_type": Provider.PROVIDER_GCP,
                "billing_source": {"data_source": {"dataset": "test_dataset"}},
                "exception": False,
            },
            {
                "provider_type": Provider.PROVIDER_GCP,
                "billing_source": {"data_source": {"table_id": "test_table_id"}},
                "exception": True,
            },
            {"provider_type": Provider.PROVIDER_GCP, "billing_source": {}, "exception": True},
        ]

        for test in test_matrix:
            with self.subTest(test=test):
                if test.get("exception"):
                    with self.assertRaises(storage.SourcesStorageError):
                        storage._validate_billing_source(test.get("provider_type"), test.get("billing_source"))
                else:
                    try:
                        storage._validate_billing_source(test.get("provider_type"), test.get("billing_source"))
                    except Exception as error:
                        self.fail(str(error))

    def test_update_aws_billing_source(self):
        """Test to validate that the billing source dictionary is updated."""
        aws_instance = Sources(
            source_id=3,
            auth_header=self.test_header,
            offset=3,
            endpoint_id=4,
            source_type=Provider.PROVIDER_AWS,
            name="Test AWS Source",
            billing_source={"data_source": {"bucket": "my_s3_bucket"}},
        )
        aws_instance.save()
        test_matrix = [
            {
                "instance": aws_instance,
                "billing_source": {"bucket": "test-bucket"},
                "expected": {"data_source": {"bucket": "test-bucket"}},
            },
            {
                "instance": aws_instance,
                "billing_source": {"data_source": {"bucket": "test-bucket"}},
                "expected": {"data_source": {"bucket": "test-bucket"}},
            },
        ]

        for test in test_matrix:
            with self.subTest(test=test):
                try:
                    new_billing = storage._update_billing_source(aws_instance, test.get("billing_source"))
                    self.assertEqual(new_billing, test.get("expected"))
                except Exception as error:
                    self.fail(str(error))
        aws_instance.delete()

    def test_update_azure_billing_source(self):
        """Test to validate that the billing source dictionary is updated."""
        azure_instance = Sources(
            source_id=4,
            auth_header=self.test_header,
            offset=3,
            endpoint_id=4,
            source_type=Provider.PROVIDER_AZURE,
            name="Test Azure Source",
            billing_source={"data_source": {"resource_group": "original-1", "storage_account": "original-2"}},
        )

        azure_instance.save()
        test_matrix = [
            {
                "instance": azure_instance,
                "billing_source": {"data_source": {"resource_group": "foo", "storage_account": "bar"}},
                "expected": {"data_source": {"resource_group": "foo", "storage_account": "bar"}},
            },
            {
                "instance": azure_instance,
                "billing_source": {"data_source": {"resource_group": "foo"}},
                "expected": {"data_source": {"resource_group": "foo", "storage_account": "original-2"}},
            },
            {
                "instance": azure_instance,
                "billing_source": {"data_source": {"storage_account": "bar"}},
                "expected": {"data_source": {"resource_group": "original-1", "storage_account": "bar"}},
            },
        ]

        for test in test_matrix:
            with self.subTest(test=test):
                try:
                    new_billing = storage._update_billing_source(azure_instance, test.get("billing_source"))
                    self.assertEqual(new_billing, test.get("expected"))
                except Exception as error:
                    self.fail(str(error))
        azure_instance.delete()
