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
        authentication = 'testauth'

        storage.add_provider_sources_network_info(self.test_source_id, test_name, source_type, authentication)

        test_source = Sources.objects.get(source_id=self.test_source_id)
        self.assertEqual(test_source.name, test_name)
        self.assertEqual(test_source.source_type, source_type)
        self.assertEqual(test_source.authentication, authentication)

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
        s3_bucket = 'test-bucket'
        storage.add_provider_sources_network_info(self.test_source_id, 'AWS Account', 'AWS', 'testauth')
        storage.add_provider_billing_source(self.test_source_id, s3_bucket)
        self.assertEqual(Sources.objects.get(source_id=self.test_source_id).billing_source, s3_bucket)

    def test_add_provider_billing_source_non_aws(self):
        """Tests that add a non-AWS billing source to a Source."""
        s3_bucket = 'test-bucket'
        storage.add_provider_sources_network_info(self.test_source_id, 'OCP Account', 'OCP', 'testauth')
        with self.assertRaises(SourcesStorageError):
            storage.add_provider_billing_source(self.test_source_id, s3_bucket)

    def test_add_provider_billing_source_non_existent(self):
        """Tests that add a billing source to a non-existent Source."""
        s3_bucket = 'test-bucket'
        storage.add_provider_sources_network_info(self.test_source_id + 1, 'AWS Account', 'AWS', 'testauth')
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
