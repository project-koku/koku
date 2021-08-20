#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ProviderDBAccessor utility object."""
import uuid

from masu.database.provider_collector import ProviderCollector
from masu.test import MasuTestCase


class ProviderQueryTest(MasuTestCase):
    """Test Cases for the ProviderDBAccessor object."""

    def test_get_uuids(self):
        """Test getting all uuids."""
        collector = ProviderCollector()
        providers = collector.get_providers()
        test_provider_found = False
        for provider in providers:
            if uuid.UUID(self.aws_provider_uuid) == provider.uuid:
                test_provider_found = True
        self.assertTrue(test_provider_found)
