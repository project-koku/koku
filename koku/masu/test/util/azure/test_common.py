"""Masu AWS common module tests."""
#
# Copyright 2020 Red Hat, Inc.
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
import pandas as pd

from api.utils import DateHelper
from masu.test import MasuTestCase
from masu.util.azure.common import azure_date_converter
from masu.util.azure.common import azure_json_converter
from masu.util.azure.common import azure_post_processor
from reporting.provider.azure.models import PRESTO_COLUMNS


class TestAzureUtils(MasuTestCase):
    """Tests for Azure utilities."""

    def test_azure_date_converter(self):
        """Test that we convert the new Azure date format."""
        today = DateHelper().today
        old_azure_format = today.strftime("%Y-%m-%d")
        new_azure_format = today.strftime("%m/%d/%Y")

        self.assertEqual(azure_date_converter(old_azure_format).date(), today.date())
        self.assertEqual(azure_date_converter(new_azure_format).date(), today.date())

    def test_azure_json_converter(self):
        """Test that we successfully process both Azure JSON formats."""

        first_format = '{  "ResourceType": "Bandwidth",  "DataCenter": "BN3",  "NetworkBucket": "BY1"}'
        first_expected = '{"ResourceType": "Bandwidth", "DataCenter": "BN3", "NetworkBucket": "BY1"}'

        self.assertEqual(azure_json_converter(first_format), first_expected)

        second_format = '{"project":"p1","cost":"management"}'
        second_expected = '{"project": "p1", "cost": "management"}'

        self.assertEqual(azure_json_converter(second_format), second_expected)

        third_format = '"created-by": "kubernetes-azure","kubernetes.io-created-for-pv-name": "pvc-123"'
        third_expected = '{"created-by": "kubernetes-azure", "kubernetes.io-created-for-pv-name": "pvc-123"}'

        self.assertEqual(azure_json_converter(third_format), third_expected)

    def test_azure_post_processor(self):
        """Test that we end up with a dataframe with the correct columns."""

        data = {"MeterSubCategory": [1]}
        df = pd.DataFrame(data)
        result = azure_post_processor(df)

        columns = list(result)

        expected_columns = sorted(
            [col.replace("-", "_").replace("/", "_").replace(":", "_").lower() for col in PRESTO_COLUMNS]
        )

        self.assertEqual(columns, expected_columns)
