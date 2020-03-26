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
from masu.test import MasuTestCase

# from masu.external.accounts.hierarchy.aws.aws_org_unit_crawler import AWSOrgUnitCrawler
# from masu.test.external.downloader.aws.test_aws_report_downloader import FakeSession

# A good resouce for how to much this stuff:
# https://github.com/project-koku/koku/blob/500fec9597bd6011b837d95904b3bc03cbb951aa/koku/masu/test/util/aws/test_common.py


class AWSOrgUnitCrawlerTest(MasuTestCase):
    """Test Cases for the AWSOrgUnitCrawler object."""

    def setUp(self):
        """Set up test case."""
        super().setUp()
        self.account_id = "111111111111"

    # @patch("masu.external.accounts.labels.aws.aws_account_alias.get_assume_role_session", return_value=FakeSession)
    # def test_initializer(self, session_mock):
    #     """Test AWSAccountAlias initializer."""
    #     arn = "roleArn"
    #     schema = "acct10001"
    #     accessor = AWSOrgUnitCrawler(arn, schema)
    #     # self.assertEqual(accessor._role_arn, arn)
    #     # self.assertEqual(accessor._schema, schema)
    #     # TODO: I need to figure
