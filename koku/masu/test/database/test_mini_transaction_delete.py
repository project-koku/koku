#
# Copyright 2021 Red Hat, Inc.
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
"""Test the mini_transaction_delete utility function."""
import os
from unittest.mock import patch

from api.provider.models import Sources
from koku.env import ENVIRONMENT
from masu.database.koku_database_access import mini_transaction_delete
from masu.test import MasuTestCase


class MiniTransactionDeleteTest(MasuTestCase):
    """Test Cases for the ReportSchema object."""

    def test_mini_transaction_delete_base(self):
        for id in range(100, 110):
            Sources.objects.create(source_id=-id, offset=1, authentication={})
        src_query = Sources.objects.filter(source_id__lt=-99)
        start_count = src_query.count()
        self.assertEqual(start_count, 10)
        del_count, remainder = mini_transaction_delete(src_query)
        end_count = src_query.count()
        self.assertEqual(del_count, start_count)
        self.assertEqual(remainder, 0)
        self.assertEqual(end_count, 0)

    @patch("masu.database.koku_database_access.mtd_check_remainder")
    def test_mini_transaction_delete_remainder(self, remainder_check):
        remainder_check.return_value = 1
        del_rec_lim_key = "DELETE_CYCLE_RECORD_LIMIT"
        del_cycle_try_key = "DELETE_CYCLE_MAX_RETRY"
        dcrl = ENVIRONMENT.get_value(del_rec_lim_key, default=None)
        dcmr = ENVIRONMENT.get_value(del_cycle_try_key, default=None)
        os.environ[del_rec_lim_key] = "3"
        os.environ[del_cycle_try_key] = "1"

        for id in range(110, 120):
            Sources.objects.create(source_id=-id, offset=1, authentication={})
        src_query = Sources.objects.filter(source_id__lt=-109)

        start_count = src_query.count()
        del_count, remainder = mini_transaction_delete(src_query)
        end_count = src_query.count()

        if dcrl is None:
            del os.environ[del_rec_lim_key]
        else:
            os.environ[del_rec_lim_key] = dcrl
        if dcmr is None:
            del os.environ[del_cycle_try_key]
        else:
            os.environ[del_cycle_try_key] = dcmr

        self.assertEqual(start_count, 10)
        self.assertEqual(remainder, 1)
        self.assertEqual(end_count, 0)  # Based on how this test is constructed, the records would be deleted anyway.
