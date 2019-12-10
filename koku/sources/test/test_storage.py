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

from django.test import TestCase
from faker import Faker
from sources import storage
from sources.config import Config
from sources.storage import SourcesStorageError

from api.provider.models import Sources

faker = Faker()


class MockProvider:
    """Mock Provider Class."""

    def __init__(self, source_id, name, source_type, auth, billing_source, auth_header, offset,
                 pending_delete, koku_uuid=None):
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
        self.test_obj = Sources(source_id=self.test_source_id,
                                auth_header=self.test_header,
                                offset=self.test_offset)
        decoded_rh_auth = b64decode(self.test_header)
        json_rh_auth = json_loads(decoded_rh_auth)
        self.account_id = json_rh_auth.get('identity', {}).get('account_number')

        self.test_obj.save()

    def test_is_known_source(self):
        """Tests is_known_source method."""
        self.assertTrue(storage.is_known_source(self.test_source_id))
        self.assertFalse(storage.is_known_source(self.test_source_id + 1))

    def test_create_provider_event(self):
        """Tests that a source can be created."""
        test_source_id = 2
        test_offset = 3
        storage.create_provider_event(test_source_id, Config.SOURCES_FAKE_HEADER, test_offset)
        db_obj = Sources.objects.get(source_id=test_source_id)
        self.assertEqual(db_obj.source_id, test_source_id)
        self.assertEqual(db_obj.auth_header, Config.SOURCES_FAKE_HEADER)
        self.assertEqual(db_obj.offset, test_offset)
        self.assertEqual(db_obj.account_id, self.account_id)

    def test_create_provider_event_invalid_auth_header(self):
        """Tests creating a source db record with invalid auth_header."""
        test_source_id = 2
        test_offset = 3
        storage.create_provider_event(test_source_id, 'bad', test_offset)
        with self.assertRaises(Sources.DoesNotExist):
            Sources.objects.get(source_id=test_source_id)

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
        source_uuid = faker.uuid4()
        storage.add_provider_sources_network_info(self.test_source_id, source_uuid,
                                                  test_name, source_type, endpoint_id)

        test_source = Sources.objects.get(source_id=self.test_source_id)
        self.assertEqual(test_source.name, test_name)
        self.assertEqual(test_source.source_type, source_type)
        self.assertEqual(test_source.endpoint_id, endpoint_id)
        self.assertEqual(str(test_source.source_uuid), source_uuid)

    def test_add_provider_network_info_not_found(self):
        """Tests that adding information retrieved from the sources network API is not successful."""
        try:
            test_name = 'My Source Name'
            source_type = 'AWS'
            authentication = 'testauth'
            storage.add_provider_sources_network_info(self.test_source_id + 1, faker.uuid4(),
                                                      test_name, source_type, authentication)
        except Exception as error:
            self.fail(str(error))

    def test_add_provider_billing_source(self):
        """Tests that add an AWS billing source to a Source."""
        s3_bucket = {'bucket': 'test-bucket'}
        storage.add_provider_sources_network_info(self.test_source_id, faker.uuid4(),
                                                  'AWS Account', 'AWS', 1)
        storage.add_provider_billing_source({'source_id': self.test_source_id}, s3_bucket)
        self.assertEqual(Sources.objects.get(source_id=self.test_source_id).billing_source, s3_bucket)

    def test_add_provider_billing_source_non_aws(self):
        """Tests that add a non-AWS billing source to a Source."""
        s3_bucket = {'bucket': 'test-bucket'}
        storage.add_provider_sources_network_info(self.test_source_id, faker.uuid4(),
                                                  'OCP Account', 'OCP', 1)
        with self.assertRaises(SourcesStorageError):
            storage.add_provider_billing_source({'source_id': self.test_source_id}, s3_bucket)

    def test_add_provider_billing_source_non_existent(self):
        """Tests that add a billing source to a non-existent Source."""
        s3_bucket = {'bucket': 'test-bucket'}
        storage.add_provider_sources_network_info(self.test_source_id + 1, faker.uuid4(),
                                                  'AWS Account', 'AWS', 1)
        with self.assertRaises(SourcesStorageError):
            storage.add_provider_billing_source({'source_id': self.test_source_id}, s3_bucket)

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
                                                 'authheader', 1, False),
                        'expected_response': {'operation': 'create', 'offset': 1}},
                       {'provider': MockProvider(1, 'AWS Provider', 'AWS',
                                                 {'resource_name': 'arn:fake'},
                                                 None,
                                                 'authheader', 1, False),
                        'expected_response': {}},
                       {'provider': MockProvider(2, 'OCP Provider', 'OCP',
                                                 {'resource_name': 'my-cluster-id'},
                                                 {'bucket': ''},
                                                 'authheader', 2, False),
                        'expected_response': {'operation': 'create', 'offset': 2}},
                       {'provider': MockProvider(2, 'OCP Provider', 'OCP',
                                                 {'resource_name': 'my-cluster-id'},
                                                 {'bucket': ''},
                                                 'authheader', 2, True),
                        'expected_response': {}},
                       {'provider': MockProvider(2, None, 'OCP',
                                                 {'resource_name': 'my-cluster-id'},
                                                 {'bucket': ''},
                                                 'authheader', 2, False),
                        'expected_response': {}},
                       {'provider': MockProvider(3, 'Azure Provider', 'AZURE',
                                                 {'credentials': {'client_id': 'test_client_id',
                                                                  'tenant_id': 'test_tenant_id',
                                                                  'client_secret': 'test_client_secret',
                                                                  'subscription_id': 'test_subscription_id'}},
                                                 {'data_source': {'resource_group': 'test_resource_group',
                                                                  'storage_account': 'test_storage_account'}},
                                                 'authheader', 3, False),
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
        storage.add_subscription_id_to_credentials({'source_id': test_source_id}, subscription_id)

        response_obj = Sources.objects.get(source_id=test_source_id)
        self.assertEqual(response_obj.authentication.get('credentials').get('subscription_id'), subscription_id)

    def test_add_subscription_id_to_credentials_with_koku_uuid(self):
        """Test to add subscription_id to AZURE credentials with koku_uuid."""
        test_source_id = 2
        subscription_id = 'test_sub_id'
        azure_obj = Sources(source_id=test_source_id,
                            auth_header=self.test_header,
                            offset=2,
                            koku_uuid=faker.uuid4(),
                            source_type='AZURE',
                            name='Test Azure Source',
                            authentication={'credentials': {'client_id': 'test_client',
                                                            'tenant_id': 'test_tenant',
                                                            'client_secret': 'test_secret'}},
                            billing_source={'data_source': {'resource_group': 'RG1',
                                                            'storage_account': 'test_storage'}})
        azure_obj.save()
        storage.add_subscription_id_to_credentials({'source_id': test_source_id}, subscription_id)

        response_obj = Sources.objects.get(source_id=test_source_id)
        self.assertEqual(response_obj.authentication.get('credentials').get('subscription_id'), subscription_id)
        self.assertTrue(response_obj.pending_update)

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
            storage.add_subscription_id_to_credentials({'source_id': test_source_id}, subscription_id)

    def test_add_subscription_id_to_credentials_non_existent(self):
        """Test to add subscription_id to a non-existent Source."""
        test_source_id = 4
        subscription_id = 'test_sub_id'

        with self.assertRaises(SourcesStorageError):
            storage.add_subscription_id_to_credentials({'source_id': test_source_id}, subscription_id)

    def test_add_subscription_id_to_credentials_malformed_cred(self):
        """Test to add subscription_id to with a malformed authentication structure."""
        test_source_id = 3
        subscription_id = 'test_sub_id'
        azure_obj = Sources(source_id=test_source_id,
                            auth_header=self.test_header,
                            offset=3,
                            source_type='AZURE',
                            name='Test AZURE Source',
                            authentication={},
                            billing_source={'billing_source': {'data_source': {'resource_group': 'foo',
                                                                               'storage_account': 'bar'}}})
        azure_obj.save()

        with self.assertRaises(SourcesStorageError):
            storage.add_subscription_id_to_credentials({'source_id': test_source_id}, subscription_id)

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
        self.assertEquals(storage.get_source_from_endpoint(test_source_id + 10), None)

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
        response = Sources.objects.filter(source_id=test_source_id).first()
        self.assertEquals(response.authentication, test_authentication)

    def test_add_provider_sources_auth_info_with_sub_id(self):
        """Test to add authentication to a source with subscription_id."""
        test_source_id = 3
        test_endpoint_id = 4
        test_authentication = {'credentials': {'client_id': 'new-client-id'}}
        azure_obj = Sources(source_id=test_source_id,
                            auth_header=self.test_header,
                            offset=3,
                            endpoint_id=test_endpoint_id,
                            source_type='AZURE',
                            name='Test AZURE Source',
                            authentication={'credentials': {'subscription_id': 'orig-sub-id',
                                                            'client_id': 'test-client-id'}})
        azure_obj.save()

        storage.add_provider_sources_auth_info(test_source_id, test_authentication)
        response = Sources.objects.filter(source_id=test_source_id).first()
        self.assertEquals(response.authentication.get('credentials').get('subscription_id'), 'orig-sub-id')
        self.assertEquals(response.authentication.get('credentials').get('client_id'), 'new-client-id')

    def test_enqueue_source_delete(self):
        """Test for enqueuing source delete."""
        test_source_id = 3
        aws_obj = Sources(source_id=test_source_id,
                          auth_header=self.test_header,
                          offset=3,
                          endpoint_id=4,
                          source_type='AWS',
                          name='Test AWS Source',
                          billing_source={'bucket': 'test-bucket'})
        aws_obj.save()

        storage.enqueue_source_delete(test_source_id)
        response = Sources.objects.get(source_id=test_source_id)
        self.assertTrue(response.pending_delete)

    def test_enqueue_source_delete_in_pending(self):
        """Test for enqueuing source delete while pending delete."""
        test_source_id = 3
        aws_obj = Sources(source_id=test_source_id,
                          auth_header=self.test_header,
                          offset=3,
                          endpoint_id=4,
                          source_type='AWS',
                          name='Test AWS Source',
                          billing_source={'bucket': 'test-bucket'},
                          pending_delete=True)
        aws_obj.save()

        storage.enqueue_source_delete(test_source_id)
        response = Sources.objects.get(source_id=test_source_id)
        self.assertTrue(response.pending_delete)

    def test_enqueue_source_update(self):
        """Test for enqueuing source updating."""
        test_matrix = [{'koku_uuid': None, 'pending_delete': False, 'pending_update': False,
                        'expected_pending_update': False},
                       {'koku_uuid': None, 'pending_delete': True, 'pending_update': False,
                        'expected_pending_update': False},
                       {'koku_uuid': faker.uuid4(), 'pending_delete': True, 'pending_update': False,
                        'expected_pending_update': False},
                       {'koku_uuid': faker.uuid4(), 'pending_delete': False, 'pending_update': False,
                        'expected_pending_update': True},
                       {'koku_uuid': faker.uuid4(), 'pending_delete': False, 'pending_update': True,
                        'expected_pending_update': True}]
        test_source_id = 3
        for test in test_matrix:
            aws_obj = Sources(source_id=test_source_id,
                              auth_header=self.test_header,
                              koku_uuid=test.get('koku_uuid'),
                              pending_delete=test.get('pending_delete'),
                              pending_update=test.get('pending_update'),
                              offset=3,
                              endpoint_id=4,
                              source_type='AWS',
                              name='Test AWS Source',
                              billing_source={'bucket': 'test-bucket'})
            aws_obj.save()

            storage.enqueue_source_update(test_source_id)
            response = Sources.objects.get(source_id=test_source_id)
            self.assertEquals(test.get('expected_pending_update'), response.pending_update)
            test_source_id += 1

    def test_clear_update_flag(self):
        """Test for clearing source update flag."""
        test_matrix = [{'koku_uuid': None, 'pending_update': False, 'expected_pending_update': False},
                       {'koku_uuid': faker.uuid4(), 'pending_update': False, 'expected_pending_update': False},
                       {'koku_uuid': faker.uuid4(), 'pending_update': True, 'expected_pending_update': False}]
        test_source_id = 3
        for test in test_matrix:
            aws_obj = Sources(source_id=test_source_id,
                              auth_header=self.test_header,
                              koku_uuid=test.get('koku_uuid'),
                              pending_update=test.get('pending_update'),
                              offset=3,
                              endpoint_id=4,
                              source_type='AWS',
                              name='Test AWS Source',
                              billing_source={'bucket': 'test-bucket'})
            aws_obj.save()

            storage.clear_update_flag(test_source_id)
            response = Sources.objects.get(source_id=test_source_id)
            self.assertEquals(test.get('expected_pending_update'), response.pending_update)
            test_source_id += 1

    def test_load_providers_to_update(self):
        """Test loading pending update events."""
        test_matrix = [{'koku_uuid': faker.uuid4(), 'pending_update': False, 'pending_delete': False,
                        'expected_list_length': 0},
                       {'koku_uuid': faker.uuid4(), 'pending_update': True, 'pending_delete': False,
                        'expected_list_length': 1},
                       {'koku_uuid': None, 'pending_update': True, 'pending_delete': False,
                        'expected_list_length': 0}]

        test_source_id = 3
        for test in test_matrix:
            aws_obj = Sources(source_id=test_source_id,
                              auth_header=self.test_header,
                              koku_uuid=test.get('koku_uuid'),
                              pending_update=test.get('pending_update'),
                              pending_delete=test.get('pending_delete'),
                              offset=3,
                              endpoint_id=4,
                              source_type='AWS',
                              name='Test AWS Source',
                              billing_source={'bucket': 'test-bucket'})
            aws_obj.save()

            response = storage.load_providers_to_update()
            self.assertEquals(len(response), test.get('expected_list_length'))
            test_source_id += 1
            aws_obj.delete()

    def test_get_query_from_api_data(self):
        """Test helper method to get query based on API request_data."""
        test_source_id = 3
        test_source_name = 'Test AWS Source'
        test_endpoint_id = 4
        aws_obj = Sources(source_id=test_source_id,
                          auth_header=self.test_header,
                          offset=3,
                          endpoint_id=test_endpoint_id,
                          source_type='AWS',
                          name=test_source_name,
                          billing_source={'bucket': 'test-bucket'})
        aws_obj.save()

        test_matrix = [{'request_data': {'source_id': test_source_id}, 'expected_exception': None},
                       {'request_data': {'source_name': test_source_name}, 'expected_exception': None},
                       {'request_data': {'source_id': test_source_id, 'source_name': test_source_name},
                        'expected_exception': SourcesStorageError}]

        for test in test_matrix:
            if not test.get('expected_exception'):
                response = storage.get_query_from_api_data(test.get('request_data'))
                self.assertEquals(response.source_id, test_source_id)
            else:
                with self.assertRaises(test.get('expected_exception')):
                    storage.get_query_from_api_data(test.get('request_data'))
