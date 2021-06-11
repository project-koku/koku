#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the AWSLocalProvider implementation for the Koku interface."""
import os
import tempfile

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from api.models import Provider
from providers.aws_local.provider import AWSLocalProvider


class AWSLocalProviderTestCase(TestCase):
    """Parent Class for AWSLocalProvider test cases."""

    def setUp(self):
        """Create test case objects."""
        super().setUp()
        self.cur_source = tempfile.mkdtemp()

    def tearDown(self):
        """Tear down test case objects."""
        os.rmdir(self.cur_source)
        super().tearDown()

    def test_get_name(self):
        """Get name of provider."""
        provider = AWSLocalProvider()
        self.assertEqual(provider.name(), Provider.PROVIDER_AWS_LOCAL)

    def test_cost_usage_source_is_reachable(self):
        """Verify that the cost usage source is authenticated and created."""
        credentials = {"role_arn": "arn:aws:s3:::my_s3_bucket"}
        data_source = {"bucket": self.cur_source}

        provider_interface = AWSLocalProvider()

        try:
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
        except Exception as error:
            self.fail("Unexpected Error: {}".format(str(error)))

    def test_cost_usage_source_is_reachable_no_bucket(self):
        """Verify that the cost usage source is not authenticated and created when no bucket is provided."""
        credentials = {"role_arn": "arn:aws:s3:::my_s3_bucket"}
        data_source = {"bucket": None}

        provider_interface = AWSLocalProvider()

        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
