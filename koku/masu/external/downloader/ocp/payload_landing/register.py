#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Turn a pending S3 marker into an IngressStagingPayload row."""
import logging

from django.db import IntegrityError
from django.utils import timezone
from kombu.exceptions import OperationalError as KombuOperationalError

from api.common import log_json
from api.utils import DateHelper
from common.queues import IngressQueue
from koku import celery_app
from masu.external.downloader.ocp.exceptions import KafkaMsgHandlerError
from masu.external.downloader.ocp.payload_landing.constants import _DB_ERRORS
from masu.external.downloader.ocp.payload_landing.constants import INGRESS_STAGING_REGISTER_LIMIT
from masu.external.downloader.ocp.payload_landing.constants import PROCESS_STAGED_INGRESS_TASK
from masu.external.downloader.ocp.payload_landing.constants import REGISTER_INGRESS_STAGING_TASK
from masu.external.downloader.ocp.payload_landing.keys import _pending_marker_key
from masu.external.downloader.ocp.payload_landing.keys import _receipt_key
from masu.external.downloader.ocp.payload_landing.objects import _list_pending_markers
from masu.external.downloader.ocp.payload_landing.objects import _read_marker_json
from masu.prometheus_stats import INGRESS_STAGING_PENDING_MARKER_OLDEST_AGE
from masu.prometheus_stats import INGRESS_STAGING_PENDING_MARKERS
from masu.util.aws.common import delete_s3_objects
from reporting_common.models import IngressStagingPayload
from reporting_common.models import IngressStagingState

LOG = logging.getLogger(__name__)


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
