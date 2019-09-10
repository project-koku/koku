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
import os
import time
import logging
import json
import asyncio
import threading
from aiokafka import AIOKafkaConsumer

from django.db.models.signals import post_save
from django.dispatch import receiver
from api.provider.models import Sources

from kafka.errors import KafkaError

from sources.utils import extract_from_header
from sources.sources_http_client import SourcesHTTPClient, SourcesHTTPClientError
from sources.koku_http_client import KokuHTTPClient, KokuHTTPClientError, KokuHTTPClientNonRecoverableError
from sources import storage


LOG = logging.getLogger(__name__)
SOURCES_KAFKA_HOST = os.getenv('SOURCES_KAFKA_HOST', 'localhost')
SOURCES_KAFKA_PORT = os.getenv('SOURCES_KAFKA_PORT', '29092')
SOURCES_KAFKA_ADDRESS = f'{SOURCES_KAFKA_HOST}:{SOURCES_KAFKA_PORT}'
SOURCES_TOPIC = os.getenv('SOURCES_KAFKA_TOPIC', 'platform.sources.event-stream')

EVENT_LOOP = asyncio.new_event_loop()
BUILDER_LOOP = asyncio.new_event_loop()

process_queue = asyncio.Queue(loop=EVENT_LOOP)


class KafkaMsgHandlerError(Exception):
    """Kafka msg handler error."""


def load_process_queue():
    create_events = storage.load_providers_to_create()
    destroy_events = storage.load_providers_to_delete()
    pending_events = create_events + destroy_events
    pending_events.sort(key=lambda item:item.get('offset'))
    for event in pending_events:
        process_queue.put_nowait(event)


@receiver(post_save, sender=Sources)
def storage_callback(sender, **kwargs):
    pending_events = storage.load_providers_to_create()
    for event in pending_events:
        process_queue.put_nowait(event)


def get_sources_msg_data(msg, app_type_id):
    msg_data = {}
    if msg.topic == SOURCES_TOPIC:
        try:
            value = json.loads(msg.value.decode('utf-8'))
            event_type = extract_from_header(msg.headers, 'event_type')
            if event_type in ('Application.create', 'Application.destroy'):
                if int(value.get('application_type_id')) == app_type_id:
                    print("Application Message: ", str(msg))
                    msg_data['event_type'] = event_type
                    msg_data['offset'] = msg.offset
                    msg_data['source_id'] = int(value.get('source_id'))
                    msg_data['auth_header'] = extract_from_header(msg.headers, 'x-rh-identity')
            elif event_type in ('Source.destroy', ):
                print("Source Message: ", str(msg))
                msg_data['event_type'] = event_type
                msg_data['offset'] = msg.offset
                msg_data['source_id'] = int(value.get('id'))
                msg_data['auth_header'] = extract_from_header(msg.headers, 'x-rh-identity')
            else:
                print("Other Message: ", str(msg))
        except Exception as error:
            LOG.error('Unable load message. Error: %s', str(error))
            raise KafkaMsgHandlerError("Unable to load message")

    return msg_data


async def sources_network_info(source_id, auth_header):
    sources_network = SourcesHTTPClient(auth_header, source_id)
    try:
        source_details = sources_network.get_source_details()
    except SourcesHTTPClientError as conn_err:
        err_msg = f'Unable to get for Source {source_id} information. Reason: {str(conn_err)}'
        print(err_msg)
        return
    source_name = source_details.get('name')
    source_type_id = int(source_details.get('source_type_id'))

    authentication = ''
    if source_type_id == 1:
        source_type = 'OCP'
        authentication = source_details.get('uid')
    elif source_type_id == 2:
        source_type = 'AWS'
        authentication = sources_network.get_aws_role_arn()
    else:
        source_type = 'UNK'

    storage.add_provider_sources_network_info(source_id, source_name, source_type, authentication)


async def process_messages(msg_pending_queue, in_progress_queue, application_source_id):  # pragma: no cover
    print("Waiting to process incoming kafka messages...")
    while True:
        msg = await msg_pending_queue.get()

        msg_data = get_sources_msg_data(msg, application_source_id)
        if msg_data.get('event_type') == 'Application.create':
            storage.create_provider_event(msg_data.get('source_id'), msg_data.get('auth_header'), msg_data.get('offset'))
            await sources_network_info(msg_data.get('source_id'), msg_data.get('auth_header'))
        elif msg_data.get('event_type') in ('Application.destroy', 'Source.destroy'):
            await storage.enqueue_source_delete(in_progress_queue, msg_data.get('source_id'))


async def listen_for_messages(consumer, msg_pending_queue):  # pragma: no cover
    print('Listener started.  Waiting for messages...')
    try:
        # Consume messages
        async for msg in consumer:
            await msg_pending_queue.put(msg)
    finally:
        # Will leave consumer group; perform autocommit if enabled.
        await consumer.stop()


def execute_koku_provider_op(msg):
    provider = msg.get('provider')
    operation = msg.get('operation')
    koku_client = KokuHTTPClient(provider.auth_header)
    try:
        if operation == 'create':
            print(f'Creating Koku Provider for Source ID: {str(provider.source_id)}')
            koku_details = koku_client.create_provider(provider.name, provider.source_type, provider.authentication,
                                                       provider.billing_source)
            print(f'Koku Provider UUID {str(koku_details.get("uuid"))} assigned to Source ID {str(provider.source_id)}.')
            storage.add_provider_koku_uuid(provider.source_id, koku_details.get('uuid'))
        elif operation == 'destroy':
            if provider.koku_uuid:
                response = koku_client.destroy_provider(provider.koku_uuid)
                print(f'Koku Provider UUID ({str(provider.koku_uuid)}) Removal Status Code: {str(response.status_code)}')
            storage.destroy_provider_event(provider.source_id)
    except KokuHTTPClientError as koku_error:
        raise KafkaMsgHandlerError('Koku provider error: ', str(koku_error))
    except KokuHTTPClientNonRecoverableError as koku_error:
        err_msg = f'Unable to {operation} provider for Source ID: {str(provider.source_id)}. Reason: {str(koku_error)}'
        print(err_msg)


async def synchronize_sources(process_queue):
    print('Processing koku provider events...')
    while True:
        msg = await process_queue.get()
        try:
            execute_koku_provider_op(msg)
        except KafkaMsgHandlerError as error:
            print('Unable to process objects. Error: ', str(error))
            await asyncio.sleep(10)
            print('Retry Failed. re-queuing...')
            await process_queue.put(msg)


async def connect_consumer(consumer):
    """Connect consumer."""
    try:
        await consumer.start()
    except KafkaError as kafka_error:
        raise KafkaMsgHandlerError('Unable to connect to kafka server. Reason: ', str(kafka_error))


def asyncio_listener_thread(event_loop):
    """
    Listener thread function to run the asyncio event loop.

    Args:
        None

    Returns:
        None

    """
    pending_process_queue = asyncio.Queue(loop=event_loop)

    consumer = AIOKafkaConsumer(
        SOURCES_TOPIC,
        loop=event_loop, bootstrap_servers=SOURCES_KAFKA_ADDRESS, group_id='hccm-group'
    )
    while True:
        try:
            event_loop.run_until_complete(connect_consumer(consumer))
            break
        except KafkaMsgHandlerError as err:
            print('Kafka connection failure.  Error: ', str(err))
        print('Attempting kafka reconnect...')
        time.sleep(10)

    try:
        fake_header = 'eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzNDUiLCAiaW50ZXJuYWwiOiB7Im9yZ19pZCI6ICI1NDMyMSJ9fX0='
        cost_management_type_id = SourcesHTTPClient(fake_header).get_cost_management_application_type_id()

        load_process_queue()
        while True:
            event_loop.create_task(listen_for_messages(consumer, pending_process_queue))
            event_loop.create_task(process_messages(pending_process_queue, process_queue, cost_management_type_id))
            event_loop.create_task(synchronize_sources(process_queue))
            event_loop.run_forever()
    except SourcesHTTPClientError:
        print("Unable to connect to Sources REST API.  Check configuration and restart server...")
        exit(0)
    except KeyboardInterrupt:
        exit(0)


def initialize_kafka_listener():
    event_loop_thread = threading.Thread(target=asyncio_listener_thread, args=(EVENT_LOOP,))
    event_loop_thread.start()
    print('Listening for kafka events')
