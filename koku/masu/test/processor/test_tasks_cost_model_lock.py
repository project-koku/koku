#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the worker cache lock timeout of update_cost_model_costs."""
from unittest.mock import patch

from django.test.utils import override_settings

from masu.processor.tasks import update_cost_model_costs
from masu.test import MasuTestCase

NORMAL = 111
LARGE = 222


@override_settings(HOSTNAME="kokuworker", WORKER_CACHE_TIMEOUT=NORMAL, WORKER_CACHE_LARGE_CUSTOMER_TIMEOUT=LARGE)
class CostModelLockTimeoutTest(MasuTestCase):
    """XL and penalty customers get the large-customer lock timeout, like the summary tasks."""

    def run_task(self, penalty=False, large=False, rate_limit=False):
        """Run update_cost_model_costs for a customer tier; return (lock timeout, rate_limit_tasks mock)."""
        with patch("common.queues.is_customer_penalty", return_value=penalty), patch(
            "common.queues.is_customer_large", return_value=large
        ), patch("masu.processor.tasks.is_rate_limit_customer_large", return_value=rate_limit), patch(
            "masu.processor.tasks.rate_limit_tasks", return_value=False
        ) as mock_rate_limit, patch(
            "masu.processor.tasks.CostModelCostUpdater"
        ), patch(
            "masu.processor.worker_cache.CELERY_INSPECT"
        ) as mock_inspect, patch(
            "masu.processor.tasks.WorkerCache.single_task_is_running", return_value=False
        ), patch(
            "masu.processor.tasks.WorkerCache.release_single_task"
        ), patch(
            "masu.processor.tasks.WorkerCache.lock_single_task"
        ) as mock_lock:
            mock_inspect.reserved.return_value = {"celery@kokuworker": []}
            update_cost_model_costs(self.schema, self.aws_provider_uuid, "2026-10-01", "2026-10-31")
        mock_lock.assert_called_once()
        return mock_lock.call_args.kwargs["timeout"], mock_rate_limit

    def test_default_customer_gets_normal_timeout(self):
        """A default-queue customer without the rate-limit flag keeps WORKER_CACHE_TIMEOUT."""
        timeout, mock_rate_limit = self.run_task()
        self.assertEqual(timeout, NORMAL)
        mock_rate_limit.assert_not_called()

    def test_penalty_customer_gets_large_timeout(self):
        """A penalty customer without the rate-limit flag gets the large-customer timeout."""
        timeout, mock_rate_limit = self.run_task(penalty=True)
        self.assertEqual(timeout, LARGE)
        mock_rate_limit.assert_not_called()

    def test_xl_customer_gets_large_timeout(self):
        """An XL customer without the rate-limit flag gets the large-customer timeout."""
        timeout, mock_rate_limit = self.run_task(large=True)
        self.assertEqual(timeout, LARGE)
        mock_rate_limit.assert_not_called()

    def test_rate_limited_customer_keeps_large_timeout_and_rate_limit(self):
        """A rate-limited default-queue customer keeps the large timeout and is still rate limited."""
        timeout, mock_rate_limit = self.run_task(rate_limit=True)
        self.assertEqual(timeout, LARGE)
        mock_rate_limit.assert_called_once()

    def test_rate_limited_penalty_customer(self):
        """Penalty plus rate-limit flag: large timeout and rate limiting."""
        timeout, mock_rate_limit = self.run_task(penalty=True, rate_limit=True)
        self.assertEqual(timeout, LARGE)
        mock_rate_limit.assert_called_once()
