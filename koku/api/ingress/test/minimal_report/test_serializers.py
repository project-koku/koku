#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Minimal Serializer."""
from rest_framework import serializers
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.ingress.minimal_report.serializers import MinimalReportSerializer
from api.provider.models import Provider
from reporting.minimal_report.models import MinimalReport


class MinimalReportSerializerTest(IamTestCase):
    """Tests for the exclude serializer."""

    def setUp(self):
        """Set up the tests."""
        super().setUp()

        self.ocp_provider = Provider.objects.filter(type=Provider.PROVIDER_OCP).first()
        self.aws_provider = Provider.objects.filter(type=Provider.PROVIDER_AWS_LOCAL).first()

    def tearDown(self):
        """Clean up test cases."""
        with tenant_context(self.tenant):
            MinimalReport.objects.all().delete()

    def test_invalid_source_type(self):
        """Test minimal report with invalid source type."""
        minimal_reports = {
            "source": self.ocp_provider.uuid,
            "reports_list": ["test-file"],
        }
        with tenant_context(self.tenant):
            serializer = MinimalReportSerializer(data=minimal_reports)
            with self.assertRaises(serializers.ValidationError):
                serializer.is_valid(raise_exception=True)

    def test_valid_data(self):
        """Test minimal report valid entries."""
        minimal_reports = {
            "source": self.aws_provider.uuid,
            "reports_list": ["test-file"],
        }
        with tenant_context(self.tenant):
            instance = None
            serializer = MinimalReportSerializer(data=minimal_reports)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
            self.assertTrue(instance.source.uuid, minimal_reports.get("source"))
            self.assertTrue(instance.reports_list, minimal_reports.get("reports_list"))
