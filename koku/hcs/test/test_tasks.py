#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the HCS task."""
import logging
from datetime import timedelta
from unittest.mock import patch

from api.models import Provider
from api.utils import DateHelper
from hcs.test import HCSTestCase

LOG = logging.getLogger(__name__)


@patch("hcs.daily_report.ReportHCS.generate_report")
@patch("hcs.tasks.enable_hcs_processing")
class TestHCSTasks(HCSTestCase):
    """Test cases for HCS Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.today = DateHelper().today
        cls.yesterday = cls.today - timedelta(days=1)
        cls.provider = Provider.PROVIDER_AWS
        cls.provider_uuid = "cabfdddb-4ed5-421e-a041-311b75daf235"

    def test_get_report_dates(self, mock_ehp, mock_report):
        """Test with start and end dates provided"""
        from hcs.tasks import collect_hcs_report_data

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.yesterday
            end_date = self.today
            collect_hcs_report_data(self.schema, self.provider, self.provider_uuid, start_date, end_date)

            self.assertIn("[collect_hcs_report_data]", _logs.output[0])

    def test_get_report_no_start_date(self, mock_ehp, mock_report):
        """Test no start or end dates provided"""
        from hcs.tasks import collect_hcs_report_data

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_data(self.schema, self.provider, self.provider_uuid)

            self.assertIn("[collect_hcs_report_data]", _logs.output[0])

    def test_get_report_no_end_date(self, mock_ehp, mock_report):
        """Test no start date provided"""
        from hcs.tasks import collect_hcs_report_data

        mock_ehp.return_value = True

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.yesterday
            collect_hcs_report_data(self.schema, self.provider, self.provider_uuid, start_date)

            self.assertIn("[collect_hcs_report_data]", _logs.output[0])

    def test_get_report_invalid_provider(self, mock_ehp, mock_report):
        """Test invalid provider"""
        from hcs.tasks import collect_hcs_report_data

        mock_ehp.return_value = False

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.yesterday
            collect_hcs_report_data(self.schema, "bogus", self.provider_uuid, start_date)

            self.assertIn("[SKIPPED] HCS report generation", _logs.output[0])

    def test_schema_no_acct_prefix(self, mock_ehp, mock_report):
        """Test no schema name prefix provided"""
        from hcs.tasks import collect_hcs_report_data

        mock_ehp.return_value = True
        collect_hcs_report_data("10001", self.provider, self.provider_uuid, self.yesterday)

        self.assertEqual("acct10001", self.schema)

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_get_report_with_manifest(self, rd, mock_ehp, mock_report):
        """Test report with manifest"""
        from hcs.tasks import collect_hcs_report_data_from_manifest

        mock_ehp.return_value = True

        manifests = [
            {
                "schema_name": self.schema,
                "provider_type": self.provider,
                "provider_uuid": self.provider_uuid,
                "tracing_id": self.provider_uuid,
            }
        ]

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_data_from_manifest(manifests)

            self.assertIn("[collect_hcs_report_data_from_manifest]", _logs.output[0])
            self.assertIn(f"schema_name: {self.schema}", _logs.output[0])
            self.assertIn(f"provider_type: {self.provider}", _logs.output[0])
            self.assertIn(f"provider_uuid: {self.provider_uuid}", _logs.output[0])
            self.assertIn("start:", _logs.output[0])
            self.assertIn("end:", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    def test_get_report_with_manifest_and_dates(self, rd, mock_ehp, mock_report):
        """Test report with manifest and dates"""
        from hcs.tasks import collect_hcs_report_data_from_manifest

        mock_ehp.return_value = True
        manifests = [
            {
                "schema_name": self.schema,
                "provider_type": self.provider,
                "provider_uuid": self.provider_uuid,
                "start": self.today.strftime("%Y-%m-%d"),
                "end": self.yesterday.strftime("%Y-%m-%d"),
            }
        ]

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_data_from_manifest(manifests)
            self.assertIn("using start and end dates from the manifest for HCS processing", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    @patch("api.provider.models")
    def test_get_collect_hcs_report_finalization(self, provider, rd, mock_ehp, mock_report):
        """Test report finalization"""
        from hcs.tasks import collect_hcs_report_finalization

        mock_ehp.return_value = True
        provider.customer.schema_name.return_value = provider(side_effect=Provider.objects.filter(type="AWS"))

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization()

            self.assertIn("[collect_hcs_report_finalization]:", _logs.output[0])
            self.assertIn("schema_name:", _logs.output[0])
            self.assertIn("provider_type:", _logs.output[0])
            self.assertIn("provider_uuid:", _logs.output[0])
            self.assertIn("dates:", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    @patch("api.provider.models")
    def test_get_collect_hcs_report_finalization_month(self, provider, rd, mock_ehp, mock_report):
        """Test finalization providing month"""
        from hcs.tasks import collect_hcs_report_finalization

        mock_ehp.return_value = True
        provider.customer.schema_name.return_value = provider(side_effect=Provider.objects.filter(type="AWS"))

        start_date = "2022-10-01"
        end_date = "2022-10-31"

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization(month=10)

            self.assertIn("[collect_hcs_report_finalization]:", _logs.output[0])
            self.assertIn("schema_name:", _logs.output[0])
            self.assertIn("provider_type:", _logs.output[0])
            self.assertIn("provider_uuid:", _logs.output[0])
            self.assertIn(f"dates: {start_date} - {end_date}", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    @patch("api.provider.models")
    def test_get_collect_hcs_report_finalization_provider(self, provider, rd, mock_ehp, mock_report):
        """Test finalization with providing a provider_type"""
        from hcs.tasks import collect_hcs_report_finalization

        mock_ehp.return_value = True

        p_type = "AWS"
        provider.type.return_value = p_type

        with self.assertLogs("hcs.tasks", "DEBUG") as _logs:
            collect_hcs_report_finalization(provider_type=p_type)

            self.assertIn(f"provider type provided: {p_type}", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    @patch("api.provider.models")
    def test_get_collect_hcs_report_finalization_provider_negative(self, provider, rd, mock_ehp, mock_report):
        """Test finalization with providing a bogus provider_type"""
        from hcs.tasks import collect_hcs_report_finalization

        mock_ehp.return_value = True

        p_type = "BOGUS"

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization(provider_type=p_type)

            self.assertIn(f"provider type: {p_type} is not an excepted HCS provider", _logs.output[0])

    @patch("hcs.tasks.collect_hcs_report_data")
    @patch("api.provider.models.Provider.objects")
    def test_get_collect_hcs_report_finalization_provider_uuid(self, provider, rd, mock_ehp, mock_report):
        """Test finalization with providing a provider_uuid"""
        from hcs.tasks import collect_hcs_report_finalization

        mock_ehp.return_value = True
        p_type = "AWS"
        provider.type.return_value = p_type

        p_u = "05e04f00-18db-4ab5-8960-88854c6f9d88"
        provider.uuid.return_value = p_u

        with self.assertLogs("hcs.tasks", "DEBUG") as _logs:
            collect_hcs_report_finalization(provider_uuid=p_u)

            self.assertIn(f"excepted_provider: {p_type}", _logs.output[0])
            self.assertIn(f"provider uuid provided: {p_u}", _logs.output[1])

    @patch("hcs.tasks.collect_hcs_report_data")
    @patch("api.provider.models")
    def test_get_collect_hcs_report_finalization_provider_uuid_negative(self, provider, rd, mock_ehp, mock_report):
        """Test hcs finalization for a given bad provider_uuid"""
        from hcs.tasks import collect_hcs_report_finalization

        mock_ehp.return_value = True
        p_u = "11111111-0000-1111-0000-111111111111"

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization(provider_uuid=p_u)

            self.assertIn(f"provider_uuid: {p_u} does not exist", _logs.output[1])

    @patch("hcs.tasks.collect_hcs_report_data")
    @patch("api.provider.models")
    def test_get_collect_hcs_report_finalization_schema_name_negative(self, provider, rd, mock_ehp, mock_report):
        """Test hcs finalization for a given bad schema_name"""
        from hcs.tasks import collect_hcs_report_finalization

        schema_name = "acct10001123"
        mock_ehp.return_value = False

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_finalization(schema_name=schema_name)

            self.assertIn(f"schema_name provided: {schema_name} is not HCS enabled", _logs.output[0])
