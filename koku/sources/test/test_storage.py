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

from django.test import TestCase
from faker import Faker
from sources import storage
from sources.config import Config
from sources.storage import SourcesStorageError

from api.provider.models import Sources

faker = Faker()


class MockProvider:
    """Mock Provider Class."""

    def __init__(self, source_id, name, source_type, auth, billing_source, auth_header, offset, koku_uuid=None):
        """Init mock provider."""
        self.source_id = source_id
        self.name = name
        self.source_type = source_type
        self.authentication = auth
        self.billing_source = billing_source
        self.auth_header = auth_header
        self.offset = offset
        self.koku_uuid = koku_uuid


class SourcesStorageTest(TestCase):
    """Test cases for Sources Storage."""

    def setUp(self):
        """Test case setup."""
        self.test_source_id = 1
        self.test_offset = 2
        self.test_header = Config.SOURCES_FAKE_HEADER
        self.test_obj = Sources(source_id=self.test_source_id,
                                auth_header=self.test_header,
                                offset=self.test_offset)
        self.test_obj.save()

    def test_create_provider_event(self):
        """Tests that a source can be created."""
        test_source_id = 2
        test_offset = 3
        storage.create_provider_event(test_source_id, Config.SOURCES_FAKE_HEADER, test_offset)
        db_obj = Sources.objects.get(source_id=test_source_id)
        self.assertEqual(db_obj.source_id, test_source_id)
        self.assertEqual(db_obj.auth_header, Config.SOURCES_FAKE_HEADER)
        self.assertEqual(db_obj.offset, test_offset)

    def test_destroy_provider_event(self):
        """Tests that a source can be destroyed."""
        test_uuid = faker.uuid4()
        self.assertIsNotNone(self.test_obj)
        storage.add_provider_koku_uuid(self.test_source_id, test_uuid)
        response = storage.destroy_provider_event(self.test_source_id)
        self.assertFalse(Sources.objects.filter(source_id=self.test_source_id).exists())
        self.assertEqual(response, test_uuid)

    def test_destroy_provider_event_not_found(self):
        """Tests when destroying a non-existent source."""
        response = storage.destroy_provider_event(self.test_source_id + 1)
        self.assertIsNone(response)

    def test_add_provider_network_info(self):
        """Tests that adding information retrieved from the sources network API is successful."""
        test_source = Sources.objects.get(source_id=self.test_source_id)
        self.assertIsNone(test_source.name)
        self.assertEqual(test_source.source_type, '')
        self.assertEqual(test_source.authentication, {})

        test_name = 'My Source Name'
        source_type = 'AWS'
        endpoint_id = 1

        storage.add_provider_sources_network_info(self.test_source_id, test_name, source_type,
                                                  endpoint_id)

        test_source = Sources.objects.get(source_id=self.test_source_id)
        self.assertEqual(test_source.name, test_name)
        self.assertEqual(test_source.source_type, source_type)
        self.assertEqual(test_source.endpoint_id, endpoint_id)

    def test_add_provider_network_info_not_found(self):
        """Tests that adding information retrieved from the sources network API is not successful."""
        try:
            test_name = 'My Source Name'
            source_type = 'AWS'
            authentication = 'testauth'
            storage.add_provider_sources_network_info(self.test_source_id + 1,
                                                      test_name, source_type, authentication)
        except Exception as error:
            self.fail(str(error))

    def test_add_provider_billing_source(self):
        """Tests that add an AWS billing source to a Source."""
        s3_bucket = {'bucket': 'test-bucket'}
        storage.add_provider_sources_network_info(self.test_source_id, 'AWS Account', 'AWS', 1)
        storage.add_provider_billing_source(self.test_source_id, s3_bucket)
        self.assertEqual(Sources.objects.get(source_id=self.test_source_id).billing_source, s3_bucket)

    def test_add_provider_billing_source_non_aws(self):
        """Tests that add a non-AWS billing source to a Source."""
        s3_bucket = {'bucket': 'test-bucket'}
        storage.add_provider_sources_network_info(self.test_source_id, 'OCP Account', 'OCP', 1)
        with self.assertRaises(SourcesStorageError):
            storage.add_provider_billing_source(self.test_source_id, s3_bucket)

    def test_add_provider_billing_source_non_existent(self):
        """Tests that add a billing source to a non-existent Source."""
        s3_bucket = {'bucket': 'test-bucket'}
        storage.add_provider_sources_network_info(self.test_source_id + 1, 'AWS Account', 'AWS', 1)
        with self.assertRaises(SourcesStorageError):
            storage.add_provider_billing_source(self.test_source_id, s3_bucket)

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
        test_matrix = [{'provider': MockProvider(1, 'AWS Provider', 'AWS',
                                                 {'resource_name': 'arn:fake'},
                                                 {'bucket': 'testbucket'},
                                                 'authheader', 1),
                        'expected_response': {'operation': 'create', 'offset': 1}},
                       {'provider': MockProvider(1, 'AWS Provider', 'AWS',
                                                 {'resource_name': 'arn:fake'},
                                                 None,
                                                 'authheader', 1),
                        'expected_response': {}},
                       {'provider': MockProvider(2, 'OCP Provider', 'OCP',
                                                 {'resource_name': 'my-cluster-id'},
                                                 {'bucket': ''},
                                                 'authheader', 2),
                        'expected_response': {'operation': 'create', 'offset': 2}},
                       {'provider': MockProvider(2, None, 'OCP',
                                                 {'resource_name': 'my-cluster-id'},
                                                 {'bucket': ''},
                                                 'authheader', 2),
                        'expected_response': {}},
                       {'provider': MockProvider(3, 'Azure Provider', 'AZURE',
                                                 {'credentials': {'client_id': 'test_client_id',
                                                                  'tenant_id': 'test_tenant_id',
                                                                  'client_secret': 'test_client_secret',
                                                                  'subscription_id': 'test_subscription_id'}},
                                                 {'data_source': {'resource_group': 'test_resource_group',
                                                                  'storage_account': 'test_storage_account'}},
                                                 'authheader', 3),
                        'expected_response': {'operation': 'create', 'offset': 3}}
                       ]

        for test in test_matrix:
            response = storage.screen_and_build_provider_sync_create_event(test.get('provider'))

            if response:
                self.assertEqual(response.get('operation'), test.get('expected_response').get('operation'))
                self.assertEqual(response.get('offset'), test.get('expected_response').get('offset'))
            else:
                self.assertEqual(response, {})

    def test_add_subscription_id_to_credentials(self):
        """Test to add subscription_id to AZURE credentials."""
        test_source_id = 2
        subscription_id = 'test_sub_id'
        azure_obj = Sources(source_id=test_source_id,
                            auth_header=self.test_header,
                            offset=2,
                            source_type='AZURE',
                            name='Test Azure Source',
                            authentication={'credentials': {'client_id': 'test_client',
                                                            'tenant_id': 'test_tenant',
                                                            'client_secret': 'test_secret'}},
                            billing_source={'data_source': {'resource_group': 'RG1',
                                                            'storage_account': 'test_storage'}})
        azure_obj.save()
        storage.add_subscription_id_to_credentials(test_source_id, subscription_id)

        response_obj = Sources.objects.get(source_id=test_source_id)
        self.assertEqual(response_obj.authentication.get('credentials').get('subscription_id'), subscription_id)

    def test_add_subscription_id_to_credentials_non_azure(self):
        """Test to add subscription_id to a non-AZURE credentials."""
        test_source_id = 3
        subscription_id = 'test_sub_id'
        ocp_obj = Sources(source_id=test_source_id,
                          auth_header=self.test_header,
                          offset=3,
                          source_type='AWS',
                          name='Test AWS Source',
                          authentication={'resource_name': 'arn:test'},
                          billing_source={'bucket': 'test-bucket'})
        ocp_obj.save()

        with self.assertRaises(SourcesStorageError):
            storage.add_subscription_id_to_credentials(test_source_id, subscription_id)

    def test_add_subscription_id_to_credentials_non_existent(self):
        """Test to add subscription_id to a non-existent Source."""
        test_source_id = 4
        subscription_id = 'test_sub_id'

        with self.assertRaises(SourcesStorageError):
            storage.add_subscription_id_to_credentials(test_source_id, subscription_id)

    def test_validate_billing_source(self):
        """Test to validate that the billing source dictionary is valid."""
        test_matrix = [{'provider_type': 'AWS', 'billing_source': {'bucket': 'test-bucket'},
                        'exception': False},
                       {'provider_type': 'AZURE', 'billing_source': {'data_source': {'resource_group': 'foo',
                                                                                     'storage_account': 'bar'}},
                        'exception': False},
                       {'provider_type': 'AWS', 'billing_source': {'nobucket': 'test-bucket'},
                        'exception': True},
                       {'provider_type': 'AWS', 'billing_source': {},
                        'exception': True},
                       {'provider_type': 'AZURE', 'billing_source': {},
                        'exception': True},
                       {'provider_type': 'AZURE', 'billing_source': {'nodata_source': {'resource_group': 'foo',
                                                                                       'storage_account': 'bar'}},
                        'exception': True},
                       {'provider_type': 'AZURE', 'billing_source': {'data_source': {'noresource_group': 'foo',
                                                                                     'storage_account': 'bar'}},
                        'exception': True},
                       {'provider_type': 'AZURE', 'billing_source': {'data_source': {'resource_group': 'foo',
                                                                                     'nostorage_account': 'bar'}},
                        'exception': True},
                       {'provider_type': 'AZURE', 'billing_source': {'data_source': {'resource_group': 'foo'}},
                        'exception': True},
                       {'provider_type': 'AZURE', 'billing_source': {'data_source': {'storage_account': 'bar'}},
                        'exception': True},
                       ]

        for test in test_matrix:
            if test.get('exception'):
                with self.assertRaises(SourcesStorageError):
                    storage._validate_billing_source(test.get('provider_type'), test.get('billing_source'))
            else:
                try:
                    storage._validate_billing_source(test.get('provider_type'), test.get('billing_source'))
                except Exception as error:
                    self.fail(str(error))

    def test_get_source_type(self):
        """Test to source type from source."""
        test_source_id = 3

        ocp_obj = Sources(source_id=test_source_id,
                          auth_header=self.test_header,
                          offset=3,
                          source_type='OCP',
                          name='Test OCP Source',
                          authentication={'resource_name': 'arn:test'},
                          billing_source={'bucket': 'test-bucket'})
        ocp_obj.save()

        response = storage.get_source_type(test_source_id)
        self.assertEquals(response, 'OCP')
        self.assertEquals(storage.get_source_type(test_source_id + 1), None)

    def test_get_source_from_endpoint(self):
        """Test to source from endpoint id."""
        test_source_id = 3
        test_endpoint_id = 4
        aws_obj = Sources(source_id=test_source_id,
                          auth_header=self.test_header,
                          offset=3,
                          endpoint_id=test_endpoint_id,
                          source_type='AWS',
                          name='Test AWS Source',
                          authentication={'resource_name': 'arn:test'},
                          billing_source={'bucket': 'test-bucket'})
        aws_obj.save()

        response = storage.get_source_from_endpoint(test_endpoint_id)
        self.assertEquals(response, test_source_id)
        self.assertEquals(storage.get_source_from_endpoint(test_source_id + 1), None)

    def test_add_provider_sources_auth_info(self):
        """Test to add authentication to a source."""
        test_source_id = 3
        test_endpoint_id = 4
        test_authentication = {'resource_name': 'arn:test'}
        aws_obj = Sources(source_id=test_source_id,
                          auth_header=self.test_header,
                          offset=3,
                          endpoint_id=test_endpoint_id,
                          source_type='AWS',
                          name='Test AWS Source',
                          billing_source={'bucket': 'test-bucket'})
        aws_obj.save()

        storage.add_provider_sources_auth_info(test_source_id, test_authentication)
        response = Sources.objects.filter(source_id=test_source_id)
        self.assertEquals(response.authentication, test_authentication)
