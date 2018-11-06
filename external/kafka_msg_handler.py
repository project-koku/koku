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
import json
import logging
import os
import shutil
import tempfile
import threading
from tarfile import ReadError, TarFile

import requests
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from kafka.errors import ConnectionError as KafkaConnectionError

from masu.config import Config
from masu.util.ocp import common as utils

LOG = logging.getLogger(__name__)
EVENT_LOOP = asyncio.get_event_loop()
MSG_PENDING_QUEUE = asyncio.Queue()
HCCM_TOPIC = 'platform.upload.hccm'
AVAILABLE_TOPIC = 'platform.upload.available'
SUCCESS_CONFIRM_STATUS = 'success'
FAILURE_CONFIRM_STATUS = 'failure'


class KafkaMsgHandlerError(Exception):
    """Kafka mmsg handler error."""

    pass


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
        None

    """
    # Create temporary directory for initial file staging and verification
    temp_dir = tempfile.mkdtemp()

    # Download file from quarntine bucket as tar.gz
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
    except ReadError as error:
        LOG.error('Unable to untar file. Reason: %s', str(error))
        shutil.rmtree(temp_dir)
        raise KafkaMsgHandlerError('Extraction failure.')

    # Open manifest.json file and build the payload dictionary.
    report_meta = utils.get_report_details(temp_dir)

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
    payload_source_path = '{}/{}'.format(temp_dir, report_meta.get('file'))
    payload_destination_path = '{}/{}'.format(destination_dir, report_meta.get('file'))
    shutil.copy(payload_source_path, payload_destination_path)

    LOG.info('Successfully extracted OCP for %s/%s', report_meta.get('cluster_id'), usage_month)
    # Remove temporary directory and files
    shutil.rmtree(temp_dir)


async def send_confirmation(file_hash, status):  # pragma: no cover
    """
    Send kafka validation message to Insights Upload service.

    When a new file lands for topic 'hccm' we must validate it
    so that it will be made perminenantly available to other
    apps listening on the 'platform.upload.available' topic.

    Args:
        file_hash (String): Hash for file being confirmed.
        status (String): Either 'success' or 'failure'

    Returns:
        None

    """
    producer = AIOKafkaProducer(
        loop=EVENT_LOOP, bootstrap_servers=Config.INSIGHTS_KAFKA_ADDRESS
    )
    try:
        await producer.start()
    except KafkaConnectionError:
        await producer.stop()
        raise KafkaMsgHandlerError('Unable to connect to kafka server.  Closing producer.')

    try:
        validation = {
            'hash': file_hash,
            'validation': status
        }
        msg = bytes(json.dumps(validation), 'utf-8')
        await producer.send_and_wait('uploadvalidation', msg)
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
        None

    Returns:
        None

    """
    if msg.topic == HCCM_TOPIC:
        value = json.loads(msg.value.decode('utf-8'))
        try:
            extract_payload(value['url'])
            return SUCCESS_CONFIRM_STATUS
        except KafkaMsgHandlerError as error:
            LOG.error('Unable to extract payload. Error: %s', str(error))
            return FAILURE_CONFIRM_STATUS

    elif msg.topic == AVAILABLE_TOPIC:
        value = json.loads(msg.value.decode('utf-8'))
        # Decide if we want to keep track of confirmed messages.
        # If so we will have to store the hash for hccm topic msg and
        # look for them on a list here to get the validated url.
        LOG.info('File available: %s', value['url'])
    else:
        LOG.error('Unexpected Message')
    return None


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
        status = handle_message(msg)
        if status:
            value = json.loads(msg.value.decode('utf-8'))
            await send_confirmation(value['hash'], status)


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
    except KafkaConnectionError:
        await consumer.stop()
        raise KafkaMsgHandlerError('Unable to connect to kafka server.  Closing consumer.')

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
    consumer = AIOKafkaConsumer(
        AVAILABLE_TOPIC, HCCM_TOPIC,
        loop=EVENT_LOOP, bootstrap_servers=Config.INSIGHTS_KAFKA_ADDRESS,
        group_id='hccm-group'
    )

    loop.create_task(process_messages())

    try:
        loop.run_until_complete(listen_for_messages(consumer))
    except KafkaMsgHandlerError as err:
        LOG.info('Stopping kafka worker thread.  Error: %s', str(err))


def initialize_kafka_handler():  # pragma: no cover
    """
    Create asyncio tasks and daemon thread to run event loop.

    Args:
        None

    Returns:
        None

    """
    event_loop_thread = threading.Thread(target=asyncio_worker_thread, args=(EVENT_LOOP,))
    event_loop_thread.daemon = True
    event_loop_thread.start()
