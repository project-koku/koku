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
import logging
import json
import asyncio
import threading
from aiokafka import AIOKafkaConsumer

from kafka.errors import ConnectionError as KafkaConnectionError

from sources.utils import extract_from_header
from sources.sources_http_client import SourcesHTTPClient
from sources.koku_http_client import KokuHTTPClient
from sources import storage

LOG = logging.getLogger(__name__)
SOURCES_KAFKA_HOST = os.getenv('SOURCES_KAFKA_HOST', 'localhost')
SOURCES_KAFKA_PORT = os.getenv('SOURCES_KAFKA_PORT', '29092')
SOURCES_KAFKA_ADDRESS = f'{SOURCES_KAFKA_HOST}:{SOURCES_KAFKA_PORT}'
SOURCES_TOPIC = os.getenv('SOURCES_KAFKA_TOPIC', 'platform.sources.event-stream')

EVENT_LOOP = asyncio.new_event_loop()
BUILDER_LOOP = asyncio.new_event_loop()

class KafkaMsgHandlerError(Exception):
    """Kafka msg handler error."""


def filter_message(msg, application_source_id):
    if msg.topic == SOURCES_TOPIC:
        if extract_from_header(msg.headers, 'event_type') == 'Application.create':
            try:
                value = json.loads(msg.value.decode('utf-8'))
                print('handle msg value: ', str(value))
                if int(value.get('application_type_id')) == application_source_id:
                    return True, 'create'
                else:
                    print('Ignoring message; wrong application source id')
                    return False, None
            except Exception as error:
                LOG.error('Unable load message. Error: %s', str(error))
                return False, None
        elif extract_from_header(msg.headers, 'event_type') == 'Application.destroy':
            try:
                value = json.loads(msg.value.decode('utf-8'))
                print('handle msg value: ', str(value))
                if int(value.get('application_type_id')) == application_source_id:
                    return True, 'destroy'
                else:
                    print('Ignoring message; wrong application source id')
                    return False, None
            except Exception as error:
                LOG.error('Unable load message. Error: %s', str(error))
                return False, None
        else:
            value = json.loads(msg.value.decode('utf-8'))
            print('Kafka event recieved: ', str(value))
            return False, None
    else:
        LOG.error('Unexpected Message')
    return False


async def sources_network_info(source_id, auth_header):
    sources_network = SourcesHTTPClient(auth_header, source_id)
    source_details = sources_network.get_source_details()
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


async def process_messages(msg_pending_queue, in_progress_queue):  # pragma: no cover
    application_source_id = None
    print("IN process_messages")
    while True:
        msg = await msg_pending_queue.get()
        if not application_source_id:
            fake_header = 'eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzNDUiLCAiaW50ZXJuYWwiOiB7Im9yZ19pZCI6ICI1NDMyMSJ9fX0='
            application_source_id = SourcesHTTPClient(fake_header).get_cost_management_application_type_id()

        valid_msg, operation = filter_message(msg, application_source_id)
        if valid_msg and operation == 'create':
            storage.create_provider_event(msg)
            auth_header = extract_from_header(msg.headers, 'x-rh-identity')
            value = json.loads(msg.value.decode('utf-8'))
            source_id = int(value.get('source_id'))
            await sources_network_info(source_id, auth_header)
        elif valid_msg and operation == 'destroy':
            koku_uuid = storage.destroy_provider_event(msg)
            value = json.loads(msg.value.decode('utf-8'))
            source_id = int(value.get('source_id'))
            auth_header = extract_from_header(msg.headers, 'x-rh-identity')
            koku_client = KokuHTTPClient(source_id, auth_header)
            koku_client.destroy_provider(koku_uuid)
        await load_pending_items(in_progress_queue)


async def listen_for_messages(consumer, msg_pending_queue):  # pragma: no cover
    print('Listener started.  Waiting for messages...')
    try:
        # Consume messages
        async for msg in consumer:
            await msg_pending_queue.put(msg)
    finally:
        # Will leave consumer group; perform autocommit if enabled.
        await consumer.stop()


async def process_in_progress_objects(in_progress_queue):
    print('IN process_in_progress_objects')
    while True:
        msg = await in_progress_queue.get()
        koku_client = KokuHTTPClient(msg.source_id, msg.auth_header)
        koku_details = koku_client.create_provider(msg.name, msg.source_type, msg.authentication, msg.billing_source)
        storage.add_provider_koku_uuid(msg.source_id, koku_details.get('uuid'))


async def load_pending_items(in_progress_queue):
    print("LOAD_PENDING_ITEMS")
    pending_events = storage.load_providers_to_create()
    for event in pending_events:
        print("EVENT TO ADD TO QUEUE")
        await in_progress_queue.put(event)


async def connect_consumer(consumer):
    """Connect consumer."""
    try:
        await consumer.start()
    except KafkaConnectionError:
        await consumer.stop()
        raise KafkaMsgHandlerError('Unable to connect to kafka server.')
    return True


def asyncio_listener_thread(event_loop):
    """
    Listener thread function to run the asyncio event loop.

    Args:
        None

    Returns:
        None

    """
    pending_process_queue = asyncio.Queue(loop=event_loop)
    in_progress_queue = asyncio.Queue(loop=event_loop)

    consumer = AIOKafkaConsumer(
        SOURCES_TOPIC,
        loop=event_loop, bootstrap_servers=SOURCES_KAFKA_ADDRESS
    )
    while True:
        try:
            event_loop.run_until_complete(connect_consumer(consumer))
            break
        except KafkaMsgHandlerError as err:
            print('Kafka connection failure.  Error: ', str(err))
        print('Attempting to reconnect')

    try:
        while True:
            event_loop.create_task(listen_for_messages(consumer, pending_process_queue))
            event_loop.create_task(process_messages(pending_process_queue, in_progress_queue))
            event_loop.create_task(process_in_progress_objects(in_progress_queue))
            event_loop.run_forever()
    except KeyboardInterrupt:
        exit(0)


def initialize_kafka_listener():
    event_loop_thread = threading.Thread(target=asyncio_listener_thread, args=(EVENT_LOOP,))
    #event_loop_thread.daemon = True
    event_loop_thread.start()
    print('Listening for kafka events')
