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
"""Sources Integration Service."""
import asyncio
import json
import logging
import threading
import time

from aiokafka import AIOKafkaConsumer
from django.db.models.signals import post_save
from django.dispatch import receiver
from kafka.errors import KafkaError
from sources import storage
from sources.config import Config
from sources.koku_http_client import KokuHTTPClient, KokuHTTPClientError, KokuHTTPClientNonRecoverableError
from sources.sources_http_client import SourcesHTTPClient, SourcesHTTPClientError

from api.provider.models import Sources

LOG = logging.getLogger(__name__)

EVENT_LOOP = asyncio.new_event_loop()
PROCESS_QUEUE = asyncio.Queue(loop=EVENT_LOOP)
KAFKA_APPLICATION_CREATE = 'Application.create'
KAFKA_APPLICATION_DESTROY = 'Application.destroy'
KAFKA_SOURCE_DESTROY = 'Source.destroy'
KAFKA_HDR_RH_IDENTITY = 'x-rh-identity'
KAFKA_HDR_EVENT_TYPE = 'event_type'


class SourcesIntegrationError(Exception):
    """Sources Integration error."""


def _extract_from_header(headers, header_type):
    """Retrieve information from Kafka Headers."""
    for header in headers:
        if header_type in header:
            for item in header:
                if item == header_type:
                    continue
                else:
                    return item.decode('ascii')
    return None


def _collect_pending_items():
    """Gather all sources to create or delete."""
    create_events = storage.load_providers_to_create()
    destroy_events = storage.load_providers_to_delete()
    pending_events = create_events + destroy_events
    pending_events.sort(key=lambda item: item.get('offset'))
    return pending_events


def load_process_queue():
    """
    Re-populate the process queue for any Source events that need synchronization.

    Handles the case for when the Sources Integration service goes down before
    Koku Synchronization could be completed.

    Args:
        None

    Returns:
        None

    """
    pending_events = _collect_pending_items()
    for event in pending_events:
        PROCESS_QUEUE.put_nowait(event)


@receiver(post_save, sender=Sources)
def storage_callback(sender, instance, **kwargs):
    """Load Sources ready for Koku Synchronization when Sources table is updated."""
    process_event = storage.screen_and_build_provider_sync_create_event(instance)
    if process_event:
        PROCESS_QUEUE.put_nowait(process_event)


def get_sources_msg_data(msg, app_type_id):
    """
    General filter and data extractor for Platform-Sources kafka messages.

    Args:
        msg (Kafka msg): Platform-Sources kafka message
        app_type_id (Integer): Cost Management's current Application Source ID. Used for
            kafka message filtering.  Initialized at service startup time.

    Returns:
        Dictionary - Keys: event_type, offset, source_id, auth_header

    """
    msg_data = {}
    if msg.topic == Config.SOURCES_TOPIC:
        try:
            value = json.loads(msg.value.decode('utf-8'))
            event_type = _extract_from_header(msg.headers, KAFKA_HDR_EVENT_TYPE)
            if event_type in (KAFKA_APPLICATION_CREATE, KAFKA_APPLICATION_DESTROY):
                if int(value.get('application_type_id')) == app_type_id:
                    LOG.debug('Application Message: %s', str(msg))
                    msg_data['event_type'] = event_type
                    msg_data['offset'] = msg.offset
                    msg_data['source_id'] = int(value.get('source_id'))
                    msg_data['auth_header'] = _extract_from_header(msg.headers, KAFKA_HDR_RH_IDENTITY)
            elif event_type in (KAFKA_SOURCE_DESTROY, ):
                LOG.debug('Source Message: %s', str(msg))
                msg_data['event_type'] = event_type
                msg_data['offset'] = msg.offset
                msg_data['source_id'] = int(value.get('id'))
                msg_data['auth_header'] = _extract_from_header(msg.headers, KAFKA_HDR_RH_IDENTITY)
            else:
                LOG.debug('Other Message: %s', str(msg))
        except (AttributeError, ValueError, TypeError) as error:
            LOG.error('Unable load message. Error: %s', str(error))
            raise SourcesIntegrationError('Unable to load message')

    return msg_data


def _sources_network_info_sync(source_id, auth_header):
    """Get sources context synchronously."""
    sources_network = SourcesHTTPClient(auth_header, source_id)
    try:
        source_details = sources_network.get_source_details()
    except SourcesHTTPClientError as conn_err:
        err_msg = f'Unable to get for Source {source_id} information. Reason: {str(conn_err)}'
        LOG.error(err_msg)
        return
    source_name = source_details.get('name')
    source_type_id = int(source_details.get('source_type_id'))

    if source_type_id == 1:
        source_type = 'OCP'
        authentication = {'resource_name': source_details.get('uid')}
    elif source_type_id == 2:
        source_type = 'AWS'
        authentication = {'resource_name': sources_network.get_aws_role_arn()}
    elif source_type_id == 3:
        source_type = 'AZURE'
        authentication = {'credentials': sources_network.get_azure_credentials()}
        print(f'AZURE Authentication: {str(authentication)}')
    else:
        LOG.error(f'Unexpected source type ID: {source_type_id}')
        return

    storage.add_provider_sources_network_info(source_id, source_name, source_type, authentication)


async def sources_network_info(source_id, auth_header):  # pragma: no cover
    """
    Get additional sources context from Sources REST API.

    Additional details retrieved from the network includes:
        - Source Name
        - Source ID Type -> AWS, Azure, or OCP
        - Authentication: OCP -> Source uid; AWS -> Network call to Sources Authentication Store

    Details are stored in the Sources database table.

    Args:
        source_id (Integer): Source identifier
        auth_header (String): Authentication Header.

    Returns:
        None

    """
    _sources_network_info_sync(source_id, auth_header)


async def process_messages(msg_pending_queue, in_progress_queue, application_source_id):  # pragma: no cover
    """
    Process messages from Platform-Sources kafka service.

    Handler for various application/source create and delete events.
    'create' events:
        Issues a Sources REST API call to get additional context for the Platform-Sources kafka event.
        This information is stored in the Sources database table.
    'destroy' events:
        Enqueues a source delete event which will be processed in the synchronize_sources method.

    Args:
        msg_pending_queue (Asyncio queue): Queue to hold kafka messages to be filtered
        in_progress_queue (Asyncio queue): Queue for filtered cost management messages awaiting
            Koku-Provider synchronization.
        application_source_id (Integer): Cost Management's current Application Source ID. Used for
            kafka message filtering.

    Returns:
        None

    """
    LOG.info('Waiting to process incoming kafka messages...')
    while True:
        msg = await msg_pending_queue.get()

        msg_data = get_sources_msg_data(msg, application_source_id)
        if msg_data:
            LOG.info(f'Processing Message Details: {str(msg_data)}')
        if msg_data.get('event_type') == KAFKA_APPLICATION_CREATE:
            storage.create_provider_event(msg_data.get('source_id'),
                                          msg_data.get('auth_header'),
                                          msg_data.get('offset'))
            await sources_network_info(msg_data.get('source_id'), msg_data.get('auth_header'))
        elif msg_data.get('event_type') in (KAFKA_APPLICATION_DESTROY, KAFKA_SOURCE_DESTROY):
            await storage.enqueue_source_delete(in_progress_queue, msg_data.get('source_id'))


async def listen_for_messages(consumer, msg_pending_queue):  # pragma: no cover
    """
    Listen for Platform-Sources kafka messages.

    Args:
        consumer (AIOKafkaConsumer): Kafka consumer object
        msg_pending_queue (Asyncio queue): Queue to hold kafka messages to be filtered

    Returns:
        None

    """
    LOG.info('Listener started.  Waiting for messages...')
    try:
        async for msg in consumer:
            await msg_pending_queue.put(msg)
    finally:
        await consumer.stop()


def execute_koku_provider_op_sync(msg):
    """Execute the 'create' or 'destroy Koku-Provider operations synchronously."""
    provider = msg.get('provider')
    operation = msg.get('operation')
    koku_client = KokuHTTPClient(provider.auth_header)
    try:
        if operation == 'create':
            LOG.info(f'Creating Koku Provider for Source ID: {str(provider.source_id)}')
            koku_details = koku_client.create_provider(provider.name, provider.source_type, provider.authentication,
                                                       provider.billing_source)
            LOG.info(f'Koku Provider UUID {koku_details.get("uuid")} assigned to Source ID {str(provider.source_id)}.')
            storage.add_provider_koku_uuid(provider.source_id, koku_details.get('uuid'))
        elif operation == 'destroy':
            if provider.koku_uuid:
                response = koku_client.destroy_provider(provider.koku_uuid)
                LOG.info(f'Koku Provider UUID ({provider.koku_uuid}) Removal Status Code: {str(response.status_code)}')
            storage.destroy_provider_event(provider.source_id)
    except KokuHTTPClientError as koku_error:
        raise SourcesIntegrationError('Koku provider error: ', str(koku_error))
    except KokuHTTPClientNonRecoverableError as koku_error:
        err_msg = f'Unable to {operation} provider for Source ID: {str(provider.source_id)}. Reason: {str(koku_error)}'
        LOG.error(err_msg)


async def execute_koku_provider_op(msg):
    """
    Execute the 'create' or 'destroy Koku-Provider operations.

    'create' operations:
        Koku POST /providers is executed along with updating the Sources database table with
        the Koku Provider uuid.
    'destroy' operations:
        Koku DELETE /providers is executed along with removing the Sources database entry.

    Two types of exceptions are handled for Koku HTTP operations.  Recoverable client and
    Non-Recoverable client errors.  If the error is recoverable the calling function
    (synchronize_sources) will re-queue the operation.

    Args:
        msg (Asyncio msg): Dictionary messages containing operation,
                                       provider and offset.
            example: {'operation': 'create', 'provider': SourcesModelObj, 'offset': 3}

    Returns:
        None

    """
    execute_koku_provider_op_sync(msg)


async def synchronize_sources(process_queue):  # pragma: no cover
    """
    Synchronize Platform Sources with Koku Providers.

    Task will process the process_queue which contains filtered
    events (Cost Management Platform-Sources).

    The items on the queue are Koku-Provider 'create' or 'destroy
    events.  If the Koku-Provider operation fails the event will
    be re-queued until the operation is successful.

    Args:
        process_queue (Asyncio.Queue): Dictionary messages containing operation,
                                       provider and offset.
            example: {'operation': 'create', 'provider': SourcesModelObj, 'offset': 3}

    Returns:
        None

    """
    LOG.info('Processing koku provider events...')
    while True:
        msg = await process_queue.get()
        try:
            await execute_koku_provider_op(msg)
        except SourcesIntegrationError as error:
            LOG.error('Re-queueing failed operation. Error: %s', str(error))
            await asyncio.sleep(Config.RETRY_SECONDS)
            await process_queue.put(msg)


async def connect_consumer(consumer):  # pragma: no cover
    """Connect consumer."""
    try:
        await consumer.start()
    except KafkaError as kafka_error:
        raise SourcesIntegrationError('Unable to connect to kafka server. Reason: ', str(kafka_error))


def asyncio_sources_thread(event_loop):  # pragma: no cover
    """
    Configure Sources listener thread function to run the asyncio event loop.

    Args:
        event_loop: Asyncio event loop.

    Returns:
        None

    """
    pending_process_queue = asyncio.Queue(loop=event_loop)

    consumer = AIOKafkaConsumer(
        Config.SOURCES_TOPIC,
        loop=event_loop, bootstrap_servers=Config.SOURCES_KAFKA_ADDRESS, group_id='hccm-group'
    )
    while True:
        try:
            event_loop.run_until_complete(connect_consumer(consumer))
            break
        except SourcesIntegrationError as err:
            err_msg = f'Kafka Connection Failure: {str(err)}. Reconnecting...'
            LOG.error(err_msg)
        time.sleep(Config.RETRY_SECONDS)

    try:
        cost_management_type_id = SourcesHTTPClient(Config.SOURCES_FAKE_HEADER).\
            get_cost_management_application_type_id()

        load_process_queue()
        while True:
            event_loop.create_task(listen_for_messages(consumer, pending_process_queue))
            event_loop.create_task(process_messages(pending_process_queue, PROCESS_QUEUE, cost_management_type_id))
            event_loop.create_task(synchronize_sources(PROCESS_QUEUE))
            event_loop.run_forever()
    except SourcesHTTPClientError:
        LOG.error('Unable to connect to Sources REST API.  Check configuration and restart server...')
        exit(0)
    except KeyboardInterrupt:
        exit(0)


def initialize_sources_integration():  # pragma: no cover
    """Start Sources integration thread."""
    event_loop_thread = threading.Thread(target=asyncio_sources_thread, args=(EVENT_LOOP,))
    event_loop_thread.start()
    LOG.info('Listening for kafka events')
