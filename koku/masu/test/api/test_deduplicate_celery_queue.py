#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the deduplicate_celery_queue endpoint."""
import base64
import json
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from masu.api.running_celery_tasks import _task_identity

QUEUE = "summary_penalty"


def message(
    task="masu.processor.tasks.update_openshift_on_cloud",
    args=("acct1", "ocp-1", "2026-08-01"),
    kwargs=None,
    chain=None,
):
    """Build a Celery message as kombu stores it: unique id per message, same body for duplicates."""
    kwargs = kwargs or {}
    body = base64.b64encode(json.dumps([list(args), kwargs, {"callbacks": None, "chain": chain}]).encode()).decode()
    headers = {"task": task, "id": str(uuid4()), "argsrepr": repr(tuple(args))[:20], "kwargsrepr": repr(kwargs)}
    return json.dumps({"body": body, "headers": headers, "properties": {"body_encoding": "base64"}}).encode()


class FakeRedisList:
    """A Redis list with LRANGE/LREM semantics; LPUSH adds at the left, workers pop from the right."""

    def __init__(self, items):
        self.items = list(items)

    def lrange(self, name, start, end):
        return list(self.items)

    def lrem(self, name, count, value):
        removed = 0
        for i, item in enumerate(list(self.items)):
            if item == value and removed < count:
                self.items.pop(i - removed)
                removed += 1
        return removed


@override_settings(ROOT_URLCONF="masu.urls")
@patch("koku.middleware.MASU", return_value=True)
class DeduplicateCeleryQueueTests(TestCase):
    """Test cases for the deduplicate_celery_queue endpoint."""

    def setUp(self):
        self.url = reverse("deduplicate_celery_queue") + f"?queue={QUEUE}"

    def _client(self, items):
        fake = FakeRedisList(items)
        patcher = patch("masu.api.running_celery_tasks._redis_client", return_value=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def test_get_reports_without_removing(self, _):
        """GET only simulates: duplicates are reported, the queue is unchanged."""
        dup_a, dup_b, other = message(), message(), message(args=("acct2", "ocp-2", "2026-09-01"))
        fake = self._client([dup_a, other, dup_b])
        body = self.client.get(self.url).json()
        self.assertEqual((body["queued"], body["duplicates"], body["removed"], body["simulate"]), (3, 1, 0, True))
        self.assertEqual(body["duplicated_tasks"][0]["extra_copies"], 1)
        self.assertEqual(len(fake.items), 3)

    def test_delete_keeps_the_copy_that_runs_first(self, _):
        """DELETE removes extra copies and keeps the rightmost one (next to be popped)."""
        older, middle, newest = message(), message(), message()
        other = message(task="masu.processor.tasks.summarize_reports")
        fake = self._client([newest, other, middle, older])
        body = self.client.delete(self.url).json()
        self.assertEqual((body["duplicates"], body["removed"], body["simulate"]), (2, 2, False))
        self.assertEqual(fake.items, [other, older])

    def test_different_kwargs_are_not_duplicates(self, _):
        """Same task and args with another manifest/tracing id is a different task."""
        fake = self._client([message(kwargs={"manifest_id": 1}), message(kwargs={"manifest_id": 2})])
        body = self.client.delete(self.url).json()
        self.assertEqual((body["duplicates"], body["removed"]), (0, 0))
        self.assertEqual(len(fake.items), 2)

    def test_message_taken_meanwhile_is_not_counted(self, _):
        """A duplicate popped by a worker before LREM is simply not found."""
        first, second = message(), message()
        fake = self._client([first, second])
        original_lrem = fake.lrem

        def lrem_after_pop(name, count, value):
            fake.items.remove(value)  # a worker took it first
            return original_lrem(name, count, value)

        fake.lrem = lrem_after_pop
        body = self.client.delete(self.url).json()
        self.assertEqual((body["duplicates"], body["removed"]), (1, 0))

    def test_unreadable_messages_are_left_alone(self, _):
        """Messages that are not Celery task JSON are neither counted nor removed."""
        fake = self._client([b"not json", b"not json", message()])
        body = self.client.delete(self.url).json()
        self.assertEqual((body["queued"], body["duplicates"], body["removed"]), (3, 0, 0))
        self.assertEqual(len(fake.items), 3)

    def test_truncated_reprs_are_not_compared(self, _):
        """Tasks whose argsrepr headers match after truncation but whose args differ are kept."""
        fake = self._client(
            [message(args=("acct1", "ocp-1", "2026-08-01")), message(args=("acct1", "ocp-1", "2026-09-01"))]
        )
        body = self.client.delete(self.url).json()
        self.assertEqual((body["duplicates"], body["removed"]), (0, 0))
        self.assertEqual(len(fake.items), 2)

    def test_different_follow_up_tasks_are_not_duplicates(self, _):
        """A copy that carries a chain is not a duplicate of one without it."""
        chained = message(chain=[{"task": "masu.processor.tasks.mark_manifest_complete", "args": [1]}])
        fake = self._client([chained, message()])
        body = self.client.delete(self.url).json()
        self.assertEqual((body["duplicates"], body["removed"]), (0, 0))
        self.assertEqual(len(fake.items), 2)

    def test_post_is_not_allowed(self, _):
        """Only GET (simulate) and DELETE are accepted."""
        self._client([message(), message()])
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_invalid_queue(self, _):
        """An unknown queue is rejected."""
        response = self.client.get(reverse("deduplicate_celery_queue") + "?queue=nope")
        self.assertEqual(response.status_code, 400)

    def test_task_identity(self, _):
        """The identity is task name, args and kwargs; the per-message id is ignored."""
        self.assertEqual(_task_identity(message()), _task_identity(message()))
        self.assertIsNone(_task_identity(b"{}"))
        self.assertIsNone(_task_identity(None))
