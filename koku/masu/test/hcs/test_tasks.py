#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the HCS task."""
import logging
from datetime import timedelta
from unittest.mock import patch

import faker

from api.models import Provider
from api.utils import DateHelper
from masu.test import MasuTestCase

LOG = logging.getLogger(__name__)


class TestHCSTasks(MasuTestCase):
    """Test cases for Processor Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.fake = faker.Faker()
        cls.fake_uuid = "d4703b6e-cd1f-4253-bfd4-32bdeaf24f97"
        cls.today = DateHelper().today
        cls.yesterday = cls.today - timedelta(days=1)

    def setUp(self):
        """Set up shared test variables."""
        super().setUp()
        self.test_assembly_id = "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"
        self.test_etag = "fake_etag"
        self.get_report_args = {
            "customer_name": self.schema,
            "authentication": self.aws_provider.authentication.credentials,
            "provider_type": Provider.PROVIDER_AWS_LOCAL,
            "schema_name": self.schema,
            "billing_source": self.aws_provider.billing_source.data_source,
            "provider_uuid": self.aws_provider_uuid,
            "report_month": DateHelper().today,
            "report_context": {"current_file": f"/my/{self.test_assembly_id}/koku-1.csv.gz"},
        }

    @patch("masu.hcs.tasks.update_hcs_report")
    def test_get_report_download_warning(self, mock_get_files, mock_inspect, mock_cache_remove):
        """Test raising download warning is handled."""
        mock_get_files.return_value = {"file": self.fake.word(), "compression": "GZIP"}

        mock_cache_remove.assert_called()
