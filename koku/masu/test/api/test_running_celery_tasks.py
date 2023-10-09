#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the running_celery_tasks endpoint view."""
from unittest.mock import patch
from urllib.parse import urlencode

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse


@override_settings(ROOT_URLCONF="masu.urls")
class RunningCeleryTasksTests(TestCase):
    """Test cases for the running_celery_tasks endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.CELERY_INSPECT")
    def test_get_running_celery_tasks_empty(self, mock_celery, _):
        """Test the GET of running_celery_tasks endpoint no tasks running."""
        mock_celery.active.return_value = {}
        response = self.client.get(reverse("running_celery_tasks"))
        self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.CELERY_INSPECT")
    def test_get_one_running_task(self, mock_celery, _):
        """Test the GET of running_celery_tasks endpoint."""
        mock_celery.active.return_value = {
            "celery@koku-worker-1": [
                {
                    "id": "a789bda7-f3fe-4af0-a327-fee32d777cd5",
                    "name": "masu.celery.tasks.crawl_account_hierarchy",
                    "args": [],
                    "kwargs": {"provider_uuid": "1fdb20f1-c68c-457f-a1d5-4b8544284e40"},
                    "type": "masu.celery.tasks.crawl_account_hierarchy",
                    "hostname": "celery@koku-worker-1",
                    "time_start": 1606753210.7729583,
                    "acknowledged": True,
                    "delivery_info": {"exchange": "", "routing_key": "celery", "priority": 0, "redelivered": False},
                    "worker_pid": 153,
                }
            ]
        }
        response = self.client.get(reverse("running_celery_tasks"))
        self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.collect_queue_metrics")
    def test_celery_queue_lengths(self, mock_collect, _):
        """Test the GET of celery_queue_lengths endpoint."""
        mock_collect.return_value = {}
        response = self.client.get(reverse("celery_queue_lengths"))
        self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.app")
    def test_clear_celery_queues_default(self, mock_celery, _):
        """Test the GET of clear_celery_queues endpoint."""
        mock_celery.control.purge.return_value = 0
        response = self.client.get(reverse("clear_celery_queues"))
        mock_celery.control.purge.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertIn("purged_tasks", response.data)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.app")
    @patch("masu.api.running_celery_tasks.collect_queue_metrics")
    @patch("masu.api.running_celery_tasks.redis")
    def test_clear_celery_queues_clear_all(self, mock_redis, mock_collect, mock_celery, _):
        """Test the GET of clear_celery_queues endpoint with clear_all."""
        expected_key = "purged_tasks"
        mock_celery.control.purge.return_value = 0
        mock_collect.values.return_value = []
        mock_redis = mock_redis.Redis.return_value
        mock_redis.flushall.return_value = "true"
        params = {"clear_all": True}
        query_string = urlencode(params)
        url = reverse("clear_celery_queues") + "?" + query_string
        response = self.client.get(url)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_celery.control.purge.assert_called_once()
        mock_collect.assert_called_once()
        mock_redis.flushall.assert_called_once()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.app")
    @patch("masu.api.running_celery_tasks.collect_queue_metrics")
    @patch("masu.api.running_celery_tasks.redis")
    def test_clear_queue(self, mock_redis, mock_collect, mock_celery, _):
        """Test the GET of clear_celery_queues endpoint with specific queue."""
        expected_key = "purged_tasks"
        mock_celery.control.purge.return_value = 0
        mock_collect.values.return_value = []
        mock_redis = mock_redis.Redis.return_value
        mock_redis.flushall.return_value = "true"
        params = {"queue": "priority"}
        query_string = urlencode(params)
        url = reverse("clear_celery_queues") + "?" + query_string
        response = self.client.get(url)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_celery.control.purge.assert_called_once()
        mock_collect.assert_called_once()
        mock_redis.delete.assert_called_once()
