#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Claim, heartbeat, and release for one staged ingress row."""
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db.models import F
from django.db.models import IntegerField
from django.db.models import Q
from django.db.models import Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from api.common import log_json
from masu.external.downloader.ocp.payload_landing.constants import _LAST_ERROR_MAX_LENGTH
from masu.external.downloader.ocp.payload_landing.constants import INGRESS_STAGING_HANDOFF_LEASE
from masu.external.downloader.ocp.payload_landing.constants import INGRESS_STAGING_LEASE
from reporting_common.models import IngressStagingPayload
from reporting_common.models import IngressStagingState

LOG = logging.getLogger(__name__)


def _error_text(error):
    """Return a short error string that does not include the Kafka payload."""
    return f"{type(error).__name__}: {error}"[:_LAST_ERROR_MAX_LENGTH]


def _claim_filter(request_id, claim_token):
    return IngressStagingPayload.objects.filter(request_id=request_id, claim_token=claim_token)


def processing_reclaimable_q(now):
    """Return rows in ``processing`` another worker may take after lease expiry.

    ``enqueued_at`` after line-item handoff extends reclaim until
    ``INGRESS_STAGING_HANDOFF_LEASE`` so OCP queue wait is not confused with a
    dead extract worker.
    """
    lease_cutoff = now - INGRESS_STAGING_LEASE
    handoff_cutoff = now - INGRESS_STAGING_HANDOFF_LEASE
    return Q(state=IngressStagingState.PROCESSING, claimed_at__lte=lease_cutoff) & (
        Q(enqueued_at__isnull=True) | Q(enqueued_at__lte=handoff_cutoff)
    )


def claim_ingress_staging_row(request_id, now=None):
    """Claim one staging row. Returns the row when this caller wins, otherwise None.

    Pending rows are eligible at ``not_before``. A processing row is eligible again
    only after the lease expires. The winning update sets ``claim_token``. A losing
    claim does not increment ``attempts`` or change ``state``. Exhausted retries are
    marked failed by ``release_for_retry`` while that token is still held.
    """
    now = now or timezone.now()
    eligible = Q(state=IngressStagingState.PENDING) & (Q(not_before__isnull=True) | Q(not_before__lte=now)) | (
        processing_reclaimable_q(now)
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


def record_line_item_handoff(request_id, claim_token, now=None):
    """Record that line items were enqueued on the customer OCP queue."""
    now = now or timezone.now()
    updated = (
        _claim_filter(request_id, claim_token).filter(state=IngressStagingState.PROCESSING).update(enqueued_at=now)
    )
    return bool(updated)


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
