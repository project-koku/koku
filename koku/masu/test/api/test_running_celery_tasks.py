#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the running_celery_tasks endpoint view."""
import logging
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

LOG = logging.getLogger(__name__)


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
