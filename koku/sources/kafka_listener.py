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
import itertools
import json
import logging
import queue
import random
import sys
import threading
import time

from confluent_kafka import Consumer
from confluent_kafka import TopicPartition
from django.db import connection
from django.db import InterfaceError
from django.db import OperationalError
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from kafka.errors import KafkaError
from kombu.exceptions import OperationalError as RabbitOperationalError
from rest_framework.exceptions import ValidationError

from api.provider.models import Provider
from api.provider.models import Sources
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER
from sources import storage
from sources.api.status import check_kafka_connection
from sources.config import Config
from sources.sources_http_client import SourceNotFoundError
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_http_client import SourcesHTTPClientError
from sources.tasks import create_or_update_provider
from sources.tasks import delete_source_and_provider

LOG = logging.getLogger(__name__)

PROCESS_QUEUE = queue.PriorityQueue()
COUNT = itertools.count()  # next(COUNT) returns next sequential number
KAFKA_APPLICATION_CREATE = "Application.create"
KAFKA_APPLICATION_DESTROY = "Application.destroy"
KAFKA_AUTHENTICATION_CREATE = "Authentication.create"
KAFKA_AUTHENTICATION_UPDATE = "Authentication.update"
KAFKA_SOURCE_UPDATE = "Source.update"
KAFKA_SOURCE_DESTROY = "Source.destroy"
KAFKA_HDR_RH_IDENTITY = "x-rh-identity"
KAFKA_HDR_EVENT_TYPE = "event_type"
SOURCES_OCP_SOURCE_NAME = "openshift"
SOURCES_AWS_SOURCE_NAME = "amazon"
SOURCES_AWS_LOCAL_SOURCE_NAME = "amazon-local"
SOURCES_AZURE_SOURCE_NAME = "azure"
SOURCES_AZURE_LOCAL_SOURCE_NAME = "azure-local"

SOURCE_PROVIDER_MAP = {
    SOURCES_OCP_SOURCE_NAME: Provider.PROVIDER_OCP,
    SOURCES_AWS_SOURCE_NAME: Provider.PROVIDER_AWS,
    SOURCES_AWS_LOCAL_SOURCE_NAME: Provider.PROVIDER_AWS_LOCAL,
    SOURCES_AZURE_SOURCE_NAME: Provider.PROVIDER_AZURE,
    SOURCES_AZURE_LOCAL_SOURCE_NAME: Provider.PROVIDER_AZURE_LOCAL,
}


class SourcesIntegrationError(ValidationError):
    """Sources Integration error."""


class SourcesMessageError(ValidationError):
    """Sources Message error."""


def _extract_from_header(headers, header_type):
    """Retrieve information from Kafka Headers."""
    for header in headers:
        if header_type in header:
            for item in header:
                if item == header_type:
                    continue
                else:
                    return item.decode("ascii")
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
    operation = event.get("operation", "unknown")
    provider = event.get("provider")
    name = provider.name if provider else "unknown"
    LOG.info(f"Adding operation {operation} for {name} to process queue (size: {queue.qsize()})")


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
        PROCESS_QUEUE.put_nowait((next(COUNT), event))


def execute_process_queue(cost_management_type_id):
    """Execute process queue to synchronize providers."""
    while not PROCESS_QUEUE.empty():
        msg_tuple = PROCESS_QUEUE.get()
        process_synchronize_sources_msg(msg_tuple, cost_management_type_id, PROCESS_QUEUE)


@receiver(post_save, sender=Sources)
def storage_callback(sender, instance, **kwargs):
    """Load Sources ready for Koku Synchronization when Sources table is updated."""
    update_fields = kwargs.get("update_fields", ())
    if update_fields and "pending_update" in update_fields:
        if instance.koku_uuid and instance.pending_update and not instance.pending_delete:
            update_event = {"operation": "update", "provider": instance}
            _log_process_queue_event(PROCESS_QUEUE, update_event)
            LOG.debug(f"Update Event Queued for:\n{str(instance)}")
            PROCESS_QUEUE.put_nowait((next(COUNT), update_event))

    if instance.pending_delete:
        delete_event = {"operation": "destroy", "provider": instance}
        _log_process_queue_event(PROCESS_QUEUE, delete_event)
        LOG.debug(f"Delete Event Queued for:\n{str(instance)}")
        PROCESS_QUEUE.put_nowait((next(COUNT), delete_event))

    process_event = storage.screen_and_build_provider_sync_create_event(instance)
    if process_event:
        _log_process_queue_event(PROCESS_QUEUE, process_event)
        LOG.debug(f"Create Event Queued for:\n{str(instance)}")
        PROCESS_QUEUE.put_nowait((next(COUNT), process_event))


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
    if msg.topic() == Config.SOURCES_TOPIC:
        try:
            value = json.loads(msg.value().decode("utf-8"))
            LOG.debug(f"msg value: {str(value)}")
            event_type = _extract_from_header(msg.headers(), KAFKA_HDR_EVENT_TYPE)
            LOG.debug(f"event_type: {str(event_type)}")
            if event_type in (KAFKA_APPLICATION_CREATE, KAFKA_APPLICATION_DESTROY):
                if int(value.get("application_type_id")) == app_type_id:
                    LOG.debug("Application Message: %s", str(msg))
                    msg_data["event_type"] = event_type
                    msg_data["offset"] = msg.offset()
                    msg_data["partition"] = msg.partition()
                    msg_data["source_id"] = int(value.get("source_id"))
                    msg_data["auth_header"] = _extract_from_header(msg.headers(), KAFKA_HDR_RH_IDENTITY)
            elif event_type in (KAFKA_AUTHENTICATION_CREATE, KAFKA_AUTHENTICATION_UPDATE):
                LOG.debug("Authentication Message: %s", str(msg))
                if value.get("resource_type") == "Endpoint":
                    msg_data["event_type"] = event_type
                    msg_data["offset"] = msg.offset()
                    msg_data["partition"] = msg.partition()
                    msg_data["resource_id"] = int(value.get("resource_id"))
                    msg_data["auth_header"] = _extract_from_header(msg.headers(), KAFKA_HDR_RH_IDENTITY)
            elif event_type in (KAFKA_SOURCE_DESTROY, KAFKA_SOURCE_UPDATE):
                LOG.debug("Source Message: %s", str(msg))
                msg_data["event_type"] = event_type
                msg_data["offset"] = msg.offset()
                msg_data["partition"] = msg.partition()
                msg_data["source_id"] = int(value.get("id"))
                msg_data["auth_header"] = _extract_from_header(msg.headers(), KAFKA_HDR_RH_IDENTITY)
            else:
                LOG.debug("Other Message: %s", str(msg))
        except (AttributeError, ValueError, TypeError) as error:
            LOG.error("Unable load message: %s. Error: %s", str(msg.value), str(error))
            raise SourcesMessageError("Unable to load message")

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
        LOG.info(f"Source ID not found for ID: {source_id}")
        return

    try:
        if source_type == Provider.PROVIDER_OCP:
            source_details = sources_network.get_source_details()
            if source_details.get("source_ref"):
                authentication = {"resource_name": source_details.get("source_ref")}
            else:
                raise SourcesHTTPClientError("Unable to find Cluster ID")
        elif source_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            authentication = {"resource_name": sources_network.get_aws_role_arn()}
        elif source_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            authentication = {"credentials": sources_network.get_azure_credentials()}
        else:
            LOG.error(f"Unexpected source type: {source_type}")
            return
        storage.add_provider_sources_auth_info(source_id, authentication)
        storage.clear_update_flag(source_id)
        LOG.info(f"Authentication attached to Source ID: {source_id}")
    except SourcesHTTPClientError as error:
        LOG.info(f"Authentication info not available for Source ID: {source_id}")
        sources_network.set_source_status(str(error))


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
    source_details = sources_network.get_source_details()
    source_name = source_details.get("name")
    source_type_id = int(source_details.get("source_type_id"))
    source_uuid = source_details.get("uid")
    source_type_name = sources_network.get_source_type_name(source_type_id)
    endpoint_id = sources_network.get_endpoint_id()

    if not endpoint_id and not source_type_name == SOURCES_OCP_SOURCE_NAME:
        LOG.warning(f"Unable to find endpoint for Source ID: {source_id}")
        return

    source_type = SOURCE_PROVIDER_MAP.get(source_type_name)
    if not source_type:
        LOG.warning(f"Unexpected source type ID: {source_type_id}")
        return

    storage.add_provider_sources_network_info(source_id, source_uuid, source_name, source_type, endpoint_id)
    save_auth_info(auth_header, source_id)


def cost_mgmt_msg_filter(msg_data):
    """Verify that message is for cost management."""
    event_type = msg_data.get("event_type")
    auth_header = msg_data.get("auth_header")

    if event_type in (KAFKA_APPLICATION_DESTROY, KAFKA_SOURCE_DESTROY):
        return msg_data

    if event_type in (KAFKA_AUTHENTICATION_CREATE, KAFKA_AUTHENTICATION_UPDATE):
        sources_network = SourcesHTTPClient(auth_header)
        source_id = sources_network.get_source_id_from_endpoint_id(msg_data.get("resource_id"))
        msg_data["source_id"] = source_id
        if not sources_network.get_application_type_is_cost_management(source_id):
            LOG.info(f"Resource id {msg_data.get('resource_id')} not associated with cost-management.")
            return None
    else:
        source_id = msg_data.get("source_id")

    sources_network = SourcesHTTPClient(auth_header, source_id=source_id)
    source_details = sources_network.get_source_details()
    source_type_id = int(source_details.get("source_type_id"))
    source_type_name = sources_network.get_source_type_name(source_type_id)

    if source_type_name not in (
        SOURCES_OCP_SOURCE_NAME,
        SOURCES_AWS_SOURCE_NAME,
        SOURCES_AWS_LOCAL_SOURCE_NAME,
        SOURCES_AZURE_SOURCE_NAME,
        SOURCES_AZURE_LOCAL_SOURCE_NAME,
    ):
        LOG.debug(f"Filtering unexpected source type {source_type_name}.")
        return None
    return msg_data


def process_message(app_type_id, msg):  # noqa: C901
    """
    Process message from Platform-Sources kafka service.

    Handler for various application/source create and delete events.
    'create' events:
        Issues a Sources REST API call to get additional context for the Platform-Sources kafka event.
        This information is stored in the Sources database table.
    'destroy' events:
        Enqueues a source delete event which will be processed in the synchronize_sources method.

    Args:
        app_type_id - application type identifier
        msg - kafka message

    Returns:
        None

    """
    LOG.info(f"Processing Event: {msg}")
    msg_data = None
    try:
        msg_data = cost_mgmt_msg_filter(msg)
    except SourceNotFoundError:
        LOG.warning(f"Source not found in platform sources. Skipping msg: {msg}")
        return
    if not msg_data:
        LOG.debug(f"Message not intended for cost management: {msg}")
        return

    if msg_data.get("event_type") in (KAFKA_APPLICATION_CREATE,):
        storage.create_source_event(msg_data.get("source_id"), msg_data.get("auth_header"), msg_data.get("offset"))

        if storage.is_known_source(msg_data.get("source_id")):
            sources_network_info(msg_data.get("source_id"), msg_data.get("auth_header"))

    elif msg_data.get("event_type") in (KAFKA_AUTHENTICATION_CREATE, KAFKA_AUTHENTICATION_UPDATE):
        if msg_data.get("event_type") in (KAFKA_AUTHENTICATION_CREATE,):
            storage.create_source_event(  # this will create source _only_ if it does not exist.
                msg_data.get("source_id"), msg_data.get("auth_header"), msg_data.get("offset")
            )

        save_auth_info(msg_data.get("auth_header"), msg_data.get("source_id"))

    elif msg_data.get("event_type") in (KAFKA_SOURCE_UPDATE,):
        if storage.is_known_source(msg_data.get("source_id")) is False:
            LOG.info("Update event for unknown source id, skipping...")
            return
        sources_network_info(msg_data.get("source_id"), msg_data.get("auth_header"))

    elif msg_data.get("event_type") in (KAFKA_APPLICATION_DESTROY,):
        storage.enqueue_source_delete(msg_data.get("source_id"), msg_data.get("offset"), allow_out_of_order=True)

    elif msg_data.get("event_type") in (KAFKA_SOURCE_DESTROY,):
        storage.enqueue_source_delete(msg_data.get("source_id"), msg_data.get("offset"))

    if msg_data.get("event_type") in (KAFKA_SOURCE_UPDATE, KAFKA_AUTHENTICATION_UPDATE):
        storage.enqueue_source_update(msg_data.get("source_id"))


def get_consumer():
    """Create a Kafka consumer."""
    consumer = Consumer(
        {
            "bootstrap.servers": Config.SOURCES_KAFKA_ADDRESS,
            "group.id": "hccm-sources",
            "queued.max.messages.kbytes": 1024,
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([Config.SOURCES_TOPIC])
    return consumer


def listen_for_messages_loop(application_source_id):  # pragma: no cover
    """Wrap listen_for_messages in while true."""
    consumer = get_consumer()
    LOG.info("Listener started.  Waiting for messages...")
    while True:
        msg_list = consumer.consume()
        if len(msg_list) == 1:
            msg = msg_list.pop()
        else:
            continue

        listen_for_messages(msg, consumer, application_source_id)
        execute_process_queue(application_source_id)


def rewind_consumer_to_retry(consumer, topic_partition):
    """Helper method to log and rewind kafka consumer for retry."""
    LOG.info(f"Seeking back to offset: {topic_partition.offset}, partition: {topic_partition.partition}")
    consumer.seek(topic_partition)
    time.sleep(Config.RETRY_SECONDS)


@KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()  # noqa: C901
def listen_for_messages(msg, consumer, application_source_id):  # noqa: C901
    """
    Listen for Platform-Sources kafka messages.

    Args:
        consumer (Consumer): Kafka consumer object
        application_source_id (Integer): Cost Management's current Application Source ID. Used for
            kafka message filtering.

    Returns:
        None

    """
    try:
        try:
            msg = get_sources_msg_data(msg, application_source_id)
            offset = msg.get("offset")
            partition = msg.get("partition")
        except SourcesMessageError:
            return
        if msg:
            LOG.info(f"Processing message offset: {offset} partition: {partition}")
            topic_partition = TopicPartition(topic=Config.SOURCES_TOPIC, partition=partition, offset=offset)
            LOG.info(f"Cost Management Message to process: {str(msg)}")
            try:
                with transaction.atomic():
                    process_message(application_source_id, msg)
                    consumer.commit()
            except (InterfaceError, OperationalError) as err:
                connection.close()
                LOG.error(err)
                rewind_consumer_to_retry(consumer, topic_partition)
            except SourcesHTTPClientError as err:
                LOG.error(err)
                rewind_consumer_to_retry(consumer, topic_partition)
            except SourceNotFoundError:
                LOG.warning(f"Source not found in platform sources. Skipping msg: {msg}")
                consumer.commit()

    except KafkaError as error:
        LOG.error(f"[listen_for_messages] Kafka error encountered: {type(error).__name__}: {error}", exc_info=True)
    except Exception as error:
        LOG.error(f"[listen_for_messages] UNKNOWN error encountered: {type(error).__name__}: {error}", exc_info=True)


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
    provider = msg.get("provider")
    operation = msg.get("operation")

    try:
        if operation == "create":
            task = create_or_update_provider.delay(provider.source_id)
            LOG.info(f"Creating Koku Provider for Source ID: {str(provider.source_id)} in task: {task.id}")
        elif operation == "update":
            task = create_or_update_provider.delay(provider.source_id)
            LOG.info(f"Updating Koku Provider for Source ID: {str(provider.source_id)} in task: {task.id}")
        elif operation == "destroy":
            task = delete_source_and_provider.delay(provider.source_id, provider.source_uuid, provider.auth_header)
            LOG.info(f"Deleting Koku Provider/Source for Source ID: {str(provider.source_id)} in task: {task.id}")
        else:
            LOG.error(f"unknown operation: {operation}")

    except RabbitOperationalError:
        err_msg = f"RabbitmQ unavailable. Unable to {operation} Source ID: {provider.source_id}"
        LOG.error(err_msg)
        sources_network = SourcesHTTPClient(provider.auth_header, provider.source_id)
        sources_network.set_source_status(err_msg, cost_management_type_id=cost_management_type_id)

        # Re-raise exception so it can be re-queued in synchronize_sources
        raise RabbitOperationalError(err_msg)


def _requeue_provider_sync_message(priority, msg, queue):
    """Helper to requeue provider sync messages."""
    time.sleep(Config.RETRY_SECONDS)
    _log_process_queue_event(queue, msg)
    queue.put((priority, msg))
    LOG.warning(
        f'Requeue of failed operation: {msg.get("operation")} '
        f'for Source ID: {str(msg.get("provider").source_id)} complete.'
    )


def process_synchronize_sources_msg(msg_tuple, cost_management_type_id, process_queue):
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
    priority, msg = msg_tuple

    LOG.info(
        f'Koku provider operation to execute: {msg.get("operation")} '
        f'for Source ID: {str(msg.get("provider").source_id)}'
    )
    try:
        execute_koku_provider_op(msg, cost_management_type_id)
        LOG.info(
            f'Koku provider operation to execute: {msg.get("operation")} '
            f'for Source ID: {str(msg.get("provider").source_id)} complete.'
        )
        if msg.get("operation") != "destroy":
            storage.clear_update_flag(msg.get("provider").source_id)

    except (InterfaceError, OperationalError) as error:
        connection.close()
        LOG.warning(
            f"[synchronize_sources] Closing DB connection and re-queueing failed operation."
            f" Encountered {type(error).__name__}: {error}"
        )
        _requeue_provider_sync_message(priority, msg, process_queue)

    except RabbitOperationalError as error:
        LOG.warning(
            f"[synchronize_sources] RabbitMQ is down and re-queueing failed operation."
            f" Encountered {type(error).__name__}: {error}"
        )
        _requeue_provider_sync_message(priority, msg, process_queue)

    except Exception as error:
        # The reason for catching all exceptions is to ensure that the event
        # loop remains active in the event that provider synchronization fails unexpectedly.
        provider = msg.get("provider")
        source_id = provider.source_id if provider else "unknown"
        LOG.error(
            f"[synchronize_sources] Unexpected synchronization error for Source ID {source_id} "
            f"encountered: {type(error).__name__}: {error}",
            exc_info=True,
        )


def backoff(interval, maximum=120):
    """Exponential back-off."""
    wait = min(maximum, (2 ** interval)) + random.random()
    LOG.info("Sleeping for %.2f seconds.", wait)
    time.sleep(wait)


def is_kafka_connected():  # pragma: no cover
    """
    Check connectability to Kafka messenger.

    This method will block sources integration initialization until
    Kafka is connected.
    """
    count = 0
    result = False
    while not result:
        result = check_kafka_connection()
        if result:
            LOG.info("Test connection to Kafka was successful.")
        else:
            LOG.error("Unable to connect to Kafka server.")
            KAFKA_CONNECTION_ERRORS_COUNTER.inc()
            backoff(count)
            count += 1
    return result


@KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()
def sources_integration_thread():  # pragma: no cover
    """
    Configure Sources listener thread.

    Returns:
        None

    """
    cost_management_type_id = None
    count = 0
    while cost_management_type_id is None:
        # First, hit Souces endpoint to get the cost-mgmt application ID.
        # Without this initial connection/ID number, the consumer cannot start
        try:
            cost_management_type_id = SourcesHTTPClient(
                Config.SOURCES_FAKE_HEADER
            ).get_cost_management_application_type_id()
            LOG.info("Connected to Sources REST API.")
        except SourcesHTTPClientError as error:
            LOG.error(f"Unable to connect to Sources REST API. Error: {error}")
            backoff(count)
            count += 1
            LOG.info("Reattempting connection to Sources REST API.")
        except SourceNotFoundError as err:
            LOG.error(f"Cost Management application not found: {err}. Exiting...")
            sys.exit(1)
        except KeyboardInterrupt:
            sys.exit(0)

    if is_kafka_connected():  # Next, check that Kafka is running
        LOG.info("Kafka is running...")

    load_process_queue()
    execute_process_queue(cost_management_type_id)

    listen_for_messages_loop(cost_management_type_id)


def initialize_sources_integration():  # pragma: no cover
    """Start Sources integration thread."""

    event_loop_thread = threading.Thread(target=sources_integration_thread)
    event_loop_thread.start()
    LOG.info("Listening for kafka events")
