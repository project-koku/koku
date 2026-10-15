#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""S3 reads and writes for the ingress staging inbox.

Listener helpers rewind Kafka on a transient S3 error. Register and reconcile
helpers return None and leave the marker in place.
"""
import io
import json
import logging

from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError
from django.conf import settings

from api.common import log_json
from masu.external.downloader.ocp.exceptions import KafkaMsgHandlerError
from masu.external.downloader.ocp.payload_landing.constants import _MISSING_S3_CODES
from masu.external.downloader.ocp.payload_landing.keys import _pending_marker_prefix
from masu.util.aws.common import copy_data_to_s3_bucket
from masu.util.aws.common import get_s3_resource

LOG = logging.getLogger(__name__)


def _rewind_for_staging_error(request_id, context, error, message):
    """Log a transient staging failure and raise so the Kafka consumer rewinds."""
    msg = f"{message} Error: {type(error).__name__}: {error}"
    LOG.warning(log_json(request_id, msg=msg, context=context))
    raise KafkaMsgHandlerError(msg) from error


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
