#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test get queue function."""
from unittest.mock import Mock
from unittest.mock import patch

from api.models import Provider
from common.queues import DownloadQueue
from common.queues import get_customer_queue
from masu.test import MasuTestCase


class TestGetQueue(MasuTestCase):
    """Class to test getting worker queues"""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()

    def setUp(self):
        """Create test case setup."""
        super().setUp()
        p = Provider.objects.filter(uuid=self.aws_provider_uuid).first()
        self.provider_uuid = str(p.uuid)
        self.schema = p.account.get("schema_name")

    def test_get_queue(self):
        """Test getting queue"""
        default_queue = DownloadQueue.DEFAULT
        xl_queue = DownloadQueue.XL

        # Test getting default download queue with schema
        queue = get_customer_queue(self.schema)
        self.assertEqual(default_queue, queue)

        # Test getting XL download queue with schema
        with patch("common.queues.is_customer_large", return_value=True):
            queue = get_customer_queue(self.schema)
            self.assertEqual(xl_queue, queue)

        # Test getting XL download queue with schema with provider uuid
        with patch("common.queues.Provider", return_value=Mock()):
            queue = get_customer_queue(self.schema, DownloadQueue, self.provider_uuid)
            self.assertEqual(xl_queue, queue)
