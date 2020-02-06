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
"""Test the ProviderStatus object."""
import random
from datetime import timedelta

from faker import Faker
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.provider_status_accessor import ProviderStatusCode
from masu.external.date_accessor import DateAccessor
from masu.providers.status import ProviderStatus
from masu.test import MasuTestCase


class ProviderStatusTest(MasuTestCase):
    """Test Cases for the ProviderStatus object."""

    FAKE = Faker()

    def setUp(self):
        """Test set up."""
        super().setUp()
        provider_accessor = ProviderDBAccessor(self.aws_provider_uuid)
        provider = provider_accessor.get_provider()
        self.provider_uuid = provider.uuid

    def _setup_random_status(self):
        """Set up a randomized status for testing.

        This is being done in a separate function instead of in setUp() to
        facilitate testing the case where there is no status in the DB.
        """
        self.test_status = {
            "provider_id": self.provider_uuid,
            "status": random.choice(list(ProviderStatusCode)),
            "last_message": self.FAKE.word(),
            "timestamp": DateAccessor().today(),
            "retries": random.randint(0, 10),
        }

        with ProviderStatus(self.aws_provider_uuid) as accessor:
            accessor.add(**self.test_status)

    def _setup_ready_status(self):
        """Set status to READY state."""
        ready_status = {
            "provider_id": self.provider_uuid,
            "status": ProviderStatusCode.READY,
            "last_message": "none",
            "timestamp": DateAccessor().today(),
            "retries": 0,
        }
        with ProviderStatus(self.aws_provider_uuid) as accessor:
            accessor.add(**ready_status)

    def test_set_status_success(self):
        """Test set_status()."""
        self._setup_random_status()
        with ProviderStatus(self.aws_provider_uuid) as accessor:
            accessor.set_status(ProviderStatusCode.READY)

        with ProviderStatus(self.aws_provider_uuid) as new_accessor:
            self.assertEqual(new_accessor.get_status(), ProviderStatusCode.READY)
            self.assertEqual(new_accessor.get_last_message(), "none")
            self.assertEqual(new_accessor.get_retries(), 0)

    def test_set_error(self):
        """Test set_error()."""
        # set status to READY state.
        self._setup_ready_status()

        # log an error
        accessor = ProviderStatus(self.aws_provider_uuid)
        err = Exception(self.FAKE.word())
        accessor.set_error(error=err)

        # test that state moved from READY to WARNING
        with ProviderStatus(self.aws_provider_uuid) as new_accessor:
            self.assertEqual(new_accessor.get_status(), ProviderStatusCode.WARNING)
            self.assertEqual(new_accessor.get_last_message(), str(err))
            self.assertEqual(new_accessor.get_retries(), 1)

    def test_update_status_error_retries(self):
        """Test set_error() when MAX_RETRIES is exceeded."""
        # set status to READY state.
        self._setup_ready_status()

        for idx in range(1, ProviderStatus.MAX_RETRIES + 2):
            # log an error
            with ProviderStatus(self.aws_provider_uuid) as accessor:
                err = Exception(self.FAKE.word())
                accessor.set_error(error=err)

            # status should stay in WARNING until MAX_RETRIES is exceeded.
            if idx < ProviderStatus.MAX_RETRIES:
                with ProviderStatus(self.aws_provider_uuid) as new_accessor:
                    self.assertEqual(new_accessor.get_status(), ProviderStatusCode.WARNING)
                    self.assertEqual(new_accessor.get_retries(), idx)

        # status should be DISABLED after MAX_RETRIES is reached.
        with ProviderStatus(self.aws_provider_uuid) as other_accessor:
            self.assertEqual(other_accessor.get_status(), ProviderStatusCode.DISABLED_ERROR)
            self.assertEqual(other_accessor.get_retries(), ProviderStatus.MAX_RETRIES)

    def test_is_valid_ready(self):
        """Test is_valid() should be True when status is READY."""
        self._setup_ready_status()

        with ProviderStatus(self.aws_provider_uuid) as accessor:
            self.assertTrue(accessor.is_valid())

    def test_is_valid_warn(self):
        """Test is_valid() should be True when status is WARNING."""
        status = {
            "provider_id": self.provider_uuid,
            "status": ProviderStatusCode.WARNING,
            "last_message": self.FAKE.word(),
            "timestamp": DateAccessor().today(),
            "retries": 3,
        }
        with ProviderStatus(self.aws_provider_uuid) as accessor:
            accessor.add(**status)

        accessor = ProviderStatus(self.aws_provider_uuid)
        self.assertTrue(accessor.is_valid())

    def test_is_valid_disabled(self):
        """Test when is_valid() should be False when status is DISABLED."""
        status = {
            "provider_id": self.provider_uuid,
            "status": ProviderStatusCode.DISABLED_ERROR,
            "last_message": self.FAKE.word(),
            "timestamp": DateAccessor().today(),
            "retries": 3,
        }
        with ProviderStatus(self.aws_provider_uuid) as accessor:
            accessor.add(**status)

        accessor = ProviderStatus(self.aws_provider_uuid)
        self.assertFalse(accessor.is_valid())

    def test_is_valid_new(self):
        """Test when is_valid() should be False when status is NEW."""
        status = {
            "provider_id": self.provider_uuid,
            "status": ProviderStatusCode.NEW,
            "last_message": self.FAKE.word(),
            "timestamp": DateAccessor().today(),
            "retries": 3,
        }
        with ProviderStatus(self.aws_provider_uuid) as accessor:
            accessor.add(**status)

        with ProviderStatus(self.aws_provider_uuid) as accessor:
            self.assertFalse(accessor.is_valid())

    def test_is_backing_off_true(self):
        """Test is_backing_off() is true within the appropriate time window."""
        two_hours_ago = DateAccessor().today() - timedelta(hours=2)
        status = {
            "provider_id": self.provider_uuid,
            "status": ProviderStatusCode.WARNING,
            "last_message": self.FAKE.word(),
            "timestamp": two_hours_ago,
            "retries": 1,
        }
        with ProviderStatus(self.aws_provider_uuid) as accessor:
            accessor.add(**status)

        with ProviderStatus(self.aws_provider_uuid) as accessor:
            self.assertTrue(accessor.is_backing_off())

    def test_is_backing_off_false(self):
        """Test is_backing_off() is false outside the appropriate time window."""
        three_hours_ago = DateAccessor().today() - timedelta(hours=3)
        status = {
            "provider_id": self.provider_uuid,
            "status": ProviderStatusCode.WARNING,
            "last_message": self.FAKE.word(),
            "timestamp": str(three_hours_ago),
            "retries": 1,
        }

        with ProviderStatus(self.aws_provider_uuid) as accessor:
            accessor.add(**status)

        with ProviderStatus(self.aws_provider_uuid) as accessor:
            self.assertFalse(accessor.is_backing_off())
