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
import json
import logging
import os
import random
import shutil
import tempfile
import threading
import time
from tarfile import ReadError, TarFile

import requests
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from kafka.errors import KafkaError

from masu.config import Config
from masu.external.accounts_accessor import (AccountsAccessor, AccountsAccessorError)
from masu.processor.tasks import get_report_files, summarize_reports
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER
from masu.util.ocp import common as utils

LOG = logging.getLogger(__name__)

EVENT_LOOP = asyncio.get_event_loop()
MSG_PENDING_QUEUE = asyncio.Queue()

HCCM_TOPIC = 'platform.upload.hccm'
VALIDATION_TOPIC = 'platform.upload.validation'
SUCCESS_CONFIRM_STATUS = 'success'
FAILURE_CONFIRM_STATUS = 'failure'


class KafkaMsgHandlerError(Exception):
    """Kafka mmsg handler error."""


# pylint: disable=too-many-locals
def extract_payload(url):
    """
    Extract OCP usage report payload into local directory structure.

    Payload is expected to be a .tar.gz file that contains:
    1. manifest.json - dictionary containing usage report details needed
        for report processing.
        Dictionary Contains:
            file - .csv usage report file name
            date - DateTime that the payload was created
            uuid - uuid for payload
            cluster_id  - OCP cluster ID.
    2. *.csv - Actual usage report for the cluster.  Format is:
        Format is: <uuid>_report_name.csv

    On successful completion the report and manifest will be in a directory
    structure that the OCPReportDownloader is expecting.

    Ex: /var/tmp/insights_local/my-ocp-cluster-1/20181001-20181101

    Args:
        url (String): URL path to payload in the Insights upload service..

    Returns:
        (Dict): keys: value
            "file: String,
             cluster_id: String,
             payload_date: DateTime,
             manifest_path: String,
             uuid: String,
             manifest_path: String"

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
        raise KafkaMsgHandlerError('Unable to download file. Error: ', str(err))

    temp_file = '{}/{}'.format(temp_dir, 'usage.tar.gz')
    try:
        temp_file_hdl = open('{}/{}'.format(temp_dir, 'usage.tar.gz'), 'wb')
        temp_file_hdl.write(download_response.content)
        temp_file_hdl.close()
    except (OSError, IOError) as error:
        shutil.rmtree(temp_dir)
        raise KafkaMsgHandlerError('Unable to write file. Error: ', str(error))

    # Extract tarball into temp directory
    try:
        mytar = TarFile.open(temp_file)
        mytar.extractall(path=temp_dir)
        files = mytar.getnames()
        manifest_path = [manifest for manifest in files if 'manifest.json' in manifest]
    except (ReadError, EOFError) as error:
        LOG.error('Unable to untar file. Reason: %s', str(error))
        shutil.rmtree(temp_dir)
        raise KafkaMsgHandlerError('Extraction failure.')

    # Open manifest.json file and build the payload dictionary.
    full_manifest_path = '{}/{}'.format(temp_dir, manifest_path[0])
    report_meta = utils.get_report_details(os.path.dirname(full_manifest_path))

    # Create directory tree for report.
    usage_month = utils.month_date_range(report_meta.get('date'))
    destination_dir = '{}/{}/{}'.format(Config.INSIGHTS_LOCAL_REPORT_DIR,
                                        report_meta.get('cluster_id'),
                                        usage_month)
    os.makedirs(destination_dir, exist_ok=True)

    # Copy manifest
    manifest_destination_path = '{}/{}'.format(destination_dir,
                                               os.path.basename(report_meta.get('manifest_path')))
    shutil.copy(report_meta.get('manifest_path'), manifest_destination_path)

    # Copy report payload
    for report_file in report_meta.get('files'):
        subdirectory = os.path.dirname(full_manifest_path)
        payload_source_path = '{}/{}'.format(subdirectory, report_file)
        payload_destination_path = '{}/{}'.format(destination_dir, report_file)
        try:
            shutil.copy(payload_source_path, payload_destination_path)
        except FileNotFoundError as error:
            LOG.error('Unable to find file in payload. %s', str(error))
            raise KafkaMsgHandlerError('Missing file in payload')
    LOG.info('Successfully extracted OCP for %s/%s', report_meta.get('cluster_id'), usage_month)
    # Remove temporary directory and files
    shutil.rmtree(temp_dir)
    return report_meta


async def send_confirmation(request_id, status):  # pragma: no cover
    """
    Send kafka validation message to Insights Upload service.

    When a new file lands for topic 'hccm' we must validate it
    so that it will be made perminenantly available to other
    apps listening on the 'platform.upload.available' topic.

    Args:
        request_id (String): Request ID for file being confirmed.
        status (String): Either 'success' or 'failure'

    Returns:
        None

    """
    producer = AIOKafkaProducer(
        loop=EVENT_LOOP, bootstrap_servers=Config.INSIGHTS_KAFKA_ADDRESS
    )
    try:
        await producer.start()
    except (KafkaError, TimeoutError) as err:
        await producer.stop()
        LOG.exception(str(err))
        KAFKA_CONNECTION_ERRORS_COUNTER.inc()
        raise KafkaMsgHandlerError('Unable to connect to kafka server.  Closing producer.')

    try:
        validation = {
            'request_id': request_id,
            'validation': status
        }
        msg = bytes(json.dumps(validation), 'utf-8')
        LOG.info('Validating message: %s', str(msg))
        await producer.send_and_wait(VALIDATION_TOPIC, msg)
        LOG.info('Validating message complete.')
    finally:
        await producer.stop()


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
        (String, dict) - String: Upload Service confirmation status
                         dict: keys: value
                               file: String,
                               cluster_id: String,
                               payload_date: DateTime,
                               manifest_path: String,
                               uuid: String,
                               manifest_path: String

    """
    if msg.topic == HCCM_TOPIC:
        value = json.loads(msg.value.decode('utf-8'))
        try:
            LOG.info(f'Extracting Payload for msg: {str(msg)}')
            report_meta = extract_payload(value['url'])
            return SUCCESS_CONFIRM_STATUS, report_meta
        except KafkaMsgHandlerError as error:
            LOG.error('Unable to extract payload. Error: %s', str(error))
            return FAILURE_CONFIRM_STATUS, None
    else:
        LOG.error('Unexpected Message')
    return None, None


def get_account(provider_uuid):
    """
    Retrieve a provider's account configuration needed for processing.

    Args:
        provider_uuid (String): Provider unique identifier.

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
        LOG.info('Unable to get accounts. Error: %s', str(error))
        return None

    return all_accounts.pop() if all_accounts else None


def process_report(report):
    """
    Process line item report and kick off summarization celery task.

    Args:
        report (Dict) - keys: value
                        file: String,
                        cluster_id: String,
                        payload_date: DateTime,
                        manifest_path: String,
                        uuid: String,
                        manifest_path: String
    Returns:
        None

    """
    cluster_id = report.get('cluster_id')
    provider_uuid = utils.get_provider_uuid_from_cluster_id(cluster_id)
    if provider_uuid:
        LOG.info('Found provider_uuid: %s for cluster_id: %s', str(provider_uuid), str(cluster_id))
        account = get_account(provider_uuid)
        if account:
            LOG.info('Processing report for account %s', account)
            reports_to_summarize = get_report_files(**account)
            LOG.info('Processing complete for account %s', account)

            async_id = summarize_reports.delay(reports_to_summarize)
            LOG.info('Summarization celery uuid: %s', str(async_id))
    else:
        LOG.error('Could not find provider_uuid for cluster_id: %s', str(cluster_id))


# pylint: disable=broad-except
async def process_messages():  # pragma: no cover
    """
    Process asyncio MSG_PENDING_QUEUE and send validation status.

    Args:
        None

    Returns:
        None

    """
    while True:
        msg = await MSG_PENDING_QUEUE.get()
        status, report_meta = handle_message(msg)
        if status:
            value = json.loads(msg.value.decode('utf-8'))
            await send_confirmation(value['request_id'], status)
        if report_meta:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                try:
                    await EVENT_LOOP.run_in_executor(pool, process_report, report_meta)
                    LOG.info('Processing: %s complete.', str(report_meta))
                except Exception as error:
                    # The reason for catching all exceptions is to ensure that the event
                    # loop does not block if process_report fails.
                    # Since this is a critical path for the listener it's not worth the
                    # risk of missing an exception in the download->process sequence.
                    LOG.error('Line item processing exception: %s', str(error))


async def listen_for_messages(consumer):  # pragma: no cover
    """
    Listen for messages on the available and hccm topics.

    Once a message from one of these topics arrives, we add
    them to the MSG_PENDING_QUEUE.

    Args:
        None

    Returns:
        None

    """
    try:
        await consumer.start()
    except KafkaError as err:
        await consumer.stop()
        LOG.exception(str(err))
        KAFKA_CONNECTION_ERRORS_COUNTER.inc()
        raise KafkaMsgHandlerError('Unable to connect to kafka server.')

    LOG.info('Listener started.  Waiting for messages...')
    try:
        # Consume messages
        async for msg in consumer:
            await MSG_PENDING_QUEUE.put(msg)
    finally:
        # Will leave consumer group; perform autocommit if enabled.
        await consumer.stop()


def asyncio_worker_thread(loop):  # pragma: no cover
    """
    Worker thread function to run the asyncio event loop.

    Args:
        None

    Returns:
        None

    """
    def backoff(interval, maximum=64):
        """Exponential back-off."""
        wait = min(maximum, (2 ** interval)) + (random.randint(0, 1000) / 1000.0)
        LOG.info('Sleeping for %s seconds.', wait)
        time.sleep(wait)

    count = 0
    try:
        while True:

            consumer = AIOKafkaConsumer(
                HCCM_TOPIC,
                loop=EVENT_LOOP, bootstrap_servers=Config.INSIGHTS_KAFKA_ADDRESS,
                group_id='hccm-group'
            )

            loop.create_task(process_messages())

            try:
                loop.run_until_complete(listen_for_messages(consumer))
            except KafkaMsgHandlerError as err:
                LOG.info('Kafka connection failure.  Error: %s', str(err))
            backoff(count, Config.INSIGHTS_KAFKA_CONN_RETRY_MAX)
            count += 1
            LOG.info('Attempting to reconnect')

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
        event_loop_thread = threading.Thread(target=asyncio_worker_thread, args=(EVENT_LOOP,))
        event_loop_thread.daemon = True
        event_loop_thread.start()
        event_loop_thread.join()
