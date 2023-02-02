#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Minimal Serializer."""
from unittest.mock import patch

from faker import Faker
from rest_framework import serializers
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.ingress.reports.serializers import IngressReportsSerializer
from api.provider.models import Provider
from reporting.ingress.models import IngressReports

FAKE = Faker()


class IngressReportsSerializerTest(IamTestCase):
    """Tests for the exclude serializer."""

    def setUp(self):
        """Set up the tests."""
        super().setUp()

        self.ocp_provider = Provider.objects.filter(type=Provider.PROVIDER_OCP).first()
        self.aws_provider = Provider.objects.filter(type=Provider.PROVIDER_AWS_LOCAL).first()

    def tearDown(self):
        """Clean up test cases."""
        with tenant_context(self.tenant):
            IngressReports.objects.all().delete()

    def test_invalid_source_type(self):
        """Test minimal report with invalid source type."""
        reports = {
            "source": self.ocp_provider.uuid,
            "reports_list": ["test-file"],
        }
        with tenant_context(self.tenant):
            serializer = IngressReportsSerializer(data=reports)
            with self.assertRaises(serializers.ValidationError):
                serializer.is_valid(raise_exception=True)

    @patch(
        "providers.aws.provider._get_sts_access",
        return_value=dict(
            aws_access_key_id=FAKE.md5(), aws_secret_access_key=FAKE.md5(), aws_session_token=FAKE.md5()
        ),
    )
    def test_valid_data(self, mock_get_sts_access):
        """Test minimal report valid entries."""
        reports = {
            "source": self.aws_provider.uuid,
            "reports_list": ["test-file"],
        }
        with tenant_context(self.tenant):
            instance = None
            serializer = IngressReportsSerializer(data=reports)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
            self.assertTrue(instance.source.uuid, reports.get("source"))
            self.assertTrue(instance.reports_list, reports.get("reports_list"))
