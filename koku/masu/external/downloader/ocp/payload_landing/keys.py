#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Object keys and the marker document for a staged ingress payload."""
import re

from masu.config import Config


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
