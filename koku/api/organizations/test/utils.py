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
from tenant_schemas.utils import schema_context

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
        self.schema = schema_name
        self.account = {
            "authentication": fake_arn(service="iam", generate_account_id=True),
            "customer_name": CUSTOMER_NAME,
            "billing_source": BUCKET,
            "provider_type": P_TYPE,
            "schema_name": self.schema,
            "provider_uuid": P_UUID,
        }
        self.data_list = [
            {"ou": {"Name": "root", "Id": "r-id"}, "path": "r-id", "level": 0, "account": None},
            {"ou": {"Name": "big-ou", "Id": "big-ou0"}, "path": "r-id&big-ou0", "level": 1, "account": None},
            {
                "ou": {"Name": "big-ou", "Id": "big-ou0"},
                "path": "r-id&big-ou0",
                "level": 1,
                "account": {"Id": "0", "Name": "Zero"},
            },
            {
                "ou": {"Name": "big-ou", "Id": "big-ou0"},
                "path": "r-id&big-ou0",
                "level": 1,
                "account": {"Id": "1", "Name": "One"},
            },
            {"ou": {"Name": "sub-ou", "Id": "sub-ou0"}, "path": "r-id&big-ou0&sub-ou0", "level": 2, "account": None},
        ]

    def _generate_results_metadata(self):
        """Generate metadata for data list for testing confirmation purposes"""
        metadata = dict()
        for data in self.data_list:
            data_key = data["ou"]["Id"]
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
        unit_crawler._structure_yesterday = {}
        unit_crawler._account_alias_map = {}
        for insert_data in self.data_list:
            created_date = insert_data.get("created", None)
            deleted_date = insert_data.get("deleted", None)
            node = unit_crawler._save_aws_org_method(
                insert_data["ou"], insert_data["path"], insert_data["level"], insert_data["account"]
            )
            with schema_context(self.schema):
                if created_date is not None:
                    print(node)
                    node.created_timestamp = created_date
                    node.save()
                if deleted_date is not None:
                    print(node)
                    node.deleted_timestamp = deleted_date
                    node.save()
        metadata = self._generate_results_metadata()
        return metadata
