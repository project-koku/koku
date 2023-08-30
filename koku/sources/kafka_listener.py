#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Sources Integration Service."""
import itertools
import logging
import queue
import random
import sys
import threading
import time

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

from api.provider.models import Sources
from kafka_utils.utils import get_consumer
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER
from masu.prometheus_stats import SOURCES_HTTP_CLIENT_ERROR_COUNTER
from masu.prometheus_stats import SOURCES_KAFKA_LOOP_RETRY
from masu.prometheus_stats import SOURCES_PROVIDER_OP_RETRY_LOOP_COUNTER
from providers.provider_errors import SkipStatusPush
from sources import storage
from sources.api.status import check_kafka_connection
from sources.config import Config
from sources.kafka_message_processor import create_msg_processor
from sources.kafka_message_processor import SourcesMessageError
from sources.sources_http_client import SourceNotFoundError
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_http_client import SourcesHTTPClientError
from sources.sources_provider_coordinator import SourcesProviderCoordinator
from sources.sources_provider_coordinator import SourcesProviderCoordinatorError
from sources.tasks import delete_source

LOG = logging.getLogger(__name__)

PROCESS_QUEUE = queue.PriorityQueue()
COUNT = itertools.count()  # next(COUNT) returns next sequential number


class SourcesIntegrationError(ValidationError):
    """Sources Integration error."""


def load_process_queue():
    """
    Re-populate the process queue for any Source events that need synchronization.

    Handles the case for when the Sources Integration service goes down before
    Koku Synchronization could be completed.
    """
    pending_events = _collect_pending_items()
    for event in pending_events:
        _log_process_queue_event(PROCESS_QUEUE, event, "load_process_queue")
        PROCESS_QUEUE.put_nowait((next(COUNT), event))


def _collect_pending_items():
    """Gather all sources to create update, or delete."""
    create_events = storage.load_providers_to_create()
    update_events = storage.load_providers_to_update()
    destroy_events = storage.load_providers_to_delete()
    return create_events + update_events + destroy_events


def _log_process_queue_event(queue, event, trigger=""):
    """Log process queue event."""
    operation = event.get("operation", "unknown")
    provider = event.get("provider")
    name = provider.name if provider else "unknown"
    LOG.info(f"[{trigger}] adding operation {operation} for {name} to process queue (size: {queue.qsize()})")


@receiver(post_save, sender=Sources)
def storage_callback(sender, instance, **kwargs):
    """Load Sources ready for Koku Synchronization when Sources table is updated."""
    if instance.koku_uuid and instance.pending_update and not instance.pending_delete:
        update_event = {"operation": "update", "provider": instance}
        _log_process_queue_event(PROCESS_QUEUE, update_event, "storage_callback")
        LOG.debug(f"Update Event Queued for:\n{str(instance)}")
        PROCESS_QUEUE.put_nowait((next(COUNT), update_event))

    if instance.pending_delete:
        delete_event = {"operation": "destroy", "provider": instance}
        _log_process_queue_event(PROCESS_QUEUE, delete_event, "storage_callback")
        LOG.debug(f"Delete Event Queued for:\n{str(instance)}")
        PROCESS_QUEUE.put_nowait((next(COUNT), delete_event))

    process_event = storage.screen_and_build_provider_sync_create_event(instance)
    if process_event:
        _log_process_queue_event(PROCESS_QUEUE, process_event, "storage_callback")
        LOG.debug(f"Create Event Queued for:\n{str(instance)}")
        PROCESS_QUEUE.put_nowait((next(COUNT), process_event))

    execute_process_queue()


def execute_process_queue():
    """Execute process queue to synchronize providers."""
    while not PROCESS_QUEUE.empty():
        msg_tuple = PROCESS_QUEUE.get()
        process_synchronize_sources_msg(msg_tuple, PROCESS_QUEUE)


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

    LOG.info(f"[synchronize_sources] starting `{operation}` for source_id: {provider.source_id}")
    try:
        execute_koku_provider_op(msg)
        LOG.info(f"[synchronize_sources] completed `{operation}` for source_id: {provider.source_id}")
    except (IntegrityError, SourcesIntegrationError) as error:
        LOG.warning(f"[synchronize_sources] re-queuing failed operation. Error: {error}")
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
            f"[synchronize_sources] Unexpected synchronization error for source_id {source_id} "
            f"encountered: {type(error).__name__}: {error}",
            exc_info=True,
        )


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
    provider: Sources = msg.get("provider")
    operation = msg.get("operation")
    account_coordinator = SourcesProviderCoordinator(
        provider.source_id, provider.auth_header, provider.account_id, provider.org_id
    )
    sources_client = SourcesHTTPClient(provider.auth_header, provider.source_id, provider.account_id, provider.org_id)

    try:
        if operation == "create":
            LOG.info(f"[provider_operation] creating Koku Provider for source_id: {provider.source_id}")
            instance = account_coordinator.create_account(provider)
            LOG.info(f"[provider_operation] created provider {instance.uuid} for source_id: {provider.source_id}")
        elif operation == "update":
            LOG.info(f"[provider_operation] updating Koku Provider for source_id: {provider.source_id}")
            instance = account_coordinator.update_account(provider)
            LOG.info(f"[provider_operation] updated provider {instance.uuid} for source_id: {provider.source_id}")
        elif operation == "destroy":
            LOG.info(f"[provider_operation] destroying Koku Provider for source_id: {provider.source_id}")
            delete_source.delay(
                provider.source_id, provider.auth_header, provider.koku_uuid, provider.account_id, provider.org_id
            )
            LOG.info(
                f"[provider_operation] destroy provider task queued for provider {provider.koku_uuid}"
                f" for source_id: {provider.source_id}"
            )
        else:
            LOG.error(f"unknown operation: {operation}")
        sources_client.set_source_status(None)

    except SourcesProviderCoordinatorError as account_error:
        sources_client.set_source_status(account_error)
        raise SourcesIntegrationError(f"[provider_operation] Koku Provider error: {account_error}")
    except ValidationError as account_error:
        err_msg = (
            f"[provider_operation] unable to {operation} provider for"
            f" source_id: {provider.source_id}. Reason: {account_error}"
        )
        LOG.warning(err_msg)
        sources_client.set_source_status(account_error)
    except SkipStatusPush as error:
        LOG.info(f"[provider_operation] platform sources status push skipped. Reason: {error}")


def _requeue_provider_sync_message(priority, msg, queue):
    """Helper to requeue provider sync messages."""
    SOURCES_PROVIDER_OP_RETRY_LOOP_COUNTER.inc()
    time.sleep(Config.RETRY_SECONDS)
    _log_process_queue_event(queue, msg, "_requeue_provider_sync_message")
    queue.put((priority, msg))
    LOG.warning(
        f'Requeue of failed operation: {msg.get("operation")} '
        f'for source_id: {msg.get("provider").source_id} complete.'
    )


def listen_for_messages_loop(application_source_id):  # pragma: no cover
    """Wrap listen_for_messages in while true."""
    kafka_conf = {
        "group.id": "hccm-sources",
        "queued.max.messages.kbytes": 1024,
        "enable.auto.commit": False,
    }
    consumer = get_consumer(kafka_conf)
    consumer.subscribe([Config.SOURCES_TOPIC])
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
            if msg_processor and msg_processor.source_id and msg_processor.auth_header:
                tp = TopicPartition(Config.SOURCES_TOPIC, msg_processor.partition, msg_processor.offset)
                if not msg_processor.msg_for_cost_mgmt():
                    LOG.info("Event not associated with cost-management.")
                    consumer.commit()
                    return
                LOG.info(f"processing cost-mgmt message: {msg_processor}")
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
            LOG.warning(f"[listen_for_messages] {type(error).__name__}: {error}. Skipping msg: {kaf_msg.value()}")
            consumer.commit()
        else:
            consumer.commit()

    except KafkaError as error:
        LOG.error(f"[listen_for_messages] Kafka error encountered: {type(error).__name__}: {error}", exc_info=True)
    except Exception as error:
        LOG.error(f"[listen_for_messages] UNKNOWN error encountered: {type(error).__name__}: {error}", exc_info=True)


def close_and_set_db_connection():  # pragma: no cover
    """Close the db connection and set to None."""
    if connections[DEFAULT_DB_ALIAS].connection:
        connections[DEFAULT_DB_ALIAS].connection.close()
    connections[DEFAULT_DB_ALIAS].connection = None


def rewind_consumer_to_retry(consumer, topic_partition):
    """Helper method to log and rewind kafka consumer for retry."""
    SOURCES_KAFKA_LOOP_RETRY.inc()
    LOG.info(f"Seeking back to offset: {topic_partition.offset}, partition: {topic_partition.partition}")
    consumer.seek(topic_partition)
    time.sleep(Config.RETRY_SECONDS)


def backoff(interval, maximum=120):
    """Exponential back-off."""
    wait = min(maximum, (2**interval)) + random.random()
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
                Config.SOURCES_PROBE_HEADER
            ).get_cost_management_application_type_id()
            LOG.info("Connected to Sources REST API.")
        except SourcesHTTPClientError as error:
            LOG.error(f"Unable to connect to Sources REST API. Error: {error}")
            backoff(count)
            count += 1
            LOG.info("Reattempting connection to Sources REST API.")
        except SourceNotFoundError as err:
            LOG.error(f"Cost Management application not found: {err}")
            backoff(count)
            count += 1
            LOG.info("Reattempting connection to Sources REST API.")
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
    event_loop_thread.join()
    LOG.info("Listening for kafka events")
