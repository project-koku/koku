#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Minimal Serializer."""
from rest_framework import serializers
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.ingress.report.serializers import ReportSerializer
from api.provider.models import Provider
from reporting.report.models import Report


class ReportSerializerTest(IamTestCase):
    """Tests for the exclude serializer."""

    def setUp(self):
        """Set up the tests."""
        super().setUp()

        self.ocp_provider = Provider.objects.filter(type=Provider.PROVIDER_OCP).first()
        self.aws_provider = Provider.objects.filter(type=Provider.PROVIDER_AWS_LOCAL).first()

    def tearDown(self):
        """Clean up test cases."""
        with tenant_context(self.tenant):
            Report.objects.all().delete()

    def test_invalid_source_type(self):
        """Test minimal report with invalid source type."""
        reports = {
            "source": self.ocp_provider.uuid,
            "reports_list": ["test-file"],
        }
        with tenant_context(self.tenant):
            serializer = ReportSerializer(data=reports)
            with self.assertRaises(serializers.ValidationError):
                serializer.is_valid(raise_exception=True)

    def test_valid_data(self):
        """Test minimal report valid entries."""
        reports = {
            "source": self.aws_provider.uuid,
            "reports_list": ["test-file"],
        }
        with tenant_context(self.tenant):
            instance = None
            serializer = ReportSerializer(data=reports)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
            self.assertTrue(instance.source.uuid, reports.get("source"))
            self.assertTrue(instance.reports_list, reports.get("reports_list"))
