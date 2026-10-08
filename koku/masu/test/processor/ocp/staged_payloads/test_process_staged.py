#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the worker that processes a staged ingress tarball."""
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.utils import timezone

from common.queues import OCPQueue
from masu.external.downloader.ocp.payload_landing import claim_ingress_staging_row
from masu.processor.ocp.staged_payloads.process_staged import process_staged_ingress_payload
from masu.processor.ocp.staged_payloads.process_staged import process_staged_ingress_reports
from masu.processor.ocp.staged_payloads.process_staged import PROCESS_STAGED_INGRESS_REPORTS_TASK
from masu.test import MasuTestCase
from reporting_common.models import IngressStagingPayload
from reporting_common.models import IngressStagingState


class ProcessStagedIngressTests(MasuTestCase):
    """Tests for process_staged_ingress_payload."""

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

    def test_replay_does_not_reprocess_completed_report_file(self):
        """Test that a file already marked complete is not sent through process_report again."""
        request_id = "replay-complete"
        row = self._pending_row(request_id)
        payload_dir = Path(tempfile.mkdtemp())
        payload_file = payload_dir / "payload.tar.gz"
        payload_file.write_bytes(b"tar")
        completed = {
            "process_complete": True,
            "files": ["file.csv"],
            "current_file": "file.csv",
            "manifest_id": 1,
            "schema_name": self.schema,
            "provider_type": "OCP",
            "provider_uuid": self.ocp_provider_uuid,
        }
        with (
            patch(
                "masu.processor.ocp.staged_payloads.process_staged.download_staged_tarball", return_value=payload_file
            ),
            patch(
                "masu.processor.ocp.staged_payloads.processing.extract_payload",
                return_value=([completed], "manifest-uuid"),
            ) as mock_extract,
            patch("masu.processor.ocp.staged_payloads.processing.process_report") as mock_process,
            patch("masu.processor.ocp.staged_payloads.processing.summarize_manifest", return_value=None),
        ):
            process_staged_ingress_payload(request_id)

        mock_extract.assert_called_once()
        self.assertEqual(mock_extract.call_args.args[2], "secret-identity")
        extract_dir = mock_extract.call_args.kwargs["local_report_dir"]
        self.assertIsInstance(extract_dir, Path)
        self.assertFalse(extract_dir.exists())
        mock_process.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.state, IngressStagingState.PROCESSED)

        row.state = IngressStagingState.PENDING
        row.not_before = timezone.now() - timedelta(minutes=1)
        row.save(update_fields=["state", "not_before"])
        with (
            patch(
                "masu.processor.ocp.staged_payloads.process_staged.download_staged_tarball", return_value=payload_file
            ),
            patch(
                "masu.processor.ocp.staged_payloads.processing.extract_payload",
                return_value=([completed], "manifest-uuid"),
            ),
            patch("masu.processor.ocp.staged_payloads.processing.process_report") as mock_process_again,
            patch("masu.processor.ocp.staged_payloads.processing.summarize_manifest", return_value=None),
        ):
            process_staged_ingress_payload(request_id)

        mock_process_again.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.state, IngressStagingState.PROCESSED)

    def test_extract_enqueues_line_items_on_customer_ocp_queue(self):
        """Test that extract hands line items to the customer OCP queue."""
        request_id = "enqueue-lines"
        row = self._pending_row(request_id)
        payload_dir = Path(tempfile.mkdtemp())
        payload_file = payload_dir / "payload.tar.gz"
        payload_file.write_bytes(b"tar")
        report_meta = {
            "process_complete": False,
            "files": ["file.csv"],
            "current_file": Path("/tmp/file.csv"),
            "split_files": [Path("/tmp/pod_usage.2026-01-01.1.abc.csv")],
            "ocp_files_to_process": {
                "pod_usage.2026-01-01.1.abc": {
                    "meta_reportdatestart": "2026-01-01",
                    "meta_reportnumhours": "24",
                    "s3_key": "data/csv/pod_usage.2026-01-01.1.abc.csv",
                }
            },
            "manifest_id": 1,
            "schema_name": self.schema,
            "provider_type": "OCP",
            "provider_uuid": self.ocp_provider_uuid,
            "uuid": "manifest-uuid",
        }
        with (
            patch(
                "masu.processor.ocp.staged_payloads.process_staged.download_staged_tarball", return_value=payload_file
            ),
            patch(
                "masu.processor.ocp.staged_payloads.processing.extract_payload",
                return_value=([report_meta], "manifest-uuid"),
            ),
            patch("masu.processor.ocp.staged_payloads.processing._process_report_file") as mock_process_file,
            patch(
                "masu.processor.ocp.staged_payloads.process_staged.get_customer_queue",
                return_value=OCPQueue.XL,
            ) as mock_queue,
            patch("masu.processor.ocp.staged_payloads.process_staged.celery_app.send_task") as mock_enqueue,
        ):
            process_staged_ingress_payload(request_id)

        mock_process_file.assert_not_called()
        mock_queue.assert_called_once_with(self.schema, OCPQueue)
        mock_enqueue.assert_called_once()
        self.assertEqual(mock_enqueue.call_args.args[0], PROCESS_STAGED_INGRESS_REPORTS_TASK)
        self.assertEqual(mock_enqueue.call_args.kwargs["queue"], OCPQueue.XL)
        self.assertEqual(mock_enqueue.call_args.kwargs["args"][0], request_id)
        queued_files = mock_enqueue.call_args.kwargs["args"][2][0]["split_files"]
        self.assertEqual(queued_files, ["pod_usage.2026-01-01.1.abc.csv"])
        row.refresh_from_db()
        self.assertEqual(row.state, IngressStagingState.PROCESSING)
        self.assertIsNotNone(row.payload)
        self.assertIsNotNone(row.enqueued_at)

    def test_line_item_task_marks_processed_after_reports(self):
        """Test that the OCP task marks the row processed only after line items return."""
        request_id = "line-items"
        row = self._pending_row(request_id)
        claimed = claim_ingress_staging_row(request_id)
        report_metas = [
            {
                "schema_name": self.schema,
                "uuid": "manifest-uuid",
                "split_files": ["pod_usage.2026-01-01.1.abc.csv"],
                "current_file": "file.csv",
                "ocp_files_to_process": {
                    "pod_usage.2026-01-01.1.abc": {"s3_key": "data/csv/pod_usage.2026-01-01.1.abc.csv"}
                },
            }
        ]
        with (
            patch(
                "masu.processor.ocp.staged_payloads.process_staged.heartbeat_ingress_claim",
                return_value=True,
            ) as mock_heartbeat,
            patch(
                "masu.processor.ocp.staged_payloads.process_staged.materialize_report_files",
                return_value=(None, report_metas),
            ),
            patch(
                "masu.processor.ocp.staged_payloads.processing.process_extracted_reports",
                return_value=True,
            ) as mock_reports,
        ):
            process_staged_ingress_reports(request_id, str(claimed.claim_token), report_metas)

        mock_heartbeat.assert_called()

        mock_reports.assert_called_once()
        row.refresh_from_db()
        self.assertEqual(row.state, IngressStagingState.PROCESSED)
        self.assertIsNone(row.payload)

    def test_scheduler_worker_queue_omits_ingress(self):
        """Test that the scheduler pod is not subscribed to the ingress queue."""
        repo = Path(__file__).resolve().parents[6]
        for relative in ("deploy/clowdapp.yaml", "deploy/kustomize/patches/scheduler.yaml"):
            queue_line = ""
            for line in (repo / relative).read_text().splitlines():
                if "cost_model" in line and "download" in line and "summary" in line:
                    queue_line = line
                    break
            self.assertTrue(
                queue_line,
                f"no scheduler queue line (cost_model/download/summary) in {relative}",
            )
            tokens = {token.strip().strip("'\"") for token in queue_line.split("value:")[-1].split(",")}
            self.assertNotIn("ingress", tokens, relative)

    def test_processed_row_is_not_claimed_again(self):
        """Test that a finished tarball is left alone when the task is enqueued twice."""
        row = self._pending_row("already-processed", state=IngressStagingState.PROCESSED)
        with patch("masu.processor.ocp.staged_payloads.processing.extract_payload") as mock_extract:
            process_staged_ingress_payload(row.request_id)
        mock_extract.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.state, IngressStagingState.PROCESSED)
