#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Store an HCCM ingress tarball in our bucket and record the staging row.

Download is finished when the raw tar is durable. The listener either upserts
the staging row or, when the S3 inbox flag is on, writes a pending marker and
leaves the row to the register task. The processor task reads that object back
and turns it into line items. This module enqueues that task by name and does
not import it.
"""
import io
import json
import logging
import re
import shutil
import uuid
from datetime import timedelta

import requests
from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError
from django.conf import settings
from django.db import IntegrityError
from django.db import InterfaceError
from django.db import OperationalError
from django.db import ProgrammingError
from django.db.models import F
from django.db.models import IntegerField
from django.db.models import Min
from django.db.models import Q
from django.db.models import Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from kombu.exceptions import OperationalError as KombuOperationalError

from api.common import log_json
from api.utils import DateHelper
from common.queues import IngressQueue
from koku import celery_app
from masu.config import Config
from masu.external.downloader.ocp import download
from masu.external.downloader.ocp.exceptions import FAILURE_CONFIRM_STATUS
from masu.external.downloader.ocp.exceptions import KafkaMsgHandlerError
from masu.external.downloader.ocp.exceptions import SUCCESS_CONFIRM_STATUS
from masu.prometheus_stats import INGRESS_STAGING_FAILED
from masu.prometheus_stats import INGRESS_STAGING_OLDEST_AGE
from masu.prometheus_stats import INGRESS_STAGING_PENDING
from masu.prometheus_stats import INGRESS_STAGING_PENDING_MARKER_OLDEST_AGE
from masu.prometheus_stats import INGRESS_STAGING_PENDING_MARKERS
from masu.util.aws.common import copy_data_to_s3_bucket
from masu.util.aws.common import delete_s3_objects
from masu.util.aws.common import get_s3_resource
from masu.util.aws.common import UploadError
from reporting_common.models import IngressStagingPayload
from reporting_common.models import IngressStagingState

LOG = logging.getLogger(__name__)

# Long enough that a healthy line-item run is not reclaimed, short enough that
# a dead worker is retried. Matches the rough upper bound used for large downloads.
INGRESS_STAGING_LEASE = timedelta(hours=2)
INGRESS_STAGING_BEAT_GRACE = timedelta(minutes=1)
INGRESS_STAGING_RETENTION = timedelta(days=7)
INGRESS_STAGING_RECONCILE_BATCH = 100
# One beat registers this many markers so a long outage drains faster than the
# row reconciler's batch of 100, without listing the prefix without a cap.
INGRESS_STAGING_REGISTER_LIMIT = 1000
_LAST_ERROR_MAX_LENGTH = 1024
_DB_ERRORS = (OperationalError, InterfaceError, ProgrammingError)
_MISSING_S3_CODES = {"404", "NoSuchKey", "NotFound"}

PROCESS_STAGED_INGRESS_TASK = "masu.processor.ocp.staged_payloads.process_staged.process_staged_ingress_payload"
REGISTER_INGRESS_STAGING_TASK = "masu.external.downloader.ocp.ingress_staging.register_ingress_staging_marker"
RECONCILE_INGRESS_STAGING_TASK = "masu.external.downloader.ocp.ingress_staging.reconcile_ingress_staging"
EXPIRE_INGRESS_STAGING_TASK = "masu.external.downloader.ocp.ingress_staging.expire_ingress_staging"


def _error_text(error):
    """Return a short error string that does not include the Kafka payload."""
    return f"{type(error).__name__}: {error}"[:_LAST_ERROR_MAX_LENGTH]


def _sanitized_request_id(request_id):
    return re.sub("[^A-Za-z0-9]+", "", request_id)


def _pending_marker_prefix():
    return f"{Config.WAREHOUSE_PATH}/ingress_staging/pending/"


def _pending_marker_key(request_id):
    return f"{_pending_marker_prefix()}{_sanitized_request_id(request_id)}.json"


def _receipt_key(request_id):
    return f"{Config.WAREHOUSE_PATH}/ingress_staging/by_request/{_sanitized_request_id(request_id)}.json"


def _inbox_tar_key(org_id, cluster_id, request_id):
    filename = f"{_sanitized_request_id(request_id)}.tar.gz"
    return f"{Config.WAREHOUSE_PATH}/ingress_staging/{org_id}/{cluster_id}/{filename}"


def _marker_document(request_id, value, s3_key, cluster_id, assembly_id):
    """Build the S3 marker. ``value`` includes ``b64_identity``. Do not log it."""
    return {
        "request_id": request_id,
        "s3_key": s3_key,
        "org_id": value.get("org_id"),
        "cluster_id": cluster_id,
        "assembly_id": str(assembly_id) if assembly_id is not None else None,
        "account": value.get("account"),
        "payload": value,
    }


def _enqueue_task(request_id, context, task_name, failure_message):
    """Best-effort enqueue. A broker failure must not rewind the Kafka consumer."""
    try:
        celery_app.send_task(task_name, args=[request_id], queue=IngressQueue.DEFAULT)
    except KombuOperationalError as error:
        LOG.warning(
            log_json(
                request_id,
                msg=failure_message,
                context=context,
                error=type(error).__name__,
            )
        )


def _enqueue_staged_ingress(request_id, context):
    """Enqueue extract. A broker failure must not rewind the Kafka consumer."""
    _enqueue_task(
        request_id,
        context,
        PROCESS_STAGED_INGRESS_TASK,
        "failed to enqueue staged ingress payload; reconciler will retry",
    )


def _enqueue_register_ingress(request_id, context):
    """Enqueue marker registration. A broker failure must not rewind the Kafka consumer."""
    _enqueue_task(
        request_id,
        context,
        REGISTER_INGRESS_STAGING_TASK,
        "failed to enqueue ingress staging register; reconciler will retry",
    )


def _reset_listener_db_connection():
    """Drop a broken connection before the Kafka consumer rewinds."""
    from masu.external.kafka_msg_handler import close_and_set_db_connection

    close_and_set_db_connection()


def _save_staging_row(request_id, value, s3_key, cluster_id, assembly_id, now):
    """Insert or fill in the staging row. Do not reset a row that already has an S3 key."""
    defaults = {
        "payload": value,
        "s3_key": s3_key,
        "org_id": value.get("org_id"),
        "cluster_id": cluster_id,
        "assembly_id": str(assembly_id) if assembly_id is not None else None,
        "account": value.get("account"),
        "state": IngressStagingState.PENDING,
        "stored_at": now,
        "not_before": now,
        "last_error": None,
    }
    try:
        row, created = IngressStagingPayload.objects.get_or_create(request_id=request_id, defaults=defaults)
    except IntegrityError:
        row = IngressStagingPayload.objects.get(request_id=request_id)
        created = False
    except _DB_ERRORS as error:
        _reset_listener_db_connection()
        raise KafkaMsgHandlerError("Unable to store ingress staging row.") from error
    if created or row.s3_key:
        return row
    for field, field_value in defaults.items():
        setattr(row, field, field_value)
    try:
        row.save()
    except _DB_ERRORS as error:
        _reset_listener_db_connection()
        raise KafkaMsgHandlerError("Unable to store ingress staging row.") from error
    return row


def _lookup_staged_s3_key(request_id):
    """Return the stored object key, or None when this request has not been staged."""
    try:
        existing = IngressStagingPayload.objects.filter(request_id=request_id).only("s3_key").first()
    except _DB_ERRORS as error:
        _reset_listener_db_connection()
        raise KafkaMsgHandlerError("Unable to read ingress staging row.") from error
    if existing and existing.s3_key:
        return existing.s3_key
    return None


def _rewind_for_staging_error(request_id, context, error, message):
    """Log a transient staging failure and raise so the Kafka consumer rewinds."""
    msg = f"{message} Error: {type(error).__name__}: {error}"
    LOG.warning(log_json(request_id, msg=msg, context=context))
    raise KafkaMsgHandlerError(msg) from error


def _download_ingress_tarball(request_id, url, context):
    """Download the tarball. None means a permanent failure that should be confirmed."""
    try:
        return download.download_payload(request_id, url, context)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
        _rewind_for_staging_error(request_id, context, error, "Unable to stage ingress payload.")
    except KafkaMsgHandlerError as error:
        if download.is_permanent_download_error(error):
            msg = f"Unable to stage ingress payload. Error: {type(error).__name__}: {error}"
            LOG.warning(log_json(request_id, msg=msg, context=context))
            return None
        raise


def _manifest_for_staging(request_id, payload_path, context):
    """Peek at the manifest. None means the tarball should be confirmed as a failure."""
    try:
        return download.read_manifest_from_tarball(request_id, payload_path, context)
    except KafkaMsgHandlerError as error:
        msg = f"Unable to read manifest for staged ingress payload. Error: {error}"
        LOG.warning(log_json(request_id, msg=msg, context=context))
        return None


def _store_staged_tarball(request_id, value, payload_path, manifest, context):
    """Upload the raw tar and record the staging row. Returns the object key."""
    now = DateHelper().now_utc
    org_id = value.get("org_id")
    cluster_id = manifest.cluster_id
    s3_path = (
        f"{Config.WAREHOUSE_PATH}/ingress_staging/{org_id}/{cluster_id}"
        f"/{now.strftime('%Y')}/{now.strftime('%m')}/{now.strftime('%d')}"
    )
    filename = f"{re.sub('[^A-Za-z0-9]+', '', request_id)}.tar.gz"
    s3_key = f"{s3_path}/{filename}"
    try:
        with open(payload_path, "rb") as payload_file:
            copy_data_to_s3_bucket(request_id, s3_path, filename, payload_file, context=context)
        _save_staging_row(request_id, value, s3_key, cluster_id, manifest.uuid, now)
    except (UploadError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
        _rewind_for_staging_error(request_id, context, error, "Unable to store staged ingress payload.")
    return s3_key


def stage_ingress_payload(request_id, value, context):
    """Download the ingress tarball, store it, and hand processing to a worker.

    Returns SUCCESS_CONFIRM_STATUS when the object is durable and the staging row
    is recorded. Returns FAILURE_CONFIRM_STATUS for an invalid manifest or a
    permanent download error. Raises KafkaMsgHandlerError so the consumer rewinds
    on a transient download, an S3 failure, or a failed upsert.

    ``value`` is stored on the row and includes ``b64_identity``. Do not log it.
    """
    payload_path = None
    try:
        if s3_key := _lookup_staged_s3_key(request_id):
            LOG.info(log_json(request_id, msg="ingress payload already staged", context=context, s3_key=s3_key))
            _enqueue_staged_ingress(request_id, context)
            return SUCCESS_CONFIRM_STATUS

        try:
            url = value["url"]
        except KeyError:
            LOG.warning(log_json(request_id, msg="ingress message missing url", context=context))
            return FAILURE_CONFIRM_STATUS

        payload_path = _download_ingress_tarball(request_id, url, context)
        if payload_path is None:
            return FAILURE_CONFIRM_STATUS
        manifest = _manifest_for_staging(request_id, payload_path, context)
        if manifest is None:
            return FAILURE_CONFIRM_STATUS

        s3_key = _store_staged_tarball(request_id, value, payload_path, manifest, context)
        LOG.info(log_json(request_id, msg="ingress payload staged", context=context, s3_key=s3_key))
        _enqueue_staged_ingress(request_id, context)
        return SUCCESS_CONFIRM_STATUS
    finally:
        if payload_path is not None:
            shutil.rmtree(payload_path.parent, ignore_errors=True)


def _s3_error_code(error):
    response = getattr(error, "response", None) or {}
    return response.get("Error", {}).get("Code", "")


def _s3_object(key):
    s3_resource = get_s3_resource(settings.S3_ACCESS_KEY, settings.S3_SECRET, settings.S3_REGION)
    return s3_resource.Object(settings.S3_BUCKET_NAME, key)


def _s3_key_exists(request_id, key, context):
    """Return True when the object is already in the bucket. Missing is False."""
    try:
        _s3_object(key).load()
    except ClientError as error:
        if _s3_error_code(error) in _MISSING_S3_CODES:
            return False
        _rewind_for_staging_error(request_id, context, error, "Unable to read ingress staging receipt.")
    except EndpointConnectionError as error:
        _rewind_for_staging_error(request_id, context, error, "Unable to read ingress staging receipt.")
    return True


def _put_bytes(request_id, key, data, context):
    path, filename = key.rsplit("/", 1)
    copy_data_to_s3_bucket(request_id, path, filename, data, context=context)


def _put_json(request_id, key, document, context):
    """Write a marker. ``document`` includes the Kafka payload. Do not log it."""
    _put_bytes(request_id, key, io.BytesIO(json.dumps(document).encode("utf-8")), context)


def _copy_s3_key(request_id, source_key, dest_key, context):
    """Copy one object onto another. A failure rewinds the consumer."""
    source = {"Bucket": settings.S3_BUCKET_NAME, "Key": source_key}
    try:
        _s3_object(dest_key).copy_from(CopySource=source)
    except (ClientError, EndpointConnectionError) as error:
        _rewind_for_staging_error(request_id, context, error, "Unable to store ingress staging marker.")


def _read_marker_json(key):
    """Return a marker document, or None when it is missing or unreadable.

    The document includes ``b64_identity``. Do not log it.
    """
    try:
        body = _s3_object(key).get()["Body"].read()
    except ClientError as error:
        if _s3_error_code(error) in _MISSING_S3_CODES:
            return None
        LOG.warning(log_json(msg="unable to read ingress staging marker", s3_key=key, error=type(error).__name__))
        return None
    except EndpointConnectionError:
        LOG.warning(log_json(msg="unable to read ingress staging marker", s3_key=key, error="EndpointConnectionError"))
        return None
    try:
        document = json.loads(body)
    except json.JSONDecodeError:
        LOG.warning(log_json(msg="ingress staging marker is not json", s3_key=key))
        return None
    if not isinstance(document, dict):
        LOG.warning(log_json(msg="ingress staging marker is not an object", s3_key=key))
        return None
    return document


def _store_s3_inbox_objects(request_id, value, payload_path, manifest, context):
    """Upload the tar, the receipt, and the pending marker. Returns the tar key."""
    org_id = value.get("org_id")
    cluster_id = manifest.cluster_id
    tar_key = _inbox_tar_key(org_id, cluster_id, request_id)
    document = _marker_document(request_id, value, tar_key, cluster_id, manifest.uuid)
    try:
        with open(payload_path, "rb") as payload_file:
            _put_bytes(request_id, tar_key, payload_file, context)
        _put_json(request_id, _receipt_key(request_id), document, context)
        _put_json(request_id, _pending_marker_key(request_id), document, context)
    except (UploadError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
        _rewind_for_staging_error(request_id, context, error, "Unable to store staged ingress payload.")
    return tar_key


def stage_ingress_s3_inbox(request_id, value, context):
    """Store the tarball and a pending marker without opening Postgres or Trino.

    Returns SUCCESS_CONFIRM_STATUS when the tar, receipt, and pending marker are
    durable. A redelivery that finds the receipt skips the quarantine download
    and does not upload the tarball again. Returns FAILURE_CONFIRM_STATUS for an
    invalid manifest or a permanent download error. Raises KafkaMsgHandlerError
    so the consumer rewinds on a transient download or an S3 failure.

    The receipt and the pending marker include ``b64_identity``. Do not log them.
    """
    payload_path = None
    try:
        receipt_key = _receipt_key(request_id)
        if _s3_key_exists(request_id, receipt_key, context):
            LOG.info(log_json(request_id, msg="ingress payload already stored", context=context, s3_key=receipt_key))
            _copy_s3_key(request_id, receipt_key, _pending_marker_key(request_id), context)
            _enqueue_register_ingress(request_id, context)
            return SUCCESS_CONFIRM_STATUS

        try:
            url = value["url"]
        except KeyError:
            LOG.warning(log_json(request_id, msg="ingress message missing url", context=context))
            return FAILURE_CONFIRM_STATUS

        payload_path = _download_ingress_tarball(request_id, url, context)
        if payload_path is None:
            return FAILURE_CONFIRM_STATUS
        manifest = _manifest_for_staging(request_id, payload_path, context)
        if manifest is None:
            return FAILURE_CONFIRM_STATUS

        s3_key = _store_s3_inbox_objects(request_id, value, payload_path, manifest, context)
        LOG.info(log_json(request_id, msg="ingress payload stored for registration", context=context, s3_key=s3_key))
        _enqueue_register_ingress(request_id, context)
        return SUCCESS_CONFIRM_STATUS
    finally:
        if payload_path is not None:
            shutil.rmtree(payload_path.parent, ignore_errors=True)


def _payload_for_marker(document):
    """Copy marker fields onto the Kafka value without logging the payload."""
    value = dict(document.get("payload") or {})
    if document.get("org_id") and not value.get("org_id"):
        value["org_id"] = document["org_id"]
    if document.get("account") and not value.get("account"):
        value["account"] = document["account"]
    return value


def _register_staging_document(document, pending_key):
    """Upsert the staging row, then delete the pending marker.

    Returns False when Postgres rejects the upsert. The marker stays so the
    next beat can retry. A row that already has an ``s3_key`` is not reset.
    """
    request_id = document.get("request_id")
    s3_key = document.get("s3_key")
    if not request_id or not s3_key:
        LOG.warning(log_json(msg="ingress staging marker is missing request fields", s3_key=pending_key))
        return True
    value = _payload_for_marker(document)
    now = DateHelper().now_utc
    try:
        _save_staging_row(
            request_id,
            value,
            s3_key,
            document.get("cluster_id"),
            document.get("assembly_id"),
            now,
        )
    except (KafkaMsgHandlerError, *_DB_ERRORS) as error:
        cause = error.__cause__ if isinstance(error, KafkaMsgHandlerError) else error
        LOG.warning(
            log_json(
                request_id,
                msg="ingress staging marker left for retry",
                s3_key=pending_key,
                error=type(cause).__name__ if cause else "database",
            )
        )
        return False
    if pending_key:
        deleted = delete_s3_objects(request_id, [pending_key], {})
        if not deleted:
            LOG.warning(log_json(request_id, msg="ingress staging marker remains after upsert", s3_key=pending_key))
    context = {"org_id": document.get("org_id"), "account": document.get("account")}
    _enqueue_staged_ingress(request_id, context)
    return True


def _marker_document_or_none(key):
    document = _read_marker_json(key)
    if document is None:
        return None
    if not document.get("request_id") or not document.get("s3_key"):
        LOG.warning(log_json(msg="ingress staging marker is missing request fields", s3_key=key))
        return None
    return document


@celery_app.task(name=REGISTER_INGRESS_STAGING_TASK, queue=IngressQueue.DEFAULT)
def register_ingress_staging_marker(request_id):
    """Insert the staging row for one S3 marker and enqueue extract.

    The pending marker is deleted only after the upsert succeeds. A missing
    marker falls back to the receipt so a redelivery can still create the row.
    """
    pending_key = _pending_marker_key(request_id)
    document = _marker_document_or_none(pending_key)
    if document is None:
        document = _marker_document_or_none(_receipt_key(request_id))
        pending_key = None
    if document is None:
        LOG.info(log_json(request_id, msg="ingress staging marker is gone"))
        return
    _register_staging_document(document, pending_key)


def _list_pending_markers(limit):
    """Return up to ``limit`` pending marker keys and the oldest LastModified.

    None means the list failed. The scan stops at ``limit``.
    """
    prefix = _pending_marker_prefix()
    s3_resource = get_s3_resource(settings.S3_ACCESS_KEY, settings.S3_SECRET, settings.S3_REGION)
    keys = []
    oldest = None
    try:
        for summary in s3_resource.Bucket(settings.S3_BUCKET_NAME).objects.filter(Prefix=prefix):
            key = summary.key
            if not key.endswith(".json"):
                continue
            modified = summary.last_modified
            if modified is not None and (oldest is None or modified < oldest):
                oldest = modified
            keys.append(key)
            if len(keys) >= limit:
                break
    except (EndpointConnectionError, ClientError) as error:
        LOG.warning(log_json(msg="unable to list ingress staging markers", error=type(error).__name__))
        return None
    return keys, oldest


def _marker_age_seconds(now, oldest):
    if oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    return max((now - oldest).total_seconds(), 0)


def _publish_pending_marker_gauges(now, listed):
    """Record how many pending markers are waiting and how old the oldest is."""
    if listed is None:
        return
    keys, oldest = listed
    INGRESS_STAGING_PENDING_MARKERS.set(len(keys))
    if oldest is None:
        INGRESS_STAGING_PENDING_MARKER_OLDEST_AGE.set(0)
        return
    INGRESS_STAGING_PENDING_MARKER_OLDEST_AGE.set(_marker_age_seconds(now, oldest))


def _register_pending_markers(now):
    """Turn pending S3 markers into staging rows. Stop the batch if Postgres is down."""
    listed = _list_pending_markers(INGRESS_STAGING_REGISTER_LIMIT)
    _publish_pending_marker_gauges(now, listed)
    if listed is None:
        return
    keys, _oldest = listed
    if keys:
        LOG.info(log_json(msg="registering ingress staging markers", count=len(keys)))
    for key in keys:
        document = _marker_document_or_none(key)
        if document is None:
            continue
        if _register_staging_document(document, key) is False:
            return


def _claim_filter(request_id, claim_token):
    return IngressStagingPayload.objects.filter(request_id=request_id, claim_token=claim_token)


def claim_ingress_staging_row(request_id, now=None):
    """Claim one staging row. Returns the row when this caller wins, otherwise None.

    Pending rows are eligible at ``not_before``. A processing row is eligible again
    only after the lease expires. The winning update sets ``claim_token``. A losing
    claim does not increment ``attempts`` or change ``state``. Exhausted retries are
    marked failed by ``release_for_retry`` while that token is still held.
    """
    now = now or timezone.now()
    lease_cutoff = now - INGRESS_STAGING_LEASE
    eligible = Q(state=IngressStagingState.PENDING) & (Q(not_before__isnull=True) | Q(not_before__lte=now)) | Q(
        state=IngressStagingState.PROCESSING, claimed_at__lte=lease_cutoff
    )
    attempts_remaining = Q(attempts__lt=settings.MAX_UPDATE_RETRIES) | Q(attempts__isnull=True)
    claim_token = uuid.uuid4()
    updated = (
        IngressStagingPayload.objects.filter(request_id=request_id)
        .filter(eligible)
        .filter(attempts_remaining)
        .update(
            state=IngressStagingState.PROCESSING,
            claimed_at=now,
            claim_token=claim_token,
            enqueued_at=None,
            attempts=Coalesce(F("attempts"), Value(0), output_field=IntegerField()) + Value(1),
        )
    )
    if not updated:
        return None
    return IngressStagingPayload.objects.get(request_id=request_id)


def ingress_claim_held(request_id, claim_token):
    """Return True when this token still owns the processing row."""
    return _claim_filter(request_id, claim_token).filter(state=IngressStagingState.PROCESSING).exists()


def heartbeat_ingress_claim(request_id, claim_token, now=None):
    """Refresh the lease for the worker that still holds ``claim_token``.

    Returns False when another worker has taken the row. The caller must stop.
    """
    now = now or timezone.now()
    updated = (
        _claim_filter(request_id, claim_token).filter(state=IngressStagingState.PROCESSING).update(claimed_at=now)
    )
    return bool(updated)


def _log_lost_claim(request_id, action):
    LOG.info(log_json(request_id, msg="ingress staging claim lost", action=action))


def release_for_retry(request_id, claim_token, error):
    """Return a failed claim to pending, or mark it failed at the retry limit.

    The update matches ``claim_token``. A worker that lost the row does not write
    ``pending`` or ``failed``.
    """
    row = _claim_filter(request_id, claim_token).first()
    if row is None:
        _log_lost_claim(request_id, "release")
        return False
    message = _error_text(error)
    if (row.attempts or 0) >= settings.MAX_UPDATE_RETRIES:
        updated = _claim_filter(request_id, claim_token).update(
            state=IngressStagingState.FAILED,
            last_error=message,
            claim_token=None,
        )
        if not updated:
            _log_lost_claim(request_id, "fail")
            return False
        LOG.error(
            log_json(
                row.request_id,
                msg="staged ingress payload failed permanently",
                org_id=row.org_id,
                cluster_id=row.cluster_id,
                s3_key=row.s3_key,
                attempts=row.attempts,
            )
        )
        return True
    delay_minutes = min(2 ** ((row.attempts or 1) - 1), 30)
    not_before = timezone.now() + timedelta(minutes=delay_minutes)
    updated = _claim_filter(request_id, claim_token).update(
        state=IngressStagingState.PENDING,
        not_before=not_before,
        last_error=message,
        claim_token=None,
    )
    if not updated:
        _log_lost_claim(request_id, "retry")
        return False
    LOG.warning(
        log_json(
            request_id,
            msg="staged ingress payload will be retried",
            attempts=row.attempts,
            not_before=not_before.isoformat(),
            error=type(error).__name__,
        )
    )
    return True


def mark_processed(request_id, claim_token):
    """Mark the row processed and drop the Kafka payload, including identity.

    Returns False when this worker no longer holds ``claim_token``.
    """
    updated = _claim_filter(request_id, claim_token).update(
        state=IngressStagingState.PROCESSED,
        last_error=None,
        payload=None,
        claim_token=None,
    )
    if not updated:
        _log_lost_claim(request_id, "processed")
        return False
    return True


def _recently_enqueued(now):
    """Skip rows the reconciler already handed off inside the lease window."""
    lease_cutoff = now - INGRESS_STAGING_LEASE
    return Q(enqueued_at__isnull=True) | Q(enqueued_at__lte=lease_cutoff)


def _record_reconciler_enqueue(request_id, now):
    """Remember a successful reconciler publish without blocking a live claim."""
    lease_cutoff = now - INGRESS_STAGING_LEASE
    still_unclaimed = (
        Q(state=IngressStagingState.PENDING)
        | Q(state=IngressStagingState.PROCESSING, claimed_at__lte=lease_cutoff)
        | Q(state=IngressStagingState.PROCESSING, claimed_at__isnull=True)
    )
    IngressStagingPayload.objects.filter(request_id=request_id).filter(still_unclaimed).update(enqueued_at=now)


def _claimable_request_ids(now):
    """Return request ids the eager enqueue did not finish.

    Pending rows younger than the beat grace are left for the in-flight task.
    Rows already published by this reconciler stay ineligible for one lease.
    """
    grace_cutoff = now - INGRESS_STAGING_BEAT_GRACE
    lease_cutoff = now - INGRESS_STAGING_LEASE
    pending = Q(state=IngressStagingState.PENDING, stored_at__lte=grace_cutoff) & (
        Q(not_before__isnull=True) | Q(not_before__lte=now)
    )
    expired_lease = Q(state=IngressStagingState.PROCESSING, claimed_at__lte=lease_cutoff)
    attempts_remaining = Q(attempts__lt=settings.MAX_UPDATE_RETRIES) | Q(attempts__isnull=True)
    return list(
        IngressStagingPayload.objects.filter(pending | expired_lease)
        .filter(attempts_remaining)
        .filter(_recently_enqueued(now))
        .order_by("stored_at")
        .values_list("request_id", flat=True)[:INGRESS_STAGING_RECONCILE_BATCH]
    )


def _publish_ingress_staging_gauges(now):
    """Record how many staging rows are waiting and how old the oldest one is."""
    INGRESS_STAGING_PENDING.set(IngressStagingPayload.objects.filter(state=IngressStagingState.PENDING).count())
    INGRESS_STAGING_FAILED.set(IngressStagingPayload.objects.filter(state=IngressStagingState.FAILED).count())
    oldest = IngressStagingPayload.objects.filter(
        state__in=(
            IngressStagingState.PENDING,
            IngressStagingState.PROCESSING,
            IngressStagingState.FAILED,
        ),
        stored_at__isnull=False,
    ).aggregate(oldest=Min("stored_at"))["oldest"]
    if oldest is None:
        INGRESS_STAGING_OLDEST_AGE.set(0)
        return
    INGRESS_STAGING_OLDEST_AGE.set(max((now - oldest).total_seconds(), 0))


@celery_app.task(name=RECONCILE_INGRESS_STAGING_TASK, queue=IngressQueue.DEFAULT)
def reconcile_ingress_staging():
    """Register pending S3 markers, then enqueue rows the eager handoff did not finish.

    Marker registration upserts a staging row and deletes the marker only after
    that upsert succeeds. A successful row publish sets ``enqueued_at``. That
    row is not published again until the lease passes, which is the same window
    used for a dropped worker.
    """
    now = timezone.now()
    _publish_ingress_staging_gauges(now)
    _register_pending_markers(now)
    request_ids = _claimable_request_ids(now)
    LOG.info(log_json(msg="reconciling staged ingress payloads", count=len(request_ids)))
    for request_id in request_ids:
        try:
            celery_app.send_task(PROCESS_STAGED_INGRESS_TASK, args=[request_id], queue=IngressQueue.DEFAULT)
        except KombuOperationalError as error:
            LOG.warning(
                log_json(
                    request_id,
                    msg="failed to enqueue staged ingress reconciler task",
                    error=type(error).__name__,
                )
            )
            continue
        _record_reconciler_enqueue(request_id, now)


@celery_app.task(name=EXPIRE_INGRESS_STAGING_TASK, queue=IngressQueue.DEFAULT)
def expire_ingress_staging():
    """Delete processed staging rows, their tarballs, and their receipts.

    Failed rows and their objects stay until an operator replays or drops them.
    The ``by_request`` receipt is deleted with the tarball so a later redelivery
    does not treat an expired object as already stored.
    """
    cutoff = timezone.now() - INGRESS_STAGING_RETENTION
    rows = list(
        IngressStagingPayload.objects.filter(state=IngressStagingState.PROCESSED, stored_at__lte=cutoff)
        .order_by("stored_at")
        .values_list("id", "s3_key", "request_id")[:INGRESS_STAGING_RECONCILE_BATCH]
    )
    if not rows:
        return 0
    keys = []
    for _, s3_key, request_id in rows:
        if s3_key:
            keys.append(s3_key)
        receipt_key = _receipt_key(request_id)
        if receipt_key not in keys:
            keys.append(receipt_key)
    if keys:
        deleted = delete_s3_objects("ingress-staging-expire", keys, {})
        if not deleted:
            LOG.warning(log_json(msg="ingress staging retention left objects in place", count=len(keys)))
            return 0
    deleted_rows, _ = IngressStagingPayload.objects.filter(id__in=[row_id for row_id, _, _ in rows]).delete()
    LOG.info(log_json(msg="expired processed ingress staging rows", count=deleted_rows))
    return deleted_rows
