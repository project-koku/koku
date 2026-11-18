#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for _remove_expired_data task passthrough."""
import os
from unittest.mock import patch

from api.provider.models import Provider
from masu.processor._tasks.remove_expired import _remove_expired_data
from masu.test import MasuTestCase


class RemoveExpiredDataTaskTest(MasuTestCase):
    """Tests for the _remove_expired_data task function."""

    def setUp(self):
        super().setUp()
        self._env_patcher = patch.dict(
            os.environ,
            {k: v for k, v in os.environ.items() if k != "RETAIN_NUM_MONTHS"},
            clear=True,
        )
        self._env_patcher.start()

    def tearDown(self):
        self._env_patcher.stop()
        super().tearDown()

    @patch("masu.processor._tasks.remove_expired.get_data_retention_months", return_value=12)
    @patch("masu.processor._tasks.remove_expired.ExpiredDataRemover")
    def test_passes_tenant_retention_to_remover(self, mock_remover_cls, mock_get_retention):
        """The task reads per-tenant retention and passes it to ExpiredDataRemover."""
        _remove_expired_data(self.schema, Provider.PROVIDER_AWS, simulate=False)
        mock_get_retention.assert_called_once_with(self.schema)
        mock_remover_cls.assert_called_once_with(self.schema, Provider.PROVIDER_AWS, num_of_months_to_keep=12)

    @patch("masu.processor._tasks.remove_expired.get_data_retention_months", return_value=None)
    @patch("masu.processor._tasks.remove_expired.ExpiredDataRemover")
    def test_skips_purge_when_retention_is_none(self, mock_remover_cls, mock_get_retention):
        """When get_data_retention_months returns None, purge is skipped (R7)."""
        _remove_expired_data(self.schema, Provider.PROVIDER_AWS, simulate=False)
        mock_remover_cls.assert_not_called()

    @patch("masu.processor._tasks.remove_expired.get_data_retention_months", return_value=6)
    @patch("masu.processor._tasks.remove_expired.ExpiredDataRemover")
    def test_passes_provider_uuid_through(self, mock_remover_cls, mock_get_retention):
        """provider_uuid is forwarded to remover.remove()."""
        fake_uuid = "test-uuid-1234"
        mock_instance = mock_remover_cls.return_value
        _remove_expired_data(self.schema, Provider.PROVIDER_AWS, simulate=False, provider_uuid=fake_uuid)
        mock_instance.remove.assert_called_once_with(simulate=False, provider_uuid=fake_uuid)
