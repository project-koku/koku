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
"""Test Celery utility functions."""
from unittest.mock import patch

from api.iam.test.iam_test_case import IamTestCase
from koku.celery import is_task_currently_running


class CeleryTest(IamTestCase):
    @patch("koku.celery.CELERY_INSPECT")
    def test_is_task_currently_running(self, mock_inspect):
        """Test the various conditions for our running task checker."""
        mock_inspect.active.return_value = {
            "celery@koku-worker-1": [
                {
                    "id": "26256b1d-b0d8-4822-ba70-73da82af9542",
                    "name": "masu.processor.tasks.update_summary_tables",
                    "args": ["acct10001", "AWS-local", "2878097c-7693-4a4a-9726-e75124457805", "2020-08-01", None],
                    "kwargs": {},
                    "type": "masu.processor.tasks.update_summary_tables",
                    "hostname": "celery@koku-worker-1",
                    "time_start": 1597940661.4609702,
                    "acknowledged": True,
                    "delivery_info": {"exchange": "", "routing_key": "celery", "priority": 0, "redelivered": False},
                    "worker_pid": 68,
                }
            ]
        }

        self.assertTrue(
            is_task_currently_running("masu.processor.tasks.update_summary_tables", check_args=["acct10001"])
        )
        self.assertTrue(is_task_currently_running("masu.processor.tasks.update_summary_tables"))

        self.assertFalse(is_task_currently_running("update_summary_tables", check_args=["acct10001"]))
        self.assertFalse(
            is_task_currently_running("masu.processor.tasks.update_summary_tables", check_args=["acct10002"])
        )
        self.assertFalse(is_task_currently_running("masu.processor.tasks.update_cost_model_costs"))
