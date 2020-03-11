from celery.utils.log import get_task_logger

from api.provider.models import Provider
from api.provider.models import Sources
from koku.celery import app
from sources.kafka_source_manager import KafkaSourceManager

LOG = get_task_logger(__name__)


@app.task(name="sources.tasks.create_provider")
def create_provider(source_id):
    try:
        instance = Sources.objects.get(source_id=source_id)
    except Exception as e:
        LOG.error(f"This source should exist. error: {e}")

    uuid = instance.source_uuid
    source_mgr = KafkaSourceManager(instance.auth_header)

    try:
        obj = Provider.objects.get(uuid=uuid)
    except Provider.DoesNotExist:
        obj = source_mgr.create_provider(
            instance.name, instance.source_type, instance.authentication, instance.billing_source, instance.source_uuid
        )
        instance.koku_uuid = obj.uuid
        instance.pending_update = False
        instance.save()
        LOG.info(f"Provider created: {obj.uuid}")
    else:
        obj = source_mgr.update_provider(
            instance.source_uuid, instance.name, instance.source_type, instance.authentication, instance.billing_source
        )
        instance.koku_uuid = obj.uuid
        instance.save()
        LOG.info(f"Provider updated: {obj.uuid}")
