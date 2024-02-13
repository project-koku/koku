#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common util functions."""
from django.db.models import IntegerChoices

from common.enum import StrEnum


class ReportStep(IntegerChoices):
    DOWNLOADING = 3
    PROCESSING = 4
    OCP_CLOUD_PROCESSING = (5, "OCP-Cloud-Processing")


class Status(IntegerChoices):
    DONE = 1
    FAILED = 2


class CombinedChoices(IntegerChoices):
    DOWNLOADING = ReportStep.DOWNLOADING
    PROCESSING = ReportStep.PROCESSING
    OCP_CLOUD_PROCESSING = ReportStep.OCP_CLOUD_PROCESSING
    DONE = Status.DONE
    FAILED = Status.FAILED


class ManifestStep(StrEnum):
    DOWNLOAD = "download"
    PROCESSING = "processing"
    SUMMARY = "summary"


class ManifestState(StrEnum):
    START = "start"
    END = "end"
    FAILED = "failed"
    PENDING = "pending"
    IN_PROGRESS = "in-progress"
    COMPLETE = "complete"
