#
# Copyright 2018 Red Hat, Inc.
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
"""Kafka message handler."""
import asyncio
import concurrent.futures
import functools
import json
import logging
import os
import random
import re
import shutil
import signal
import tempfile
import threading
import time
import traceback
import uuid
from tarfile import ReadError
from tarfile import TarFile

import requests
from aiokafka import AIOKafkaConsumer
from aiokafka import AIOKafkaProducer
from django.db import connection
from django.db import InterfaceError
from django.db import OperationalError
from kafka.errors import KafkaError

from api.common import log_json
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.accounts_accessor import AccountsAccessor
from masu.external.accounts_accessor import AccountsAccessorError
from masu.external.downloader.ocp.ocp_report_downloader import OCPReportDownloader
from masu.processor._tasks.process import _process_report_file
from masu.processor.report_processor import ReportProcessorDBError
from masu.processor.report_processor import ReportProcessorError
from masu.processor.tasks import record_all_manifest_files
from masu.processor.tasks import record_report_status
from masu.processor.tasks import summarize_reports
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER
from masu.util.ocp import common as utils

LOG = logging.getLogger(__name__)

EVENT_LOOP = asyncio.get_event_loop()

HCCM_TOPIC = "platform.upload.hccm"
VALIDATION_TOPIC = "platform.upload.validation"
SUCCESS_CONFIRM_STATUS = "success"
FAILURE_CONFIRM_STATUS = "failure"


class KafkaMsgHandlerError(Exception):
    """Kafka msg handler error."""


def backoff(interval, maximum=64):  # pragma: no cover
    """Exponential back-off."""
    wait = min(maximum, (2 ** interval)) + random.random()
    LOG.info("Sleeping for %.2f seconds.", wait)
    time.sleep(wait)


def create_manifest_entries(report_meta, request_id, context={}):
    """
    Creates manifest database entries for report processing tracking.

    Args:
        report_meta (dict): Report context dictionary from extract_payload.
        request_id (String): Identifier associated with the payload
        context (Dict): Context for logging (account, etc)

    Returns:
        manifest_id (Integer): Manifest identifier of the created db entry.

    """

    class Request:
        id = uuid.uuid4()

    class Task:
        request = Request()

    downloader = OCPReportDownloader(
        Task(),
        report_meta.get("schema_name"),
        report_meta.get("cluster_id"),
        None,
        provider_uuid=report_meta.get("provider_uuid"),
        request_id=request_id,
        account=context.get("account", "no_account"),
    )
    return downloader._prepare_db_manifest_record(report_meta)


def get_account_from_cluster_id(cluster_id, request_id, context={}):
    """
    Returns the provider details for a given OCP cluster id.

    Args:
        cluster_id (String): Cluster UUID.
        request_id (String): Identifier associated with the payload
        context (Dict): Context for logging (account, etc)

    Returns:
        (dict) - keys: value
                 authentication: String,
                 customer_name: String,
                 billing_source: String,
                 provider_type: String,
                 schema_name: String,
                 provider_uuid: String

    """
    account = None
    provider_uuid = utils.get_provider_uuid_from_cluster_id(cluster_id)
    if provider_uuid:
        msg = f"Found provider_uuid: {str(provider_uuid)} for cluster_id: {str(cluster_id)}"
        LOG.info(log_json(request_id, msg, context))
        if context:
            context["provider_uuid"] = provider_uuid
        account = get_account(provider_uuid, request_id, context)
    return account


def download_payload(request_id, url, context={}):
    """
    Download the payload from ingress to temporary location.

        Args:
        request_id (String): Identifier associated with the payload
        url (String): URL path to payload in the Insights upload service..
        context (Dict): Context for logging (account, etc)

        Returns:
        Tuple: temp_dir (String), temp_file (String)
    """
    # Create temporary directory for initial file staging and verification in the
    # OpenShift PVC directory so that any failures can be triaged in the event
    # the pod goes down.
    os.makedirs(Config.PVC_DIR, exist_ok=True)
    temp_dir = tempfile.mkdtemp(dir=Config.PVC_DIR)

    # Download file from quarantine bucket as tar.gz
    try:
        download_response = requests.get(url)
        download_response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        shutil.rmtree(temp_dir)
        msg = f"Unable to download file. Error: {str(err)}"
        LOG.warning(log_json(request_id, msg))
        raise KafkaMsgHandlerError("Unable to download file. Error: ", str(err))

    sanitized_request_id = re.sub("[^A-Za-z0-9]+", "", request_id)
    gzip_filename = f"{sanitized_request_id}.tar.gz"
    temp_file = f"{temp_dir}/{gzip_filename}"
    try:
        temp_file_hdl = open(temp_file, "wb")
        temp_file_hdl.write(download_response.content)
        temp_file_hdl.close()
    except (OSError, IOError) as error:
        shutil.rmtree(temp_dir)
        msg = f"Unable to write file. Error: {str(error)}"
        LOG.warning(log_json(request_id, msg, context))
        raise KafkaMsgHandlerError("Unable to write file. Error: ", str(error))
        LOG.warning(log_json(request_id, msg, context))

    return (temp_dir, temp_file, gzip_filename)


def extract_payload_contents(request_id, out_dir, tarball_path, tarball, context={}):
    """
    Extract the payload contents into a temporary location.

        Args:
        request_id (String): Identifier associated with the payload
        out_dir (String): temporary directory to extract data to
        tarball_path (String): the path to the payload file to extract
        tarball (String): the payload file to extract
        context (Dict): Context for logging (account, etc)

        Returns:
            (String): path to manifest file
    """
    # Extract tarball into temp directory

    if not os.path.isfile(tarball_path):
        msg = f"Unable to find tar file {tarball_path}."
        LOG.warning(log_json(request_id, msg, context))
        raise KafkaMsgHandlerError("Extraction failure, file not found.")

    try:
        mytar = TarFile.open(tarball_path, mode="r:gz")
        mytar.extractall(path=out_dir)
        files = mytar.getnames()
        manifest_path = [manifest for manifest in files if "manifest.json" in manifest]
    except (ReadError, EOFError, OSError) as error:
        msg = f"Unable to untar file {tarball_path}. Reason: {str(error)}"
        LOG.warning(log_json(request_id, msg, context))
        shutil.rmtree(out_dir)
        raise KafkaMsgHandlerError("Extraction failure.")

    if not manifest_path:
        msg = "No manifest found in payload."
        LOG.warning(log_json(request_id, msg, context))
        raise KafkaMsgHandlerError("No manifest found in payload.")

    return manifest_path


# pylint: disable=too-many-locals
def extract_payload(url, request_id, context={}):  # noqa: C901
    """
    Extract OCP usage report payload into local directory structure.

    Payload is expected to be a .tar.gz file that contains:
    1. manifest.json - dictionary containing usage report details needed
        for report processing.
        Dictionary Contains:
            files - names of .csv usage reports for the manifest
            date - DateTime that the payload was created
            uuid - uuid for payload
            cluster_id  - OCP cluster ID.
    2. *.csv - Actual usage report for the cluster.  Format is:
        Format is: <uuid>_report_name.csv

    On successful completion the report and manifest will be in a directory
    structure that the OCPReportDownloader is expecting.

    Ex: /var/tmp/insights_local/my-ocp-cluster-1/20181001-20181101

    Once the files are extracted:
    1. Provider account is retrieved for the cluster id.  If no account is found we return.
    2. Manifest database record is created which will establish the assembly_id and number of files
    3. Report stats database record is created and is used as a filter to determine if the file
       has already been processed.
    4. All report files that have not been processed will have the local path to that report file
       added to the report_meta context dictionary for that file.
    5. Report file context dictionaries that require processing is added to a list which will be
       passed to the report processor.  All context from report_meta is used by the processor.

    Args:
        url (String): URL path to payload in the Insights upload service..
        request_id (String): Identifier associated with the payload
        context (Dict): Context for logging (account, etc)

    Returns:
        [dict]: keys: value
                files: [String],
                date: DateTime,
                cluster_id: String
                manifest_path: String,
                provider_uuid: String,
                provider_type: String
                schema_name: String
                manifest_id: Integer
                current_file: String

    """
    temp_dir, temp_file_path, temp_file = download_payload(request_id, url, context)
    manifest_path = extract_payload_contents(request_id, temp_dir, temp_file_path, temp_file, context)

    # Open manifest.json file and build the payload dictionary.
    full_manifest_path = "{}/{}".format(temp_dir, manifest_path[0])
    report_meta = utils.get_report_details(os.path.dirname(full_manifest_path))

    # Filter and get account from payload's cluster-id
    cluster_id = report_meta.get("cluster_id")
    if context:
        context["cluster_id"] = cluster_id
    account = get_account_from_cluster_id(cluster_id, request_id, context)
    if not account:
        msg = f"Recieved unexpected OCP report from {cluster_id}"
        LOG.error(log_json(request_id, msg, context))
        shutil.rmtree(temp_dir)
        return None
    schema_name = account.get("schema_name")
    provider_type = account.get("provider_type")
    context["account"] = schema_name[4:]
    context["provider_type"] = provider_type
    report_meta["provider_uuid"] = account.get("provider_uuid")
    report_meta["provider_type"] = provider_type
    report_meta["schema_name"] = schema_name

    # Create directory tree for report.
    usage_month = utils.month_date_range(report_meta.get("date"))
    destination_dir = "{}/{}/{}".format(Config.INSIGHTS_LOCAL_REPORT_DIR, report_meta.get("cluster_id"), usage_month)
    os.makedirs(destination_dir, exist_ok=True)

    # Copy manifest
    manifest_destination_path = "{}/{}".format(destination_dir, os.path.basename(report_meta.get("manifest_path")))
    shutil.copy(report_meta.get("manifest_path"), manifest_destination_path)

    # Save Manifest
    report_meta["manifest_id"] = create_manifest_entries(report_meta, request_id, context)

    # Copy report payload
    report_metas = []
    for report_file in report_meta.get("files"):
        current_meta = report_meta.copy()
        subdirectory = os.path.dirname(full_manifest_path)
        payload_source_path = f"{subdirectory}/{report_file}"
        payload_destination_path = f"{destination_dir}/{report_file}"
        try:
            shutil.copy(payload_source_path, payload_destination_path)
            current_meta["current_file"] = payload_destination_path
            record_all_manifest_files(report_meta["manifest_id"], report_meta.get("files"))
            if not record_report_status(report_meta["manifest_id"], report_file):
                msg = f"Successfully extracted OCP for {report_meta.get('cluster_id')}/{usage_month}"
                LOG.info(log_json(request_id, msg, context))
                report_metas.append(current_meta)
            else:
                # Report already processed
                pass
        except FileNotFoundError:
            msg = f"File {str(report_file)} has not downloaded yet."
            LOG.debug(log_json(request_id, msg, context))

    # Remove temporary directory and files
    shutil.rmtree(temp_dir)
    return report_metas


@KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()
async def send_confirmation(request_id, status):  # pragma: no cover
    """
    Send kafka validation message to Insights Upload service.

    When a new file lands for topic 'hccm' we must validate it
    so that it will be made permanently available to other
    apps listening on the 'platform.upload.available' topic.

    Args:
        request_id (String): Request ID for file being confirmed.
        status (String): Either 'success' or 'failure'

    Returns:
        None

    """
    producer = AIOKafkaProducer(loop=EVENT_LOOP, bootstrap_servers=Config.INSIGHTS_KAFKA_ADDRESS)
    try:
        await producer.start()
    except (KafkaError, TimeoutError) as err:
        await producer.stop()
        LOG.exception(f"Unable to connect to kafka server.  Closing producer. {str(err)}")
        KAFKA_CONNECTION_ERRORS_COUNTER.inc()
        raise KafkaMsgHandlerError("Unable to connect to kafka server.  Closing producer.")

    LOG.debug("Producer started...")
    try:
        validation = {"request_id": request_id, "validation": status}
        msg = bytes(json.dumps(validation), "utf-8")
        LOG.info("Validating message: %s", str(msg))
        await producer.send_and_wait(VALIDATION_TOPIC, msg)
        LOG.info("Validating message complete.")
    finally:
        await producer.stop()
        LOG.debug("Producer stopped.")


def handle_message(msg):
    """
    Handle messages from message pending queue.

    Handle's messages with topics: 'platform.upload.hccm',
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


    Args:
        msg - Upload Service message containing usage payload information.

    Returns:
        (String, [dict]) - String: Upload Service confirmation status
                         [dict]: keys: value
                                 files: [String],
                                 date: DateTime,
                                 cluster_id: String
                                 manifest_path: String,
                                 provider_uuid: String,
                                 provider_type: String
                                 schema_name: String
                                 manifest_id: Integer
                                 current_file: String

    """
    if msg.topic == HCCM_TOPIC:
        value = json.loads(msg.value.decode("utf-8"))
        request_id = value.get("request_id", "no_request_id")
        account = value.get("account", "no_account")
        context = {"account": account}
        try:
            msg = f"Extracting Payload for msg: {str(value)}"
            LOG.info(log_json(request_id, msg, context))
            report_metas = extract_payload(value["url"], request_id, context)
            return SUCCESS_CONFIRM_STATUS, report_metas
        except (OperationalError, InterfaceError):
            msg = "Unable to extract payload, database is closed.  Retrying..."
            LOG.error(log_json(request_id, msg, context))
            raise KafkaMsgHandlerError("Unable to extract payload, db closed.")
        except Exception as error:  # noqa
            traceback.print_exc()
            msg = "Unable to extract payload. Error: %s", str(type(error))
            LOG.warning(log_json(request_id, msg, context))
            return FAILURE_CONFIRM_STATUS, None
    else:
        LOG.error("Unexpected Message")
    return None, None


def get_account(provider_uuid, request_id, context={}):
    """
    Retrieve a provider's account configuration needed for processing.

    Args:
        provider_uuid (String): Provider unique identifier.
        request_id (String): Identifier associated with the payload
        context (Dict): Context for logging (account, etc)

    Returns:
        (dict) - keys: value
                 authentication: String,
                 customer_name: String,
                 billing_source: String,
                 provider_type: String,
                 schema_name: String,
                 provider_uuid: String

    """
    all_accounts = []
    try:
        all_accounts = AccountsAccessor().get_accounts(provider_uuid)
    except AccountsAccessorError as error:
        msg = f"Unable to get accounts. Error: {str(error)}"
        LOG.warning(log_json(request_id, msg, context))
        return None

    return all_accounts.pop() if all_accounts else None


def process_report(report):
    """
    Process line item report.

    Returns True when line item processing is complete.  This is important because
    the listen_for_messages -> process_messages path must have a positive acknowledgement
    that line item processing is complete before committing.

    If the service goes down in the middle of processing (SIGTERM) we do not want a
    stray kafka commit to prematurely commit the message before processing has been
    complete.

    Args:
        report (Dict) - keys: value
                        schema_name: String,
                        manifest_id: Integer,
                        provider_uuid: String,
                        provider_type: String,
                        current_file: String,

    Returns:
        True if line item report processing is complete.

    """
    schema_name = report.get("schema_name")
    manifest_id = report.get("manifest_id")
    provider_uuid = report.get("provider_uuid")
    provider_type = report.get("provider_type")

    report_dict = {
        "file": report.get("current_file"),
        "compression": UNCOMPRESSED,
        "manifest_id": manifest_id,
        "provider_uuid": provider_uuid,
    }
    return _process_report_file(schema_name, provider_type, provider_uuid, report_dict)


def report_metas_complete(report_metas):
    """
    Verify if all reports from the ingress payload have been processed.

    in process_messages, a dictionary value "process_complete" is added to the
    report metadata dictionary for a report file.  This must be True for it to be
    considered processed.

    Args:
        report_metas (list) - List of report metadata dictionaries needed for line item
        processing.

    Returns:
        True if all report files for the payload have completed line item processing.

    """
    process_complete = False
    for report_meta in report_metas:
        if not report_meta.get("process_complete"):
            process_complete = False
            break
        else:
            process_complete = True
    return process_complete


def summarize_manifest(report_meta):
    """
    Kick off manifest summary when all report files have completed line item processing.

    Args:
        report (Dict) - keys: value
                        schema_name: String,
                        manifest_id: Integer,
                        provider_uuid: String,
                        provider_type: String,

    Returns:
        Celery Async UUID.

    """
    async_id = None
    schema_name = report_meta.get("schema_name")
    manifest_id = report_meta.get("manifest_id")
    provider_uuid = report_meta.get("provider_uuid")
    schema_name = report_meta.get("schema_name")
    provider_type = report_meta.get("provider_type")

    with ReportManifestDBAccessor() as manifest_accesor:
        if manifest_accesor.manifest_ready_for_summary(manifest_id):
            report_meta = {
                "schema_name": schema_name,
                "provider_type": provider_type,
                "provider_uuid": provider_uuid,
                "manifest_id": manifest_id,
            }
            async_id = summarize_reports.delay([report_meta])
    return async_id


async def process_messages(msg, loop=EVENT_LOOP):
    """
    Process asyncio messages and send validation status.

    Processing involves:
    1. Downloading, verifying, extracting, and preparing report files for processing.
    2. Line item processing each report file in the payload (downloaded from step 1).
    3. Check if all reports have been processed for the manifest and if so, kick off
       the celery worker task to summarize.
    4. Send payload validation status to ingress service.

    Args:
        msg (ConsumerRecord) - Message from kafka hccm topic.
        loop (Asyncio Event Loop) - Event loop while listening for messages.

    Returns:
        None

    """
    process_complete = False
    with concurrent.futures.ThreadPoolExecutor() as pool:
        status, report_metas = await loop.run_in_executor(pool, handle_message, msg)

    if report_metas:
        with concurrent.futures.ThreadPoolExecutor() as pool:
            for report_meta in report_metas:
                report_meta["process_complete"] = await loop.run_in_executor(pool, process_report, report_meta)
                LOG.info(f"Processing: {report_meta.get('current_file')} complete.")
            process_complete = report_metas_complete(report_metas)
            async_id = await loop.run_in_executor(pool, summarize_manifest, report_meta)
            if async_id:
                LOG.info("Summarization celery uuid: %s", str(async_id))
    if status:
        value = json.loads(msg.value.decode("utf-8"))
        count = 0
        while True:
            try:
                if report_metas:
                    file_list = [meta.get("current_file") for meta in report_metas]
                    files_string = ",".join(map(str, file_list))
                    LOG.info(f"Sending Ingress Service confirmation for: {files_string}")
                else:
                    LOG.info(f"Sending Ingress Service confirmation for: {str(value)}")
                await send_confirmation(value["request_id"], status)
                break
            except KafkaMsgHandlerError as err:
                LOG.error(f"Resending message confirmation due to error: {err}")
                backoff(count, Config.INSIGHTS_KAFKA_CONN_RETRY_MAX)
                count += 1
                continue

    return process_complete


def get_consumer(event_loop):  # pragma: no cover
    """Create a Kafka consumer."""
    return AIOKafkaConsumer(
        HCCM_TOPIC,
        loop=event_loop,
        bootstrap_servers=Config.INSIGHTS_KAFKA_ADDRESS,
        group_id="hccm-group",
        enable_auto_commit=False,
    )


async def listen_for_messages_loop(event_loop):
    """Wrap listen_for_messages in while true."""
    while True:
        consumer = get_consumer(event_loop)
        await listen_for_messages(consumer)


@KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()
async def listen_for_messages(consumer):
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

    Args:
        consumer - (AIOKafkaConsumer): kafka consumer for HCCM ingress topic.

    Returns:
        None

    """
    LOG.info("Kafka consumer starting...")
    await consumer.start()
    LOG.info("Listener started.  Waiting for messages...")
    try:
        async for msg in consumer:
            process_complete = False
            try:
                process_complete = await process_messages(msg)
                if process_complete:
                    await consumer.commit()
            except (InterfaceError, OperationalError, ReportProcessorDBError) as err:
                connection.close()
                LOG.error(f"[listen_for_messages] database error. Seeking to committed. Error: {str(err)}")
                await asyncio.sleep(Config.RETRY_SECONDS)
                await consumer.seek_to_committed()
            except KafkaMsgHandlerError as error:
                LOG.error(f"[listen_for_messages] internal error. Seeking to committed. Error: {str(error)}")
                await asyncio.sleep(Config.RETRY_SECONDS)
                await consumer.seek_to_committed()
            except ReportProcessorError as error:
                LOG.error(f"Report processing error: {str(error)}")
                await consumer.commit()

    except KafkaError as error:
        LOG.error(f"[listen_for_messages] Kafka error encountered: {type(error).__name__}: {error}", exc_info=True)
        KAFKA_CONNECTION_ERRORS_COUNTER.inc()
    except Exception as error:
        traceback.print_exc()
        LOG.error(f"[listen_for_messages] UNKNOWN error encountered: {type(error).__name__}: {error}", exc_info=True)
    finally:
        # Will leave consumer group; perform autocommit if enabled.
        await consumer.stop()


def shutdown(loop):  # pragma: no cover
    """SIGTERM asyncio event handler."""
    LOG.info("Received stop signal...")


@KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()
def asyncio_worker_thread(loop):  # pragma: no cover
    """
    Worker thread function to run the asyncio event loop.

    Args:
        loop - Asyncio event loop

    Returns:
        None

    """
    try:
        loop.create_task(listen_for_messages_loop(loop))
        loop.run_forever()
    except KeyboardInterrupt:
        exit(0)


def initialize_kafka_handler():  # pragma: no cover
    """
    Create asyncio tasks and daemon thread to run event loop.

    Args:
        None

    Returns:
        None

    """
    if Config.KAFKA_CONNECT:
        EVENT_LOOP.add_signal_handler(signal.SIGTERM, functools.partial(shutdown, EVENT_LOOP))
        event_loop_thread = threading.Thread(target=asyncio_worker_thread, args=(EVENT_LOOP,))
        event_loop_thread.daemon = True
        event_loop_thread.start()
        event_loop_thread.join()
