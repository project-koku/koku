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
import concurrent.futures
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

from api.provider.models import Provider, Sources

LOG = logging.getLogger(__name__)

EVENT_LOOP = asyncio.new_event_loop()
PENDING_PROCESS_QUEUE = asyncio.Queue(loop=EVENT_LOOP)
PROCESS_QUEUE = asyncio.Queue(loop=EVENT_LOOP)
KAFKA_APPLICATION_CREATE = 'Application.create'
KAFKA_APPLICATION_DESTROY = 'Application.destroy'
KAFKA_AUTHENTICATION_CREATE = 'Authentication.create'
KAFKA_AUTHENTICATION_UPDATE = 'Authentication.update'
KAFKA_SOURCE_UPDATE = 'Source.update'
KAFKA_SOURCE_DESTROY = 'Source.destroy'
KAFKA_HDR_RH_IDENTITY = 'x-rh-identity'
KAFKA_HDR_EVENT_TYPE = 'event_type'
SOURCES_OCP_SOURCE_NAME = 'openshift'
SOURCES_AWS_SOURCE_NAME = 'amazon'
SOURCES_AZURE_SOURCE_NAME = 'azure'


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
    """Gather all sources to create update, or delete."""
    create_events = storage.load_providers_to_create()
    update_events = storage.load_providers_to_update()
    destroy_events = storage.load_providers_to_delete()
    pending_events = create_events + update_events + destroy_events

    return pending_events


def _log_process_queue_event(queue, event):
    """Log process queue event."""
    operation = event.get('operation', 'unknown')
    provider = event.get('provider')
    name = provider.name if provider else 'unknown'
    LOG.info(f'Adding operation {operation} for {name} to process queue (size: {queue.qsize()})')


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
        _log_process_queue_event(PROCESS_QUEUE, event)
        PROCESS_QUEUE.put_nowait(event)


@receiver(post_save, sender=Sources)
def storage_callback(sender, instance, **kwargs):
    """Load Sources ready for Koku Synchronization when Sources table is updated."""
    update_fields = kwargs.get('update_fields', ())
    if update_fields and 'pending_update' in update_fields:
        if instance.koku_uuid and instance.pending_update and not instance.pending_delete:
            update_event = {'operation': 'update', 'provider': instance}
            _log_process_queue_event(PROCESS_QUEUE, update_event)
            LOG.debug(f'Update Event Queued for:\n{str(instance)}')
            PROCESS_QUEUE.put_nowait(update_event)

    if instance.pending_delete:
        delete_event = {'operation': 'destroy', 'provider': instance}
        _log_process_queue_event(PROCESS_QUEUE, delete_event)
        LOG.debug(f'Delete Event Queued for:\n{str(instance)}')
        PROCESS_QUEUE.put_nowait(delete_event)

    process_event = storage.screen_and_build_provider_sync_create_event(instance)
    if process_event:
        _log_process_queue_event(PROCESS_QUEUE, process_event)
        LOG.debug(f'Create Event Queued for:\n{str(instance)}')
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
            elif event_type in (KAFKA_AUTHENTICATION_CREATE, KAFKA_AUTHENTICATION_UPDATE):
                LOG.debug('Authentication Message: %s', str(msg))
                if value.get('resource_type') == 'Endpoint':
                    msg_data['event_type'] = event_type
                    msg_data['resource_id'] = int(value.get('resource_id'))
                    msg_data['auth_header'] = _extract_from_header(msg.headers, KAFKA_HDR_RH_IDENTITY)
            elif event_type in (KAFKA_SOURCE_DESTROY, KAFKA_SOURCE_UPDATE):
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


def save_auth_info(auth_header, source_id):
    """
    Store Sources Authentication information given an Source ID.

    This method is called when a Cost Management application is
    attached to a given Source as well as when an Authentication
    is created.  We have to handle both cases since an
    Authentication.create event can occur before a Source is
    attached to the Cost Management application.

    Authentication is stored in the Sources database table.

    Args:
        source_id (Integer): Platform Sources ID.
        auth_header (String): Authentication Header.

    Returns:
        None

    """
    source_type = storage.get_source_type(source_id)

    if source_type:
        sources_network = SourcesHTTPClient(auth_header, source_id)
    else:
        LOG.info(f'Source ID not found for ID: {source_id}')
        return

    try:
        if source_type == Provider.PROVIDER_OCP:
            source_details = sources_network.get_source_details()
            if source_details.get('source_ref'):
                authentication = {'resource_name': source_details.get('source_ref')}
            else:
                raise SourcesHTTPClientError('Unable to find Cluster ID')
        elif source_type == Provider.PROVIDER_AWS:
            authentication = {'resource_name': sources_network.get_aws_role_arn()}
        elif source_type == Provider.PROVIDER_AZURE:
            authentication = {'credentials': sources_network.get_azure_credentials()}
        else:
            LOG.error(f'Unexpected source type: {source_type}')
            return
        storage.add_provider_sources_auth_info(source_id, authentication)
        storage.clear_update_flag(source_id)
    except SourcesHTTPClientError as error:
        LOG.info(f'Authentication info not available for Source ID: {source_id}')
        sources_network.set_source_status(str(error))


def sources_network_auth_info(resource_id, auth_header):
    """
    Store Sources Authentication information given an endpoint (Resource ID).

    Convenience method when a Resource ID (Endpoint) is known and the Source ID
    is not.  This happens when from an Authentication.create message.

    Args:
        resource_id (Integer): Platform Sources Endpoint ID, aka resource_id.
        auth_header (String): Authentication Header.

    Returns:
        None

    """
    source_id = storage.get_source_from_endpoint(resource_id)
    if source_id:
        save_auth_info(auth_header, source_id)
    else:
        sources_network = SourcesHTTPClient(auth_header)
        source_id = sources_network.get_source_id_from_endpoint_id(resource_id)
        storage.update_endpoint_id(source_id, resource_id)
        save_auth_info(auth_header, source_id)


def sources_network_info(source_id, auth_header):
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
    sources_network = SourcesHTTPClient(auth_header, source_id)
    try:
        source_details = sources_network.get_source_details()
    except SourcesHTTPClientError as conn_err:
        err_msg = f'Unable to get for Source {source_id} information. Reason: {str(conn_err)}'
        LOG.error(err_msg)
        return
    source_name = source_details.get('name')
    source_type_id = int(source_details.get('source_type_id'))
    source_uuid = source_details.get('uid')
    source_type_name = sources_network.get_source_type_name(source_type_id)
    endpoint_id = sources_network.get_endpoint_id()

    if not endpoint_id and not source_type_name == SOURCES_OCP_SOURCE_NAME:
        LOG.error(f'Unable to find endpoint for Source ID: {source_id}')

    if source_type_name == SOURCES_OCP_SOURCE_NAME:
        source_type = Provider.PROVIDER_OCP
    elif source_type_name == SOURCES_AWS_SOURCE_NAME:
        source_type = Provider.PROVIDER_AWS
    elif source_type_name == SOURCES_AZURE_SOURCE_NAME:
        source_type = Provider.PROVIDER_AZURE
    else:
        LOG.error(f'Unexpected source type ID: {source_type_id}')
        return

    storage.add_provider_sources_network_info(source_id, source_uuid, source_name,
                                              source_type, endpoint_id)
    save_auth_info(auth_header, source_id)


async def process_messages(msg_pending_queue):  # pragma: no cover
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


    Returns:
        None

    """
    LOG.info('Waiting to process incoming kafka messages...')
    while True:
        msg_data = await msg_pending_queue.get()

        LOG.info(f'Processing Event: {str(msg_data)}')
        try:
            if msg_data.get('event_type') in (KAFKA_APPLICATION_CREATE, ):
                storage.create_provider_event(msg_data.get('source_id'),
                                              msg_data.get('auth_header'),
                                              msg_data.get('offset'))

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    await EVENT_LOOP.run_in_executor(pool, sources_network_info,
                                                     msg_data.get('source_id'),
                                                     msg_data.get('auth_header'))

            elif msg_data.get('event_type') in (KAFKA_SOURCE_UPDATE, ):
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    if storage.is_known_source(msg_data.get('source_id')) is False:
                        LOG.info(f'Update event for unknown source id, skipping...')
                        continue
                    await EVENT_LOOP.run_in_executor(pool, sources_network_info,
                                                     msg_data.get('source_id'),
                                                     msg_data.get('auth_header'))

            elif msg_data.get('event_type') in (KAFKA_AUTHENTICATION_CREATE, KAFKA_AUTHENTICATION_UPDATE):
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    await EVENT_LOOP.run_in_executor(pool, sources_network_auth_info,
                                                     msg_data.get('resource_id'),
                                                     msg_data.get('auth_header'))
                    msg_data['source_id'] = storage.get_source_from_endpoint(msg_data.get('resource_id'))

            elif msg_data.get('event_type') in (KAFKA_APPLICATION_DESTROY, KAFKA_SOURCE_DESTROY):
                storage.enqueue_source_delete(msg_data.get('source_id'))

            if msg_data.get('event_type') in (KAFKA_SOURCE_UPDATE, KAFKA_AUTHENTICATION_UPDATE):
                storage.enqueue_source_update(msg_data.get('source_id'))
        except Exception as error:
            # The reason for catching all exceptions is to ensure that the event
            # loop remains active in the event that message processing fails unexpectedly.
            source_id = str(msg_data.get('source_id', 'unknown'))
            LOG.error(f'Source {source_id} Unexpected message processing error: {str(error)}')


async def listen_for_messages(consumer, application_source_id, msg_pending_queue):  # pragma: no cover
    """
    Listen for Platform-Sources kafka messages.

    Args:
        consumer (AIOKafkaConsumer): Kafka consumer object
        application_source_id (Integer): Cost Management's current Application Source ID. Used for
            kafka message filtering.
        msg_pending_queue (Asyncio queue): Queue to hold kafka messages to be filtered

    Returns:
        None

    """
    try:
        await consumer.start()
    except KafkaError as err:
        await consumer.stop()
        LOG.exception(str(err))
        raise SourcesIntegrationError('Unable to connect to kafka server.')

    LOG.info('Listener started.  Waiting for messages...')
    try:
        async for msg in consumer:
            LOG.debug(f'Filtering Message: {str(msg)}')
            msg = get_sources_msg_data(msg, application_source_id)
            if msg:
                LOG.info(f'Cost Management Message to process: {str(msg)}')
                await msg_pending_queue.put(msg)
    finally:
        await consumer.stop()


def execute_koku_provider_op(msg, cost_management_type_id):
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
        cost_management_type_id (Integer): Cost Management Type Identifier

    Returns:
        None

    """
    provider = msg.get('provider')
    operation = msg.get('operation')
    koku_client = KokuHTTPClient(provider.auth_header)
    sources_client = SourcesHTTPClient(provider.auth_header, provider.source_id)
    try:
        if operation == 'create':
            LOG.info(f'Creating Koku Provider for Source ID: {str(provider.source_id)}')
            koku_details = koku_client.create_provider(provider.name, provider.source_type, provider.authentication,
                                                       provider.billing_source, provider.source_uuid)
            LOG.info(f'Koku Provider UUID {koku_details.get("uuid")} assigned to Source ID {str(provider.source_id)}.')
            storage.add_provider_koku_uuid(provider.source_id, koku_details.get('uuid'))
        elif operation == 'destroy':
            if provider.koku_uuid:
                try:
                    response = koku_client.destroy_provider(provider.koku_uuid)
                    LOG.info(
                        f'Koku Provider UUID ({provider.koku_uuid}) Removal Status Code: {str(response.status_code)}')
                except KokuHTTPClientNonRecoverableError:
                    LOG.info(f'Koku Provider already removed.  Remove Source ID: {str(provider.source_id)}.')
            storage.destroy_provider_event(provider.source_id)
        elif operation == 'update':
            koku_details = koku_client.update_provider(provider.koku_uuid, provider.name, provider.source_type,
                                                       provider.authentication, provider.billing_source)
            storage.clear_update_flag(provider.source_id)
            LOG.info(f'Koku Provider UUID {koku_details.get("uuid")} with Source ID {str(provider.source_id)} updated.')
        sources_client.set_source_status(None, cost_management_type_id)

    except KokuHTTPClientError as koku_error:
        raise SourcesIntegrationError('Koku provider error: ', str(koku_error))
    except KokuHTTPClientNonRecoverableError as koku_error:
        err_msg = f'Unable to {operation} provider for Source ID: {str(provider.source_id)}. Reason: {str(koku_error)}'
        LOG.error(err_msg)
        sources_client.set_source_status(str(koku_error), cost_management_type_id)


async def synchronize_sources(process_queue, cost_management_type_id):  # pragma: no cover
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
        cost_management_type_id (Integer): Cost Management Type Identifier

    Returns:
        None

    """
    LOG.info('Processing koku provider events...')
    while True:
        msg = await process_queue.get()
        LOG.info(f'Koku provider operation to execute: {msg.get("operation")} '
                 f'for Source ID: {str(msg.get("provider").source_id)}')
        try:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                await EVENT_LOOP.run_in_executor(pool, execute_koku_provider_op, msg, cost_management_type_id)
            LOG.info(f'Koku provider operation to execute: {msg.get("operation")} '
                     f'for Source ID: {str(msg.get("provider").source_id)} complete.')
            storage.clear_update_flag(msg.get('provider').source_id)
        except SourcesIntegrationError as error:
            LOG.error('Re-queueing failed operation. Error: %s', str(error))
            await asyncio.sleep(Config.RETRY_SECONDS)
            _log_process_queue_event(process_queue, msg)
            await process_queue.put(msg)
            LOG.info(f'Requeue of failed operation: {msg.get("operation")} '
                     f'for Source ID: {str(msg.get("provider").source_id)} complete.')
        except Exception as error:
            # The reason for catching all exceptions is to ensure that the event
            # loop remains active in the event that provider synchronization fails unexpectedly.
            provider = msg.get('provider')
            source_id = provider.source_id if provider else 'unknown'
            LOG.error(f'Source {source_id} Unexpected synchronization error: {str(error)}')


def asyncio_sources_thread(event_loop):  # pragma: no cover
    """
    Configure Sources listener thread function to run the asyncio event loop.

    Args:
        event_loop: Asyncio event loop.

    Returns:
        None

    """
    try:
        cost_management_type_id = SourcesHTTPClient(Config.SOURCES_FAKE_HEADER).\
            get_cost_management_application_type_id()

        load_process_queue()
        while True:
            consumer = AIOKafkaConsumer(
                Config.SOURCES_TOPIC,
                loop=event_loop, bootstrap_servers=Config.SOURCES_KAFKA_ADDRESS, group_id='hccm-sources'
            )
            event_loop.create_task(listen_for_messages(consumer, cost_management_type_id, PENDING_PROCESS_QUEUE))
            event_loop.create_task(process_messages(PENDING_PROCESS_QUEUE))
            event_loop.create_task(synchronize_sources(PROCESS_QUEUE, cost_management_type_id))
            event_loop.run_forever()
    except SourcesIntegrationError as error:
        err_msg = f'Kafka Connection Failure: {str(error)}. Reconnecting...'
        LOG.error(err_msg)
        time.sleep(Config.RETRY_SECONDS)
    except SourcesHTTPClientError as error:
        LOG.error(f'Unable to connect to Sources REST API.  Check configuration and restart server... Error: {error}')
        exit(0)
    except KeyboardInterrupt:
        exit(0)


def initialize_sources_integration():  # pragma: no cover
    """Start Sources integration thread."""
    event_loop_thread = threading.Thread(target=asyncio_sources_thread, args=(EVENT_LOOP,))
    event_loop_thread.start()
    LOG.info('Listening for kafka events')
