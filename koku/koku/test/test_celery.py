#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Celery utility functions."""
from unittest.mock import patch

from api.iam.test.iam_test_case import IamTestCase
from koku import is_task_currently_running


class CeleryTest(IamTestCase):
    @patch("koku.celery.CELERY_INSPECT")
    def test_is_task_currently_running(self, mock_inspect):
        """Test the various conditions for our running task checker."""
        mock_inspect.active.return_value = {
            "celery@koku-worker-1": [
                {
                    "id": "26256b1d-b0d8-4822-ba70-73da82af9542",
                    "name": "masu.processor.tasks.update_summary_tables",
                    "args": ["org1234567", "AWS-local", "2878097c-7693-4a4a-9726-e75124457805", "2020-08-01", None],
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

        # No task ID
        self.assertTrue(
            is_task_currently_running("masu.processor.tasks.update_summary_tables", None, check_args=["org1234567"])
        )
        # Different task ID running the check than the listed currently running task
        self.assertTrue(
            is_task_currently_running(
                "masu.processor.tasks.update_summary_tables",
                "26256b1d-b0d8-4822-ba70-73da82af9543",
                check_args=["org1234567"],
            )
        )
        # No check args
        self.assertTrue(is_task_currently_running("masu.processor.tasks.update_summary_tables", None))

        # The task ID of the currently running task
        self.assertFalse(
            is_task_currently_running(
                "masu.processor.tasks.update_summary_tables",
                "26256b1d-b0d8-4822-ba70-73da82af9542",
                check_args=["org1234567"],
            )
        )

        # An incomplete task name
        self.assertFalse(is_task_currently_running("update_summary_tables", None, check_args=["org1234567"]))
        # A different check arg
        self.assertFalse(
            is_task_currently_running("masu.processor.tasks.update_summary_tables", None, check_args=["org2222222"])
        )
        # A different task
        self.assertFalse(is_task_currently_running("masu.processor.tasks.update_cost_model_costs", None))
