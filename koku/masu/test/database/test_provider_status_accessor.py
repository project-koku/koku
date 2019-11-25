#
# Copyright 2018 Red Hat, Inc.
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

"""Test the ProviderStatusAccessor object."""

import random
import uuid

from faker import Faker

from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.provider_status_accessor import (
    ProviderStatusAccessor,
    ProviderStatusCode,
)
from masu.exceptions import MasuProviderError
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase


class ProviderStatusAccessorTest(MasuTestCase):
    """Test Cases for the ProviderStatusAccessor object."""

    FAKE = Faker()

    def setUp(self):
        """Test set up."""
        super().setUp()

        self.date_accessor = DateAccessor()

        with ProviderDBAccessor(self.aws_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
            self.provider_uuid = provider.uuid

    def _setup_random_status(self):
        """Set up a randomized status for testing.

        This is being done in a separate function instead of in setUp() to
        facilitate testing the case where there is no status in the DB.
        """
        self.test_status = {
            'provider_id': self.provider_uuid,
            'status': random.choice(list(ProviderStatusCode)),
            'last_message': self.FAKE.word(),
            'retries': random.randint(0, 10),
            'timestamp': self.date_accessor.today_with_timezone('UTC'),
        }

        with ProviderStatusAccessor(self.aws_provider_uuid) as accessor:
            status = accessor.add(**self.test_status)
            status.save()
            self.time_stamp = status.timestamp

    def test_init(self):
        """Test __init__() when a status is in the DB."""
        self._setup_random_status()
        with ProviderStatusAccessor(self.aws_provider_uuid) as accessor:
            self.assertIsNotNone(accessor._table)
            self.assertIsNotNone(accessor._obj)

    def test_init_wo_provider(self):
        """Test __init__() when a provider is not in the DB."""
        with self.assertRaises(MasuProviderError):
            ProviderStatusAccessor(str(uuid.uuid4()))

    def test_get_status(self):
        """Test get_status()."""
        self._setup_random_status()
        with ProviderStatusAccessor(self.aws_provider_uuid) as accessor:
            output = accessor.get_status()
            self.assertEqual(output, self.test_status.get('status'))

    def test_get_last_message(self):
        """Test get_last_message()."""
        self._setup_random_status()
        with ProviderStatusAccessor(self.aws_provider_uuid) as accessor:
            output = accessor.get_last_message()
            self.assertEqual(output, self.test_status.get('last_message'))

    def test_get_retries(self):
        """Test get_retries()."""
        self._setup_random_status()
        with ProviderStatusAccessor(self.aws_provider_uuid) as accessor:
            output = accessor.get_retries()
            self.assertEqual(output, self.test_status.get('retries'))

    def test_get_provider_uuid(self):
        """Test get_provider_uuid()."""
        self._setup_random_status()
        with ProviderStatusAccessor(self.aws_provider_uuid) as accessor:
            output = accessor.get_provider_uuid()
            self.assertEqual(output, self.aws_provider_uuid)

    def test_get_timestamp(self):
        """Test get_timestamp()."""
        self._setup_random_status()
        with ProviderStatusAccessor(self.aws_provider_uuid) as accessor:
            output = accessor.get_timestamp()
            self.assertEqual(output, self.time_stamp)
