"""Masu AWS common module tests."""
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import random
from collections import namedtuple
from datetime import datetime
from unittest import TestCase
from unittest.mock import call
from unittest.mock import Mock
from unittest.mock import patch
from unittest.mock import PropertyMock
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from dateutil.relativedelta import relativedelta
from django_tenants.utils import schema_context
from faker import Faker

from api.provider.models import Provider
from masu.config import Config
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.external import AWS_REGIONS
from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn
from masu.test.external.downloader.aws import fake_aws_account_id
from masu.test.external.downloader.aws.test_aws_report_downloader import FakeSession
from masu.util.aws import common as utils
from masu.util.common import get_path_prefix
from reporting.models import AWSAccountAlias
from reporting.models import AWSCostEntryBill

# the cn endpoints aren't supported by moto, so filter them out
AWS_REGIONS = list(filter(lambda reg: not reg.startswith("cn-"), AWS_REGIONS))
REGION = random.choice(AWS_REGIONS)

KEY = Faker()
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

DummyS3Object = namedtuple("DummyS3Object", "key")


class TestAWSUtils(MasuTestCase):
    """Tests for AWS utilities."""

    fake = Faker()

    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.account_id = fake_aws_account_id()
        self.arn = fake_arn(account_id=self.account_id, region=REGION, service="iam")
        self.credentials = {"role_arn": self.arn}
        self.aws_arn = utils.AwsArn(self.credentials)
        self.external_id = str(uuid4())
        self.credentials_with_external = {"role_arn": self.arn, "external_id": self.external_id}
        self.aws_arn_external_id = utils.AwsArn(self.credentials_with_external)

    @patch("masu.util.aws.common.boto3.client", return_value=MOCK_BOTO_CLIENT)
    def test_get_assume_role_session(self, mock_boto_client):
        """Test get_assume_role_session is successful."""
        session = utils.get_assume_role_session(self.aws_arn)
        MOCK_BOTO_CLIENT.assume_role.assert_called_with(RoleArn=str(self.aws_arn), RoleSessionName="MasuSession")
        self.assertIsInstance(session, boto3.Session)

    @patch("masu.util.aws.common.boto3.client", return_value=MOCK_BOTO_CLIENT)
    def test_get_assume_role_session_with_external_id(self, mock_boto_client):
        """Test get_assume_role_session is successful."""
        session = utils.get_assume_role_session(self.aws_arn_external_id)
        MOCK_BOTO_CLIENT.assume_role.assert_called_with(
            RoleArn=str(self.aws_arn_external_id), RoleSessionName="MasuSession", ExternalId=self.external_id
        )
        self.assertIsInstance(session, boto3.Session)

    def test_get_available_regions(self):
        regions = utils.get_available_regions()
        expected_subset = {
            "us-east-1",
            "us-east-2",
            "eu-central-1",
            "sa-east-1",
        }
        self.assertTrue(expected_subset.issubset(regions))

    def test_get_available_regions_service_name(self):
        regions = utils.get_available_regions("ec2")
        expected_subset = {
            "us-east-1",
            "us-east-2",
            "eu-central-1",
            "sa-east-1",
        }
        self.assertTrue(expected_subset.issubset(regions))

    def test_get_available_regions_bad_service_name(self):
        regions = utils.get_available_regions("not a service")
        self.assertEqual(regions, [])

    def test_month_date_range(self):
        """Test month_date_range returns correct month range."""
        today = datetime.now()
        out = utils.month_date_range(today)

        start_month = today.replace(day=1, second=1, microsecond=1)
        end_month = start_month + relativedelta(months=+1)
        timeformat = "%Y%m%d"
        expected_string = f"{start_month.strftime(timeformat)}-{end_month.strftime(timeformat)}"

        self.assertEqual(out, expected_string)

    def test_get_cur_report_definitions(self):
        """Test get_cur_report_definitions is successful."""
        session = FakeSession()
        cur_client = session.client("cur", region_name="us-east-1")
        defs = utils.get_cur_report_definitions(cur_client)
        self.assertEqual(len(defs), 1)

    def test_get_cur_report_definitions_failure(self):
        retries = 3
        max_wait_time = 1
        session = FakeSession()
        cur_client = session.client("cur")
        cur_client.describe_report_definitions = Mock(side_effect=[ClientError({}, "Testing") for i in range(retries)])

        with self.assertRaises(ClientError):
            utils.get_cur_report_definitions(cur_client, retries=retries, max_wait_time=max_wait_time)

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_get_cur_report_definitions_no_session(self, fake_session):
        """Test get_cur_report_definitions for no sessions."""
        defs = utils.get_cur_report_definitions(None, role_arn=self.aws_arn)
        self.assertEqual(len(defs), 1)

    def test_get_account_alias_from_role_arn(self):
        """Test get_account_alias_from_role_arn is functional."""
        mock_account_id = "111111111111"
        role_arn = f"arn:aws:iam::{mock_account_id}:role/CostManagement"
        credentials = {"role_arn": role_arn}
        arn = utils.AwsArn(credentials)
        mock_alias = "test-alias"

        session = Mock()
        mock_client = Mock()
        mock_client.list_account_aliases.return_value = {"AccountAliases": [mock_alias]}
        session.client.return_value = mock_client
        account_id, account_alias = utils.get_account_alias_from_role_arn(arn, self.aws_provider, session)
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
        credentials = {"role_arn": role_arn}
        arn = utils.AwsArn(credentials)

        account_id, account_alias = utils.get_account_alias_from_role_arn(arn, self.aws_provider, mock_session)
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
        credentials = {"role_arn": role_arn}
        arn = utils.AwsArn(credentials)

        account_id, account_alias = utils.get_account_alias_from_role_arn(arn, self.aws_provider)
        self.assertEqual(mock_account_id, account_id)
        self.assertEqual(mock_account_id, account_alias)

    def test_get_account_names_by_organization(self):
        """Test get_account_names_by_organization is functional."""
        mock_account_id = "111111111111"
        role_arn = f"arn:aws:iam::{mock_account_id}:role/CostManagement"
        credentials = {"role_arn": role_arn}
        arn = utils.AwsArn(credentials)
        mock_alias = "test-alias"
        expected = [{"id": mock_account_id, "name": mock_alias}]

        session = Mock()
        mock_client = Mock()
        mock_paginator = Mock()
        paginated_results = [{"Accounts": [{"Id": mock_account_id, "Name": mock_alias}]}]
        mock_paginator.paginate.return_value = paginated_results
        mock_client.get_paginator.return_value = mock_paginator
        session.client.return_value = mock_client
        accounts = utils.get_account_names_by_organization(arn, self.aws_provider, session)
        self.assertEqual(accounts, expected)

    @patch("masu.util.aws.common.get_assume_role_session")
    def test_get_account_names_by_organization_no_policy(self, mock_get_role_session):
        """Test get_account_names_by_organization gets nothing if there are no policies."""
        mock_session = mock_get_role_session.return_value
        mock_client = mock_session.client
        mock_client.return_value.get_paginator.side_effect = ClientError({}, "Error")

        mock_account_id = "111111111111"
        role_arn = f"arn:aws:iam::{mock_account_id}:role/CostManagement"
        credentials = {"role_arn": role_arn}
        arn = utils.AwsArn(credentials)

        accounts = utils.get_account_names_by_organization(arn, self.aws_provider, mock_session)
        self.assertEqual(accounts, [])

    @patch("masu.util.aws.common.get_assume_role_session")
    def test_get_account_names_by_organization_no_session(self, mock_get_role_session):
        """Test get_account_names_by_organization gets nothing if there are no sessions."""
        mock_session = mock_get_role_session.return_value
        mock_client = mock_session.client
        mock_client.return_value.get_paginator.side_effect = ClientError({}, "Error")

        mock_account_id = "111111111111"
        role_arn = f"arn:aws:iam::{mock_account_id}:role/CostManagement"
        credentials = {"role_arn": role_arn}
        arn = utils.AwsArn(credentials)

        accounts = utils.get_account_names_by_organization(arn, self.aws_provider)
        self.assertEqual(accounts, [])

    def test_update_account_aliases_no_aliases(self):
        with schema_context(self.schema):
            orig_count = AWSAccountAlias.objects.all().count()

            mock_account_id = self.account_id

            with (
                patch("masu.util.aws.common.get_account_alias_from_role_arn") as mock_get,
                patch("masu.util.aws.common.get_account_names_by_organization"),
            ):
                mock_get.return_value = (mock_account_id, mock_account_id)
                utils.update_account_aliases(self.aws_provider)

            after_count = AWSAccountAlias.objects.all().count()
            self.assertEqual(orig_count + 1, after_count)
            self.assertTrue(AWSAccountAlias.objects.get(account_id=mock_account_id, account_alias=mock_account_id))

    def test_update_account_aliases_with_aliases(self):
        with schema_context(self.schema):
            orig_count = AWSAccountAlias.objects.all().count()

            mock_account_id = self.account_id
            mock_alias = "mock_alias"

            with (
                patch("masu.util.aws.common.get_account_alias_from_role_arn") as mock_get,
                patch("masu.util.aws.common.get_account_names_by_organization"),
            ):
                mock_get.return_value = (mock_account_id, mock_alias)
                utils.update_account_aliases(self.aws_provider)

            after_count = AWSAccountAlias.objects.all().count()
            self.assertEqual(orig_count + 1, after_count)
            self.assertTrue(AWSAccountAlias.objects.get(account_id=mock_account_id, account_alias=mock_alias))

    def test_update_account_aliases_with_aliases_and_orgs(self):
        with schema_context(self.schema):
            orig_count = AWSAccountAlias.objects.all().count()

            mock_account_id = self.account_id
            mock_account_id2 = fake_aws_account_id()
            mock_alias = "mock_alias"
            mock_alias2 = "mock_alias2"

            with (
                patch("masu.util.aws.common.get_account_alias_from_role_arn") as mock_get,
                patch("masu.util.aws.common.get_account_names_by_organization") as mock_get_orgs,
            ):
                mock_get.return_value = (mock_account_id, mock_alias)
                mock_get_orgs.return_value = [{"id": mock_account_id2, "name": mock_alias2}]
                utils.update_account_aliases(self.aws_provider)

            after_count = AWSAccountAlias.objects.all().count()
            self.assertEqual(orig_count + 2, after_count)
            self.assertTrue(AWSAccountAlias.objects.get(account_id=mock_account_id, account_alias=mock_alias))
            self.assertTrue(AWSAccountAlias.objects.get(account_id=mock_account_id2, account_alias=mock_alias2))

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
            expected_bill_ids = sorted(bill_id[0] for bill_id in expected_bill_ids)
        bills = utils.get_bills_from_provider(self.aws_provider_uuid, self.schema)

        with schema_context(self.schema):
            bill_ids = sorted(bill.id for bill in bills)

        self.assertEqual(bill_ids, expected_bill_ids)

        # Try with unknown provider uuid
        bills = utils.get_bills_from_provider(self.unkown_test_provider_uuid, self.schema)
        self.assertEqual(bills, [])

    def test_get_bill_ids_from_provider_with_start_date(self):
        """Test that bill IDs are returned for an AWS provider with start date."""
        with AWSReportDBAccessor(schema=self.schema) as accessor:
            end_date = self.dh.this_month_start
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(self.aws_provider_uuid)
            with schema_context(self.schema):
                bills = bills.filter(billing_period_start__gte=end_date).all()
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(self.aws_provider_uuid, self.schema, start_date=end_date)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_get_bill_ids_from_provider_with_end_date(self):
        """Test that bill IDs are returned for an AWS provider with end date."""
        with AWSReportDBAccessor(schema=self.schema) as accessor:
            end_date = self.dh.this_month_start
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(self.aws_provider_uuid)
            with schema_context(self.schema):
                bills = bills.filter(billing_period_start__lte=start_date).all()
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(self.aws_provider_uuid, self.schema, end_date=start_date)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_get_bill_ids_from_provider_with_start_and_end_date(self):
        """Test that bill IDs are returned for an AWS provider with both dates."""
        with AWSReportDBAccessor(schema=self.schema) as accessor:
            end_date = self.dh.this_month_start
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(self.aws_provider_uuid)
            with schema_context(self.schema):
                bills = (
                    bills.filter(billing_period_start__gte=start_date).filter(billing_period_start__lte=end_date).all()
                )
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(
            self.aws_provider_uuid, self.schema, start_date=start_date, end_date=end_date
        )
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_safe_str_int_conversion_valid_int_str(self):
        """Test safe_str_int_conversion with valid integer str."""

        test_int_str_lst = ["5", "8", "13", "21"]

        for int_str in test_int_str_lst:
            expected_resp = int(int_str)
            with self.subTest(int_str=int_str):
                test_resp = utils.safe_str_int_conversion(int_str)
            self.assertIsInstance(test_resp, int)
            self.assertEqual(expected_resp, test_resp)

    def test_safe_str_int_conversion_invalid_int_str(self):
        """Test safe_str_int_conversion with invalid integer str."""

        test_invalid_int_str_lst = ["", "  ", "None", None, "invalid string"]

        for invalid_int_str in test_invalid_int_str_lst:
            with self.subTest(invalid_str=invalid_int_str):
                test_resp = utils.safe_str_int_conversion(invalid_int_str)
                self.assertIsNone(test_resp)

    def test_filter_s3_objects_less_than(self):
        """Test filter_s3_objects_less_than."""
        metadata_key = "number-of-hours-in-report"
        metadata_value = "24"

        metadata = PropertyMock(
            side_effect=[
                {metadata_key: "12", "extra": "this will not be filtered"},
                {metadata_key: "18", "extra": "this will not be filtered"},
                {metadata_key: "invalid", "extra": "this will be filtered"},
                {metadata_key: None, "extra": "this WILL be filtered"},
                {metadata_key: "25", "extra": "this WILL be filtered"},
            ]
        )

        keys = [12, 18, 25]
        with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
            type(mock_s3.return_value.Object.return_value).metadata = metadata
            filtered = utils.filter_s3_objects_less_than(
                "request_id", keys, metadata_key=metadata_key, metadata_value_check=metadata_value
            )
            self.assertListEqual(filtered, [12, 18])

    def test_filter_s3_objects_less_than_with_error(self):
        """Test filter_s3_objects_less_than with error."""

        metadata_key = "number-of-hours-in-report"
        metadata_value = "24"

        metadata = PropertyMock(
            side_effect=[{metadata_key: "18", "extra": "this will NOT be filtered"}, ClientError({}, "test")]
        )

        keys = [18, 25]
        with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
            type(mock_s3.return_value.Object.return_value).metadata = metadata
            filtered = utils.filter_s3_objects_less_than(
                "request_id", keys, metadata_key=metadata_key, metadata_value_check=metadata_value
            )
            self.assertListEqual(filtered, [])

    @patch("masu.util.aws.common.get_s3_resource")
    def test_batch_delete_s3_objects(self, mock_resource):
        """Test that delete_archived_data correctly interacts with AWS S3."""
        context = {"test_delete": "testing"}
        # Generate enough fake objects to expect calling the S3 delete api twice.
        mock_bucket = mock_resource.return_value.Bucket.return_value
        bucket_objects = [DummyS3Object(key=KEY.file_path()) for _ in range(1234)]
        keys = [bucket_object.key for bucket_object in bucket_objects]
        expected_keys = [{"Key": bucket_object.key} for bucket_object in bucket_objects]

        # Leave one object mysteriously not deleted to cover the LOG.warning use case.
        mock_bucket.objects.filter.side_effect = [bucket_objects, bucket_objects[:1]]

        with self.assertLogs("masu.util.aws.common") as captured_logs:
            utils.delete_s3_objects("request_id", keys, context)
        mock_resource.assert_called()
        mock_bucket.delete_objects.assert_has_calls(
            [call(Delete={"Objects": expected_keys[:1000]}), call(Delete={"Objects": expected_keys[1000:]})]
        )
        self.assertIn("removed batch files from s3 bucket", captured_logs.output[-1])

    def test_remove_s3_objects_not_matching_metadata(self):
        """Test remove_s3_objects_not_matching_metadata."""
        metadata_key = "manifestid"
        metadata_value = "manifest_id"
        removed = utils.delete_s3_objects_not_matching_metadata(
            "request_id", None, metadata_key=metadata_key, metadata_value_check=metadata_value
        )
        self.assertEqual(removed, [])

        start_date = self.dh.this_month_start
        s3_csv_path = get_path_prefix(
            "account", Provider.PROVIDER_AWS, "provider_uuid", start_date, Config.CSV_DATA_TYPE
        )
        expected_key = "not_matching_key"
        mock_object = Mock(metadata={metadata_key: "this will be deleted"}, key=expected_key)
        not_matching_summary = Mock()
        not_matching_summary.Object.return_value = mock_object
        not_expected_key = "matching_key"
        mock_object = Mock(metadata={metadata_key: metadata_value}, key=not_expected_key)
        matching_summary = Mock()
        matching_summary.Object.return_value = mock_object
        with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
            mock_s3.return_value.Bucket.return_value.objects.filter.return_value = [
                not_matching_summary,
                matching_summary,
            ]
            removed = utils.delete_s3_objects_not_matching_metadata(
                "request_id", s3_csv_path, metadata_key=metadata_key, metadata_value_check=metadata_value
            )
            self.assertListEqual(removed, [{"Key": expected_key}])

        with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
            client_error_object = Mock()
            client_error_object.Object.side_effect = ClientError({}, "Error")
            mock_s3.return_value.Bucket.return_value.objects.filter.return_value = [
                not_matching_summary,
                client_error_object,
            ]
            removed = utils.delete_s3_objects_not_matching_metadata(
                "request_id", s3_csv_path, metadata_key=metadata_key, metadata_value_check=metadata_value
            )
            self.assertListEqual(removed, [])

        with (
            patch("masu.util.aws.common.get_s3_objects_not_matching_metadata") as mock_get_objects,
            patch("masu.util.aws.common.get_s3_resource") as mock_s3,
        ):
            mock_s3.return_value.Object.return_value.delete.side_effect = ClientError({}, "Error")
            mock_get_objects.return_value = []
            removed = utils.delete_s3_objects_not_matching_metadata(
                "request_id", s3_csv_path, metadata_key=metadata_key, metadata_value_check=metadata_value
            )
            self.assertListEqual(removed, [])

    def test_clear_s3_files(self):
        """Test clearing s3 files."""
        metadata_key = "manifestid"
        metadata_value = "manifest_id"
        context = {"account": self.account_id, "provider_type": self.aws_provider.type}
        start_date = self.dh.this_month_start.date()
        s3_csv_path = get_path_prefix(
            self.account_id, Provider.PROVIDER_AWS, self.aws_provider_uuid, start_date, Config.CSV_DATA_TYPE
        )
        expected_key = "not_matching_key"
        mock_object = Mock(metadata={metadata_key: "this will be deleted"}, key=expected_key)
        not_matching_summary = Mock()
        not_matching_summary.Object.return_value = mock_object
        not_expected_key = "matching_key"
        mock_object = Mock(metadata={metadata_key: metadata_value}, key=not_expected_key)
        matching_summary = Mock()
        matching_summary.Object.return_value = mock_object
        with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
            mock_s3.return_value.Bucket.return_value.objects.filter.return_value = [
                not_matching_summary,
                matching_summary,
            ]
            with patch("masu.util.aws.common.delete_s3_objects") as mock_delete:
                utils.clear_s3_files(
                    s3_csv_path, self.aws_provider_uuid, start_date, "manifestid", 1, context, "requiest_id"
                )
                mock_delete.assert_called

    def test_clear_s3_files_gcp(self):
        """Test clearing s3 GCP ingress files."""
        metadata_key = "manifestid"
        metadata_value = "manifest_id"
        prov_uuid = self.gcp_provider_uuid
        prov_type = self.gcp_provider.type
        context = {"account": self.account_id, "provider_type": prov_type}
        start_date = self.dh.this_month_start
        s3_csv_path = get_path_prefix(self.account_id, "GCP", prov_uuid, start_date, Config.CSV_DATA_TYPE)
        expected_key = "not_matching_key"
        mock_object = Mock(metadata={metadata_key: "this will be deleted"}, key=expected_key)
        not_matching_summary = Mock()
        not_matching_summary.Object.return_value = mock_object
        not_expected_key = "matching_key"
        mock_object = Mock(metadata={metadata_key: metadata_value}, key=not_expected_key)
        matching_summary = Mock()
        matching_summary.Object.return_value = mock_object
        with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
            mock_s3.return_value.Bucket.return_value.objects.filter.return_value = [
                not_matching_summary,
                matching_summary,
            ]
            with patch("masu.util.aws.common.delete_s3_objects") as mock_delete:
                utils.clear_s3_files(s3_csv_path, prov_uuid, start_date, "manifestid", 1, context, "requiest_id")
                mock_delete.assert_called

    def test_remove_s3_objects_matching_metadata(self):
        """Test remove_s3_objects_matching_metadata."""
        metadata_key = "manifestid"
        metadata_value = "manifest_id"
        removed = utils.delete_s3_objects_matching_metadata(
            "request_id", None, metadata_key=metadata_key, metadata_value_check=metadata_value
        )
        self.assertEqual(removed, [])

        start_date = self.dh.this_month_start
        s3_csv_path = get_path_prefix(
            "account", Provider.PROVIDER_AWS, "provider_uuid", start_date, Config.CSV_DATA_TYPE
        )
        not_expected_key = "not_matching_key"
        mock_object = Mock(metadata={metadata_key: "this will not be deleted"}, key=not_expected_key)
        not_matching_summary = Mock()
        not_matching_summary.Object.return_value = mock_object

        expected_key = "matching_key"
        mock_object = Mock(metadata={metadata_key: metadata_value}, key=expected_key)
        matching_summary = Mock()
        matching_summary.Object.return_value = mock_object
        with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
            mock_s3.return_value.Bucket.return_value.objects.filter.return_value = [
                not_matching_summary,
                matching_summary,
            ]
            removed = utils.delete_s3_objects_matching_metadata(
                "request_id", s3_csv_path, metadata_key=metadata_key, metadata_value_check=metadata_value
            )
            self.assertListEqual(removed, [{"Key": expected_key}])

        with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
            client_error_object = Mock()
            client_error_object.Object.side_effect = ClientError({}, "Error")
            mock_s3.return_value.Bucket.return_value.objects.filter.return_value = [
                not_matching_summary,
                client_error_object,
            ]
            removed = utils.delete_s3_objects_matching_metadata(
                "request_id", s3_csv_path, metadata_key=metadata_key, metadata_value_check=metadata_value
            )
            self.assertListEqual(removed, [])

        with (
            patch("masu.util.aws.common.get_s3_objects_matching_metadata") as mock_get_objects,
            patch("masu.util.aws.common.get_s3_resource") as mock_s3,
        ):
            mock_s3.return_value.Object.return_value.delete.side_effect = ClientError({}, "Error")
            mock_get_objects.return_value = []
            removed = utils.delete_s3_objects_matching_metadata(
                "request_id", s3_csv_path, metadata_key=metadata_key, metadata_value_check=metadata_value
            )
            self.assertListEqual(removed, [])

    def test_copy_data_to_s3_bucket(self):
        """Test copy_data_to_s3_bucket."""
        with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
            upload = utils.copy_data_to_s3_bucket("request_id", "path", "filename", "data", "manifest_id")
            self.assertIsNotNone(upload)

        with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
            mock_s3.return_value.Object.return_value.upload_fileobj.side_effect = ClientError({}, "Error")
            with self.assertRaises(utils.UploadError):
                utils.copy_data_to_s3_bucket("request_id", "path", "filename", "data", "manifest_id")

    @patch("masu.util.aws.common.get_s3_resource")
    def test_get_or_clear_daily_s3_by_date(self, mock_resource):
        """test getting daily archive start date"""
        start_date = self.dh.this_month_start.replace(year=2019, month=7, day=1).date()
        end_date = self.dh.this_month_start.replace(year=2019, month=7, day=2).date()
        with patch(
            "masu.database.report_manifest_db_accessor.ReportManifestDBAccessor.get_manifest_daily_start_date",
            return_value=None,
        ):
            result = utils.get_or_clear_daily_s3_by_date(
                "None",
                "provider_uuid",
                start_date,
                end_date,
                1,
                {"account": "test", "provider_type": "AWS"},
                "request_id",
            )
            self.assertEqual(result, start_date)


class AwsArnTest(TestCase):
    """AwnArn class test case."""

    fake = Faker()

    def test_parse_arn_with_region_and_account(self):
        """Assert successful account ID parsing from a well-formed ARN."""
        mock_account_id = fake_aws_account_id()
        mock_arn = fake_arn(account_id=mock_account_id, region="test-region-1")
        credentials = {"role_arn": mock_arn}

        arn_object = utils.AwsArn(credentials)

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
        credentials = {"role_arn": mock_arn}
        arn_object = utils.AwsArn(credentials)

        region = arn_object.region
        self.assertEqual(region, None)

        account_id = arn_object.account_id
        self.assertEqual(account_id, None)

    def test_parse_arn_with_slash_separator(self):
        """Assert successful ARN parsing with a slash separator."""
        mock_arn = fake_arn(resource_separator="/")
        credentials = {"role_arn": mock_arn}
        arn_object = utils.AwsArn(credentials)

        resource_type = arn_object.resource_type
        self.assertIsNotNone(resource_type)

        resource_separator = arn_object.resource_separator
        self.assertEqual(resource_separator, "/")

        resource = arn_object.resource
        self.assertIsNotNone(resource)

    def test_parse_arn_with_custom_resource_type(self):
        """Assert valid ARN when resource type contains extra characters."""
        mock_arn = "arn:aws:fakeserv:test-reg-1:012345678901:test.res type:foo"
        credentials = {"role_arn": mock_arn}
        arn_object = utils.AwsArn(credentials)

        resource_type = arn_object.resource_type
        self.assertIsNotNone(resource_type)

        resource = arn_object.resource
        self.assertIsNotNone(resource)

    def test_error_from_invalid_arn(self):
        """Assert error in account ID parsing from a badly-formed ARN."""
        mock_arn = self.fake.text()
        credentials = {"role_arn": mock_arn}
        with self.assertLogs("masu.util.aws", level="WARNING") as logger:
            utils.AwsArn(credentials)
            self.assertTrue(any(f"Invalid ARN: {mock_arn}" in log for log in logger.output))

    def test_arn_and_external_id(self):
        """Assert that the AwsArn processes an ExternalId."""
        mock_arn = fake_arn()
        credentials = {"role_arn": mock_arn}
        arn = utils.AwsArn(credentials)
        self.assertIsNone(arn.external_id)

        external_id = "1234567"
        credentials = {"role_arn": mock_arn, "external_id": external_id}
        arn = utils.AwsArn(credentials)
        self.assertIsNotNone(arn.external_id)
