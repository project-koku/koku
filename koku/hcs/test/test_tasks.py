#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the HCS task."""
import uuid
from datetime import timedelta
from unittest.mock import Mock
from unittest.mock import patch
from unittest.mock import PropertyMock

import hcs.tasks as tasks
from api.utils import DateHelper
from hcs.tasks import collect_hcs_report_data
from hcs.tasks import collect_hcs_report_data_from_manifest
from hcs.tasks import collect_hcs_report_finalization
from hcs.tasks import get_start_and_end_from_manifest_id
from hcs.tasks import should_finalize
from hcs.test import HCSTestCase


@patch("hcs.daily_report.ReportHCS.generate_report")
@patch("hcs.tasks.enable_hcs_processing")
class TestHCSTasks(HCSTestCase):
    """Test cases for HCS Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.today = DateHelper().today
        cls.dh = DateHelper()
        cls.yesterday = cls.today - timedelta(days=1)
        cls.tracing_id = str(uuid.uuid4())
        cls.account_based_schema = "acct10001"

    def test_get_report_dates(self, mock_ehp, mock_report):
        """Test with start and end dates provided"""
        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.yesterday
            end_date = self.today
            collect_hcs_report_data(
                self.schema, self.aws_provider_type, str(self.aws_provider.uuid), start_date, end_date
            )

            self.assertIn("collecting hcs report data", _logs.output[0])

    def test_get_report_no_start_date(self, mock_ehp, mock_report):
        """Test no start or end dates provided"""
        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_data(self.schema, self.aws_provider_type, str(self.aws_provider.uuid))

            self.assertIn("collecting hcs report data", _logs.output[0])

    def test_get_report_no_tracing_id(self, mock_ehp, mock_report):
        """Test that tracing_id is added to log output when not provided"""
        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_data(self.schema, self.aws_provider_type, str(self.aws_provider.uuid))

            self.assertIn("tracing_id", _logs.output[0])

    def test_get_report_tracing_id(self, mock_ehp, mock_report):
        """Test that tracing_id can be overridden"""
        mock_ehp.return_value = True
        test_id = str(uuid.uuid4())

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_data(
                self.schema, self.aws_provider_type, str(self.aws_provider.uuid), tracing_id=test_id
            )

            self.assertIn(f"'tracing_id': '{test_id}'", _logs.output[0])

    def test_get_report_no_end_date(self, mock_ehp, mock_report):
        """Test no start date provided"""
        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.yesterday
            collect_hcs_report_data(self.schema, self.aws_provider_type, str(self.aws_provider.uuid), start_date)

            self.assertIn("collecting hcs report data", _logs.output[0])

    def test_get_report_invalid_provider(self, mock_ehp, mock_report):
        """Test invalid provider"""
        mock_ehp.return_value = False

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.yesterday
            collect_hcs_report_data(self.schema, "bogus", str(self.aws_provider.uuid), start_date)

            self.assertIn("skipping hcs report generation", _logs.output[0])

    def test_get_report_schema_no_acct_prefix(self, mock_ehp, mock_report):
        """Test no schema name prefix provided"""
        mock_ehp.return_value = True
        collect_hcs_report_data("10001", self.aws_provider_type, str(self.aws_provider.uuid), self.yesterday)

        self.assertEqual("org1234567", self.schema)

    @patch("hcs.tasks.get_start_and_end_from_manifest_id")
    @patch("masu.database.report_manifest_db_accessor.ReportManifestDBAccessor")
    @patch("hcs.tasks.collect_hcs_report_data")
    def test_get_report_with_manifest(self, mock_report, mock_manifest_accessor, mock_start_end, mock_ehp, rd):
        """Test report with manifest"""
        mock_ehp.return_value = True
        mock_start_end.return_value = (self.dh.this_month_start.date(), self.dh.this_month_end.date())

        manifests = [
            {
                "schema_name": self.schema,
                "provider_type": self.aws_provider_type,
                "provider_uuid": str(self.aws_provider.uuid),
                "tracing_id": self.tracing_id,
            }
        ]

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_data_from_manifest(manifests)

            self.assertIn("collect hcs report data from manifest", _logs.output[0])
            self.assertIn(f"'schema_name': '{self.schema}'", _logs.output[0])
            self.assertIn(f"'provider_type': '{self.aws_provider_type}'", _logs.output[0])
            self.assertIn(f"'provider_uuid': '{str(self.aws_provider.uuid)}'", _logs.output[0])
            self.assertIn("'start_date':", _logs.output[0])
            self.assertIn("'end_date':", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_get_report_with_manifest_and_dates(self, rd, mock_ehp, mock_report):
        """Test report with manifest and dates"""
        mock_ehp.return_value = True
        manifests = [
            {
                "schema_name": self.schema,
                "aws_provider": self.aws_provider_type,
                "provider_uuid": str(self.aws_provider.uuid),
                "start": self.today.strftime("%Y-%m-%d"),
                "end": self.yesterday.strftime("%Y-%m-%d"),
            }
        ]

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_data_from_manifest(manifests)
            self.assertIn("using start and end dates from the manifest for HCS processing", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization(self, rd, mock_ehp, mock_report):
        """Test report finalization"""

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization()

            self.assertIn("collecting hcs report finalization", _logs.output[0])
            self.assertIn("'schema_name':", _logs.output[0])
            self.assertIn("'provider_type':", _logs.output[0])
            self.assertIn("'provider_uuid':", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_tracing_id(self, rd, mock_ehp, mock_report):
        """Test report finalization tracing_id provided"""

        mock_ehp.return_value = True
        test_id = str(uuid.uuid4())

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization(tracing_id=test_id)

            self.assertIn(f"'tracing_id': '{test_id}'", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_no_tracing_id(self, rd, mock_ehp, mock_report):
        """Test report finalization tracing_id not provided"""

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization()

            self.assertIn("tracing_id", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_month(self, rd, mock_ehp, mock_report):
        """Test finalization providing month but no year fails since both are required."""

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "WARNING") as _logs:
            collect_hcs_report_finalization(provider_type=self.aws_provider_type, month=10)
            expected_errmsg = "month and year must be provided together."
            self.assertIn(expected_errmsg, _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_monthyear(self, rd, mock_ehp, mock_report):
        """Test finalization providing year and month"""

        mock_ehp.return_value = True
        start_date = "2021-10-01"
        end_date = "2021-10-31"

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization(provider_type=self.aws_provider_type, month=10, year=2021)
            self.assertIn(f"'start_date': '{start_date}'", _logs.output[0])
            self.assertIn(f"'end_date': '{end_date}'", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_report_finalization_provider_type(self, rd, mock_ehp, mock_report):
        """Test finalization with providing provider_type"""

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "DEBUG") as _logs:
            collect_hcs_report_finalization(provider_type=self.aws_provider_type)

            self.assertIn(f"provided provider_type: {self.aws_provider_type}", _logs.output[0])
            self.assertIn(f"'provider_type': '{self.aws_provider_type}'", _logs.output[1])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_provider_negative(self, rd, mock_ehp, mock_report):
        """Test finalization with providing a bogus provider_type"""

        mock_ehp.return_value = True
        p_type = "BOGUS"

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization(provider_type=p_type)

            self.assertIn(f"no valid providers found for provider_type: {p_type}", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_provider_uuid(self, rd, mock_ehp, mock_report):
        """Test finalization with providing a provider_uuid"""

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "DEBUG") as _logs:
            collect_hcs_report_finalization(provider_uuid=str(self.aws_provider.uuid))

            self.assertIn(f"provided provider_uuid: {str(self.aws_provider.uuid)}", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_provider_uuid_negative(self, rd, mock_ehp, mock_report):
        """Test hcs finalization for a given bad provider_uuid"""

        mock_ehp.return_value = True
        p_u = "11111111-0000-1111-0000-111111111111"

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization(provider_uuid=p_u)

            self.assertIn(f"provider_uuid: {p_u} does not exist", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_schema_name_and_provider_type(self, rd, mock_ehp, mock_report):
        """Test hcs finalization for a given schema_name and provider_type"""

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "DEBUG") as _logs:
            collect_hcs_report_finalization(schema_name=self.schema, provider_type=self.aws_provider_type)

            self.assertIn(
                f"provided schema_name: {self.schema}, provided provider_type: {self.aws_provider_type}",
                _logs.output[0],
            )
            self.assertIn(f"'schema_name': '{self.schema}'", _logs.output[1])
            self.assertIn(f"'provider_type': '{self.aws_provider_type}'", _logs.output[1])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_schema_name(self, rd, mock_ehp, mock_report):
        """Test hcs finalization for a given schema_name"""

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "DEBUG") as _logs:
            collect_hcs_report_finalization(schema_name=self.schema)

            self.assertIn(f"provided schema_name: {self.schema}", _logs.output[0])
            self.assertIn(f"'schema_name': '{self.schema}'", _logs.output[1])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_schema_no_acct_prefix(self, rd, mock_ehp, mock_report):
        """Test hcs finalization for a given schema_name when no 'acct' prefix is given"""

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "DEBUG") as _logs:
            collect_hcs_report_finalization(schema_name="10001")

            self.assertIn(f"provided schema_name: {self.account_based_schema}", _logs.output[0])
            self.assertIn(f"schema_name: {self.account_based_schema}", _logs.output[1])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_schema_org_schema(self, rd, mock_ehp, mock_report):
        """Test hcs finalization for a given schema_name when no 'acct' prefix is given"""

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "DEBUG") as _logs:
            collect_hcs_report_finalization(schema_name="org1234567")

            self.assertIn(f"provided schema_name: {self.schema}", _logs.output[0])
            self.assertIn(f"'schema_name': '{self.schema}'", _logs.output[1])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_schema_name_negative(self, rd, mock_ehp, mock_report):
        """Test hcs finalization for a given bad schema_name"""

        schema_name = "acct10001123"
        mock_ehp.return_value = False

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization(schema_name=schema_name)

            self.assertIn(f"schema_name provided: {schema_name} is not HCS enabled", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_provider_type_and_provider_uuid(self, rd, mock_ehp, mock_report):
        """Test hcs finalization negative test when supplying both provider_type & provider_uuid arguments"""

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization(
                provider_type=self.aws_provider_type, provider_uuid=str(self.aws_provider.uuid)
            )

            self.assertIn("'provider_type' and 'provider_uuid' are not supported in the same request", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_report_finalization_schema_name_and_provider_uuid(self, rd, mock_ehp, mock_report):
        """Test hcs finalization for a given bad schema_name"""

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization(schema_name=self.schema, provider_uuid=str(self.aws_provider.uuid))

            self.assertIn("'schema_name' and 'provider_uuid' are not supported in the same request", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_get_providers_by_type_negative(self, rd, mock_ehp, mock_report):
        """Test hcs finalization for a given bad schema_name"""
        from hcs.tasks import get_providers_by_type

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            bad_type = "bogus"
            get_providers_by_type(bad_type)

            self.assertIn(f"no valid providers found for provider_type: {bad_type}", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_get_providers_by_uuid_negative(self, rd, mock_ehp, mock_report):
        """Test hcs finalization for a given bad schema_name"""
        from hcs.tasks import get_providers_by_uuid

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            bad_uuid = "11111111-0000-1111-0000-111111111111"
            get_providers_by_uuid(bad_uuid)

            self.assertIn(f"provider_uuid: {bad_uuid} does not exist", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_hcs_get_providers_by_schema_negative(self, rd, mock_ehp, mock_report):
        """Test hcs finalization for a given bad schema_name"""
        from hcs.tasks import get_providers_by_schema

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            bad_schema = "bogus"
            get_providers_by_schema(bad_schema)

            self.assertIn(f"no valid providers found for schema_name: {bad_schema}", _logs.output[0])

    @patch("masu.database.report_manifest_db_accessor.ReportManifestDBAccessor")
    def test_get_start_and_end_from_manifest_id(self, rd, mock_ehp, mock_manifest_accessor):
        """Test that given a manifest ID, this function returns a start and end date"""
        mock_manifest_accessor.get_manifest_by_id.return_value = Mock(
            billing_period_start_datetime=self.dh.last_month_start
        )
        mock_manifest_accessor.get_manifest_list_for_provider_and_bill_date.return_value = [1]
        start, end = get_start_and_end_from_manifest_id(1)
        self.assertEqual(start, self.dh.last_month_start.date())
        self.assertEqual(end, self.dh.last_month_end.date())

    @patch("masu.database.report_manifest_db_accessor.ReportManifestDBAccessor.get_manifest_by_id", return_value=None)
    def test_get_start_and_end_from_manifest_id_no_manifest(self, rd, mock_ehp, mock_manifest_accessor):
        """Test that given a NULL maniest, this function returns None"""
        date_tuple = get_start_and_end_from_manifest_id(1)
        self.assertIsNone(date_tuple)

    def test_should_finalize(self, rd, mock_ehp):
        """test the different cases that finalize should return true or false"""
        table = [
            {"name": "none-dates", "start": None, "end": None, "now": self.dh.this_month_start, "expected": False},
            {
                "name": "old-dates",
                "start": self.dh.relative_month_start(-3).date(),
                "end": self.dh.relative_month_end(-3).date(),
                "now": self.dh.this_month_start,
                "expected": True,
            },
            {
                "name": "before-15th-and-last-month",
                "start": self.dh.last_month_start.date(),
                "end": self.dh.last_month_end.date(),
                "now": self.dh.this_month_start,
                "expected": False,
            },
            {
                "name": "after-15th-and-last-month",
                "start": self.dh.last_month_start.date(),
                "end": self.dh.last_month_end.date(),
                "now": self.dh.this_month_end,
                "expected": True,
            },
            {
                "name": "on-the-15th-and-last-month",
                "start": self.dh.last_month_start.date(),
                "end": self.dh.last_month_end.date(),
                "now": self.dh.this_month_end.replace(day=15),
                "expected": True,
            },
            {
                "name": "on-the-14th-and-last-month",
                "start": self.dh.last_month_start.date(),
                "end": self.dh.last_month_end.date(),
                "now": self.dh.this_month_end.replace(day=14),
                "expected": False,
            },
            {
                "name": "on-the-16th-and-last-month",
                "start": self.dh.last_month_start.date(),
                "end": self.dh.last_month_end.date(),
                "now": self.dh.this_month_end.replace(day=16),
                "expected": True,
            },
        ]

        for test in table:
            with self.subTest(test=test["name"]):
                with patch.object(tasks.DateHelper, "now", new_callable=PropertyMock) as mock_now:
                    mock_now.return_value = test["now"]
                    self.assertEqual(test["expected"], should_finalize(test["start"], test["end"]))
