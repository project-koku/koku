#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Kafka listener for HCCM ingress uploads.

Downloading a payload and turning it into line items are separate steps.
Download ends when the raw tarball is durable in our bucket. Processing
starts on the ingress worker, which reads that object back.
This module polls Kafka, confirms the upload, and chooses which step runs
on the listener.
"""
import itertools
import json
import logging
import re
import shutil
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone

import requests
import sentry_sdk
from confluent_kafka import TopicPartition
from django.conf import settings
from django.db import connections
from django.db import DEFAULT_DB_ALIAS
from django.db import IntegrityError
from django.db import InterfaceError
from django.db import OperationalError
from kombu.exceptions import OperationalError as KombuOperationalError

from api.common import log_json
from api.iam.models import Customer
from api.utils import DateHelper
from kafka_utils.utils import extract_from_header
from kafka_utils.utils import get_consumer
from kafka_utils.utils import get_producer
from kafka_utils.utils import is_kafka_connected
from kafka_utils.utils import UPLOAD_TOPIC
from kafka_utils.utils import VALIDATION_TOPIC
from koku.probe_server import register_consumer_thread
from masu.config import Config
from masu.external.downloader.ocp.download import download_payload
from masu.external.downloader.ocp.download import is_permanent_download_error as _is_permanent_download_error
from masu.external.downloader.ocp.exceptions import FAILURE_CONFIRM_STATUS
from masu.external.downloader.ocp.exceptions import KafkaMsgHandlerError
from masu.external.downloader.ocp.exceptions import SUCCESS_CONFIRM_STATUS
from masu.external.downloader.ocp.ingress_staging import stage_ingress_payload
from masu.processor import INGRESS_DEAD_LETTER_QUEUE_FLAG
from masu.processor import INGRESS_STAGING_LISTENER_FLAG
from masu.processor import is_feature_flag_enabled_by_schema
from masu.processor.ocp.staged_payloads.processing import extract_payload
from masu.processor.ocp.staged_payloads.processing import process_extracted_reports
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessorError
from masu.processor.report_processor import ReportProcessorDBError
from masu.processor.report_processor import ReportProcessorError
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER
from masu.prometheus_stats import KAFKA_LISTENER_INFLIGHT_MESSAGE_AGE_SECONDS
from masu.prometheus_stats import KAFKA_LISTENER_WATCHDOG_DIAGNOSTICS_COUNTER
from masu.util.aws.common import copy_data_to_s3_bucket
from masu.util.aws.common import UploadError
from reporting_common.models import IngressDeadLetterQueue

LOG = logging.getLogger(__name__)
KAFKA_MAX_POLL_INTERVAL_SECONDS = 18 * 60
KAFKA_WATCHDOG_METRIC_UPDATE_SECONDS = 5


@dataclass
class KafkaMessageWatchdog:
    """Emit diagnostics when a Kafka message handler exceeds its time budget.

    The watchdog only observes the handler. In particular, it does not touch the
    consumer, so it cannot commit, seek, pause, or discard an in-flight message.
    """

    context: dict
    timeout_seconds: int

    def __post_init__(self):
        self.validate_timeout(self.timeout_seconds)
        self._start_monotonic = time.monotonic()
        self._stop_event = threading.Event()
        self._thread = None

    @staticmethod
    def validate_timeout(timeout_seconds):
        if not 0 < timeout_seconds < KAFKA_MAX_POLL_INTERVAL_SECONDS:
            raise ValueError(
                "KAFKA_LISTENER_WATCHDOG_TIMEOUT_SECONDS must be greater than 0 "
                f"and less than {KAFKA_MAX_POLL_INTERVAL_SECONDS} seconds"
            )

    def __enter__(self):
        KAFKA_LISTENER_INFLIGHT_MESSAGE_AGE_SECONDS.set(0)
        self._thread = threading.Thread(target=self._monitor, name="kafka_message_watchdog", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback_value):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)
        KAFKA_LISTENER_INFLIGHT_MESSAGE_AGE_SECONDS.set(0)
        return False

    def _monitor(self):
        diagnostic_emitted = False
        while not self._stop_event.is_set():
            elapsed_seconds = time.monotonic() - self._start_monotonic
            KAFKA_LISTENER_INFLIGHT_MESSAGE_AGE_SECONDS.set(elapsed_seconds)
            if elapsed_seconds >= self.timeout_seconds and not diagnostic_emitted:
                self._emit_diagnostic(elapsed_seconds)
                diagnostic_emitted = True
            wait_seconds = (
                KAFKA_WATCHDOG_METRIC_UPDATE_SECONDS
                if diagnostic_emitted
                else min(KAFKA_WATCHDOG_METRIC_UPDATE_SECONDS, self.timeout_seconds - elapsed_seconds)
            )
            self._stop_event.wait(wait_seconds)

    def _emit_diagnostic(self, elapsed_seconds):
        thread_stacks = {
            f"{thread.name}:{thread.ident}": "".join(traceback.format_stack(frame))
            for thread_id, frame in sys._current_frames().items()
            for thread in threading.enumerate()
            if thread.ident == thread_id
        }
        diagnostic_context = {
            **self.context,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "thread_stacks": thread_stacks,
        }
        LOG.error(
            log_json(
                self.context["request_id"],
                msg="Kafka listener message processing exceeded watchdog threshold",
                context=diagnostic_context,
            )
        )
        KAFKA_LISTENER_WATCHDOG_DIAGNOSTICS_COUNTER.inc()
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("execution_path", "kafka_listener")
            scope.set_tag("failure_type", "processing_watchdog")
            scope.set_context("kafka_message", diagnostic_context)
            sentry_sdk.capture_message("Kafka listener message processing exceeded watchdog threshold", level="error")


def _message_watchdog_context(msg, service):
    """Build safe, early message context for a listener watchdog diagnostic."""
    context = {
        "execution_path": "kafka_listener",
        "operation": "process_messages",
        "topic": msg.topic(),
        "partition": msg.partition(),
        "offset": msg.offset(),
        "service": service,
        "request_id": "no_request_id",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        value = json.loads(msg.value().decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        LOG.warning("Unable to extract Kafka watchdog message context", exc_info=True)
        return context

    context["request_id"] = value.get("request_id", "no_request_id")
    context["account"] = value.get("account")
    context["org_id"] = value.get("org_id")
    if org_id := value.get("org_id"):
        org_id = str(org_id)
        if settings.SCHEMA_SUFFIX and not org_id.endswith(settings.SCHEMA_SUFFIX):
            org_id = f"{org_id}{settings.SCHEMA_SUFFIX}"
        context["schema"] = f"org{org_id}"
    return context


def close_and_set_db_connection():  # pragma: no cover
    """Close the db connection and set to None."""
    if connections[DEFAULT_DB_ALIAS].connection:
        connections[DEFAULT_DB_ALIAS].connection.close()
    connections[DEFAULT_DB_ALIAS].connection = None


def delivery_callback(err, msg):
    """Acknowledge message success or failure."""
    if err is not None:
        LOG.error(f"Failed to deliver message: {msg}: {err}")
    else:
        LOG.info("Validation message delivered.")


@KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()
def send_confirmation(request_id, status):  # pragma: no cover
    """
    Send kafka validation message to Insights Upload service.

    When a new file lands for topic 'hccm' we must validate it
    so that it will be made permanently available to other
    apps listening on the 'platform.upload.available' topic.
    """
    producer = get_producer()
    validation = {"request_id": request_id, "validation": status}
    msg = bytes(json.dumps(validation), "utf-8")
    producer.produce(VALIDATION_TOPIC, value=msg, callback=delivery_callback)
    producer.poll(0)


def _get_or_create_dlq_entry(request_id, value, schema_name):
    """Return the DLQ row for request_id, creating it when this is the first attempt."""
    dlq_payload = {key: value.get(key) for key in ("request_id", "url", "account", "org_id")}
    try:
        dlq_entry, _created = IngressDeadLetterQueue.objects.get_or_create(
            request_id=request_id,
            defaults={
                "account": value.get("account"),
                "org_id": value.get("org_id"),
                "schema_name": schema_name,
                "payload": dlq_payload,
            },
        )
    except IntegrityError:
        dlq_entry = IngressDeadLetterQueue.objects.get(request_id=request_id)
    return dlq_entry


def send_to_dead_letter_queue(request_id, value, schema_name, context):
    """Persist the Kafka message and copy the raw ingress payload to S3 without processing.

    Returns SUCCESS_CONFIRM_STATUS when the payload is parked (or already parked).
    Returns FAILURE_CONFIRM_STATUS for permanent download errors so the consumer commits.
    Raises KafkaMsgHandlerError (or DB errors) so the consumer rewinds on transient failures.
    """
    dlq_entry = _get_or_create_dlq_entry(request_id, value, schema_name)
    if dlq_entry.s3_key:
        LOG.info(
            log_json(
                request_id,
                msg="ingress payload already stored in dead letter queue",
                context=context,
                s3_key=dlq_entry.s3_key,
            )
        )
        return SUCCESS_CONFIRM_STATUS

    payload_path = None
    try:
        LOG.info(log_json(request_id, msg="sending ingress payload to dead letter queue", context=context))
        payload_path = download_payload(request_id, value["url"], context)
        now = DateHelper().now_utc
        s3_path = (
            f"{Config.WAREHOUSE_PATH}/dead_letter_queue/{schema_name}"
            f"/{now.strftime('%Y')}/{now.strftime('%m')}/{now.strftime('%d')}"
        )
        sanitized_request_id = re.sub("[^A-Za-z0-9]+", "", request_id)
        filename = f"{sanitized_request_id}.tar.gz"
        with open(payload_path, "rb") as fin:
            copy_data_to_s3_bucket(request_id, s3_path, filename, fin, context=context)
        dlq_entry.s3_key = f"{s3_path}/{filename}"
        dlq_entry.save(update_fields=["s3_key"])
        LOG.info(
            log_json(
                request_id,
                msg="ingress payload stored in dead letter queue",
                context=context,
                s3_key=dlq_entry.s3_key,
            )
        )
        return SUCCESS_CONFIRM_STATUS
    except (OperationalError, InterfaceError):
        raise
    except (UploadError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
        msg = f"Unable to send payload to dead letter queue. Error: {type(error).__name__}: {error}"
        LOG.warning(log_json(request_id, msg=msg, context=context))
        raise KafkaMsgHandlerError(msg) from error
    except KafkaMsgHandlerError as error:
        if _is_permanent_download_error(error):
            msg = f"Unable to send payload to dead letter queue. Error: {type(error).__name__}: {error}"
            LOG.warning(log_json(request_id, msg=msg, context=context))
            return FAILURE_CONFIRM_STATUS
        raise
    except KeyError as error:
        msg = f"Unable to send payload to dead letter queue. Error: {type(error).__name__}: {error}"
        LOG.warning(log_json(request_id, msg=msg, context=context))
        return FAILURE_CONFIRM_STATUS
    finally:
        if payload_path is not None:
            shutil.rmtree(payload_path.parent, ignore_errors=True)


def legacy_message_processing(request_id, value, context):
    """Download and extract an ingress payload on the listener thread.

    This is the path used when INGRESS_STAGING_LISTENER_FLAG is off. Production
    on-prem stays here: MockUnleashClient does not list that flag, and
    ``dev_fallback=True`` is true only when the Unleash environment is
    ``development``. Remove this function once the flag is confirmed for every
    schema that should take the staging path.
    """
    payload_path = None
    try:
        try:
            msg = f"Downloading Payload for msg: {str(value)}"
            LOG.info(log_json(request_id, msg=msg, context=context))
            payload_path = download_payload(request_id, value["url"], context)
        except Exception as error:
            traceback.print_exc()
            msg = f"Unable to download payload. Error: {type(error).__name__}: {error}"
            LOG.warning(log_json(request_id, msg=msg, context=context))
            return FAILURE_CONFIRM_STATUS, None, None

        try:
            msg = f"Extracting Payload for msg: {str(value)}"
            LOG.info(log_json(request_id, msg=msg, context=context))
            report_metas, manifest_uuid = extract_payload(payload_path, request_id, value["b64_identity"], context)
            return SUCCESS_CONFIRM_STATUS, report_metas, manifest_uuid
        except (OperationalError, InterfaceError) as error:
            close_and_set_db_connection()
            msg = f"Unable to extract payload, db closed. {type(error).__name__}: {error}"
            LOG.warning(log_json(request_id, msg=msg, context=context))
            raise KafkaMsgHandlerError(msg) from error
        except Exception as error:  # noqa
            traceback.print_exc()
            msg = f"Unable to extract payload. Error: {type(error).__name__}: {error}"
            LOG.warning(log_json(request_id, msg=msg, context=context))
            return FAILURE_CONFIRM_STATUS, None, None
    finally:
        if payload_path is not None:
            shutil.rmtree(payload_path.parent, ignore_errors=True)


def handle_message(kmsg):
    """
    Handle messages from message pending queue.

    Handle's messages with topics: 'platform.upload.announce',
    and 'platform.upload.available'.

    The OCP cost usage payload will land on topic hccm.
    These messages will be extracted into the local report
    directory structure.  Once the file has been verified
    (successfully extracted) we will report the status to
    the Insights Upload Service so the file can be made available
    to other apps on the service.

    Messages on the available topic are messages that have
    been verified by an app on the Insights upload service.
    For now we are just logging the URL for demonstration purposes.
    In the future if we want to maintain a URL to our report files
    in the upload service we could look for hashes for files that
    we have previously validated on the hccm topic.
    """
    value = json.loads(kmsg.value().decode("utf-8"))
    request_id = value.get("request_id", "no_request_id")
    account = value.get("account")
    org_id = value.get("org_id")
    context = {"account": account, "org_id": org_id}
    if not org_id:
        msg = f"Received unknown organization message: {str(value)}"
        LOG.info(log_json(request_id, msg=msg, context=context))
        return FAILURE_CONFIRM_STATUS, None, None

    schema_name = Customer.objects.filter(org_id=org_id).values_list("schema_name", flat=True).first()
    if schema_name and is_feature_flag_enabled_by_schema(
        schema_name, INGRESS_STAGING_LISTENER_FLAG, dev_fallback=True
    ):
        context["schema"] = schema_name
        return stage_ingress_payload(request_id, value, context), None, None
    # Park-and-skip: keep default dev_fallback=False so local/dev still extracts payloads.
    if schema_name and is_feature_flag_enabled_by_schema(schema_name, INGRESS_DEAD_LETTER_QUEUE_FLAG):
        context["schema"] = schema_name
        return send_to_dead_letter_queue(request_id, value, schema_name, context), None, None

    # Remove with legacy_message_processing once INGRESS_STAGING_LISTENER_FLAG is confirmed.
    return legacy_message_processing(request_id, value, context)


def process_messages(msg):
    """
    Process messages and send validation status.

    Processing involves:
    1. Downloading, verifying, extracting, and preparing report files for processing.
    2. Line item processing each report file in the payload (downloaded from step 1).
    3. Check if all reports have been processed for the manifest and if so, kick off
       the celery worker task to summarize.
    4. Send payload validation status to ingress service.
    """
    process_complete = False
    status, report_metas, manifest_uuid = handle_message(msg)

    value = json.loads(msg.value().decode("utf-8"))
    request_id = value.get("request_id", "no_request_id")
    tracing_id = manifest_uuid or request_id
    if report_metas:
        process_complete = process_extracted_reports(request_id, report_metas, tracing_id)

    if status and not settings.DEBUG:
        if report_metas:
            file_list = [meta.get("current_file") for meta in report_metas]
            files_string = ",".join(map(str, file_list))
            LOG.info(log_json(tracing_id, msg=f"Sending Ingress Service confirmation for: {files_string}"))
        else:
            logged_value = {key: item for key, item in value.items() if key != "b64_identity"}
            LOG.info(log_json(tracing_id, msg=f"Sending Ingress Service confirmation for: {logged_value}"))
        send_confirmation(value["request_id"], status)

    return process_complete


def listen_for_messages_loop():
    """Wrap listen_for_messages in while true."""
    KafkaMessageWatchdog.validate_timeout(Config.KAFKA_LISTENER_WATCHDOG_TIMEOUT_SECONDS)
    kafka_conf = {
        "group.id": "hccm-group",
        "queued.max.messages.kbytes": 1024,
        "enable.auto.commit": False,
        "max.poll.interval.ms": KAFKA_MAX_POLL_INTERVAL_SECONDS * 1000,
    }
    consumer = get_consumer(kafka_conf)
    consumer.subscribe([UPLOAD_TOPIC])
    LOG.info("Consumer is listening for messages...")
    for _ in itertools.count():  # equivalent to while True, but mockable
        msg = consumer.poll(timeout=1.0)
        if msg is None:
            continue

        if msg.error():
            KAFKA_CONNECTION_ERRORS_COUNTER.inc()
            LOG.error(f"[listen_for_messages_loop] consumer.poll message: {msg}. Error: {msg.error()}")
            continue

        listen_for_messages(msg, consumer)


def rewind_consumer_to_retry(consumer, topic_partition):
    """Helper method to log and rewind kafka consumer for retry."""
    LOG.info(f"Seeking back to offset: {topic_partition.offset}, partition: {topic_partition.partition}")
    consumer.seek(topic_partition)
    time.sleep(Config.RETRY_SECONDS)


def listen_for_messages(msg, consumer):
    """
    Listen for messages on the hccm topic.

    Once a message from one of these topics arrives, we add
    them extract the payload and line item process the report files.

    Once all files from the manifest are complete a celery job is
    dispatched to the worker to complete summary processing for the manifest.

    Several exceptions can occur while listening for messages:
    Database Errors - Re-processing attempts will be made until successful.
    Internal Errors - Re-processing attempts will be made until successful.
    Report Processing Errors - Kafka message will be committed with an error.
                               Errors of this type would require a report processor
                               fix and we do not want to block the message queue.

    Upon successful processing the kafka message is manually committed.  Manual
    commits are used so we can use the message queue to store unprocessed messages
    to make the service more tolerant of SIGTERM events.
    """
    offset = msg.offset()
    partition = msg.partition()
    topic_partition = TopicPartition(topic=msg.topic(), partition=partition, offset=offset)
    try:
        LOG.info(f"Processing message offset: {offset} partition: {partition}")
        service = extract_from_header(msg.headers(), "service")
        LOG.debug(f"service: {service} | {msg.headers()}")
        if service == "hccm":
            watchdog_context = _message_watchdog_context(msg, service)
            with KafkaMessageWatchdog(watchdog_context, Config.KAFKA_LISTENER_WATCHDOG_TIMEOUT_SECONDS):
                process_messages(msg)
        LOG.debug(f"COMMITTING: message offset: {offset} partition: {partition}")
        consumer.commit()
    except (InterfaceError, OperationalError, ReportProcessorDBError) as error:
        close_and_set_db_connection()
        LOG.error(f"[listen_for_messages] Database error. Error: {type(error).__name__}: {error}. Retrying...")
        rewind_consumer_to_retry(consumer, topic_partition)
    except (KafkaMsgHandlerError, KombuOperationalError) as error:
        LOG.error(f"[listen_for_messages] Internal error. {type(error).__name__}: {error}. Retrying...")
        rewind_consumer_to_retry(consumer, topic_partition)
    except (ReportProcessorError, ParquetReportProcessorError) as error:
        LOG.warning(f"[listen_for_messages] Report processing error: {str(error)}", exc_info=error)
        LOG.debug(f"COMMITTING: message offset: {offset} partition: {partition}")
        consumer.commit()
    except Exception as error:
        LOG.error(f"[listen_for_messages] UNKNOWN error encountered: {type(error).__name__}: {error}", exc_info=True)


def koku_listener_thread():  # pragma: no cover
    """Configure Listener listener thread."""
    if is_kafka_connected():  # Check that Kafka is running
        LOG.info("Kafka is running.")

    try:
        listen_for_messages_loop()
    except KeyboardInterrupt:
        exit(0)


def initialize_kafka_handler():
    """Start Listener thread."""
    if Config.KAFKA_CONNECT:
        event_loop_thread = threading.Thread(target=koku_listener_thread)
        event_loop_thread.daemon = True
        event_loop_thread.start()
        register_consumer_thread(event_loop_thread)
        event_loop_thread.join()
