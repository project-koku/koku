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

"""Test the ExpiredDataRemover object."""

from datetime import datetime
from unittest.mock import patch

import pytz

from masu.external import PROVIDER_AWS, PROVIDER_AZURE, PROVIDER_OCP
from masu.external.date_accessor import DateAccessor
from masu.processor.expired_data_remover import (
    ExpiredDataRemover,
    ExpiredDataRemoverError,
)
from masu.test import MasuTestCase


class ExpiredDataRemoverTest(MasuTestCase):
    """Test Cases for the ExpiredDataRemover object."""

    def test_initializer(self):
        """Test to init."""
        remover = ExpiredDataRemover(self.schema, PROVIDER_AWS)
        self.assertEqual(remover._months_to_keep, 3)
        self.assertIsInstance(remover._expiration_date, datetime)

    def test_initializer_ocp(self):
        """Test to init for OCP."""
        remover = ExpiredDataRemover(self.schema, PROVIDER_OCP)
        self.assertEqual(remover._months_to_keep, 3)
        self.assertIsInstance(remover._expiration_date, datetime)

    def test_initializer_azure(self):
        """Test to init for Azure."""
        remover = ExpiredDataRemover(self.schema, PROVIDER_AZURE)
        self.assertEqual(remover._months_to_keep, 3)
        self.assertIsInstance(remover._expiration_date, datetime)

    def test_initializer_invalid_provider(self):
        """Test to init with unknown provider."""
        with self.assertRaises(ExpiredDataRemoverError):
            ExpiredDataRemover(self.schema, 'BAD')

    @patch(
        'masu.processor.aws.aws_report_db_cleaner.AWSReportDBCleaner.__init__',
        side_effect=Exception,
    )
    def test_initializer_provider_exception(self, mock_aws_cleaner):
        """Test to init."""
        with self.assertRaises(ExpiredDataRemoverError):
            ExpiredDataRemover(self.schema, PROVIDER_AWS)

    def test_calculate_expiration_date(self):
        """Test that the expiration date is correctly calculated."""
        date_matrix = [
            {
                'current_date': datetime(year=2018, month=7, day=1),
                'expected_expire': datetime(year=2018, month=4, day=1, tzinfo=pytz.UTC),
                'months_to_keep': None,
            },
            {
                'current_date': datetime(year=2018, month=7, day=31),
                'expected_expire': datetime(year=2018, month=4, day=1, tzinfo=pytz.UTC),
                'months_to_keep': None,
            },
            {
                'current_date': datetime(year=2018, month=3, day=20),
                'expected_expire': datetime(year=2017, month=12, day=1, tzinfo=pytz.UTC),
                'months_to_keep': None,
            },
            {
                'current_date': datetime(year=2018, month=7, day=1),
                'expected_expire': datetime(year=2017, month=7, day=1, tzinfo=pytz.UTC),
                'months_to_keep': 12,
            },
            {
                'current_date': datetime(year=2018, month=7, day=31),
                'expected_expire': datetime(year=2017, month=7, day=1, tzinfo=pytz.UTC),
                'months_to_keep': 12,
            },
            {
                'current_date': datetime(year=2018, month=3, day=20),
                'expected_expire': datetime(year=2016, month=3, day=1, tzinfo=pytz.UTC),
                'months_to_keep': 24,
            },
        ]
        for test_case in date_matrix:
            with patch.object(DateAccessor, 'today', return_value=test_case.get('current_date')):
                retention_policy = test_case.get('months_to_keep')
                if retention_policy:
                    remover = ExpiredDataRemover(self.schema, 'AWS', retention_policy)
                else:
                    remover = ExpiredDataRemover(self.schema, 'AWS')
                expire_date = remover._calculate_expiration_date()
                self.assertEqual(expire_date, test_case.get('expected_expire'))

    def test_remove(self):
        """Test that removes the expired data based on the retention policy."""
        remover = ExpiredDataRemover(self.schema, PROVIDER_AWS)
        removed_data = remover.remove()
        self.assertEqual(len(removed_data), 0)

    @patch('masu.processor.expired_data_remover.AWSReportDBCleaner.purge_expired_report_data')
    def test_remove_provider(self, mock_purge):
        """Test that remove is called with provider_uuid."""
        provider_uuid = self.aws_provider_uuid
        remover = ExpiredDataRemover(self.schema, PROVIDER_AWS)
        remover.remove(provider_uuid=provider_uuid)
        mock_purge.assert_called_with(simulate=False, provider_uuid=provider_uuid)
