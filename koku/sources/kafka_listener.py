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
import logging
import queue
import random
import sys
import threading
import time

from confluent_kafka import Consumer
from confluent_kafka import TopicPartition
from django.db import connections
from django.db import DEFAULT_DB_ALIAS
from django.db import IntegrityError
from django.db import InterfaceError
from django.db import OperationalError
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from kafka.errors import KafkaError
from rest_framework.exceptions import ValidationError

from api.provider.models import Provider
from api.provider.models import Sources
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER
from masu.prometheus_stats import SOURCES_HTTP_CLIENT_ERROR_COUNTER
from masu.prometheus_stats import SOURCES_KAFKA_LOOP_RETRY
from masu.prometheus_stats import SOURCES_PROVIDER_OP_RETRY_LOOP_COUNTER
from providers.provider_errors import SkipStatusPush
from sources import storage
from sources.api.status import check_kafka_connection
from sources.config import Config
from sources.kafka_message_processor import create_msg_processor
from sources.sources_http_client import SourceNotFoundError
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_http_client import SourcesHTTPClientError
from sources.sources_provider_coordinator import SourcesProviderCoordinator
from sources.sources_provider_coordinator import SourcesProviderCoordinatorError

LOG = logging.getLogger(__name__)

PROCESS_QUEUE = queue.PriorityQueue()
COUNT = itertools.count()  # next(COUNT) returns next sequential number
KAFKA_APPLICATION_CREATE = "Application.create"
KAFKA_APPLICATION_UPDATE = "Application.update"
KAFKA_APPLICATION_DESTROY = "Application.destroy"
KAFKA_AUTHENTICATION_CREATE = "Authentication.create"
KAFKA_AUTHENTICATION_UPDATE = "Authentication.update"
KAFKA_SOURCE_DESTROY = "Source.destroy"
KAFKA_HDR_RH_IDENTITY = "x-rh-identity"
KAFKA_HDR_EVENT_TYPE = "event_type"
SOURCES_OCP_SOURCE_NAME = "openshift"
SOURCES_AWS_SOURCE_NAME = "amazon"
SOURCES_AWS_LOCAL_SOURCE_NAME = "amazon-local"
SOURCES_AZURE_SOURCE_NAME = "azure"
SOURCES_AZURE_LOCAL_SOURCE_NAME = "azure-local"
SOURCES_GCP_SOURCE_NAME = "google"
SOURCES_GCP_LOCAL_SOURCE_NAME = "google-local"

SOURCE_PROVIDER_MAP = {
    SOURCES_OCP_SOURCE_NAME: Provider.PROVIDER_OCP,
    SOURCES_AWS_SOURCE_NAME: Provider.PROVIDER_AWS,
    SOURCES_AWS_LOCAL_SOURCE_NAME: Provider.PROVIDER_AWS_LOCAL,
    SOURCES_AZURE_SOURCE_NAME: Provider.PROVIDER_AZURE,
    SOURCES_AZURE_LOCAL_SOURCE_NAME: Provider.PROVIDER_AZURE_LOCAL,
    SOURCES_GCP_SOURCE_NAME: Provider.PROVIDER_GCP,
    SOURCES_GCP_LOCAL_SOURCE_NAME: Provider.PROVIDER_GCP_LOCAL,
}


class SourcesIntegrationError(ValidationError):
    """Sources Integration error."""


class SourcesMessageError(ValidationError):
    """Sources Message error."""


class SourceDetails:
    """Sources Details object."""

    def __init__(self, auth_header, source_id):
        """Constructor."""
        sources_network = SourcesHTTPClient(auth_header, source_id)
        details = sources_network.get_source_details()
        self.name = details.get("name")
        self.source_type_id = int(details.get("source_type_id"))
        self.source_uuid = details.get("uid")
        self.source_type_name = sources_network.get_source_type_name(self.source_type_id)
        self.source_type = SOURCE_PROVIDER_MAP.get(self.source_type_name)
        self.app_settings = sources_network.get_application_settings(self.source_type)


def _collect_pending_items():
    """Gather all sources to create update, or delete."""
    create_events = storage.load_providers_to_create()
    update_events = storage.load_providers_to_update()
    destroy_events = storage.load_providers_to_delete()
    return create_events + update_events + destroy_events


def _log_process_queue_event(queue, event):
    """Log process queue event."""
    operation = event.get("operation", "unknown")
    provider = event.get("provider")
    name = provider.name if provider else "unknown"
    LOG.info(f"Adding operation {operation} for {name} to process queue (size: {queue.qsize()})")


def close_and_set_db_connection():  # pragma: no cover
    """Close the db connection and set to None."""
    if connections[DEFAULT_DB_ALIAS].connection:
        connections[DEFAULT_DB_ALIAS].connection.close()
    connections[DEFAULT_DB_ALIAS].connection = None


def load_process_queue():
    """
    Re-populate the process queue for any Source events that need synchronization.

    Handles the case for when the Sources Integration service goes down before
    Koku Synchronization could be completed.
    """
    pending_events = _collect_pending_items()
    for event in pending_events:
        _log_process_queue_event(PROCESS_QUEUE, event)
        PROCESS_QUEUE.put_nowait((next(COUNT), event))


def execute_process_queue():
    """Execute process queue to synchronize providers."""
    while not PROCESS_QUEUE.empty():
        msg_tuple = PROCESS_QUEUE.get()
        process_synchronize_sources_msg(msg_tuple, PROCESS_QUEUE)


@receiver(post_save, sender=Sources)
def storage_callback(sender, instance, **kwargs):
    """Load Sources ready for Koku Synchronization when Sources table is updated."""
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

    execute_process_queue()


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
            consumer.commit()
            continue

        listen_for_messages(msg, consumer, application_source_id)
        execute_process_queue()


def rewind_consumer_to_retry(consumer, topic_partition):
    """Helper method to log and rewind kafka consumer for retry."""
    SOURCES_KAFKA_LOOP_RETRY.inc()
    LOG.info(f"Seeking back to offset: {topic_partition.offset}, partition: {topic_partition.partition}")
    consumer.seek(topic_partition)
    time.sleep(Config.RETRY_SECONDS)


@KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()  # noqa: C901
def listen_for_messages(kaf_msg, consumer, application_source_id):  # noqa: C901
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
            msg_processor = create_msg_processor(kaf_msg, application_source_id)
            if msg_processor and msg_processor.source_id:
                if not msg_processor.msg_for_cost_mgmt():
                    LOG.info("Event not associated with cost-management.")
                    consumer.commit()
                    return
                tp = TopicPartition(Config.SOURCES_TOPIC, msg_processor.partition, msg_processor.offset)
                LOG.info(f"Processing message offset: {msg_processor.offset} partition: {msg_processor.partition}")
                LOG.info(f"Cost Management Message to process: {msg_processor}")
                with transaction.atomic():
                    msg_processor.process()
        except (InterfaceError, OperationalError) as error:
            close_and_set_db_connection()
            LOG.error(f"[listen_for_messages] Database error. Error: {type(error).__name__}: {error}. Retrying...")
            rewind_consumer_to_retry(consumer, tp)
        except IntegrityError as error:
            LOG.error(f"[listen_for_messages] {type(error).__name__}: {error}. Retrying...", exc_info=True)
            rewind_consumer_to_retry(consumer, tp)
        except SourcesHTTPClientError as err:
            LOG.warning(f"[listen_for_messages] {type(err).__name__}: {err}. Retrying...")
            SOURCES_HTTP_CLIENT_ERROR_COUNTER.inc()
            rewind_consumer_to_retry(consumer, tp)
        except (SourcesMessageError, SourceNotFoundError) as error:
            LOG.warning(f"[listen_for_messages] {type(error).__name__}: {error}. Skipping msg: {kaf_msg}")
            consumer.commit()
        else:
            consumer.commit()

    except KafkaError as error:
        LOG.error(f"[listen_for_messages] Kafka error encountered: {type(error).__name__}: {error}", exc_info=True)
    except Exception as error:
        LOG.error(f"[listen_for_messages] UNKNOWN error encountered: {type(error).__name__}: {error}", exc_info=True)


def execute_koku_provider_op(msg):
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
    provider = msg.get("provider")
    operation = msg.get("operation")
    account_coordinator = SourcesProviderCoordinator(provider.source_id, provider.auth_header)
    sources_client = SourcesHTTPClient(provider.auth_header, provider.source_id)

    try:
        if operation == "create":
            LOG.info(f"Creating Koku Provider for Source ID: {provider.source_id}")
            instance = account_coordinator.create_account(provider)
            LOG.info(f"Created provider {instance.uuid} for Source ID: {provider.source_id}")
        elif operation == "update":
            LOG.info(f"Updating Koku Provider for Source ID: {provider.source_id}")
            instance = account_coordinator.update_account(provider)
            LOG.info(f"Updated provider {instance.uuid} for Source ID: {provider.source_id}")
        elif operation == "destroy":
            LOG.info(f"Destroying Koku Provider for Source ID: {provider.source_id}")
            account_coordinator.destroy_account(provider)
            LOG.info(f"Destroyed provider {provider.koku_uuid} for Source ID: {provider.source_id}")
        else:
            LOG.error(f"unknown operation: {operation}")
        sources_client.set_source_status(None)

    except SourcesProviderCoordinatorError as account_error:
        sources_client.set_source_status(account_error)
        raise SourcesIntegrationError(f"Koku provider error: {account_error}")
    except ValidationError as account_error:
        err_msg = f"Unable to {operation} provider for Source ID: {provider.source_id}. Reason: {account_error}"
        LOG.warning(err_msg)
        sources_client.set_source_status(account_error)
    except SkipStatusPush as error:
        LOG.info(f"Platform sources status push skipped. Reason: {error}")


def _requeue_provider_sync_message(priority, msg, queue):
    """Helper to requeue provider sync messages."""
    SOURCES_PROVIDER_OP_RETRY_LOOP_COUNTER.inc()
    time.sleep(Config.RETRY_SECONDS)
    _log_process_queue_event(queue, msg)
    queue.put((priority, msg))
    LOG.warning(
        f'Requeue of failed operation: {msg.get("operation")} '
        f'for Source ID: {msg.get("provider").source_id} complete.'
    )


def process_synchronize_sources_msg(msg_tuple, process_queue):
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
    priority, msg = msg_tuple
    operation = msg.get("operation")
    provider = msg.get("provider")

    LOG.info(f"Koku provider operation to execute: {operation} for Source ID: {provider.source_id}")
    try:
        execute_koku_provider_op(msg)
        LOG.info(f"Koku provider operation to execute: {operation} for Source ID: {provider.source_id} complete.")
    except (IntegrityError, SourcesIntegrationError) as error:
        LOG.warning(f"[synchronize_sources] Re-queuing failed operation. Error: {error}")
        _requeue_provider_sync_message(priority, msg, process_queue)
    except (InterfaceError, OperationalError) as error:
        close_and_set_db_connection()
        LOG.warning(
            f"[synchronize_sources] Closing DB connection and re-queueing failed operation."
            f" Encountered {type(error).__name__}: {error}"
        )
        _requeue_provider_sync_message(priority, msg, process_queue)
    except Exception as error:
        # The reason for catching all exceptions is to ensure that the event
        # loop remains active in the event that provider synchronization fails unexpectedly.
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
            LOG.error(f"Unable to connect to Kafka server [{Config.SOURCES_KAFKA_HOST}:{Config.SOURCES_KAFKA_PORT}].")
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
    execute_process_queue()
    listen_for_messages_loop(cost_management_type_id)


def initialize_sources_integration():  # pragma: no cover
    """Start Sources integration thread."""

    event_loop_thread = threading.Thread(target=sources_integration_thread)
    event_loop_thread.start()
    LOG.info("Listening for kafka events")
