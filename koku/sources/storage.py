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
import collections
import logging
import json
from api.provider.models import Sources
from sources.utils import extract_from_header

LOG = logging.getLogger(__name__)


def load_providers_to_create():
    providers_to_create = []
    all_providers = Sources.objects.all()
    for provider in all_providers:
        if provider.source_type == 'AWS':
            if provider.source_id and provider.name and provider.auth_header and provider.billing_source and not provider.koku_uuid:
                providers_to_create.append({'operation': 'create', 'provider': provider})
        else:
            if provider.source_id and provider.name and provider.auth_header and not provider.koku_uuid:
                providers_to_create.append({'operation': 'create', 'provider': provider})
    return providers_to_create


async def enqueue_source_delete(queue, source_id):
    print("IN ENQUEUE_SOURCE_DELETE")
    try:
        source = Sources.objects.get(source_id=source_id)
        print('Adding to processing queue: ', str(source))
        await queue.put({'operation': 'destroy', 'provider': source})
    except Sources.DoesNotExist:
        LOG.error("Unable to enqueue source delete.  %s not found.", str(source_id))


def enqueue_source_create(queue, topic, sources):
    ConsumerRecord = collections.namedtuple("ConsumerRecord", ["topic", "value"])
    for source in sources:
        # TODO: Need header for this to work
        payload = {'id': source.get('id'),
                   'source_id': source.get('source_id'),
                   'uid': source.get('uid'),
                   'tenant': source.get('tenant')}
        record = ConsumerRecord(topic, payload)
        queue.put_nowait(record)

def create_provider_event(msg):
    value = json.loads(msg.value.decode('utf-8'))
    offset = msg.offset
    headers = msg.headers
    source_id = int(value.get('source_id'))
    operation = extract_from_header(headers, 'event_type')
    auth_header = extract_from_header(headers, 'x-rh-identity')
    try:
        query = Sources.objects.get(source_id=source_id)
        query.auth_header = auth_header
        query.save()
    except Sources.DoesNotExist:
        new_event = Sources(source_id=source_id, auth_header=auth_header)
        new_event.save()


def destroy_provider_event(source_id):
    koku_uuid = None
    try:
        query = Sources.objects.get(source_id=source_id)
        koku_uuid = query.koku_uuid
        query.delete()
    except Sources.DoesNotExist:
        LOG.error("Unable to delete.  Source ID: %s does not exist", str(source_id))

    return koku_uuid


def add_provider_sources_network_info(source_id, name, source_type, authentication):
    try:
        query = Sources.objects.get(source_id=source_id)
        query.name = name
        query.source_type = source_type
        query.authentication = authentication
        query.save()
    except Sources.DoesNotExist:
        LOG.error("Unable to add network details.  Source ID: %s does not exist", str(source_id))


def add_provider_billing_source(source_id, billing_source):
    try:
        query = Sources.objects.get(source_id=source_id)
        query.billing_source = billing_source
        query.save()
    except Sources.DoesNotExist:
        LOG.error("Unable to add billing_source.  Source ID: %s does not exist", str(source_id))


def add_provider_koku_uuid(source_id, koku_uuid):
    try:
        query = Sources.objects.get(source_id=source_id)
        query.koku_uuid = koku_uuid
        query.save()
    except Sources.DoesNotExist:
        LOG.error("%s does not exist", str(source_id))
