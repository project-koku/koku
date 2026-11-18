#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""The delayed-task sweep must not lose a date range merged into an expired row while it runs."""
import threading
import time
import uuid
from datetime import date
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

import django.test
from django.db import connection
from django.utils import timezone

from reporting_common.models import DelayedCeleryTasks

TASK = "test.delayed_tasks_sweep"


class DelayedTasksSweepRaceTest(django.test.TransactionTestCase):
    """trigger_delayed_tasks racing create_or_reset_timeout on the same expired row (real commits)."""

    def _fixture_teardown(self):
        """Skip the TRUNCATE flush: the django-tenants FK graph breaks it. tearDown cleans up."""

    def setUp(self):
        self.provider_uuid = uuid.uuid4()
        self.addCleanup(self._delete_rows)

    @staticmethod
    def _delete_rows():
        # Deleting fires pre_delete (trigger_celery_task); keep it from sending a real task.
        with patch("reporting_common.models.celery_app"):
            DelayedCeleryTasks.objects.filter(task_name=TASK).delete()

    def _defer(self, start, end):
        return DelayedCeleryTasks.create_or_reset_timeout(
            task_name=TASK,
            task_args=["org1234567", str(self.provider_uuid)],
            task_kwargs={"start_date": start, "end_date": end},
            provider_uuid=self.provider_uuid,
            queue_name="q",
            timeout_seconds=0,
            billing_month=date(2026, 6, 1),
            merge_date_range=True,
            keep_earlier_deadline=True,
        )

    def test_merge_during_the_sweep_is_not_lost(self):
        row = self._defer("2026-06-01", "2026-06-02")
        DelayedCeleryTasks.objects.filter(pk=row.pk).update(timeout_timestamp=timezone.now() - timedelta(minutes=1))

        sending, release = threading.Event(), threading.Event()
        fired, errors = [], []

        def send_task(name, args=None, kwargs=None, queue=None):
            fired.append(dict(kwargs))
            sending.set()
            release.wait(10)
            return MagicMock(id="task-id")

        def sweep():
            try:
                DelayedCeleryTasks.trigger_delayed_tasks()
            except Exception as error:  # surfaced through `errors`
                errors.append(error)
            finally:
                sending.set()
                connection.close()

        def merge():
            try:
                self._defer("2026-06-01", "2026-06-30")
            except Exception as error:  # surfaced through `errors`
                errors.append(error)
            finally:
                connection.close()

        with patch("reporting_common.models.celery_app") as celery_app:
            celery_app.send_task.side_effect = send_task
            sweeper = threading.Thread(target=sweep)
            sweeper.start()
            self.assertTrue(sending.wait(10), "the sweep did not fire the expired row")
            merger = threading.Thread(target=merge)
            merger.start()
            time.sleep(0.5)  # the merge runs now; with the sweep holding the row lock it waits instead
            release.set()
            sweeper.join(10)
            merger.join(10)

        self.assertEqual(errors, [])
        fired_ends = {kwargs["end_date"] for kwargs in fired}
        pending_ends = set(
            DelayedCeleryTasks.objects.filter(task_name=TASK).values_list("task_kwargs__end_date", flat=True)
        )
        self.assertIn(
            "2026-06-30",
            fired_ends | pending_ends,
            f"the merged range was lost: fired {fired_ends}, pending {pending_ends}",
        )
