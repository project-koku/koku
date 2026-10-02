#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test staged ingress claim and reconciliation."""
import tempfile
from datetime import timedelta
from unittest.mock import patch

import requests_mock
from django.conf import settings
from django.db import OperationalError
from django.utils import timezone
from kombu.exceptions import OperationalError as KombuOperationalError

from masu.config import Config
from masu.external.downloader.ocp.exceptions import FAILURE_CONFIRM_STATUS
from masu.external.downloader.ocp.exceptions import KafkaMsgHandlerError
from masu.external.downloader.ocp.exceptions import SUCCESS_CONFIRM_STATUS
from masu.external.downloader.ocp.payload_landing import claim_ingress_staging_row
from masu.external.downloader.ocp.payload_landing import expire_ingress_staging
from masu.external.downloader.ocp.payload_landing import mark_processed
from masu.external.downloader.ocp.payload_landing import PROCESS_STAGED_INGRESS_TASK
from masu.external.downloader.ocp.payload_landing import reconcile_ingress_staging
from masu.external.downloader.ocp.payload_landing import register_ingress_staging_marker
from masu.external.downloader.ocp.payload_landing import REGISTER_INGRESS_STAGING_TASK
from masu.external.downloader.ocp.payload_landing import release_for_retry
from masu.external.downloader.ocp.payload_landing import stage_ingress_s3_inbox
from masu.external.downloader.ocp.payload_landing.keys import _receipt_key
from masu.test import MasuTestCase
from reporting_common.models import IngressStagingPayload
from reporting_common.models import IngressStagingState


class IngressStagingTests(MasuTestCase):
    """Tests for the ingress staging row."""

    def setUp(self):
        super().setUp()
        list_markers = patch(
            "masu.external.downloader.ocp.payload_landing.register._list_pending_markers",
            return_value=([], None),
        )
        self.list_markers = list_markers.start()
        self.addCleanup(list_markers.stop)

    def _pending_row(self, request_id, **kwargs):
        stored_at = timezone.now() - timedelta(minutes=5)
        defaults = {
            "request_id": request_id,
            "payload": {"request_id": request_id, "b64_identity": "secret-identity", "url": "http://example"},
            "s3_key": f"data/ingress_staging/{request_id}.tar.gz",
            "org_id": self.org_id,
            "cluster_id": "cluster-1",
            "assembly_id": "assembly-1",
            "account": self.acct,
            "state": IngressStagingState.PENDING,
            "attempts": 0,
            "stored_at": stored_at,
            "not_before": stored_at,
        }
        defaults.update(kwargs)
        return IngressStagingPayload.objects.create(**defaults)

    def test_claim_is_single_winner(self):
        """Test that a second claim loses while the first lease is active."""
        row = self._pending_row("claim-one")
        first = claim_ingress_staging_row(row.request_id)
        second = claim_ingress_staging_row(row.request_id)

        self.assertEqual(first.state, IngressStagingState.PROCESSING)
        self.assertEqual(first.attempts, 1)
        self.assertIsNotNone(first.claim_token)
        self.assertIsNone(second)
        row.refresh_from_db()
        self.assertEqual(row.state, IngressStagingState.PROCESSING)
        self.assertEqual(row.attempts, 1)
        self.assertEqual(row.claim_token, first.claim_token)

    def test_claim_leaves_exhausted_row_unchanged(self):
        """Test that a row at the retry limit is not claimed and is not marked failed here."""
        row = self._pending_row("claim-max", attempts=settings.MAX_UPDATE_RETRIES)
        self.assertIsNone(claim_ingress_staging_row(row.request_id))
        row.refresh_from_db()
        self.assertEqual(row.state, IngressStagingState.PENDING)
        self.assertEqual(row.attempts, settings.MAX_UPDATE_RETRIES)
        self.assertIsNone(row.last_error)

    def test_lost_claim_cannot_finish_the_row(self):
        """Test that a worker whose lease was taken cannot write processed or pending."""
        row = self._pending_row("fence-lost")
        first = claim_ingress_staging_row(row.request_id)
        stolen = claim_ingress_staging_row(row.request_id, now=timezone.now() + timedelta(hours=3))

        self.assertIsNotNone(stolen)
        self.assertNotEqual(stolen.claim_token, first.claim_token)
        self.assertFalse(mark_processed(row.request_id, first.claim_token))
        self.assertFalse(release_for_retry(row.request_id, first.claim_token, RuntimeError("late")))
        row.refresh_from_db()
        self.assertEqual(row.state, IngressStagingState.PROCESSING)
        self.assertEqual(row.claim_token, stolen.claim_token)
        self.assertEqual(row.attempts, stolen.attempts)
        self.assertIsNotNone(row.payload)

    def test_release_marks_exhausted_claim_failed(self):
        """Test that the retry limit is applied by the worker that still holds the token."""
        row = self._pending_row("release-max", attempts=settings.MAX_UPDATE_RETRIES - 1)
        claimed = claim_ingress_staging_row(row.request_id)
        self.assertTrue(release_for_retry(row.request_id, claimed.claim_token, RuntimeError("hive down")))
        row.refresh_from_db()
        self.assertEqual(row.state, IngressStagingState.FAILED)
        self.assertIn("RuntimeError", row.last_error)
        self.assertIsNone(row.claim_token)
        self.assertIsNotNone(row.payload)

    def test_reconcile_enqueues_stale_rows_only(self):
        """Test that the beat skips fresh pending rows and rows waiting on backoff."""
        stale = self._pending_row("stale-row")
        self._pending_row("fresh-row", stored_at=timezone.now(), not_before=timezone.now())
        self._pending_row("waiting-row", not_before=timezone.now() + timedelta(hours=1))
        expired = self._pending_row(
            "expired-lease",
            state=IngressStagingState.PROCESSING,
            claimed_at=timezone.now() - timedelta(hours=3),
            attempts=1,
        )
        with patch("masu.external.downloader.ocp.payload_landing.reconcile.celery_app.send_task") as mock_enqueue:
            reconcile_ingress_staging()

        enqueued = [enqueued_call.kwargs["args"][0] for enqueued_call in mock_enqueue.call_args_list]
        self.assertCountEqual(enqueued, [stale.request_id, expired.request_id])

    def test_reconcile_enqueues_each_stale_row_once(self):
        """Test that a second beat does not publish a row it already handed off."""
        stale = self._pending_row("enqueue-once")
        expired = self._pending_row(
            "enqueue-once-expired",
            state=IngressStagingState.PROCESSING,
            claimed_at=timezone.now() - timedelta(hours=3),
            attempts=1,
        )
        with patch("masu.external.downloader.ocp.payload_landing.reconcile.celery_app.send_task") as mock_enqueue:
            reconcile_ingress_staging()
            reconcile_ingress_staging()

        enqueued = [enqueued_call.kwargs["args"][0] for enqueued_call in mock_enqueue.call_args_list]
        self.assertCountEqual(enqueued, [stale.request_id, expired.request_id])

    def test_reconcile_swallows_broker_errors(self):
        """Test that a broker error on one row does not fail the reconciler."""
        self._pending_row("broker-down")
        with patch(
            "masu.external.downloader.ocp.payload_landing.reconcile.celery_app.send_task",
            side_effect=KombuOperationalError("broker down"),
        ):
            reconcile_ingress_staging()
        row = IngressStagingPayload.objects.get(request_id="broker-down")
        self.assertIsNone(row.enqueued_at)

    def test_stage_http_429_rewinds(self):
        """Test that a rate-limited quarantine download is retried by the consumer."""
        url = "http://insights-upload.example/quarantine/file"
        with (
            requests_mock.Mocker() as mock_download,
            patch("masu.external.downloader.ocp.payload_landing.listener._s3_key_exists", return_value=False),
        ):
            mock_download.get(url, status_code=429)
            with tempfile.TemporaryDirectory() as fake_data_dir:
                with patch.object(Config, "DATA_DIR", fake_data_dir):
                    with self.assertRaises(KafkaMsgHandlerError):
                        stage_ingress_s3_inbox(
                            "retry-429", {"url": url, "org_id": self.org_id}, {"org_id": self.org_id}
                        )

    def test_stage_http_404_confirms_failure(self):
        """Test that a missing quarantine object is confirmed as a failure."""
        url = "http://insights-upload.example/quarantine/missing"
        with (
            requests_mock.Mocker() as mock_download,
            patch("masu.external.downloader.ocp.payload_landing.listener._s3_key_exists", return_value=False),
        ):
            mock_download.get(url, status_code=404)
            with tempfile.TemporaryDirectory() as fake_data_dir:
                with patch.object(Config, "DATA_DIR", fake_data_dir):
                    status = stage_ingress_s3_inbox(
                        "gone-404", {"url": url, "org_id": self.org_id}, {"org_id": self.org_id}
                    )
        self.assertEqual(status, FAILURE_CONFIRM_STATUS)

    def test_expire_deletes_old_processed_rows_only(self):
        """Test that retention removes processed rows and leaves failed rows."""
        old = self._pending_row(
            "expire-old",
            state=IngressStagingState.PROCESSED,
            stored_at=timezone.now() - timedelta(days=8),
        )
        self._pending_row(
            "expire-recent",
            state=IngressStagingState.PROCESSED,
            stored_at=timezone.now() - timedelta(days=1),
        )
        failed = self._pending_row(
            "expire-failed",
            state=IngressStagingState.FAILED,
            stored_at=timezone.now() - timedelta(days=8),
        )
        with patch(
            "masu.external.downloader.ocp.payload_landing.expire.delete_s3_objects",
            return_value=[{"Key": old.s3_key}],
        ) as mock_delete:
            expire_ingress_staging()

        self.assertCountEqual(mock_delete.call_args.args[1], [old.s3_key, _receipt_key(old.request_id)])

        self.assertFalse(IngressStagingPayload.objects.filter(request_id=old.request_id).exists())
        self.assertTrue(IngressStagingPayload.objects.filter(request_id="expire-recent").exists())
        failed.refresh_from_db()
        self.assertEqual(failed.state, IngressStagingState.FAILED)

    def _marker_document(self, request_id, s3_key, identity="secret-identity"):
        return {
            "request_id": request_id,
            "s3_key": s3_key,
            "org_id": self.org_id,
            "cluster_id": "cluster-1",
            "assembly_id": "assembly-1",
            "account": self.acct,
            "payload": {
                "request_id": request_id,
                "org_id": self.org_id,
                "account": self.acct,
                "url": "http://example",
                "b64_identity": identity,
            },
        }

    def test_s3_inbox_redelivery_heads_receipt_and_skips_upload(self):
        """Test that a stored receipt confirms without another quarantine download or tar upload."""
        request_id = "inbox-redelivery"
        with (
            patch(
                "masu.external.downloader.ocp.payload_landing.listener._s3_key_exists", return_value=True
            ) as mock_head,
            patch("masu.external.downloader.ocp.payload_landing.listener._copy_s3_key") as mock_copy_key,
            patch("masu.external.downloader.ocp.payload_landing.objects.copy_data_to_s3_bucket") as mock_upload,
            patch("masu.external.downloader.ocp.download.download_payload") as mock_download,
            patch("masu.external.downloader.ocp.payload_landing.listener.celery_app.send_task") as mock_enqueue,
            patch.object(IngressStagingPayload.objects, "get_or_create", side_effect=OperationalError("db down")),
        ):
            status = stage_ingress_s3_inbox(
                request_id,
                {"url": "http://example/quarantine", "org_id": self.org_id, "b64_identity": "secret-identity"},
                {"org_id": self.org_id},
            )

        self.assertEqual(status, SUCCESS_CONFIRM_STATUS)
        self.assertEqual(mock_head.call_args.args[1], _receipt_key(request_id))
        mock_copy_key.assert_called_once()
        self.assertEqual(mock_copy_key.call_args.args[1], _receipt_key(request_id))
        mock_upload.assert_not_called()
        mock_download.assert_not_called()
        mock_enqueue.assert_called_once_with(REGISTER_INGRESS_STAGING_TASK, args=[request_id], queue="ingress")
        self.assertFalse(IngressStagingPayload.objects.filter(request_id=request_id).exists())

    def test_register_leaves_marker_when_upsert_fails(self):
        """Test that a database error keeps the pending marker and does not enqueue extract."""
        request_id = "marker-db-down"
        document = self._marker_document(request_id, f"data/ingress_staging/{request_id}.tar.gz")
        with (
            patch("masu.external.downloader.ocp.payload_landing.register._read_marker_json", return_value=document),
            patch("masu.external.downloader.ocp.payload_landing.register.delete_s3_objects") as mock_delete,
            patch("masu.external.downloader.ocp.payload_landing.register.celery_app.send_task") as mock_enqueue,
            patch("masu.external.kafka_msg_handler.close_and_set_db_connection"),
            patch.object(IngressStagingPayload.objects, "get_or_create", side_effect=OperationalError("db down")),
        ):
            register_ingress_staging_marker(request_id)

        mock_delete.assert_not_called()
        mock_enqueue.assert_not_called()
        self.assertFalse(IngressStagingPayload.objects.filter(request_id=request_id).exists())

    def test_register_does_not_reset_processed_row(self):
        """Test that registering a request that is already processed leaves that row alone."""
        request_id = "register-processed"
        row = self._pending_row(
            request_id,
            state=IngressStagingState.PROCESSED,
            payload={"request_id": request_id, "b64_identity": "original-secret"},
        )
        document = self._marker_document(request_id, row.s3_key, identity="replacement-secret")
        with (
            patch("masu.external.downloader.ocp.payload_landing.register._read_marker_json", return_value=document),
            patch(
                "masu.external.downloader.ocp.payload_landing.register.delete_s3_objects",
                return_value=[{"Key": "pending"}],
            ),
            patch("masu.external.downloader.ocp.payload_landing.register.celery_app.send_task"),
        ):
            register_ingress_staging_marker(request_id)
            register_ingress_staging_marker(request_id)

        row.refresh_from_db()
        self.assertEqual(row.state, IngressStagingState.PROCESSED)
        self.assertEqual(row.payload["b64_identity"], "original-secret")
        self.assertEqual(row.s3_key, document["s3_key"])

    def test_reconcile_registers_pending_markers(self):
        """Test that the beat inserts a row from a pending marker and records the marker gauges."""
        request_id = "marker-from-beat"
        s3_key = f"data/ingress_staging/{self.org_id}/cluster-1/{request_id}.tar.gz"
        document = self._marker_document(request_id, s3_key)
        pending_key = f"data/ingress_staging/pending/{request_id}.json"
        self.list_markers.return_value = ([pending_key], timezone.now() - timedelta(minutes=10))
        with (
            patch("masu.external.downloader.ocp.payload_landing.register._read_marker_json", return_value=document),
            patch(
                "masu.external.downloader.ocp.payload_landing.register.delete_s3_objects",
                return_value=[{"Key": pending_key}],
            ) as mock_delete,
            patch("masu.external.downloader.ocp.payload_landing.register.celery_app.send_task") as mock_enqueue,
            patch(
                "masu.external.downloader.ocp.payload_landing.register.INGRESS_STAGING_PENDING_MARKERS"
            ) as mock_count,
            patch(
                "masu.external.downloader.ocp.payload_landing.register.INGRESS_STAGING_PENDING_MARKER_OLDEST_AGE"
            ) as mock_age,
        ):
            reconcile_ingress_staging()

        row = IngressStagingPayload.objects.get(request_id=request_id)
        self.assertEqual(row.state, IngressStagingState.PENDING)
        self.assertEqual(row.s3_key, s3_key)
        self.assertEqual(row.cluster_id, "cluster-1")
        self.assertEqual(row.payload["b64_identity"], "secret-identity")
        mock_delete.assert_called_once_with(request_id, [pending_key], {})
        mock_enqueue.assert_called_once_with(PROCESS_STAGED_INGRESS_TASK, args=[request_id], queue="ingress")
        mock_count.set.assert_called_once_with(1)
        self.assertGreater(mock_age.set.call_args.args[0], 0)
