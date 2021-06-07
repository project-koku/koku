#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
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

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.collect_queue_metrics")
    def test_scheduled_celery_tasks(self, mock_collect, _):
        """Test the GET of scheduled_celery_tasks endpoint."""
        mock_collect.return_value = {}
        response = self.client.get(reverse("scheduled_celery_tasks"))
        self.assertEqual(response.status_code, 200)
