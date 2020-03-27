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
"""Test the AWSOrgUnitCrawler object."""
# from unittest.mock import patch
from unittest.mock import Mock
from unittest.mock import patch

from faker import Faker

from api.models import Provider
from masu.external.accounts.hierarchy.aws.aws_org_unit_crawler import AWSOrgUnitCrawler
from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn

FAKE = Faker()
CUSTOMER_NAME = FAKE.word()
BUCKET = FAKE.word()
P_UUID = FAKE.uuid4()
P_TYPE = Provider.PROVIDER_AWS


class FakeSession:
    """
    Fake Boto Session object.

    This is here because Moto doesn't mock out the 'cur' endpoint yet. As soon
    as Moto supports 'cur', this can be removed.
    """

    @staticmethod
    def client(service):
        """Return a fake AWS Client with a report."""

        if "cur" in service:
            return Mock(**{"describe_report_definitions.return_value": "fake_report"})
        else:
            return Mock()


class AWSOrgUnitCrawlerTest(MasuTestCase):
    """Test Cases for the AWSOrgUnitCrawler object."""

    @classmethod
    def setUpClass(cls):
        """Set up shared class variables."""
        super().setUpClass()
        cls.account = {
            "authentication": fake_arn(service="iam", generate_account_id=True),
            "customer_name": CUSTOMER_NAME,
            "billing_source": BUCKET,
            "provider_type": P_TYPE,
            "schema_name": BUCKET,
            "provider_uuid": P_UUID,
        }

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def setUp(self):
        """Set up test case."""
        super().setUp()
        self.unit_crawler = AWSOrgUnitCrawler(self.account)
        # We init the class here so that we don't have to moc the
        # assume role session in each test below.
