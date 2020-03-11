#
# Copyright 2019 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
from celery.utils.log import get_task_logger
from rest_framework.exceptions import ValidationError

from api.provider.models import Provider
from api.provider.models import Sources
from koku.celery import app
from sources.kafka_source_manager import KafkaSourceManager
from sources.storage import SCREEN_MAP

LOG = get_task_logger(__name__)


@app.task(name="sources.tasks.create_provider")
def create_provider(source_id):
    try:
        instance = Sources.objects.get(source_id=source_id)
    except Exception as e:
        LOG.error(f"This source should exist. error: {e}")

    uuid = instance.source_uuid
    source_mgr = KafkaSourceManager(instance.auth_header)

    screen_fn = SCREEN_MAP.get(instance.source_type)
    if not (screen_fn and screen_fn(instance)):
        LOG.info("WHAT")
        return

    provider = [instance.name, instance.source_type, instance.authentication, instance.billing_source]

    status = "available"
    err_msg = ""
    try:
        obj = Provider.objects.get(uuid=uuid)
    except Provider.DoesNotExist:
        func = source_mgr.create_provider
        provider.append(instance.source_uuid)
        operation = "create"
    else:
        func = source_mgr.update_provider
        provider.insert(0, instance.source_uuid)
        operation = "update"

    try:
        obj = func(*provider)
    except ValidationError as err:
        LOG.info(f"Provider {operation} ValidationError: {err}")
        status = "unavailable"
        err_msg = str(err)
    else:
        instance.koku_uuid = obj.uuid
        instance.pending_update = False
        LOG.info(f"Provider {operation}d: {obj.uuid}")

    json_data = {"availability_status": status, "availability_status_error": str(err_msg)}
    instance.status = json_data
    instance.save()
