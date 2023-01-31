#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the IngressReportDBAccessor."""
from faker import Faker
from tenant_schemas.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from masu.database.ingress_report_db_accessor import IngressReportDBAccessor
from masu.external.date_accessor import DateAccessor

FAKE = Faker()


class IngressReportDBAccessorTest(IamTestCase):
    """Test cases for the IngressReportDBAccessor."""

    def setUp(self):
        """Set up the test class."""
        super().setUp()
        self.schema = self.schema_name
        self.billing_start = DateAccessor().today_with_timezone("UTC").replace(day=1)
        self.ingress_report_dict = {
            "uuid": "1234",
            "created_timestamp": "today",
            "complete_timestamp": "tomorrow",
            "reports_list": ["test"],
            "source": "source_uuid",
        }
        self.ingress_report_accessor = IngressReportDBAccessor(self.schema)

    def tearDown(self):
        """Tear down the test class."""
        super().tearDown()
        with schema_context(self.schema):
            reports = self.ingress_report_accessor._get_db_obj_query().all()
            for report in reports:
                self.ingress_report_accessor.delete(report)

    def test_initializer(self):
        """Test the initializer."""
        accessor = IngressReportDBAccessor(self.schema)
        self.assertIsNotNone(accessor._table)

    def test_get_ingress_report_by_source(self):
        """Test that the right ingress_report is returned."""
        with schema_context(self.schema):
            added_ingress_report = self.ingress_report_accessor.add(**self.ingress_report_dict)

            ingress_report_id = self.ingress_report_dict.get("uuid")
            source_uuid = self.ingress_report_dict.get("source")
            ingress_report = self.ingress_report_accessor.get_ingress_report(ingress_report_id, source_uuid)

        self.assertIsNotNone(ingress_report)
        self.assertEqual(added_ingress_report, ingress_report)
        self.assertEqual(ingress_report.ingress_report_id, ingress_report_id)
        self.assertEqual(ingress_report.source_uuid, source_uuid)
        self.assertEqual(ingress_report.reports_list, self.ingress_report_dict.get("reports_list"))

    def test_get_ingress_report_by_id(self):
        """Test that the right ingress report is returned by id."""
        with schema_context(self.schema):
            added_ingress_report = self.ingress_report_accessor.add(**self.ingress_report_dict)
            ingress_report = self.ingress_report_accessor.get_ingress_report_by_id(added_ingress_report.id)
        self.assertIsNotNone(ingress_report)
        self.assertEqual(added_ingress_report, ingress_report)

    def test_mark_ingress_report_as_completed_none_report(self):
        """Test to mark ingress report complete with None report."""
        try:
            self.ingress_report_accessor.mark_ingress_reports_as_completed(None)
        except Exception as err:
            self.fail(f"Test failed with error: {err}")
