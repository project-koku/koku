#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Delete processed staging rows and the objects that belong to them."""
import logging

from django.utils import timezone

from api.common import log_json
from common.queues import IngressQueue
from koku import celery_app
from masu.external.downloader.ocp.ingress_staging.constants import EXPIRE_INGRESS_STAGING_TASK
from masu.external.downloader.ocp.ingress_staging.constants import INGRESS_STAGING_RECONCILE_BATCH
from masu.external.downloader.ocp.ingress_staging.constants import INGRESS_STAGING_RETENTION
from masu.external.downloader.ocp.ingress_staging.keys import _receipt_key
from masu.util.aws.common import delete_s3_objects
from reporting_common.models import IngressStagingPayload
from reporting_common.models import IngressStagingState

LOG = logging.getLogger(__name__)


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
