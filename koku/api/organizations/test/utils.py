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
"""Test utils for the organizaitons."""
from faker import Faker

from api.models import Provider
from masu.external.accounts.hierarchy.aws.aws_org_unit_crawler import AWSOrgUnitCrawler
from masu.test.external.downloader.aws import fake_arn


FAKE = Faker()
CUSTOMER_NAME = FAKE.word()
BUCKET = FAKE.word()
P_UUID = FAKE.uuid4()
P_TYPE = Provider.PROVIDER_AWS
GEN_NUM_ACT_DEFAULT = 2


class GenerateOrgTestData:
    """Utils to generate test data for organizations."""

    def __init__(self, schema_name):
        self.account = {
            "authentication": fake_arn(service="iam", generate_account_id=True),
            "customer_name": CUSTOMER_NAME,
            "billing_source": BUCKET,
            "provider_type": P_TYPE,
            "schema_name": schema_name,
            "provider_uuid": P_UUID,
        }
        self.data_list = [
            {"name": "root", "id": "r-id", "path": "r-id"},
            {"name": "big_ou", "id": "big_ou0", "path": "r-id&big_ou0"},
            {"name": "big_ou", "id": "big_ou0", "path": "r-id&big_ou0", "account": "0"},
            {"name": "big_ou", "id": "big_ou0", "path": "r-id&big_ou0", "account": "1"},
            {"name": "sub_ou", "id": "sub_ou0", "path": "r-id&big_ou0&sub_ou0"},
        ]

    def _generate_results_metadata(self):
        """Generate metadata for data list for testing confirmation purposes"""
        metadata = dict()
        for data in self.data_list:
            data_key = data["id"]
            id_exist = metadata.get(data_key)
            if not id_exist:
                metadata[data_key] = {"data": [], "account_num": 0}
            if data.get("account"):
                cur_num = metadata[data_key]["account_num"]
                metadata[data_key]["account_num"] = cur_num + 1
            metadata[data_key]["data"].append(data)
        return metadata

    def insert_data(self):
        """Insert data list into the database and returns metadata for testing purposes."""
        unit_crawler = AWSOrgUnitCrawler(self.account)
        for insert_data in self.data_list:
            if insert_data.get("account"):
                unit_crawler._save_aws_org_method(
                    insert_data["name"], insert_data["id"], insert_data["path"], insert_data["account"]
                )
            else:
                unit_crawler._save_aws_org_method(insert_data["name"], insert_data["id"], insert_data["path"])
        metadata = self._generate_results_metadata()
        return metadata
