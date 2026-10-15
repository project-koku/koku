#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Store an HCCM ingress tarball in our bucket and record the staging row.

Download is finished when the raw tar is durable. The listener writes a pending
marker and leaves the row to the register task. This package enqueues extract
by name and does not import that task.
"""
from masu.external.downloader.ocp.payload_landing.constants import PROCESS_STAGED_INGRESS_TASK
from masu.external.downloader.ocp.payload_landing.constants import REGISTER_INGRESS_STAGING_TASK
from masu.external.downloader.ocp.payload_landing.listener import stage_ingress_s3_inbox
from masu.external.downloader.ocp.payload_landing.register import register_ingress_staging_marker

__all__ = [
    "PROCESS_STAGED_INGRESS_TASK",
    "REGISTER_INGRESS_STAGING_TASK",
    "register_ingress_staging_marker",
    "stage_ingress_s3_inbox",
]
