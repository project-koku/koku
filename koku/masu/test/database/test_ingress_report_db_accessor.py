#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the IngressReportDBAccessor."""
import uuid

from django_tenants.utils import schema_context
from faker import Faker

from api.provider.models import Provider
from masu.database.ingress_report_db_accessor import IngressReportDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase

FAKE = Faker()


class IngressReportDBAccessorTest(MasuTestCase):
    """Test cases for the IngressReportDBAccessor."""

    def setUp(self):
        """Set up the test class."""
        super().setUp()
        self.schema_name = self.schema_name
        self.start = DateAccessor().today_with_timezone("UTC").replace(day=1)
        self.aws_provider = Provider.objects.filter(type=Provider.PROVIDER_AWS_LOCAL).first()
        self.ingress_report_dict = {
            "uuid": str(uuid.uuid4()),
            "created_timestamp": self.start,
            "completed_timestamp": None,
            "reports_list": ["test"],
            "source": self.aws_provider,
        }
        self.ingress_report_accessor = IngressReportDBAccessor(self.schema_name)

    def tearDown(self):
        """Tear down the test class."""
        super().tearDown()
        with schema_context(self.schema_name):
            reports = self.ingress_report_accessor._get_db_obj_query().all()
            for report in reports:
                self.ingress_report_accessor.delete(report)

    def test_initializer(self):
        """Test the initializer."""
        accessor = IngressReportDBAccessor(self.schema_name)
        self.assertIsNotNone(accessor._table)

    def test_get_ingress_reports_by_source(self):
        """Test that the right ingress reports are returned."""
        with schema_context(self.schema_name):
            added_ingress_report = self.ingress_report_accessor.add(**self.ingress_report_dict)

            ingress_report_uuid = self.ingress_report_dict.get("uuid")
            source_uuid = self.ingress_report_dict.get("source")
            ingress_report = self.ingress_report_accessor.get_ingress_reports_for_source(source_uuid=source_uuid)

        self.assertIsNotNone(ingress_report)
        self.assertEqual(added_ingress_report, ingress_report)
        self.assertEqual(str(ingress_report.uuid), ingress_report_uuid)
        self.assertEqual(ingress_report.source, source_uuid)
        self.assertEqual(ingress_report.reports_list, self.ingress_report_dict.get("reports_list"))

    def test_get_ingress_report_by_uuid(self):
        """Test that the right ingress report is returned by id."""
        with schema_context(self.schema_name):
            added_ingress_report = self.ingress_report_accessor.add(**self.ingress_report_dict)
            ingress_report = self.ingress_report_accessor.get_ingress_report_by_uuid(
                self.ingress_report_dict.get("uuid")
            )
        self.assertIsNotNone(ingress_report)
        self.assertEqual(added_ingress_report, ingress_report)

    def test_mark_ingress_report_as_completed_none_report(self):
        """Test to mark ingress report complete with None report."""
        try:
            self.ingress_report_accessor.mark_ingress_report_as_completed(ingress_report_uuid=None)
        except Exception as err:
            self.fail(f"Test failed with error: {err}")
