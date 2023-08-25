"""Masu AWS common module tests."""
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import random
from datetime import datetime
from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import mock_open
from unittest.mock import patch
from unittest.mock import PropertyMock
from uuid import uuid4

import boto3
import numpy as np
import pandas as pd
from botocore.exceptions import ClientError
from dateutil.relativedelta import relativedelta
from django_tenants.utils import schema_context
from faker import Faker

from api.provider.models import Provider
from api.utils import DateHelper
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
        account_id, account_alias = utils.get_account_alias_from_role_arn(arn, session)
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

        account_id, account_alias = utils.get_account_alias_from_role_arn(arn, mock_session)
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

        account_id, account_alias = utils.get_account_alias_from_role_arn(arn)
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
        accounts = utils.get_account_names_by_organization(arn, session)
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

        accounts = utils.get_account_names_by_organization(arn, mock_session)
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

        accounts = utils.get_account_names_by_organization(arn)
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
        date_accessor = DateAccessor()

        with ProviderDBAccessor(provider_uuid=self.aws_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with AWSReportDBAccessor(schema=self.schema) as accessor:

            end_date = date_accessor.today_with_timezone("UTC").replace(day=1)
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

            end_date = date_accessor.today_with_timezone("UTC").replace(day=1)
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

            end_date = date_accessor.today_with_timezone("UTC").replace(day=1)
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

    def test_filter_s3_objects_less_than(self):
        """Test filter_s3_objects_less_than."""
        metadata_key = "number-of-hours-in-report"
        metadata_value = "24"

        metadata = PropertyMock(
            side_effect=[
                {metadata_key: "18", "extra": "this will NOT be filtered"},
                {metadata_key: "25", "extra": "this WILL be filtered"},
            ]
        )

        keys = [18, 25]
        with patch("masu.util.aws.common.get_s3_resource") as mock_s3:
            type(mock_s3.return_value.Object.return_value).metadata = metadata
            filtered = utils.filter_s3_objects_less_than(
                "request_id", keys, metadata_key=metadata_key, metadata_value_check=metadata_value
            )
            self.assertListEqual(filtered, [18])

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

    def test_remove_s3_objects_not_matching_metadata(self):
        """Test remove_s3_objects_not_matching_metadata."""
        metadata_key = "manifestid"
        metadata_value = "manifest_id"
        removed = utils.delete_s3_objects_not_matching_metadata(
            "request_id", None, metadata_key=metadata_key, metadata_value_check=metadata_value
        )
        self.assertEqual(removed, [])

        date_accessor = DateAccessor()
        start_date = date_accessor.today_with_timezone("UTC").replace(day=1)
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
            self.assertListEqual(removed, [expected_key])

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

        with patch("masu.util.aws.common.get_s3_objects_not_matching_metadata") as mock_get_objects, patch(
            "masu.util.aws.common.get_s3_resource"
        ) as mock_s3:
            mock_s3.return_value.Object.return_value.delete.side_effect = ClientError({}, "Error")
            mock_get_objects.return_value = [expected_key]
            removed = utils.delete_s3_objects_not_matching_metadata(
                "request_id", s3_csv_path, metadata_key=metadata_key, metadata_value_check=metadata_value
            )
            self.assertListEqual(removed, [])

    def test_remove_s3_objects_matching_metadata(self):
        """Test remove_s3_objects_matching_metadata."""
        metadata_key = "manifestid"
        metadata_value = "manifest_id"
        removed = utils.delete_s3_objects_matching_metadata(
            "request_id", None, metadata_key=metadata_key, metadata_value_check=metadata_value
        )
        self.assertEqual(removed, [])

        date_accessor = DateAccessor()
        start_date = date_accessor.today_with_timezone("UTC").replace(day=1)
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
            self.assertListEqual(removed, [expected_key])

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

        with patch("masu.util.aws.common.get_s3_objects_matching_metadata") as mock_get_objects, patch(
            "masu.util.aws.common.get_s3_resource"
        ) as mock_s3:
            mock_s3.return_value.Object.return_value.delete.side_effect = ClientError({}, "Error")
            mock_get_objects.return_value = [expected_key]
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
            upload = utils.copy_data_to_s3_bucket("request_id", "path", "filename", "data", "manifest_id")
            self.assertIsNone(upload)

    @patch("masu.util.aws.common.copy_data_to_s3_bucket")
    def test_copy_local_hcs_report_file_to_s3_bucket_with_finalize(self, mock_copy):
        """Test that the proper metadata is used when a finalized date is passed in with the finalize option"""
        fake_request_id = "fake_id"
        fake_s3_path = "fake_path"
        fake_filename = "fake_filename"
        expected_metadata = {"finalized": "True", "finalized-date": "2023-08-15"}
        expected_context = {}
        mock_op = mock_open(read_data="x,y,z")
        with patch("builtins.open", mock_op):
            utils.copy_local_hcs_report_file_to_s3_bucket(
                fake_request_id, fake_s3_path, fake_filename, fake_filename, True, "2023-08-15", expected_context
            )
        mock_copy.assert_called_once_with(
            fake_request_id, fake_s3_path, fake_filename, mock_op(), expected_metadata, expected_context
        )

    def test_match_openshift_resources_and_labels(self):
        """Test OCP on AWS data matching."""
        cluster_topology = [
            {
                "resource_ids": ["id1", "id2", "id3"],
                "cluster_id": self.ocp_cluster_id,
                "cluster_alias": "my-ocp-cluster",
                "nodes": [],
                "projects": [],
            }
        ]

        matched_tags = [{"key": "value"}]

        data = [
            {"lineitem_resourceid": "id1", "lineitem_unblendedcost": 1, "resourcetags": '{"key": "value"}'},
            {"lineitem_resourceid": "id2", "lineitem_unblendedcost": 1, "resourcetags": '{"key": "other_value"}'},
            {"lineitem_resourceid": "id4", "lineitem_unblendedcost": 1, "resourcetags": '{"keyz": "value"}'},
            {"lineitem_resourceid": "id5", "lineitem_unblendedcost": 1, "resourcetags": '{"key": "value"}'},
        ]

        df = pd.DataFrame(data)

        matched_df = utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["lineitem_resourceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["lineitem_resourceid"] == "id2"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["lineitem_resourceid"] == "id3"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)

        result = matched_df[matched_df["lineitem_resourceid"] == "id4"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)

        # tag matching
        result = matched_df[matched_df["lineitem_resourceid"] == "id1"]["matched_tag"] == '"key": "value"'
        self.assertTrue(result.bool())

        result = matched_df[matched_df["lineitem_resourceid"] == "id5"]["matched_tag"] == '"key": "value"'
        self.assertTrue(result.bool())

        # Matched tags, but none that match the dataset
        matched_tags = [{"something_else": "entirely"}]
        matched_df = utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["lineitem_resourceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["lineitem_resourceid"] == "id2"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["lineitem_resourceid"] == "id3"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)

        result = matched_df[matched_df["lineitem_resourceid"] == "id4"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)
        # tag matching
        self.assertFalse((matched_df["matched_tag"] != "").any())

        # No matched tags
        matched_tags = []
        matched_df = utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["lineitem_resourceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["lineitem_resourceid"] == "id2"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["lineitem_resourceid"] == "id3"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)

        result = matched_df[matched_df["lineitem_resourceid"] == "id4"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)

        # tag matching
        self.assertFalse((matched_df["matched_tag"] != "").any())

    def test_match_openshift_labels_with_nan_resources(self):
        """Test OCP on AWS data matching."""
        cluster_topology = [
            {
                "resource_ids": ["id1", "id2", "id3"],
                "cluster_id": self.ocp_cluster_id,
                "cluster_alias": "my-ocp-cluster",
                "nodes": [],
                "projects": [],
            }
        ]

        matched_tags = [{"key": "value"}]
        data = [
            {"lineitem_resourceid": np.nan, "lineitem_unblendedcost": 1, "resourcetags": '{"key": "value"}'},
        ]

        df = pd.DataFrame(data)
        matched_df = utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # tag matching
        result = matched_df["matched_tag"] == '"key": "value"'
        self.assertTrue(result.bool())

    def test_match_openshift_resource_with_nan_labels(self):
        """Test OCP on AWS data matching."""
        cluster_topology = [
            {
                "resource_ids": ["id1", "id2", "id3"],
                "cluster_id": self.ocp_cluster_id,
                "cluster_alias": "my-ocp-cluster",
                "nodes": [],
                "projects": [],
            }
        ]

        matched_tags = [{"key": "value"}]
        data = [
            {"lineitem_resourceid": "id1", "lineitem_unblendedcost": 1, "resourcetags": np.nan},
        ]

        df = pd.DataFrame(data)
        matched_df = utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["lineitem_resourceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

    @patch("masu.util.aws.common.get_s3_resource")
    def test_get_or_clear_daily_s3_by_date(self, mock_resource):
        """test getting daily archive start date"""
        start_date = DateHelper().this_month_start.replace(year=2019, month=7, day=1, tzinfo=None)
        end_date = DateHelper().this_month_start.replace(year=2019, month=7, day=2, tzinfo=None)
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
        with self.assertRaises(SyntaxError):
            utils.AwsArn(credentials)

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
