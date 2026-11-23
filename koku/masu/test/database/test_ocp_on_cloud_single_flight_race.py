#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Simultaneous update_openshift_on_cloud runs of one work must not overlap (COST-8410).

The WorkerCache check-then-set gate cannot stop two workers that pick up duplicate
messages at the same time: both pass the gate and both used to run. Under the
single-flight flag both runs also go through the source-pair month advisory lock, so
exactly one of them writes and the other hands its window to the delayed tasks
instead of republishing itself, which is what used to amplify the queue.
"""
import threading
import uuid
from datetime import date
from unittest.mock import patch

import django.test
from django.db import connection

from api.provider.models import Provider
from masu.processor.ocp_on_cloud_run_lock import ocp_on_cloud_month_locks
from masu.processor.tasks import update_openshift_on_cloud
from masu.processor.tasks import UPDATE_OPENSHIFT_ON_CLOUD_TASK
from reporting_common.models import DelayedCeleryTasks

OCP_PROVIDER_UUID = "11112222-3333-4444-5555-666677778888"
INFRA_PROVIDER_UUID = "99998888-7777-6666-5555-444433332222"


class OcpOnCloudSingleFlightRaceTest(django.test.TransactionTestCase):
    """Two simultaneous update_openshift_on_cloud runs of the same source pair and month."""

    def _fixture_teardown(self):
        """Skip the TRUNCATE flush: the django-tenants FK graph breaks it. tearDown cleans up."""

    def setUp(self):
        from koku.koku_test_runner import KokuTestRunner

        self.schema = KokuTestRunner.schema
        self._clear_rows()

    def tearDown(self):
        self._clear_rows()

    def _clear_rows(self):
        # Deleting fires pre_delete (trigger_celery_task); keep it from sending a real task.
        with patch("reporting_common.models.celery_app"):
            DelayedCeleryTasks.objects.filter(task_name=UPDATE_OPENSHIFT_ON_CLOUD_TASK).delete()

    def _run(self, start_date, end_date):
        update_openshift_on_cloud(
            self.schema,
            OCP_PROVIDER_UUID,
            INFRA_PROVIDER_UUID,
            Provider.PROVIDER_AWS,
            start_date,
            end_date,
        )

    def test_simultaneous_runs_of_one_work_do_not_overlap(self):
        a_started, release_a = threading.Event(), threading.Event()
        errors = []

        def fast_locks(openshift_provider_uuid, infrastructure_provider_uuid, months):
            return ocp_on_cloud_month_locks(
                openshift_provider_uuid, infrastructure_provider_uuid, months, wait_seconds=1, poll_seconds=0.05
            )

        def update_then_pause(*args, **kwargs):
            a_started.set()
            release_a.wait(15)

        with (
            patch("masu.processor.tasks.is_ocp_on_cloud_single_flight_enabled", return_value=True),
            patch("masu.processor.tasks.ReportSummaryUpdater") as mock_updater,
            patch("masu.processor.tasks.WorkerCache") as mock_worker_cache,
            patch("masu.processor.tasks.update_cost_model_costs.s"),
            patch("masu.processor.tasks.validate_daily_data.s"),
            patch("masu.processor.tasks.ocp_on_cloud_month_locks", side_effect=fast_locks),
        ):
            mock_worker_cache.return_value.single_task_is_running.return_value = False
            update_summary_tables = mock_updater.return_value.update_openshift_on_cloud_summary_tables
            update_summary_tables.side_effect = update_then_pause

            def run_a():
                try:
                    self._run(date(2026, 6, 1), date(2026, 6, 10))
                except Exception as error:  # surfaced through `errors` below
                    errors.append(error)
                finally:
                    a_started.set()
                    connection.close()

            def run_b():
                try:
                    self._run(date(2026, 6, 5), date(2026, 6, 12))
                except Exception as error:  # surfaced through `errors` below
                    errors.append(error)
                finally:
                    connection.close()

            thread_a = threading.Thread(target=run_a)
            thread_a.start()
            self.assertTrue(a_started.wait(15), "run A never reached its summary update")
            thread_b = threading.Thread(target=run_b)
            thread_b.start()
            thread_b.join(30)
            release_a.set()
            thread_a.join(30)

            self.assertEqual(errors, [])
            # Exactly one of the two runs wrote; the other became one delayed successor.
            self.assertEqual(update_summary_tables.call_count, 1, "both runs must not write")
            row = DelayedCeleryTasks.objects.get(
                task_name=UPDATE_OPENSHIFT_ON_CLOUD_TASK, provider_uuid=OCP_PROVIDER_UUID
            )
            self.assertEqual(row.task_args, [self.schema, OCP_PROVIDER_UUID, INFRA_PROVIDER_UUID])
            self.assertEqual(
                (row.task_kwargs["start_date"], row.task_kwargs["end_date"]), ("2026-06-05", "2026-06-12")
            )
            self.assertEqual(row.metadata.get("work_key"), INFRA_PROVIDER_UUID)

            # Once run A is done the source pair month is free again: the successor's
            # window (or a later copy) writes normally and does not add a second row.
            self._run(date(2026, 6, 5), date(2026, 6, 12))
            self.assertEqual(update_summary_tables.call_count, 2)
            self.assertEqual(
                DelayedCeleryTasks.objects.filter(
                    task_name=UPDATE_OPENSHIFT_ON_CLOUD_TASK, provider_uuid=OCP_PROVIDER_UUID
                ).count(),
                1,
            )


class DelayedTaskFirstCreationRaceTest(django.test.TransactionTestCase):
    """Two concurrent first-time create_or_reset_timeout calls with one key make one row."""

    CREATION_RACE_TASK = "masu.test.delayed-creation-race"

    def _fixture_teardown(self):
        """Skip the TRUNCATE flush: the django-tenants FK graph breaks it. tearDown cleans up."""

    def tearDown(self):
        # Deleting fires pre_delete (trigger_celery_task); keep it from sending a real task.
        with patch("reporting_common.models.celery_app"):
            DelayedCeleryTasks.objects.filter(task_name=self.CREATION_RACE_TASK).delete()

    def test_concurrent_first_creations_coalesce_into_one_row(self):
        """Without the creation lock an empty SELECT ... FOR UPDATE locks nothing and both insert."""
        provider_uuid = uuid.uuid4()
        barrier = threading.Barrier(2)
        errors, row_ids = [], []

        def create():
            try:
                barrier.wait(15)
                row = DelayedCeleryTasks.create_or_reset_timeout(
                    task_name=self.CREATION_RACE_TASK,
                    task_args=["org1234567", str(provider_uuid)],
                    task_kwargs={"start_date": "2026-06-01", "end_date": "2026-06-10"},
                    provider_uuid=provider_uuid,
                    queue_name="q",
                    billing_month=date(2026, 6, 1),
                    merge_date_range=True,
                    keep_earlier_deadline=True,
                    work_key="infra-uuid",
                )
                row_ids.append(row.id)
            except Exception as error:  # surfaced through `errors` below
                errors.append(error)
            finally:
                connection.close()

        threads = [threading.Thread(target=create) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)

        self.assertEqual(errors, [])
        self.assertEqual(len(row_ids), 2)
        self.assertEqual(len(set(row_ids)), 1, "both calls must return the same row")
        self.assertEqual(DelayedCeleryTasks.objects.filter(task_name=self.CREATION_RACE_TASK).count(), 1)
