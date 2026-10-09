#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test staged ingress registration."""
import io
import json
import tempfile
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

import requests_mock
from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError
from django.db import OperationalError
from django.test import SimpleTestCase
from django.utils import timezone

from masu.config import Config
from masu.external.downloader.ocp.exceptions import FAILURE_CONFIRM_STATUS
from masu.external.downloader.ocp.exceptions import KafkaMsgHandlerError
from masu.external.downloader.ocp.exceptions import SUCCESS_CONFIRM_STATUS
from masu.external.downloader.ocp.payload_landing import PROCESS_STAGED_INGRESS_TASK
from masu.external.downloader.ocp.payload_landing import register_ingress_staging_marker
from masu.external.downloader.ocp.payload_landing import REGISTER_INGRESS_STAGING_TASK
from masu.external.downloader.ocp.payload_landing import stage_ingress_s3_inbox
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
