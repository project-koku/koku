#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tasks for sources-client."""
import logging

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from api.common import log_json
from api.provider.models import Sources
from api.provider.provider_manager import ProviderProcessingError
from koku import celery_app
from masu.processor.tasks import PRIORITY_QUEUE
from masu.processor.tasks import REMOVE_EXPIRED_DATA_QUEUE
from sources.api.source_status import SourceStatus
from sources.sources_provider_coordinator import SourcesProviderCoordinator
from sources.storage import load_providers_to_delete
from sources.storage import mark_provider_as_inactive


LOG = logging.getLogger(__name__)


@celery_app.task(
    name="sources.tasks.delete_source",
    bind=True,
    autoretry_for=(ProviderProcessingError,),
    retry_backoff=True,
    max_retries=settings.MAX_SOURCE_DELETE_RETRIES,
    queue=PRIORITY_QUEUE,
)
def delete_source(self, source_id, auth_header, koku_uuid):
    """Delete Provider and Source."""
    LOG.info(log_json(msg="deactivating provider", provider_uuid=koku_uuid, source_id=source_id))
    mark_provider_as_inactive(koku_uuid)
    LOG.info(log_json(msg="deleting provider", provider_uuid=koku_uuid, source_id=source_id))
    coordinator = SourcesProviderCoordinator(source_id, auth_header)
    coordinator.destroy_account(koku_uuid, self.request.retries)  # noqa: F821
    LOG.info(log_json(msg="deleted provider", provider_uuid=koku_uuid, source_id=source_id))


@celery_app.task(name="sources.tasks.delete_source_beat", queue=REMOVE_EXPIRED_DATA_QUEUE)
def delete_source_beat():
    providers = load_providers_to_delete()
    for p in providers:
        provider = p.get("provider")
        delete_source.delay(provider.source_id, provider.auth_header, provider.koku_uuid)


@celery_app.task(name="sources.tasks.source_status_beat", queue=PRIORITY_QUEUE)
def source_status_beat():
    """Source Status push."""
    sources_query = Sources.objects.filter(source_id__isnull=False).all()
    for source in sources_query:
        ctx = {"provider_uuid": source.koku_uuid, "source_id": source.source_id}
        try:
            LOG.info(log_json(msg="delivering source status", context=ctx))
            status_pusher = SourceStatus(source.source_id)
            status_pusher.push_status()
            LOG.info(log_json(msg="delivered source status", context=ctx))
        except ObjectDoesNotExist:
            LOG.info(log_json(msg="source status not pushed, unable to find source", context=ctx))
