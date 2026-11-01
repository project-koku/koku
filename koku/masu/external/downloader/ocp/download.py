#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Download an HCCM ingress tarball and read its manifest.

The listener uses this module to fetch the quarantine object and peek at
``manifest.json``. The durable copy and staging row live in
``payload_landing``. Report extraction starts after that object is in our bucket.
"""
import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from tarfile import ReadError
from tarfile import TarFile

import requests
from pydantic import ValidationError

from api.common import log_json
from masu.config import Config
from masu.external.downloader.ocp.exceptions import KafkaMsgHandlerError
from masu.prometheus_stats import OCP_INGRESS_DOWNLOAD_GUARDRAIL_COUNTER
from masu.util.ocp import common as utils

LOG = logging.getLogger(__name__)
_MAX_MANIFEST_BYTES = 10 * 1_024 * 1_024  # 10 MB — orders of magnitude above any real manifest
_CONNECT_TIMEOUT_SECONDS = 10
_READ_TIMEOUT_SECONDS = 60
_TOTAL_DOWNLOAD_TIMEOUT_SECONDS = Config.OCP_INGRESS_DOWNLOAD_TIMEOUT_SECONDS
_MAX_PAYLOAD_BYTES = Config.OCP_INGRESS_DOWNLOAD_MAX_PAYLOAD_BYTES
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
_REWINDABLE_STATUS_CODES = {408, 429}


def _write_download_chunks(request_id, download_response, payload_file, context):
    """Stream response body to ``payload_file`` with time and size limits."""
    download_started = time.monotonic()
    bytes_written = 0
    for chunk in download_response.iter_content(chunk_size=_DOWNLOAD_CHUNK_BYTES):
        if not chunk:
            continue
        elapsed_seconds = time.monotonic() - download_started
        if elapsed_seconds > _TOTAL_DOWNLOAD_TIMEOUT_SECONDS:
            OCP_INGRESS_DOWNLOAD_GUARDRAIL_COUNTER.labels(failure_type="timeout").inc()
            msg = (
                "Unable to download file. Download exceeded total time limit of "
                f"{_TOTAL_DOWNLOAD_TIMEOUT_SECONDS} seconds."
            )
            LOG.warning(log_json(request_id, msg=msg, context=context))
            raise KafkaMsgHandlerError(msg)
        bytes_written += len(chunk)
        if bytes_written > _MAX_PAYLOAD_BYTES:
            OCP_INGRESS_DOWNLOAD_GUARDRAIL_COUNTER.labels(failure_type="size").inc()
            msg = "Unable to download file. Download exceeded maximum allowed size of " f"{_MAX_PAYLOAD_BYTES} bytes."
            LOG.warning(log_json(request_id, msg=msg, context=context))
            raise KafkaMsgHandlerError(msg)
        payload_file.write(chunk)


def _stream_url_to_file(request_id, url, temp_file, context):
    """HTTP GET ``url`` and write the body to ``temp_file``."""
    try:
        with requests.get(
            url,
            stream=True,
            timeout=(_CONNECT_TIMEOUT_SECONDS, _READ_TIMEOUT_SECONDS),
        ) as download_response:
            download_response.raise_for_status()
            try:
                with temp_file.open("wb") as payload_file:
                    _write_download_chunks(request_id, download_response, payload_file, context)
            except OSError as error:
                msg = f"Unable to write file. Error: {str(error)}"
                LOG.warning(log_json(request_id, msg=msg, context=context), exc_info=error)
                raise KafkaMsgHandlerError(msg) from error
    except requests.exceptions.HTTPError as err:
        msg = f"Unable to download file. Error: {str(err)}"
        LOG.warning(log_json(request_id, msg=msg), exc_info=err)
        raise KafkaMsgHandlerError(msg) from err


def download_payload(request_id, url, context):
    """Download the payload from ingress to temporary location.

    The body is streamed to disk. Connect and per-read timeouts bound idle
    gaps; a total wall-clock limit and payload size cap stop trickle responses
    from holding the listener thread until the Kafka session times out.
    """
    # Create temporary directory for initial file staging and verification in the
    # OpenShift PVC directory so that any failures can be triaged in the event
    # the pod goes down.
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    temp_dir = tempfile.mkdtemp(dir=Config.DATA_DIR)
    try:
        sanitized_request_id = re.sub("[^A-Za-z0-9]+", "", request_id)
        temp_file = Path(temp_dir, sanitized_request_id).with_suffix(".tar.gz")
        _stream_url_to_file(request_id, url, temp_file, context)
        return temp_file
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def read_manifest_from_tarball(request_id, tarball_path, context) -> utils.Manifest:
    """Read and validate manifest.json from a tarball without extracting archive members."""
    if not os.path.isfile(tarball_path):
        msg = f"Unable to find tar file {tarball_path}."
        LOG.warning(log_json(request_id, msg=msg, context=context))
        raise KafkaMsgHandlerError("Extraction failure, file not found.")

    try:
        with TarFile.open(tarball_path, mode="r:gz") as mytar:
            manifest_member = utils.get_manifest_member_name(mytar.getnames())
            manifest_file = mytar.extractfile(manifest_member)
            if manifest_file is None:
                raise KafkaMsgHandlerError("No manifest found in payload.")
            manifest_data = manifest_file.read(_MAX_MANIFEST_BYTES + 1)
            if len(manifest_data) > _MAX_MANIFEST_BYTES:
                raise ValueError(f"manifest.json exceeds maximum allowed size of {_MAX_MANIFEST_BYTES} bytes")
            return utils.Manifest.model_validate_json(manifest_data)
    except (ReadError, EOFError, OSError, ValueError) as error:
        msg = f"Unable to read manifest from tar file {tarball_path}. Reason: {str(error)}"
        LOG.warning(log_json(request_id, msg=msg, context=context))
        raise KafkaMsgHandlerError("Extraction failure.") from error
    except ValidationError as error:
        msg = f"Invalid manifest in tar file {tarball_path}."
        LOG.warning(log_json(request_id, msg=msg, context=context))
        raise KafkaMsgHandlerError("Extraction failure.") from error


def is_permanent_download_error(error):
    """Return True when retrying the ingress download cannot recover the payload.

    408 and 429 are rewindable. Other 4xx responses, including a quarantine
    object that is gone, are confirmed as failures.

    Payload size over the configured cap is permanent for the same presigned URL —
    retry would hit the same object. Slow downloads may succeed on retry (transient
    ingress or network), so time limit violations are not permanent here.
    """
    error_msg = str(error)
    if "exceeded maximum allowed size" in error_msg:
        return True

    # Check for HTTP 4xx errors (except rewindable status codes)
    cause = error.__cause__
    if isinstance(cause, requests.exceptions.HTTPError) and cause.response is not None:
        status_code = cause.response.status_code
        if status_code in _REWINDABLE_STATUS_CODES:
            return False
        return 400 <= status_code < 500
    return False
