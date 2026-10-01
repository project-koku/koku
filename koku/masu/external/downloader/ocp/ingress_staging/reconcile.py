#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Register pending markers, then enqueue staging rows the eager handoff did not finish."""
import logging

from django.conf import settings
from django.db.models import Min
from django.db.models import Q
from django.utils import timezone
from kombu.exceptions import OperationalError as KombuOperationalError

from api.common import log_json
from common.queues import IngressQueue
from koku import celery_app
from masu.external.downloader.ocp.ingress_staging.constants import INGRESS_STAGING_BEAT_GRACE
from masu.external.downloader.ocp.ingress_staging.constants import INGRESS_STAGING_LEASE
from masu.external.downloader.ocp.ingress_staging.constants import INGRESS_STAGING_RECONCILE_BATCH
from masu.external.downloader.ocp.ingress_staging.constants import PROCESS_STAGED_INGRESS_TASK
from masu.external.downloader.ocp.ingress_staging.constants import RECONCILE_INGRESS_STAGING_TASK
from masu.external.downloader.ocp.ingress_staging.register import _register_pending_markers
from masu.prometheus_stats import INGRESS_STAGING_FAILED
from masu.prometheus_stats import INGRESS_STAGING_OLDEST_AGE
from masu.prometheus_stats import INGRESS_STAGING_PENDING
from reporting_common.models import IngressStagingPayload
from reporting_common.models import IngressStagingState

LOG = logging.getLogger(__name__)


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
