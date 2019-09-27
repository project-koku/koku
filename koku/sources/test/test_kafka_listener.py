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

"""Test the Sources Kafka Listener handler."""
import logging
from unittest.mock import patch

import requests
import requests_mock
import sources.kafka_listener as source_integration
from django.test import TestCase
from faker import Faker
from sources.config import Config
from sources.sources_http_client import SourcesHTTPClientError

from api.provider.models import Sources

faker = Faker()


class ConsumerRecord:
    """Test class for kafka msg."""

    def __init__(self, topic, offset, event_type, auth_header, value):
        """Initialize Msg."""
        self.topic = topic
        self.offset = offset
        self.headers = (('event_type', bytes(event_type, encoding='utf-8')),
                        ('x-rh-identity', bytes(auth_header, encoding='utf-8')))
        self.value = value


class SourcesKafkaMsgHandlerTest(TestCase):
    """Test Cases for the Sources Kafka Listener."""

    @patch.object(Config, 'KOKU_API_URL', 'http://www.koku.com/api/cost-management/v1')
    def test_execute_koku_provider_op_create(self):
        """Test to execute Koku Operations to sync with Sources for creation."""
        source_id = 1
        auth_header = Config.SOURCES_FAKE_HEADER
        offset = 2
        provider = Sources(source_id=source_id, auth_header=auth_header, offset=offset)
        provider.save()

        mock_koku_uuid = faker.uuid4()
        with requests_mock.mock() as m:
            m.post('http://www.koku.com/api/cost-management/v1/providers/',
                   status_code=201,
                   json={'uuid': mock_koku_uuid})
            msg = {'operation': 'create', 'provider': provider, 'offset': provider.offset}
            source_integration.execute_koku_provider_op(msg)
            self.assertEqual(Sources.objects.get(source_id=source_id).koku_uuid, mock_koku_uuid)

    @patch.object(Config, 'KOKU_API_URL', 'http://www.koku.com/api/cost-management/v1')
    def test_execute_koku_provider_op_destroy(self):
        """Test to execute Koku Operations to sync with Sources for destruction."""
        source_id = 1
        auth_header = Config.SOURCES_FAKE_HEADER
        offset = 2
        mock_koku_uuid = faker.uuid4()

        provider = Sources(source_id=source_id, auth_header=auth_header, offset=offset, koku_uuid=mock_koku_uuid)
        provider.save()

        with requests_mock.mock() as m:
            m.delete(f'http://www.koku.com/api/cost-management/v1/providers/{mock_koku_uuid}/',
                     status_code=204)
            msg = {'operation': 'destroy', 'provider': provider, 'offset': provider.offset}
            source_integration.execute_koku_provider_op(msg)
            self.assertEqual(Sources.objects.filter(source_id=source_id).exists(), False)

    @patch.object(Config, 'KOKU_API_URL', 'http://www.koku.com/api/cost-management/v1')
    def test_execute_koku_provider_op_destroy_recoverable_error(self):
        """Test to execute Koku Operations to sync with Sources with recoverable error."""
        source_id = 1
        auth_header = Config.SOURCES_FAKE_HEADER
        offset = 2

        provider = Sources(source_id=source_id, auth_header=auth_header, offset=offset)
        provider.save()

        with requests_mock.mock() as m:
            m.post('http://www.koku.com/api/cost-management/v1/providers/',
                   exc=requests.exceptions.RequestException)
            with self.assertRaises(source_integration.SourcesIntegrationError):
                msg = {'operation': 'create', 'provider': provider, 'offset': provider.offset}
                source_integration.execute_koku_provider_op(msg)

    @patch.object(Config, 'KOKU_API_URL', 'http://www.koku.com/api/cost-management/v1')
    def test_execute_koku_provider_op_destroy_non_recoverable_error(self):
        """Test to execute Koku Operations to sync with Sources with non-recoverable error."""
        source_id = 1
        auth_header = Config.SOURCES_FAKE_HEADER
        offset = 2

        provider = Sources(source_id=source_id, auth_header=auth_header, offset=offset)
        provider.save()

        logging.disable(logging.NOTSET)
        with requests_mock.mock() as m:
            m.post('http://www.koku.com/api/cost-management/v1/providers/',
                   status_code=400,
                   json={'uuid': faker.uuid4()})
            with self.assertLogs('sources.kafka_listener', level='ERROR') as logger:
                msg = {'operation': 'create', 'provider': provider, 'offset': provider.offset}
                source_integration.execute_koku_provider_op(msg)
                self.assertIn(':Unable to create provider for Source ID: 1', logger.output[0])

    def test_get_sources_msg_data(self):
        """Test to get sources details from msg."""
        test_topic = 'platform.sources.event-stream'
        test_event_type = 'Application.create'
        test_offset = 5
        cost_management_app_type = 2
        test_auth_header = 'testheader'
        test_value = '{"id":1,"source_id":1,"application_type_id":2}'

        msg = ConsumerRecord(topic=test_topic, offset=test_offset, event_type=test_event_type,
                             auth_header=test_auth_header, value=bytes(test_value, encoding='utf-8'))

        response = source_integration.get_sources_msg_data(msg, cost_management_app_type)
        self.assertEqual(response.get('event_type'), test_event_type)
        self.assertEqual(response.get('offset'), test_offset)
        self.assertEqual(response.get('source_id'), 1)
        self.assertEqual(response.get('auth_header'), test_auth_header)

    def test_get_sources_msg_data_destroy(self):
        """Test to get sources details from msg for destroy event."""
        test_topic = 'platform.sources.event-stream'
        test_event_type = 'Application.destroy'
        test_offset = 5
        cost_management_app_type = 2
        test_auth_header = 'testheader'
        test_value = '{"id":1,"source_id":1,"application_type_id":2}'

        msg = ConsumerRecord(topic=test_topic, offset=test_offset, event_type=test_event_type,
                             auth_header=test_auth_header, value=bytes(test_value, encoding='utf-8'))

        response = source_integration.get_sources_msg_data(msg, cost_management_app_type)
        self.assertEqual(response.get('event_type'), test_event_type)
        self.assertEqual(response.get('offset'), test_offset)
        self.assertEqual(response.get('source_id'), 1)
        self.assertEqual(response.get('auth_header'), test_auth_header)

    def test_get_sources_msg_data_other(self):
        """Test to get sources details from other message."""
        test_topic = 'platform.sources.event-stream'
        test_event_type = 'Source.create'
        test_offset = 5
        cost_management_app_type = 2
        test_auth_header = 'testheader'
        test_value = '{"id":1,"source_id":1,"application_type_id":2}'

        msg = ConsumerRecord(topic=test_topic, offset=test_offset, event_type=test_event_type,
                             auth_header=test_auth_header, value=bytes(test_value, encoding='utf-8'))

        response = source_integration.get_sources_msg_data(msg, cost_management_app_type)
        self.assertEqual(response, {})

    def test_get_sources_msg_data_other_app_type(self):
        """Test to get sources details from Application.create event type for a non-Cost Management app."""
        test_topic = 'platform.sources.event-stream'
        test_event_type = 'Application.create'
        test_offset = 5
        cost_management_app_type = 2
        test_auth_header = 'testheader'
        test_value = '{"id":1,"source_id":1,"application_type_id":1}'  # 1 is not Cost Management

        msg = ConsumerRecord(topic=test_topic, offset=test_offset, event_type=test_event_type,
                             auth_header=test_auth_header, value=bytes(test_value, encoding='utf-8'))

        response = source_integration.get_sources_msg_data(msg, cost_management_app_type)
        self.assertEqual(response, {})

    def test_get_sources_msg_data_malformed(self):
        """Test to get sources details from Application.create event with malformed data."""
        test_topic = 'platform.sources.event-stream'
        test_event_type = 'Application.create'
        test_offset = 5
        cost_management_app_type = 2
        test_auth_header = 'testheader'
        test_value = {'id': 1, 'source_id': 1, 'application_type_id': 2}

        msg = ConsumerRecord(topic=test_topic, offset=test_offset, event_type=test_event_type,
                             auth_header=test_auth_header, value=test_value)
        with self.assertRaises(source_integration.SourcesIntegrationError):
            source_integration.get_sources_msg_data(msg, cost_management_app_type)

    def test_collect_pending_items(self):
        """Test to load the in-progress queue."""
        aws_source = Sources(source_id=1,
                             auth_header=Config.SOURCES_FAKE_HEADER,
                             offset=1,
                             name='AWS Source',
                             source_type='AWS',
                             billing_source='s3bucket')
        aws_source.save()

        aws_source_incomplete = Sources(source_id=2,
                                        auth_header=Config.SOURCES_FAKE_HEADER,
                                        offset=2,
                                        name='AWS Source 2',
                                        source_type='AWS')
        aws_source_incomplete.save()

        ocp_source = Sources(source_id=3,
                             auth_header=Config.SOURCES_FAKE_HEADER,
                             offset=3, name='OCP Source',
                             source_type='OCP')
        ocp_source.save()

        ocp_source_complete = Sources(source_id=4,
                                      auth_header=Config.SOURCES_FAKE_HEADER,
                                      offset=4,
                                      name='Complete OCP Source',
                                      source_type='OCP',
                                      koku_uuid=faker.uuid4())
        ocp_source_complete.save()
        source_delete = Sources.objects.get(source_id=4)
        source_delete.pending_delete = True
        source_delete.save()

        response = source_integration._collect_pending_items()
        self.assertEqual(len(response), 3)

    @patch.object(Config, 'SOURCES_API_URL', 'http://www.sources.com')
    def test_sources_network_info_sync_aws(self):
        """Test to get additional Source context from Sources API for AWS."""
        test_source_id = 2
        test_auth_header = Config.SOURCES_FAKE_HEADER
        source_name = 'AWS Source'
        source_uid = faker.uuid4()
        authentication = 'roleARNhere'
        aws_source = Sources(source_id=test_source_id,
                             auth_header=test_auth_header,
                             offset=1)
        aws_source.save()
        source_type_id = 1
        mock_source_name = 'amazon'
        resource_id = 2
        authentication_id = 3
        with requests_mock.mock() as m:
            m.get(f'http://www.sources.com/api/v1.0/sources/{test_source_id}',
                  status_code=200, json={'name': source_name, 'source_type_id': source_type_id, 'uid': source_uid})
            m.get(f'http://www.sources.com/api/v1.0/source_types?filter[id]={source_type_id}',
                  status_code=200, json={'data': [{'name': mock_source_name}]})
            m.get(f'http://www.sources.com/api/v1.0/endpoints?filter[source_id]={test_source_id}',
                  status_code=200, json={'data': [{'id': resource_id}]})
            m.get((f'http://www.sources.com/api/v1.0/authentications?filter[resource_type]=Endpoint'
                  f'&[authtype]=arn&[resource_id]={resource_id}'),
                  status_code=200, json={'data': [{'id': authentication_id}]})
            m.get((f'http://www.sources.com/internal/v1.0/authentications/{authentication_id}'
                  f'?expose_encrypted_attribute[]=password'),
                  status_code=200, json={'password': authentication})

            source_integration.sources_network_info(test_source_id, test_auth_header)

        source_obj = Sources.objects.get(source_id=test_source_id)
        self.assertEqual(source_obj.name, source_name)
        self.assertEqual(source_obj.source_type, 'AWS')
        self.assertEqual(source_obj.authentication, {'resource_name': authentication})

    @patch.object(Config, 'SOURCES_API_URL', 'http://www.sources.com')
    def test_sources_network_info_sync_ocp(self):
        """Test to get additional Source context from Sources API for OCP."""
        test_source_id = 1
        test_auth_header = Config.SOURCES_FAKE_HEADER
        source_name = 'OCP Source'
        source_uid = faker.uuid4()
        ocp_source = Sources(source_id=test_source_id,
                             auth_header=test_auth_header,
                             offset=1)
        ocp_source.save()
        source_type_id = 3
        mock_source_name = 'openshift'
        with requests_mock.mock() as m:
            m.get(f'http://www.sources.com/api/v1.0/sources/{test_source_id}',
                  status_code=200, json={'name': source_name, 'source_type_id': source_type_id, 'uid': source_uid})
            m.get(f'http://www.sources.com/api/v1.0/source_types?filter[id]={source_type_id}',
                  status_code=200, json={'data': [{'name': mock_source_name}]})
            source_integration.sources_network_info(test_source_id, test_auth_header)

        source_obj = Sources.objects.get(source_id=test_source_id)
        self.assertEqual(source_obj.name, source_name)
        self.assertEqual(source_obj.source_type, 'OCP')
        self.assertEqual(source_obj.authentication, {'resource_name': source_uid})

    @patch.object(Config, 'SOURCES_API_URL', 'http://www.sources.com')
    def test_sources_network_info_sync_azure(self):
        """Test to get additional Source context from Sources API for AZURE."""
        test_source_id = 3
        test_auth_header = Config.SOURCES_FAKE_HEADER
        source_name = 'AZURE Source'
        source_uid = faker.uuid4()
        username = 'test_user'
        authentication = 'testclientcreds'
        tenent_id = 'test_tenent_id'
        azure_source = Sources(source_id=test_source_id,
                               auth_header=test_auth_header,
                               offset=1)
        azure_source.save()
        source_type_id = 2
        mock_source_name = 'azure'
        resource_id = 3
        authentication_id = 4
        authentications_response = {'id': authentication_id, 'username': username,
                                    'extra': {'azure': {'tenant_id': tenent_id}}}
        with requests_mock.mock() as m:
            m.get(f'http://www.sources.com/api/v1.0/sources/{test_source_id}',
                  status_code=200, json={'name': source_name, 'source_type_id': source_type_id, 'uid': source_uid})
            m.get(f'http://www.sources.com/api/v1.0/source_types?filter[id]={source_type_id}',
                  status_code=200, json={'data': [{'name': mock_source_name}]})
            m.get(f'http://www.sources.com/api/v1.0/endpoints?filter[source_id]={test_source_id}',
                  status_code=200, json={'data': [{'id': resource_id}]})
            m.get((f'http://www.sources.com/api/v1.0/authentications?filter[resource_type]=Endpoint'
                  f'&[authtype]=access_key_secret_key&[resource_id]={resource_id}'),
                  status_code=200, json={'data': [authentications_response]})
            m.get((f'http://www.sources.com/internal/v1.0/authentications/{authentication_id}'
                  f'?expose_encrypted_attribute[]=password'),
                  status_code=200, json={'password': authentication})

            source_integration.sources_network_info(test_source_id, test_auth_header)

        source_obj = Sources.objects.get(source_id=test_source_id)
        self.assertEqual(source_obj.name, source_name)
        self.assertEqual(source_obj.source_type, 'AZURE')
        self.assertEqual(source_obj.authentication, {'credentials': {'client_id': username,
                                                                     'client_secret': authentication,
                                                                     'tenant_id': tenent_id}})

    @patch.object(Config, 'SOURCES_API_URL', 'http://www.sources.com')
    def test_sources_network_info_sync_connection_error(self):
        """Test to get additional Source context from Sources API with connection_error."""
        test_source_id = 1
        test_auth_header = Config.SOURCES_FAKE_HEADER
        ocp_source = Sources(source_id=test_source_id,
                             auth_header=test_auth_header,
                             offset=1)
        ocp_source.save()

        with requests_mock.mock() as m:
            m.get(f'http://www.sources.com/api/v1.0/sources/{test_source_id}',
                  exc=SourcesHTTPClientError)

            source_integration.sources_network_info(test_source_id, test_auth_header)

        source_obj = Sources.objects.get(source_id=test_source_id)
        self.assertIsNone(source_obj.name)
        self.assertEquals(source_obj.source_type, '')
        self.assertEquals(source_obj.authentication, {})
