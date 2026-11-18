#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the running_celery_tasks endpoint view."""
import json
import random
from unittest.mock import patch
from urllib.parse import urlencode

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse


def _celery_message(task_id):
    """Build the JSON envelope stored in a Celery Redis queue."""
    return json.dumps({"headers": {"id": task_id, "task": "masu.test.task"}}).encode()


class FakeRedisQueue:
    """Small list-backed Redis fake for queue-removal endpoint tests."""

    def __init__(self, messages, reorder_after_read=False, consume_before_remove=False):
        self.messages = list(messages)
        self.reorder_after_read = reorder_after_read
        self.consume_before_remove = consume_before_remove
        self.lrem_calls = []

    def lrange(self, queue, start, stop):
        self.assert_queue(queue)
        messages = list(self.messages[start : None if stop == -1 else stop + 1])
        if self.reorder_after_read:
            self.messages.reverse()
        return messages

    def lrem(self, queue, count, value):
        self.assert_queue(queue)
        self.lrem_calls.append((queue, count, value))
        if self.consume_before_remove:
            for index, message in enumerate(self.messages):
                if message == value:
                    del self.messages[index]
                    break
            return 0

        removed = 0
        remaining = []
        for message in self.messages:
            if message == value and removed < count:
                removed += 1
            else:
                remaining.append(message)
        self.messages = remaining
        return removed

    @staticmethod
    def assert_queue(queue):
        if not queue:
            raise AssertionError("queue name is required")


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
    @patch("masu.api.running_celery_tasks.collect_queue_metrics")
    @patch("masu.api.running_celery_tasks.redis")
    def test_clear_queue(self, mock_redis, mock_collect, _):
        """Test the GET of clear_celery_queues endpoint with specific queue."""
        expected_key = "purged_tasks"
        expected_queue_lengths = {"priority": 2}
        mock_collect.return_value = expected_queue_lengths
        mock_redis = mock_redis.Redis.return_value
        url = reverse("clear_celery_queues") + "?queue=priority"
        response = self.client.get(url)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_collect.assert_called_once()
        mock_redis.delete.assert_called_once()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.get_celery_queue_items")
    def test_celery_queue_tasks(self, mock_queue, _):
        """Test GET request returns a 200."""
        mock_queue.return_value = {}
        response = self.client.get(reverse("celery_queue_tasks"))
        self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.get_celery_queue_items")
    def test_celery_queue_tasks_invalid_queue(self, mock_queue, _):
        """Test GET request with invalid queue name returns a 400."""
        mock_queue.return_value = {}
        params = {"queue": "taco"}
        query_string = urlencode(params)
        url = reverse("celery_queue_tasks") + "?" + query_string
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.get_celery_queue_items")
    def test_celery_queue_tasks_valid_queue(self, mock_queue, _):
        """Test GET request with a valid queue name returns a 200."""
        mock_queue.return_value = {}
        params = {"queue": "summary"}
        query_string = urlencode(params)
        url = reverse("celery_queue_tasks") + "?" + query_string
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.redis.Redis")
    def test_delete_celery_queue_task_removes_exact_message_once(self, mock_redis, _):
        """Delete only the selected serialized task message."""
        target = _celery_message("task-a")
        other = _celery_message("task-b")
        fake_redis = FakeRedisQueue([other, target])
        mock_redis.return_value = fake_redis
        params = urlencode({"queue": "summary", "task_id": "task-a"})

        response = self.client.delete(f"{reverse('celery_queue_tasks')}?{params}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"queue": "summary", "task_id": "task-a", "removed": True})
        self.assertEqual(fake_redis.lrem_calls, [("summary", 1, target)])
        self.assertEqual(fake_redis.messages, [other])

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.redis.Redis")
    def test_delete_celery_queue_task_removes_one_duplicate_id(self, mock_redis, _):
        """Only one matching queue entry is removed, even when duplicated."""
        target = _celery_message("task-a")
        other = _celery_message("task-b")
        fake_redis = FakeRedisQueue([target, target, other])
        mock_redis.return_value = fake_redis
        params = urlencode({"queue": "summary", "task_id": "task-a"})

        response = self.client.delete(f"{reverse('celery_queue_tasks')}?{params}")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["removed"])
        self.assertEqual(fake_redis.lrem_calls, [("summary", 1, target)])
        self.assertEqual(fake_redis.messages, [target, other])

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.redis.Redis")
    def test_delete_celery_queue_task_rejects_missing_or_invalid_selection(self, mock_redis, _):
        """Reject missing parameters and unknown queues before touching Redis."""
        invalid_requests = (
            {},
            {"task_id": "task-a"},
            {"queue": "summary"},
            {"queue": "taco", "task_id": "task-a"},
        )

        for params in invalid_requests:
            with self.subTest(params=params):
                url = reverse("celery_queue_tasks")
                if params:
                    url += f"?{urlencode(params)}"
                response = self.client.delete(url)
                self.assertEqual(response.status_code, 400)

        mock_redis.assert_not_called()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.redis.Redis")
    def test_delete_celery_queue_task_returns_404_when_id_is_absent(self, mock_redis, _):
        """Return not found when the selected task ID is not queued."""
        fake_redis = FakeRedisQueue([_celery_message("task-b")])
        mock_redis.return_value = fake_redis
        params = urlencode({"queue": "summary", "task_id": "task-a"})

        response = self.client.delete(f"{reverse('celery_queue_tasks')}?{params}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(fake_redis.lrem_calls, [])

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.redis.Redis")
    def test_delete_celery_queue_task_returns_404_when_worker_consumes_message(self, mock_redis, _):
        """Do not report success if a worker consumes the selected message first."""
        target = _celery_message("task-a")
        fake_redis = FakeRedisQueue([target], consume_before_remove=True)
        mock_redis.return_value = fake_redis
        params = urlencode({"queue": "summary", "task_id": "task-a"})

        response = self.client.delete(f"{reverse('celery_queue_tasks')}?{params}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(fake_redis.lrem_calls, [("summary", 1, target)])
        self.assertEqual(fake_redis.messages, [])

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.redis.Redis")
    def test_delete_celery_queue_task_skips_unreadable_messages(self, mock_redis, _):
        """Ignore invalid JSON and malformed headers while searching."""
        unreadable = [b"not-json", b'{"headers": "invalid"}']
        fake_redis = FakeRedisQueue(unreadable)
        mock_redis.return_value = fake_redis
        params = urlencode({"queue": "summary", "task_id": "task-a"})

        response = self.client.delete(f"{reverse('celery_queue_tasks')}?{params}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(fake_redis.lrem_calls, [])
        self.assertEqual(fake_redis.messages, unreadable)

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.redis.Redis")
    def test_delete_celery_queue_task_removes_after_message_moves_position(self, mock_redis, _):
        """Find by exact message value even if queue order changes after lookup."""
        target = _celery_message("task-a")
        other = _celery_message("task-b")
        fake_redis = FakeRedisQueue([target, other], reorder_after_read=True)
        mock_redis.return_value = fake_redis
        params = urlencode({"queue": "summary", "task_id": "task-a"})

        response = self.client.delete(f"{reverse('celery_queue_tasks')}?{params}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake_redis.lrem_calls, [("summary", 1, target)])
        self.assertEqual(fake_redis.messages, [other])

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.redis.Redis")
    def test_delete_celery_queue_task_preserves_other_messages_for_generated_queues(self, mock_redis, _):
        """Remove one selected task while preserving varied unrelated messages and their order."""
        rng = random.Random(8404)

        for case in range(25):
            target_id = f"target-{case}"
            other_ids = [f"other-{case}-{index}" for index in range(rng.randrange(1, 8))]
            messages = [_celery_message(task_id) for task_id in other_ids]
            target = _celery_message(target_id)
            position = rng.randrange(len(messages) + 1)
            messages.insert(position, target)
            expected_remaining = messages[:position] + messages[position + 1 :]
            fake_redis = FakeRedisQueue(messages)
            mock_redis.return_value = fake_redis
            params = urlencode({"queue": "summary", "task_id": target_id})

            with self.subTest(case=case, position=position):
                response = self.client.delete(f"{reverse('celery_queue_tasks')}?{params}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(fake_redis.messages, expected_remaining)
                self.assertEqual(fake_redis.lrem_calls, [("summary", 1, target)])

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.get_celery_queue_items")
    @patch("masu.api.running_celery_tasks.redis.Redis")
    def test_celery_queue_tasks_get_is_read_only(self, mock_redis, mock_queue, _):
        """Keep existing queue listing read-only."""
        mock_queue.return_value = {"summary": []}

        response = self.client.get(reverse("celery_queue_tasks"))

        self.assertEqual(response.status_code, 200)
        mock_queue.assert_called_once_with(queue_name=None, task_name=None)
        mock_redis.assert_not_called()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.running_celery_tasks.redis.Redis")
    def test_celery_queue_tasks_post_is_not_allowed(self, mock_redis, _):
        """Do not allow POST to the existing queue task endpoint."""
        response = self.client.post(reverse("celery_queue_tasks"))

        self.assertEqual(response.status_code, 405)
        mock_redis.assert_not_called()
