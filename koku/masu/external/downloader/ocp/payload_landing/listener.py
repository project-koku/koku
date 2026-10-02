#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Store an HCCM ingress tarball and a pending marker. This path does not open Postgres."""
import logging
import shutil

import requests
from kombu.exceptions import OperationalError as KombuOperationalError

from api.common import log_json
from common.queues import IngressQueue
from koku import celery_app
from masu.external.downloader.ocp import download
from masu.external.downloader.ocp.exceptions import FAILURE_CONFIRM_STATUS
from masu.external.downloader.ocp.exceptions import KafkaMsgHandlerError
from masu.external.downloader.ocp.exceptions import SUCCESS_CONFIRM_STATUS
from masu.external.downloader.ocp.payload_landing.constants import REGISTER_INGRESS_STAGING_TASK
from masu.external.downloader.ocp.payload_landing.keys import _inbox_tar_key
from masu.external.downloader.ocp.payload_landing.keys import _marker_document
from masu.external.downloader.ocp.payload_landing.keys import _pending_marker_key
from masu.external.downloader.ocp.payload_landing.keys import _receipt_key
from masu.external.downloader.ocp.payload_landing.objects import _copy_s3_key
from masu.external.downloader.ocp.payload_landing.objects import _put_bytes
from masu.external.downloader.ocp.payload_landing.objects import _put_json
from masu.external.downloader.ocp.payload_landing.objects import _rewind_for_staging_error
from masu.external.downloader.ocp.payload_landing.objects import _s3_key_exists
from masu.util.aws.common import UploadError

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


def _enqueue_register_ingress(request_id, context):
    """Enqueue marker registration. A broker failure must not rewind the Kafka consumer."""
    _enqueue_task(
        request_id,
        context,
        REGISTER_INGRESS_STAGING_TASK,
        "failed to enqueue ingress staging register; reconciler will retry",
    )


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
