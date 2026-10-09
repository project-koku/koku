#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test staged ingress claim and reconciliation."""
import io
import json
import tempfile
import uuid
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

import requests_mock
from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError
from django.conf import settings
from django.db import OperationalError
from django.test import SimpleTestCase
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
from masu.external.downloader.ocp.payload_landing import record_line_item_handoff
from masu.external.downloader.ocp.payload_landing import register_ingress_staging_marker
from masu.external.downloader.ocp.payload_landing import REGISTER_INGRESS_STAGING_TASK
from masu.external.downloader.ocp.payload_landing import release_for_retry
from masu.external.downloader.ocp.payload_landing import stage_ingress_s3_inbox
from masu.external.downloader.ocp.payload_landing.constants import INGRESS_STAGING_RECONCILE_BATCH
from masu.external.downloader.ocp.payload_landing.keys import _pending_marker_key
from masu.external.downloader.ocp.payload_landing.keys import _pending_marker_prefix
from masu.external.downloader.ocp.payload_landing.keys import _receipt_key
from masu.external.downloader.ocp.payload_landing.objects import _list_pending_markers
from masu.external.downloader.ocp.payload_landing.objects import _read_marker_json
from masu.external.downloader.ocp.payload_landing.objects import _s3_key_exists
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

    def test_release_returns_row_to_pending_with_backoff(self):
        """Test that a retriable failure sets pending state and exponential not_before."""
        row = self._pending_row("release-retry")
        claimed = claim_ingress_staging_row(row.request_id)
        before = timezone.now()
        self.assertTrue(release_for_retry(row.request_id, claimed.claim_token, ValueError("transient")))
        row.refresh_from_db()
        self.assertEqual(row.state, IngressStagingState.PENDING)
        self.assertIsNone(row.claim_token)
        self.assertEqual(row.attempts, 1)
        self.assertIn("ValueError", row.last_error)
        self.assertGreaterEqual(row.not_before, before + timedelta(minutes=1) - timedelta(seconds=2))
        self.assertLessEqual(row.not_before, before + timedelta(minutes=1) + timedelta(seconds=2))

    @patch("masu.external.downloader.ocp.payload_landing.claim._log_lost_claim")
    @patch("masu.external.downloader.ocp.payload_landing.claim._claim_filter")
    def test_release_for_retry_lost_during_retry_update(self, mock_claim_filter, mock_log_lost):
        """Test that a lost token during the pending update does not write retry state."""
        row = MagicMock()
        row.attempts = 2
        claim_token = uuid.uuid4()
        mock_qs = MagicMock()
        mock_qs.first.return_value = row
        mock_qs.update.return_value = 0
        mock_claim_filter.return_value = mock_qs

        self.assertFalse(release_for_retry("retry-lost", claim_token, RuntimeError("race")))
        mock_log_lost.assert_called_once_with("retry-lost", "retry")
        mock_qs.update.assert_called_once()
        update_kwargs = mock_qs.update.call_args.kwargs
        self.assertEqual(update_kwargs["state"], IngressStagingState.PENDING)
        self.assertEqual(update_kwargs["last_error"], "RuntimeError: race")
        self.assertIsNone(update_kwargs["claim_token"])
        expected_not_before = timezone.now() + timedelta(minutes=2)
        self.assertAlmostEqual(
            update_kwargs["not_before"].timestamp(),
            expected_not_before.timestamp(),
            delta=2,
        )

    def test_reconcile_fails_exhausted_expired_lease(self):
        """Test that reconciler fails processing rows stuck after max retries and lease expiry."""
        row = self._pending_row(
            "stuck-max",
            state=IngressStagingState.PROCESSING,
            claimed_at=timezone.now() - timedelta(hours=3),
            attempts=settings.MAX_UPDATE_RETRIES,
            claim_token=uuid.uuid4(),
        )
        with patch("masu.external.downloader.ocp.payload_landing.reconcile.celery_app.send_task") as mock_enqueue:
            reconcile_ingress_staging()

        mock_enqueue.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.state, IngressStagingState.FAILED)
        self.assertIn("LeaseExpired", row.last_error)
        self.assertIsNone(row.claim_token)

    def test_reconcile_skips_processing_rows_waiting_on_ocp_handoff(self):
        """Test that an expired worker lease does not reclaim a row handed off to OCP."""
        handoff = self._pending_row(
            "ocp-handoff",
            state=IngressStagingState.PROCESSING,
            claimed_at=timezone.now() - timedelta(hours=3),
            enqueued_at=timezone.now() - timedelta(hours=1),
            attempts=1,
            claim_token=uuid.uuid4(),
        )
        with patch("masu.external.downloader.ocp.payload_landing.reconcile.celery_app.send_task") as mock_enqueue:
            reconcile_ingress_staging()

        mock_enqueue.assert_not_called()
        handoff.refresh_from_db()
        self.assertEqual(handoff.state, IngressStagingState.PROCESSING)
        self.assertEqual(handoff.attempts, 1)

    def test_claim_respects_ocp_handoff_window(self):
        """Test that a second claim loses while line items wait on the OCP queue."""
        row = self._pending_row("handoff-claim")
        first = claim_ingress_staging_row(row.request_id)
        record_line_item_handoff(row.request_id, first.claim_token, now=timezone.now() - timedelta(hours=1))
        row.claimed_at = timezone.now() - timedelta(hours=3)
        row.save(update_fields=["claimed_at"])
        self.assertIsNone(claim_ingress_staging_row(row.request_id))

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
        self.assertIsNone(row.reconciled_at)

    def test_reconcile_does_not_block_claim_after_expired_processing(self):
        """Test that reconciler publish-once does not set the OCP handoff lease."""
        row = self._pending_row(
            "reconcile-then-claim",
            state=IngressStagingState.PROCESSING,
            claimed_at=timezone.now() - timedelta(hours=3),
            attempts=1,
            claim_token=uuid.uuid4(),
        )
        with patch("masu.external.downloader.ocp.payload_landing.reconcile.celery_app.send_task"):
            reconcile_ingress_staging()

        row.refresh_from_db()
        self.assertIsNotNone(row.reconciled_at)
        self.assertIsNone(row.enqueued_at)
        claimed = claim_ingress_staging_row(row.request_id)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.state, IngressStagingState.PROCESSING)

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

    def test_expire_loops_until_backlog_drained(self):
        """Test that one hourly run deletes more than a single reconcile batch."""
        old_stored = timezone.now() - timedelta(days=8)
        row_count = INGRESS_STAGING_RECONCILE_BATCH + 25
        for index in range(row_count):
            self._pending_row(
                f"expire-batch-{index}",
                state=IngressStagingState.PROCESSED,
                stored_at=old_stored,
            )
        with patch(
            "masu.external.downloader.ocp.payload_landing.expire.delete_s3_objects",
            return_value=[{"Key": "deleted"}],
        ) as mock_delete:
            deleted = expire_ingress_staging()

        self.assertEqual(deleted, row_count)
        self.assertEqual(mock_delete.call_count, 2)
        self.assertFalse(
            IngressStagingPayload.objects.filter(
                state=IngressStagingState.PROCESSED,
                stored_at__lte=old_stored,
            ).exists()
        )

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

    def test_register_falls_back_to_receipt_when_pending_gone(self):
        """Test that a missing pending marker still registers from the receipt."""
        request_id = "marker-receipt-fallback"
        s3_key = f"data/ingress_staging/{request_id}.tar.gz"
        document = self._marker_document(request_id, s3_key)

        def read_marker(key):
            if key == _pending_marker_key(request_id):
                return None
            if key == _receipt_key(request_id):
                return document
            self.fail(f"unexpected marker key {key}")

        with (
            patch(
                "masu.external.downloader.ocp.payload_landing.register._read_marker_json",
                side_effect=read_marker,
            ),
            patch("masu.external.downloader.ocp.payload_landing.register.delete_s3_objects") as mock_delete,
            patch("masu.external.downloader.ocp.payload_landing.register.celery_app.send_task") as mock_enqueue,
        ):
            register_ingress_staging_marker(request_id)

        row = IngressStagingPayload.objects.get(request_id=request_id)
        self.assertEqual(row.s3_key, s3_key)
        self.assertEqual(row.state, IngressStagingState.PENDING)
        mock_delete.assert_not_called()
        mock_enqueue.assert_called_once_with(PROCESS_STAGED_INGRESS_TASK, args=[request_id], queue="ingress")

    def test_register_returns_when_markers_gone(self):
        """Test that registration is a no-op when pending and receipt markers are missing."""
        request_id = "marker-gone"
        with (
            patch("masu.external.downloader.ocp.payload_landing.register._read_marker_json", return_value=None),
            patch("masu.external.downloader.ocp.payload_landing.register.delete_s3_objects") as mock_delete,
            patch("masu.external.downloader.ocp.payload_landing.register.celery_app.send_task") as mock_enqueue,
            patch("masu.external.downloader.ocp.payload_landing.register.LOG.info") as mock_info,
        ):
            register_ingress_staging_marker(request_id)

        mock_info.assert_called_once()
        logged = mock_info.call_args.args[0]
        self.assertEqual(logged["message"], "ingress staging marker is gone")
        self.assertEqual(logged["tracing_id"], request_id)
        mock_delete.assert_not_called()
        mock_enqueue.assert_not_called()
        self.assertFalse(IngressStagingPayload.objects.filter(request_id=request_id).exists())

    def test_register_fills_row_missing_s3_key(self):
        """Test that registration updates a placeholder row that has no S3 key yet."""
        request_id = "register-fill-s3"
        s3_key = f"data/ingress_staging/{request_id}.tar.gz"
        row = self._pending_row(
            request_id,
            s3_key=None,
            payload={"request_id": request_id, "url": "http://example"},
            cluster_id=None,
            assembly_id=None,
        )
        document = self._marker_document(request_id, s3_key)
        with (
            patch("masu.external.downloader.ocp.payload_landing.register._read_marker_json", return_value=document),
            patch(
                "masu.external.downloader.ocp.payload_landing.register.delete_s3_objects",
                return_value=[{"Key": "pending"}],
            ),
            patch("masu.external.downloader.ocp.payload_landing.register.celery_app.send_task"),
        ):
            register_ingress_staging_marker(request_id)

        row.refresh_from_db()
        self.assertEqual(row.s3_key, s3_key)
        self.assertEqual(row.cluster_id, "cluster-1")
        self.assertEqual(row.assembly_id, "assembly-1")
        self.assertEqual(row.payload["b64_identity"], "secret-identity")
        self.assertEqual(row.state, IngressStagingState.PENDING)

    def test_register_leaves_marker_when_row_save_fails(self):
        """Test that a database error on update keeps the pending marker and resets the connection."""
        request_id = "marker-save-db-down"
        s3_key = f"data/ingress_staging/{request_id}.tar.gz"
        self._pending_row(request_id, s3_key=None, payload={"request_id": request_id})
        document = self._marker_document(request_id, s3_key)
        with (
            patch("masu.external.downloader.ocp.payload_landing.register._read_marker_json", return_value=document),
            patch("masu.external.downloader.ocp.payload_landing.register.delete_s3_objects") as mock_delete,
            patch("masu.external.downloader.ocp.payload_landing.register.celery_app.send_task") as mock_enqueue,
            patch("masu.external.kafka_msg_handler.close_and_set_db_connection") as mock_reset_db,
            patch.object(IngressStagingPayload, "save", side_effect=OperationalError("db down")),
        ):
            register_ingress_staging_marker(request_id)

        mock_reset_db.assert_called_once()
        mock_delete.assert_not_called()
        mock_enqueue.assert_not_called()
        row = IngressStagingPayload.objects.get(request_id=request_id)
        self.assertIsNone(row.s3_key)

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


class S3KeyExistsTests(SimpleTestCase):
    """Tests for ingress staging receipt existence checks on S3."""

    _RECEIPT_KEY = "data/ingress_staging/receipts/exists-check.json"
    _REQUEST_ID = "exists-check"
    _CONTEXT = {"org_id": "1234567"}

    def test_s3_key_exists_returns_true_when_object_present(self):
        """Test that a successful head/load means the receipt is already stored."""
        mock_object = MagicMock()
        with patch("masu.external.downloader.ocp.payload_landing.objects._s3_object", return_value=mock_object):
            self.assertTrue(_s3_key_exists(self._REQUEST_ID, self._RECEIPT_KEY, self._CONTEXT))
        mock_object.load.assert_called_once_with()

    def test_s3_key_exists_missing_object_returns_false(self):
        """Test that missing-object S3 errors mean the receipt is not present."""
        for code in ("404", "NoSuchKey", "NotFound"):
            error = ClientError({"Error": {"Code": code}}, "HeadObject")
            mock_object = MagicMock()
            mock_object.load.side_effect = error
            with (
                patch("masu.external.downloader.ocp.payload_landing.objects._s3_object", return_value=mock_object),
                patch("masu.external.downloader.ocp.payload_landing.objects.LOG.warning") as mock_warning,
            ):
                self.assertFalse(_s3_key_exists(self._REQUEST_ID, self._RECEIPT_KEY, self._CONTEXT))
            mock_warning.assert_not_called()

    def test_s3_key_exists_s3_client_error_rewinds(self):
        """Test that other S3 read failures rewind the Kafka consumer."""
        error = ClientError({"Error": {"Code": "AccessDenied"}}, "HeadObject")
        mock_object = MagicMock()
        mock_object.load.side_effect = error
        with (
            patch("masu.external.downloader.ocp.payload_landing.objects._s3_object", return_value=mock_object),
            patch("masu.external.downloader.ocp.payload_landing.objects.LOG.warning") as mock_warning,
        ):
            with self.assertRaises(KafkaMsgHandlerError) as raised:
                _s3_key_exists(self._REQUEST_ID, self._RECEIPT_KEY, self._CONTEXT)
        self.assertIn("Unable to read ingress staging receipt.", str(raised.exception))
        mock_warning.assert_called_once()

    def test_s3_key_exists_endpoint_error_rewinds(self):
        """Test that endpoint connection errors rewind the Kafka consumer."""
        mock_object = MagicMock()
        mock_object.load.side_effect = EndpointConnectionError(endpoint_url="http://s3.example")
        with (
            patch("masu.external.downloader.ocp.payload_landing.objects._s3_object", return_value=mock_object),
            patch("masu.external.downloader.ocp.payload_landing.objects.LOG.warning") as mock_warning,
        ):
            with self.assertRaises(KafkaMsgHandlerError) as raised:
                _s3_key_exists(self._REQUEST_ID, self._RECEIPT_KEY, self._CONTEXT)
        self.assertIn("Unable to read ingress staging receipt.", str(raised.exception))
        mock_warning.assert_called_once()


class ReadMarkerJsonTests(SimpleTestCase):
    """Tests for ingress staging marker reads from S3."""

    _MARKER_KEY = "data/ingress_staging/pending/marker-read.json"

    def _s3_object_with_body(self, body):
        mock_object = MagicMock()
        mock_object.get.return_value = {"Body": io.BytesIO(body)}
        return mock_object

    def test_read_marker_json_returns_parsed_document(self):
        """Test that a valid marker object is parsed and returned."""
        document = {"request_id": "marker-read", "s3_key": "data/ingress_staging/marker-read.tar.gz"}
        mock_object = self._s3_object_with_body(json.dumps(document).encode("utf-8"))
        with patch("masu.external.downloader.ocp.payload_landing.objects._s3_object", return_value=mock_object):
            self.assertEqual(_read_marker_json(self._MARKER_KEY), document)

    def test_read_marker_json_missing_object_returns_none(self):
        """Test that missing-object S3 errors return None without treating them as fatal."""
        for code in ("404", "NoSuchKey", "NotFound"):
            error = ClientError({"Error": {"Code": code}}, "GetObject")
            mock_object = MagicMock()
            mock_object.get.side_effect = error
            with (
                patch("masu.external.downloader.ocp.payload_landing.objects._s3_object", return_value=mock_object),
                patch("masu.external.downloader.ocp.payload_landing.objects.LOG.warning") as mock_warning,
            ):
                self.assertIsNone(_read_marker_json(self._MARKER_KEY))
            mock_warning.assert_not_called()

    def test_read_marker_json_s3_client_error_returns_none(self):
        """Test that other S3 read failures return None."""
        error = ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")
        mock_object = MagicMock()
        mock_object.get.side_effect = error
        with (
            patch("masu.external.downloader.ocp.payload_landing.objects._s3_object", return_value=mock_object),
            patch("masu.external.downloader.ocp.payload_landing.objects.LOG.warning") as mock_warning,
        ):
            self.assertIsNone(_read_marker_json(self._MARKER_KEY))
        mock_warning.assert_called_once()

    def test_read_marker_json_endpoint_error_returns_none(self):
        """Test that endpoint connection errors return None."""
        mock_object = MagicMock()
        mock_object.get.side_effect = EndpointConnectionError(endpoint_url="http://s3.example")
        with (
            patch("masu.external.downloader.ocp.payload_landing.objects._s3_object", return_value=mock_object),
            patch("masu.external.downloader.ocp.payload_landing.objects.LOG.warning") as mock_warning,
        ):
            self.assertIsNone(_read_marker_json(self._MARKER_KEY))
        mock_warning.assert_called_once()

    def test_read_marker_json_invalid_json_returns_none(self):
        """Test that non-JSON marker bodies return None."""
        mock_object = self._s3_object_with_body(b"not-json")
        with (
            patch("masu.external.downloader.ocp.payload_landing.objects._s3_object", return_value=mock_object),
            patch("masu.external.downloader.ocp.payload_landing.objects.LOG.warning") as mock_warning,
        ):
            self.assertIsNone(_read_marker_json(self._MARKER_KEY))
        mock_warning.assert_called_once()

    def test_read_marker_json_non_object_json_returns_none(self):
        """Test that JSON arrays are rejected."""
        mock_object = self._s3_object_with_body(json.dumps(["not", "a", "marker"]).encode("utf-8"))
        with (
            patch("masu.external.downloader.ocp.payload_landing.objects._s3_object", return_value=mock_object),
            patch("masu.external.downloader.ocp.payload_landing.objects.LOG.warning") as mock_warning,
        ):
            self.assertIsNone(_read_marker_json(self._MARKER_KEY))
        mock_warning.assert_called_once()


class ListPendingMarkersTests(SimpleTestCase):
    """Tests for listing pending ingress staging markers on S3."""

    _PREFIX = _pending_marker_prefix()

    @staticmethod
    def _object_summary(key, last_modified):
        summary = MagicMock()
        summary.key = key
        summary.last_modified = last_modified
        return summary

    def _bucket_listing(self, summaries):
        mock_filter = MagicMock()
        mock_filter.__iter__ = MagicMock(return_value=iter(summaries))
        mock_objects = MagicMock()
        mock_objects.filter.return_value = mock_filter
        mock_bucket = MagicMock()
        mock_bucket.objects = mock_objects
        mock_resource = MagicMock()
        mock_resource.Bucket.return_value = mock_bucket
        return mock_resource, mock_objects

    def test_list_pending_markers_returns_keys_and_oldest(self):
        """Test that .json keys are collected and the oldest LastModified is returned."""
        older = timezone.now() - timedelta(hours=2)
        newer = timezone.now() - timedelta(minutes=5)
        summaries = [
            self._object_summary(f"{self._PREFIX}older.json", older),
            self._object_summary(f"{self._PREFIX}scratch.tmp", newer),
            self._object_summary(f"{self._PREFIX}newer.json", newer),
        ]
        mock_resource, mock_objects = self._bucket_listing(summaries)
        with patch(
            "masu.external.downloader.ocp.payload_landing.objects.get_s3_resource",
            return_value=mock_resource,
        ):
            keys, oldest = _list_pending_markers(10)

        mock_objects.filter.assert_called_once_with(Prefix=self._PREFIX)
        self.assertCountEqual(
            keys,
            [f"{self._PREFIX}older.json", f"{self._PREFIX}newer.json"],
        )
        self.assertEqual(oldest, older)

    def test_list_pending_markers_stops_at_limit(self):
        """Test that listing returns at most ``limit`` marker keys."""
        summaries = [
            self._object_summary(f"{self._PREFIX}one.json", timezone.now()),
            self._object_summary(f"{self._PREFIX}two.json", timezone.now()),
            self._object_summary(f"{self._PREFIX}three.json", timezone.now()),
        ]
        mock_resource, _mock_objects = self._bucket_listing(summaries)
        with patch(
            "masu.external.downloader.ocp.payload_landing.objects.get_s3_resource",
            return_value=mock_resource,
        ):
            keys, _oldest = _list_pending_markers(2)

        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0], f"{self._PREFIX}one.json")
        self.assertEqual(keys[1], f"{self._PREFIX}two.json")

    def test_list_pending_markers_empty_bucket(self):
        """Test that an empty listing returns no keys and no oldest timestamp."""
        mock_resource, _mock_objects = self._bucket_listing([])
        with patch(
            "masu.external.downloader.ocp.payload_landing.objects.get_s3_resource",
            return_value=mock_resource,
        ):
            keys, oldest = _list_pending_markers(5)

        self.assertEqual(keys, [])
        self.assertIsNone(oldest)

    def test_list_pending_markers_client_error_returns_none(self):
        """Test that S3 list failures return None."""
        error = ClientError({"Error": {"Code": "AccessDenied"}}, "ListObjectsV2")
        mock_objects = MagicMock()
        mock_objects.filter.side_effect = error
        mock_bucket = MagicMock()
        mock_bucket.objects = mock_objects
        mock_resource = MagicMock()
        mock_resource.Bucket.return_value = mock_bucket
        with (
            patch(
                "masu.external.downloader.ocp.payload_landing.objects.get_s3_resource",
                return_value=mock_resource,
            ),
            patch("masu.external.downloader.ocp.payload_landing.objects.LOG.warning") as mock_warning,
        ):
            self.assertIsNone(_list_pending_markers(5))
        mock_warning.assert_called_once()

    def test_list_pending_markers_endpoint_error_returns_none(self):
        """Test that endpoint connection errors return None."""
        mock_objects = MagicMock()
        mock_objects.filter.side_effect = EndpointConnectionError(endpoint_url="http://s3.example")
        mock_bucket = MagicMock()
        mock_bucket.objects = mock_objects
        mock_resource = MagicMock()
        mock_resource.Bucket.return_value = mock_bucket
        with (
            patch(
                "masu.external.downloader.ocp.payload_landing.objects.get_s3_resource",
                return_value=mock_resource,
            ),
            patch("masu.external.downloader.ocp.payload_landing.objects.LOG.warning") as mock_warning,
        ):
            self.assertIsNone(_list_pending_markers(5))
        mock_warning.assert_called_once()
