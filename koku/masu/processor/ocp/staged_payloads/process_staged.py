#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Read a durable OCP ingress tarball from our bucket and process it.

Download from ingress is already finished. ``process_staged_ingress_payload``
claims the row, fetches the stored object, and extracts it on the ingress
queue. Line-item work is a second task on the customer OCP queue, because
each worker pod has its own emptyDir and xl or penalty customers must not
share the ingress queue.

This module stays separate from ``processing`` while the listener still calls
``extract_payload`` and ``process_extracted_reports`` from
``legacy_message_processing`` (INGRESS_STAGING_LISTENER_FLAG off). The two
modules can be combined once that legacy path is removed.
"""
import logging
import os
import re
import shutil
import tempfile
import threading
import uuid
from datetime import date
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import close_old_connections
from django.db import connection
from kombu.exceptions import OperationalError as KombuOperationalError

from api.common import log_json
from common.queues import get_customer_queue
from common.queues import IngressQueue
from common.queues import OCPQueue
from koku import celery_app
from masu.config import Config
from masu.external.downloader.ocp.payload_landing import claim_ingress_staging_row
from masu.external.downloader.ocp.payload_landing import heartbeat_ingress_claim
from masu.external.downloader.ocp.payload_landing import ingress_claim_held
from masu.external.downloader.ocp.payload_landing import mark_processed
from masu.external.downloader.ocp.payload_landing import PROCESS_STAGED_INGRESS_TASK
from masu.external.downloader.ocp.payload_landing import release_for_retry
from masu.processor.ocp.staged_payloads import processing
from masu.util.aws.common import get_s3_resource

LOG = logging.getLogger(__name__)

# Both limits sit under INGRESS_STAGING_LEASE (2 hours). The soft limit releases
# the claim before another worker can take a row this task still holds.
INGRESS_STAGING_SOFT_TIME_LIMIT = 90 * 60
INGRESS_STAGING_HARD_TIME_LIMIT = 105 * 60
_HEARTBEAT_SECONDS = 5 * 60

PROCESS_STAGED_INGRESS_REPORTS_TASK = (
    "masu.processor.ocp.staged_payloads.process_staged.process_staged_ingress_reports"
)
_TASK_LIMITS = {
    "soft_time_limit": INGRESS_STAGING_SOFT_TIME_LIMIT,
    "time_limit": INGRESS_STAGING_HARD_TIME_LIMIT,
}


class _ClaimHeartbeat:
    """Keep claimed_at fresh until the task finishes or loses the token."""

    def __init__(self, request_id, claim_token):
        self.request_id = request_id
        self.claim_token = claim_token
        self.lost = False
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(
            target=self._run,
            name=f"ingress-staging-heartbeat-{self.request_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None

    def _run(self):
        while not self._stop.wait(_HEARTBEAT_SECONDS):
            close_old_connections()
            try:
                if not heartbeat_ingress_claim(self.request_id, self.claim_token):
                    self.lost = True
                    return
            except Exception as error:
                LOG.warning(
                    log_json(
                        self.request_id,
                        msg="ingress staging heartbeat failed",
                        error=type(error).__name__,
                    )
                )
            finally:
                connection.close()


def download_staged_tarball(s3_key, request_id):
    """Download a staged tarball from our bucket into the listener data directory."""
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    temp_dir = tempfile.mkdtemp(dir=Config.DATA_DIR)
    sanitized_request_id = re.sub("[^A-Za-z0-9]+", "", request_id)
    dest = Path(temp_dir, sanitized_request_id).with_suffix(".tar.gz")
    s3_resource = get_s3_resource(settings.S3_ACCESS_KEY, settings.S3_SECRET, settings.S3_REGION)
    try:
        s3_resource.Object(settings.S3_BUCKET_NAME, s3_key).download_file(str(dest))
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    return dest


def _json_ready(value):
    """Return a Celery JSON-safe copy. Local paths become file names."""
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return value.name
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def _line_items_pending(report_metas):
    if not report_metas:
        return False
    return any(not meta.get("process_complete") for meta in report_metas)


def _split_files_have_objects(report_metas):
    """Return False when a file that still needs processing has no S3 key."""
    for meta in report_metas:
        if meta.get("process_complete"):
            continue
        names = {Path(name).name for name in meta.get("split_files") or []}
        available = {
            Path(file_meta["s3_key"]).name
            for file_meta in (meta.get("ocp_files_to_process") or {}).values()
            if file_meta.get("s3_key")
        }
        if names and not names <= available:
            return False
    return True


def _schema_name(report_metas):
    for meta in report_metas or []:
        if meta.get("schema_name"):
            return meta["schema_name"]
    return None


def _enqueue_line_items(request_id, claim_token, report_metas, context):
    """Hand line items to the customer OCP queue. A broker failure releases the claim."""
    if not heartbeat_ingress_claim(request_id, claim_token):
        LOG.info(log_json(request_id, msg="ingress staging claim lost before line-item handoff", context=context))
        return
    if not _split_files_have_objects(report_metas):
        release_for_retry(
            request_id,
            claim_token,
            RuntimeError("staged daily csv is missing an object key"),
        )
        return
    queue = get_customer_queue(_schema_name(report_metas), OCPQueue)
    try:
        celery_app.send_task(
            PROCESS_STAGED_INGRESS_REPORTS_TASK,
            args=[request_id, str(claim_token), _json_ready(report_metas)],
            queue=queue,
        )
    except KombuOperationalError as error:
        LOG.warning(
            log_json(
                request_id,
                msg="failed to enqueue staged ingress line items",
                context=context,
                error=type(error).__name__,
            )
        )
        release_for_retry(request_id, claim_token, error)
        return
    LOG.info(log_json(request_id, msg="enqueued staged ingress line items", context=context, queue=str(queue)))


def materialize_report_files(report_metas):
    """Download daily CSVs for this payload into a temp dir and restore local paths.

    Extract ran on another pod. ``split_files`` in the task args are file names,
    and each ``ocp_files_to_process`` entry carries the object key.
    """
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=Config.DATA_DIR))
    try:
        s3_resource = get_s3_resource(settings.S3_ACCESS_KEY, settings.S3_SECRET, settings.S3_REGION)
        rebuilt = []
        for meta in report_metas:
            meta = dict(meta)
            local_by_name = {}
            for file_meta in (meta.get("ocp_files_to_process") or {}).values():
                s3_key = file_meta.get("s3_key")
                if not s3_key:
                    continue
                filename = Path(s3_key).name
                if filename in local_by_name:
                    continue
                dest = temp_dir / filename
                s3_resource.Object(settings.S3_BUCKET_NAME, s3_key).download_file(str(dest))
                local_by_name[filename] = dest
            meta["split_files"] = [local_by_name[Path(name).name] for name in meta.get("split_files") or []]
            current_name = meta.get("current_file")
            if current_name:
                current_filename = Path(current_name).name
                meta["current_file"] = local_by_name.get(current_filename, temp_dir / current_filename)
            rebuilt.append(meta)
        return temp_dir, rebuilt
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _tracing_id(request_id, report_metas):
    for meta in report_metas or []:
        if meta.get("uuid"):
            return meta["uuid"]
    return request_id


def _run_claimed(request_id, claim_token, work):
    """Run ``work`` while the claim heartbeat is alive. Failures release the token."""
    heartbeat = _ClaimHeartbeat(request_id, claim_token)
    heartbeat.start()
    try:
        work(heartbeat)
    except SoftTimeLimitExceeded as error:
        LOG.warning(log_json(request_id, msg="staged ingress task hit its time limit"))
        if not heartbeat.lost:
            release_for_retry(request_id, claim_token, error)
    except Exception as error:
        LOG.warning(
            log_json(
                request_id,
                msg="staged ingress processing failed",
                error=type(error).__name__,
            )
        )
        if not heartbeat.lost:
            release_for_retry(request_id, claim_token, error)
    finally:
        heartbeat.stop()


@celery_app.task(name=PROCESS_STAGED_INGRESS_TASK, queue=IngressQueue.DEFAULT, **_TASK_LIMITS)
def process_staged_ingress_payload(request_id):
    """Claim a staged tarball, extract it, and enqueue line items on the OCP queue.

    Unknown clusters, retention skips, and files that are already complete are
    marked processed here. A handoff to the OCP queue is not completion.
    Retries use ``attempts`` and ``not_before`` rather than Celery autoretry.
    """
    row = claim_ingress_staging_row(request_id)
    if row is None:
        LOG.info(log_json(request_id, msg="ingress staging claim missed"))
        return

    claim_token = row.claim_token
    payload_path = None

    def work(heartbeat):
        nonlocal payload_path
        value = row.payload or {}
        context = {"account": row.account, "org_id": row.org_id, "cluster_id": row.cluster_id}
        LOG.info(log_json(request_id, msg="processing staged ingress payload", context=context, s3_key=row.s3_key))
        payload_path = download_staged_tarball(row.s3_key, request_id)
        if heartbeat.lost:
            LOG.info(log_json(request_id, msg="ingress staging claim lost during download", context=context))
            return
        report_metas, _manifest_uuid = processing.extract_payload(
            payload_path, request_id, value.get("b64_identity"), context
        )
        if heartbeat.lost:
            LOG.info(log_json(request_id, msg="ingress staging claim lost during extract", context=context))
            return
        if _line_items_pending(report_metas):
            _enqueue_line_items(request_id, claim_token, report_metas, context)
            return
        if mark_processed(request_id, claim_token):
            LOG.info(log_json(request_id, msg="staged ingress payload skipped line items", context=context))

    try:
        _run_claimed(request_id, claim_token, work)
    finally:
        if payload_path is not None:
            shutil.rmtree(payload_path.parent, ignore_errors=True)


@celery_app.task(name=PROCESS_STAGED_INGRESS_REPORTS_TASK, queue=OCPQueue.DEFAULT, **_TASK_LIMITS)
def process_staged_ingress_reports(request_id, claim_token, report_metas):
    """Download extracted CSVs and run line-item processing for one staged payload.

    The row is marked processed only after this work returns. The extract task
    still holds ``claim_token``; this task does not claim the row again.
    """
    if not ingress_claim_held(request_id, claim_token):
        LOG.info(log_json(request_id, msg="ingress staging line-item claim missed"))
        return

    report_dir = None

    def work(heartbeat):
        nonlocal report_dir
        if heartbeat.lost:
            return
        report_dir, local_metas = materialize_report_files(report_metas)
        if heartbeat.lost:
            LOG.info(log_json(request_id, msg="ingress staging claim lost during csv download"))
            return
        tracing_id = _tracing_id(request_id, local_metas)
        processing.process_extracted_reports(request_id, local_metas, tracing_id)
        if heartbeat.lost:
            LOG.info(log_json(request_id, msg="ingress staging claim lost during line items"))
            return
        if mark_processed(request_id, claim_token):
            LOG.info(log_json(request_id, msg="staged ingress payload processed"))

    try:
        _run_claimed(request_id, claim_token, work)
    finally:
        if report_dir is not None:
            shutil.rmtree(report_dir, ignore_errors=True)
