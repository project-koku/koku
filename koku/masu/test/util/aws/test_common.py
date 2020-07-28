"""Masu AWS common module tests."""
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
import random
from datetime import datetime
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch

import boto3
from botocore.exceptions import ClientError
from dateutil.relativedelta import relativedelta
from faker import Faker
from tenant_schemas.utils import schema_context

from masu.config import Config
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external import AWS_REGIONS
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn
from masu.test.external.downloader.aws import fake_aws_account_id
from masu.test.external.downloader.aws.test_aws_report_downloader import FakeSession
from masu.util.aws import common as utils
from masu.util.common import get_path_prefix
from reporting.models import AWSCostEntryBill

# the cn endpoints aren't supported by moto, so filter them out
AWS_REGIONS = list(filter(lambda reg: not reg.startswith("cn-"), AWS_REGIONS))
REGION = random.choice(AWS_REGIONS)

NAME = Faker().word()
BUCKET = Faker().word()
PREFIX = Faker().word()
FORMAT = random.choice(["text", "csv"])
COMPRESSION = random.choice(["ZIP", "GZIP"])
REPORT_DEFS = [
    {
        "ReportName": NAME,
        "TimeUnit": "DAILY",
        "Format": FORMAT,
        "Compression": COMPRESSION,
        "S3Bucket": BUCKET,
        "S3Prefix": PREFIX,
        "S3Region": REGION,
    }
]
MOCK_BOTO_CLIENT = Mock()
response = {
    "Credentials": {
        "AccessKeyId": "mock_access_key_id",
        "SecretAccessKey": "mock_secret_access_key",
        "SessionToken": "mock_session_token",
    }
}
MOCK_BOTO_CLIENT.assume_role.return_value = response


class TestAWSUtils(MasuTestCase):
    """Tests for AWS utilities."""

    fake = Faker()

    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.account_id = fake_aws_account_id()
        self.arn = fake_arn(account_id=self.account_id, region=REGION, service="iam")

    @patch("masu.util.aws.common.boto3.client", return_value=MOCK_BOTO_CLIENT)
    def test_get_assume_role_session(self, mock_boto_client):
        """Test get_assume_role_session is successful."""
        session = utils.get_assume_role_session(self.arn)
        self.assertIsInstance(session, boto3.Session)

    def test_month_date_range(self):
        """Test month_date_range returns correct month range."""
        today = datetime.now()
        out = utils.month_date_range(today)

        start_month = today.replace(day=1, second=1, microsecond=1)
        end_month = start_month + relativedelta(months=+1)
        timeformat = "%Y%m%d"
        expected_string = "{}-{}".format(start_month.strftime(timeformat), end_month.strftime(timeformat))

        self.assertEqual(out, expected_string)

    @patch("masu.util.aws.common.get_cur_report_definitions", return_value=REPORT_DEFS)
    def test_cur_report_names_in_bucket(self, fake_report_defs):
        """Test get_cur_report_names_in_bucket is successful."""
        session = Mock()
        report_names = utils.get_cur_report_names_in_bucket(self.account_id, BUCKET, session)
        self.assertIn(NAME, report_names)

    @patch("masu.util.aws.common.get_cur_report_definitions", return_value=REPORT_DEFS)
    def test_cur_report_names_in_bucket_malformed(self, fake_report_defs):
        """Test get_cur_report_names_in_bucket fails for bad bucket name."""
        session = Mock()
        report_names = utils.get_cur_report_names_in_bucket(self.account_id, "wrong-bucket", session)
        self.assertNotIn(NAME, report_names)

    def test_get_cur_report_definitions(self):
        """Test get_cur_report_definitions is successful."""
        session = FakeSession()
        defs = utils.get_cur_report_definitions(self.arn, session)
        self.assertEqual(len(defs), 1)

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_get_cur_report_definitions_no_session(self, fake_session):
        """Test get_cur_report_definitions for no sessions."""
        defs = utils.get_cur_report_definitions(self.arn)
        self.assertEqual(len(defs), 1)

    def test_get_account_alias_from_role_arn(self):
        """Test get_account_alias_from_role_arn is functional."""
        mock_account_id = "111111111111"
        role_arn = f"arn:aws:iam::{mock_account_id}:role/CostManagement"
        mock_alias = "test-alias"

        session = Mock()
        mock_client = Mock()
        mock_client.list_account_aliases.return_value = {"AccountAliases": [mock_alias]}
        session.client.return_value = mock_client
        account_id, account_alias = utils.get_account_alias_from_role_arn(role_arn, session)
        self.assertEqual(mock_account_id, account_id)
        self.assertEqual(mock_alias, account_alias)

    @patch("masu.util.aws.common.get_assume_role_session")
    def test_get_account_alias_from_role_arn_no_policy(self, mock_get_role_session):
        """Test get_account_alias_from_role_arn is functional when there are no policies."""
        mock_session = mock_get_role_session.return_value
        mock_client = mock_session.client
        mock_client.return_value.list_account_aliases.side_effect = ClientError({}, "Error")

        mock_account_id = "111111111111"
        role_arn = f"arn:aws:iam::{mock_account_id}:role/CostManagement"

        account_id, account_alias = utils.get_account_alias_from_role_arn(role_arn, mock_session)
        self.assertEqual(mock_account_id, account_id)
        self.assertEqual(mock_account_id, account_alias)

    @patch("masu.util.aws.common.get_assume_role_session")
    def test_get_account_alias_from_role_arn_no_session(self, mock_get_role_session):
        """Test get_account_alias_from_role_arn is functional."""
        mock_session = mock_get_role_session.return_value
        mock_client = mock_session.client
        mock_client.return_value.list_account_aliases.side_effect = ClientError({}, "Error")

        mock_account_id = "111111111111"
        role_arn = f"arn:aws:iam::{mock_account_id}:role/CostManagement"

        account_id, account_alias = utils.get_account_alias_from_role_arn(role_arn)
        self.assertEqual(mock_account_id, account_id)
        self.assertEqual(mock_account_id, account_alias)

    def test_get_account_names_by_organization(self):
        """Test get_account_names_by_organization is functional."""
        mock_account_id = "111111111111"
        role_arn = f"arn:aws:iam::{mock_account_id}:role/CostManagement"
        mock_alias = "test-alias"
        expected = [{"id": mock_account_id, "name": mock_alias}]

        session = Mock()
        mock_client = Mock()
        mock_paginator = Mock()
        paginated_results = [{"Accounts": [{"Id": mock_account_id, "Name": mock_alias}]}]
        mock_paginator.paginate.return_value = paginated_results
        mock_client.get_paginator.return_value = mock_paginator
        session.client.return_value = mock_client
        accounts = utils.get_account_names_by_organization(role_arn, session)
        self.assertEqual(accounts, expected)

    @patch("masu.util.aws.common.get_assume_role_session")
    def test_get_account_names_by_organization_no_policy(self, mock_get_role_session):
        """Test get_account_names_by_organization gets nothing if there are no policies."""
        mock_session = mock_get_role_session.return_value
        mock_client = mock_session.client
        mock_client.return_value.get_paginator.side_effect = ClientError({}, "Error")

        mock_account_id = "111111111111"
        role_arn = f"arn:aws:iam::{mock_account_id}:role/CostManagement"

        accounts = utils.get_account_names_by_organization(role_arn, mock_session)
        self.assertEqual(accounts, [])

    @patch("masu.util.aws.common.get_assume_role_session")
    def test_get_account_names_by_organization_no_session(self, mock_get_role_session):
        """Test get_account_names_by_organization gets nothing if there are no sessions."""
        mock_session = mock_get_role_session.return_value
        mock_client = mock_session.client
        mock_client.return_value.get_paginator.side_effect = ClientError({}, "Error")

        mock_account_id = "111111111111"
        role_arn = f"arn:aws:iam::{mock_account_id}:role/CostManagement"

        accounts = utils.get_account_names_by_organization(role_arn)
        self.assertEqual(accounts, [])

    def test_get_assembly_id_from_cur_key(self):
        """Test get_assembly_id_from_cur_key is successful."""
        expected_assembly_id = "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"
        input_key = f"/koku/20180701-20180801/{expected_assembly_id}/koku-1.csv.gz"
        assembly_id = utils.get_assembly_id_from_cur_key(input_key)
        self.assertEqual(expected_assembly_id, assembly_id)

    def test_get_local_file_name_with_assembly(self):
        """Test get_local_file_name is successful with assembly ID."""
        expected_assembly_id = "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"
        input_key = f"/koku/20180701-20180801/{expected_assembly_id}/koku-1.csv.gz"
        expected_local_file = f"{expected_assembly_id}-koku-1.csv.gz"
        local_file = utils.get_local_file_name(input_key)
        self.assertEqual(expected_local_file, local_file)

    def test_get_local_file_name_no_assembly(self):
        """Test get_local_file_name is successful with no assembly ID."""
        input_key = "/koku/20180701-20180801/koku-Manifest.json"
        expected_local_file = "koku-Manifest.json"
        local_file = utils.get_local_file_name(input_key)
        self.assertEqual(expected_local_file, local_file)

    def test_get_bill_ids_from_provider(self):
        """Test that bill IDs are returned for an AWS provider."""
        with schema_context(self.schema):
            expected_bill_ids = AWSCostEntryBill.objects.values_list("id")
            expected_bill_ids = sorted([bill_id[0] for bill_id in expected_bill_ids])
        bills = utils.get_bills_from_provider(self.aws_provider_uuid, self.schema)

        with schema_context(self.schema):
            bill_ids = sorted([bill.id for bill in bills])

        self.assertEqual(bill_ids, expected_bill_ids)

        # Try with unknown provider uuid
        bills = utils.get_bills_from_provider(self.unkown_test_provider_uuid, self.schema)
        self.assertEqual(bills, [])

    def test_get_bill_ids_from_provider_with_start_date(self):
        """Test that bill IDs are returned for an AWS provider with start date."""
        date_accessor = DateAccessor()

        with ProviderDBAccessor(provider_uuid=self.aws_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with AWSReportDBAccessor(schema=self.schema) as accessor:

            end_date = date_accessor.today_with_timezone("utc").replace(day=1)
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            with schema_context(self.schema):
                bills = bills.filter(billing_period_start__gte=end_date.date()).all()
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(self.aws_provider_uuid, self.schema, start_date=end_date)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_get_bill_ids_from_provider_with_end_date(self):
        """Test that bill IDs are returned for an AWS provider with end date."""
        date_accessor = DateAccessor()

        with ProviderDBAccessor(provider_uuid=self.aws_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with AWSReportDBAccessor(schema=self.schema) as accessor:

            end_date = date_accessor.today_with_timezone("utc").replace(day=1)
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            with schema_context(self.schema):
                bills = bills.filter(billing_period_start__lte=start_date.date()).all()
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(self.aws_provider_uuid, self.schema, end_date=start_date)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_get_bill_ids_from_provider_with_start_and_end_date(self):
        """Test that bill IDs are returned for an AWS provider with both dates."""
        date_accessor = DateAccessor()

        with ProviderDBAccessor(provider_uuid=self.aws_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with AWSReportDBAccessor(schema=self.schema) as accessor:

            end_date = date_accessor.today_with_timezone("utc").replace(day=1)
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            with schema_context(self.schema):
                bills = (
                    bills.filter(billing_period_start__gte=start_date.date())
                    .filter(billing_period_start__lte=end_date.date())
                    .all()
                )
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(
            self.aws_provider_uuid, self.schema, start_date=start_date, end_date=end_date
        )
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_remove_files_not_in_set_from_s3_bucket(self):
        """Test remove_files_not_in_set_from_s3_bucket."""
        removed = utils.remove_files_not_in_set_from_s3_bucket("request_id", None, "manifest_id")
        self.assertEqual(removed, [])

        date_accessor = DateAccessor()
        start_date = date_accessor.today_with_timezone("utc").replace(day=1)
        s3_csv_path = get_path_prefix("account", "provider_uuid", start_date, Config.CSV_DATA_TYPE)
        expected_key = "removed_key"
        mock_object = Mock(metadata={}, key=expected_key)
        mock_summary = Mock()
        mock_summary.Object.return_value = mock_object
        with patch("masu.util.aws.common.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
                mock_s3.return_value.Bucket.return_value.objects.filter.return_value = [mock_summary]
                removed = utils.remove_files_not_in_set_from_s3_bucket("request_id", s3_csv_path, "manifest_id")
                self.assertEqual(removed, [expected_key])

        with patch("masu.util.aws.common.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
                mock_s3.side_effect = ClientError({}, "Error")
                removed = utils.remove_files_not_in_set_from_s3_bucket("request_id", s3_csv_path, "manifest_id")
                self.assertEqual(removed, [])

    def test_copy_data_to_s3_bucket(self):
        """Test copy_data_to_s3_bucket."""
        upload = utils.copy_data_to_s3_bucket("request_id", "path", "filename", "data", "manifest_id")
        self.assertEqual(upload, None)

        with patch("masu.util.aws.common.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
                upload = utils.copy_data_to_s3_bucket("request_id", "path", "filename", "data", "manifest_id")
                self.assertIsNotNone(upload)

        with patch("masu.util.aws.common.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
                mock_s3.side_effect = ClientError({}, "Error")
                upload = utils.copy_data_to_s3_bucket("request_id", "path", "filename", "data", "manifest_id")
                self.assertEqual(upload, None)

    def test_get_file_keys_from_s3_with_manifest_id(self):
        """Test get_file_keys_from_s3_with_manifest_id."""
        files = utils.get_file_keys_from_s3_with_manifest_id("request_id", "s3_path", "manifest_id")
        self.assertEqual(files, [])

        with patch("masu.util.aws.common.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
                files = utils.get_file_keys_from_s3_with_manifest_id("request_id", None, "manifest_id")
                self.assertEqual(files, [])

        with patch("masu.util.aws.common.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
                mock_s3.side_effect = ClientError({}, "Error")
                files = utils.get_file_keys_from_s3_with_manifest_id("request_id", "s3_path", "manifest_id")
                self.assertEqual(files, [])

    def test_convert_csv_to_parquet(self):
        """Test convert_csv_to_parquet."""
        result = utils.convert_csv_to_parquet(
            "request_id", None, "s3_parquet_path", "local_path", "manifest_id", "csv_filename"
        )
        self.assertFalse(result)

        result = utils.convert_csv_to_parquet(
            "request_id", "s3_csv_path", "s3_parquet_path", "local_path", "manifest_id", "csv_filename"
        )
        self.assertFalse(result)

        with patch("masu.util.aws.common.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
                with patch("masu.util.aws.common.shutil.rmtree"):
                    with patch("masu.util.aws.common.Path"):
                        mock_s3.side_effect = ClientError({}, "Error")
                        result = utils.convert_csv_to_parquet(
                            "request_id",
                            "s3_csv_path",
                            "s3_parquet_path",
                            "local_path",
                            "manifest_id",
                            "csv_filename.csv",
                        )
                        self.assertFalse(result)

        with patch("masu.util.aws.common.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.util.aws.common.get_s3_resource"):
                with patch("masu.util.aws.common.shutil.rmtree"):
                    with patch("masu.util.aws.common.Path"):
                        result = utils.convert_csv_to_parquet(
                            "request_id",
                            "s3_csv_path",
                            "s3_parquet_path",
                            "local_path",
                            "manifest_id",
                            "csv_filename.csv.gz",
                        )
                        self.assertFalse(result)

        with patch("masu.util.aws.common.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.util.aws.common.get_s3_resource"):
                with patch("masu.util.aws.common.shutil.rmtree"):
                    with patch("masu.util.aws.common.Path"):
                        with patch("masu.util.aws.common.pd"):
                            with patch("masu.util.aws.common.open") as mock_open:
                                mock_open.side_effect = ValueError()
                                result = utils.convert_csv_to_parquet(
                                    "request_id",
                                    "s3_csv_path",
                                    "s3_parquet_path",
                                    "local_path",
                                    "manifest_id",
                                    "csv_filename.csv.gz",
                                )
                                self.assertFalse(result)

        with patch("masu.util.aws.common.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.util.aws.common.get_s3_resource"):
                with patch("masu.util.aws.common.Path"):
                    with patch("masu.util.aws.common.shutil.rmtree"):
                        with patch("masu.util.aws.common.pd"):
                            with patch("masu.util.aws.common.open"):
                                with patch("masu.util.aws.common.BytesIO"):
                                    with patch("masu.util.aws.common.copy_data_to_s3_bucket"):
                                        result = utils.convert_csv_to_parquet(
                                            "request_id",
                                            "s3_csv_path",
                                            "s3_parquet_path",
                                            "local_path",
                                            "manifest_id",
                                            "csv_filename.csv.gz",
                                        )
                                        self.assertTrue(result)


class AwsArnTest(TestCase):
    """AwnArn class test case."""

    fake = Faker()

    def test_parse_arn_with_region_and_account(self):
        """Assert successful account ID parsing from a well-formed ARN."""
        mock_account_id = fake_aws_account_id()
        mock_arn = fake_arn(account_id=mock_account_id, region="test-region-1")

        arn_object = utils.AwsArn(mock_arn)

        partition = arn_object.partition
        self.assertIsNotNone(partition)

        service = arn_object.service
        self.assertIsNotNone(service)

        region = arn_object.region
        self.assertIsNotNone(region)

        account_id = arn_object.account_id
        self.assertIsNotNone(account_id)

        resource_type = arn_object.resource_type
        self.assertIsNotNone(resource_type)

        resource_separator = arn_object.resource_separator
        self.assertIsNotNone(resource_separator)

        resource = arn_object.resource
        self.assertIsNotNone(resource)

        reconstructed_arn = (
            "arn:"
            + partition
            + ":"
            + service
            + ":"
            + region
            + ":"
            + account_id
            + ":"
            + resource_type
            + resource_separator
            + resource
        )

        self.assertEqual(mock_account_id, account_id)
        self.assertEqual(mock_arn, reconstructed_arn)

    def test_parse_arn_without_region_or_account(self):
        """Assert successful ARN parsing without a region or an account id."""
        mock_arn = fake_arn()
        arn_object = utils.AwsArn(mock_arn)

        region = arn_object.region
        self.assertEqual(region, None)

        account_id = arn_object.account_id
        self.assertEqual(account_id, None)

    def test_parse_arn_with_slash_separator(self):
        """Assert successful ARN parsing with a slash separator."""
        mock_arn = fake_arn(resource_separator="/")
        arn_object = utils.AwsArn(mock_arn)

        resource_type = arn_object.resource_type
        self.assertIsNotNone(resource_type)

        resource_separator = arn_object.resource_separator
        self.assertEqual(resource_separator, "/")

        resource = arn_object.resource
        self.assertIsNotNone(resource)

    def test_parse_arn_with_custom_resource_type(self):
        """Assert valid ARN when resource type contains extra characters."""
        mock_arn = "arn:aws:fakeserv:test-reg-1:012345678901:test.res type:foo"
        arn_object = utils.AwsArn(mock_arn)

        resource_type = arn_object.resource_type
        self.assertIsNotNone(resource_type)

        resource = arn_object.resource
        self.assertIsNotNone(resource)

    def test_error_from_invalid_arn(self):
        """Assert error in account ID parsing from a badly-formed ARN."""
        mock_arn = self.fake.text()
        with self.assertRaises(SyntaxError):
            utils.AwsArn(mock_arn)
