#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Kafka message handler."""
import itertools
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from tarfile import ReadError
from tarfile import TarFile

import pandas as pd
import requests
from confluent_kafka import TopicPartition
from django.conf import settings
from django.db import connections
from django.db import DEFAULT_DB_ALIAS
from django.db import IntegrityError
from django.db import InterfaceError
from django.db import OperationalError
from django.db import transaction
from kombu.exceptions import OperationalError as KombuOperationalError

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from common.queues import get_customer_queue
from common.queues import OCPQueue
from kafka_utils.utils import extract_from_header
from kafka_utils.utils import get_consumer
from kafka_utils.utils import get_producer
from kafka_utils.utils import is_kafka_connected
from kafka_utils.utils import UPLOAD_TOPIC
from kafka_utils.utils import VALIDATION_TOPIC
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.ros_report_shipper import ROSReportShipper
from masu.processor._tasks.process import _process_report_file
from masu.processor.report_processor import ReportProcessorDBError
from masu.processor.report_processor import ReportProcessorError
from masu.processor.tasks import record_all_manifest_files
from masu.processor.tasks import record_report_status
from masu.processor.tasks import summarize_reports
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.common import get_path_prefix
from masu.util.ocp import common as utils
from reporting_common.models import CostUsageReportManifest
from reporting_common.states import ManifestState
from reporting_common.states import ManifestStep

LOG = logging.getLogger(__name__)
SUCCESS_CONFIRM_STATUS = "success"
FAILURE_CONFIRM_STATUS = "failure"
MANIFEST_ACCESSOR = ReportManifestDBAccessor()


class KafkaMsgHandlerError(Exception):
    """Kafka msg handler error."""


def get_data_frame(file_path: os.PathLike):
    """read csv file into dataframe"""
    try:
        return pd.read_csv(file_path, dtype=pd.StringDtype(storage="pyarrow"), on_bad_lines="warn")
    except Exception as error:
        LOG.error(f"File {file_path} could not be parsed. Reason: {str(error)}")
        raise error


def divide_csv_daily(file_path: os.PathLike, manifest_id: int, hour_dict: dict):
    """
    Split local file into daily content.
    """
    data_frame = get_data_frame(file_path)

    report_type, _ = utils.detect_type(file_path)
    unique_times = data_frame.interval_start.unique()
    days = list({cur_dt[:10] for cur_dt in unique_times})
    daily_data_frames = [
        {"data_frame": data_frame[data_frame.interval_start.str.contains(cur_day)], "date": cur_day}
        for cur_day in days
    ]

    daily_files = []
    for daily_data in daily_data_frames:
        day = daily_data["date"]
        df = daily_data["data_frame"]
        file_prefix = f"{report_type}.{day}.{manifest_id}"
        with transaction.atomic():
            # With split payloads, we could have a race condition trying to update the `report_tracker`.
            # using a transaction and `select_for_update` should minimize the risk of multiple
            # workers trying to update this field at the same time by locking the manifest during update.
            manifest = CostUsageReportManifest.objects.select_for_update().get(id=manifest_id)
            if not manifest.report_tracker.get(file_prefix):
                manifest.report_tracker[file_prefix] = 0
            counter = manifest.report_tracker[file_prefix]
            manifest.report_tracker[file_prefix] = counter + 1
            manifest.save(update_fields=["report_tracker"])
        day_file = f"{file_prefix}.{counter}.csv"
        day_filepath = file_path.parent.joinpath(day_file)
        df.to_csv(day_filepath, index=False, header=True)
        daily_files.append(
            {
                "filepath": day_filepath,
                "date": datetime.strptime(day, "%Y-%m-%d"),
                "num_hours": hour_dict.get(day) or len(df.interval_start.unique()),
            }
        )
    return daily_files


def create_daily_archives(
    payload_info: utils.PayloadInfo,
    filepath: Path,
    context,
):
    """
    Create daily CSVs from incoming report and archive to S3.

    Args:
        tracing_id (str): The tracing id
        account (str): The account number
        provider_uuid (str): The uuid of a provider
        filepath (PosixPath): The full path name of the file
        manifest_id (int): The manifest identifier
        start_date (Datetime): The start datetime of incoming report
        context (Dict): Logging context dictionary
    """
    manifest = payload_info.manifest
    cur_manifest = CostUsageReportManifest.objects.get(id=manifest.manifest_id)
    daily_file_names = {}
    if cur_manifest.operator_version and not cur_manifest.operator_daily_reports:
        # operator_version and NOT operator_daily_reports is used for payloads received from
        # cost-mgmt-metrics-operators that are not generating daily reports
        # These reports are additive and cannot be split
        daily_files = [{"filepath": filepath, "date": manifest.date, "num_hours": 0}]
    else:
        # we call divide_csv_daily for operators sending daily files
        # or for really old operators (those still relying on metering)
        daily_files = divide_csv_daily(filepath, manifest.manifest_id, manifest.hours_per_day)

    if not daily_files:
        daily_files = [{"filepath": filepath, "date": manifest.date, "num_hours": 0}]

    for daily_file in daily_files:
        # Push to S3
        s3_csv_path = get_path_prefix(
            payload_info.account,
            payload_info.provider_type,
            payload_info.provider_uuid,
            daily_file.get("date"),
            Config.CSV_DATA_TYPE,
        )
        filepath = daily_file.get("filepath")
        copy_local_report_file_to_s3_bucket(
            payload_info.request_id,
            s3_csv_path,
            filepath,
            filepath.name,
            manifest.manifest_id,
            context,
        )
        daily_file_names[filepath] = {
            "meta_reportdatestart": str(daily_file["date"].date()),
            "meta_reportnumhours": str(daily_file["num_hours"]),
        }
    return daily_file_names


def process_cr(manifest: utils.Manifest, context: dict) -> dict:
    """
    Process the manifest info.

    Args:
        report_meta (Dict): The metadata from the manifest

    Returns:
        manifest_info (Dict): Dictionary containing the following:
            airgapped: (Bool or None)
            version: (str or None)
            certified: (Bool or None)
            channel: (str or None)
            errors: (Dict or None)
    """
    LOG.info(log_json(manifest.uuid, msg="processing the manifest", context=context))

    manifest_info = {
        "cluster_id": manifest.cluster_id,
        "operator_certified": manifest.certified,
        "operator_version": manifest.operator_version,
        "cluster_channel": None,
        "operator_airgapped": None,
        "operator_errors": None,
        "operator_daily_reports": manifest.daily_reports,
    }
    if cr_status := manifest.cr_status:
        manifest_info["cluster_channel"] = cr_status.get("clusterVersion")
        manifest_info["operator_airgapped"] = not cr_status.get("upload", {}).get("upload")
        errors = {}
        for case in ["authentication", "packaging", "upload", "prometheus", "source"]:
            if err := cr_status.get(case, {}).get("error"):
                errors[case + "_error"] = err
        manifest_info["operator_errors"] = errors or None

        auth_type = cr_status.get("authentication", {}).get("type")
        if auth_type == "basic":
            LOG.info(log_json(manifest.uuid, msg="cluster is using basic auth", context=context))

    return manifest_info


def create_cost_and_usage_report_manifest(provider_uuid, manifest: utils.Manifest, context: dict) -> int:
    """Prepare to insert or update the manifest DB record."""
    assembly_id = manifest.uuid
    manifest_timestamp = manifest.date

    # old manifests may not have a 'start', so fallback to the
    # datetime when the manifest was created:
    start = manifest.start or manifest_timestamp

    date_range = utils.month_date_range(start)
    billing_str = date_range.split("-")[0]
    billing_start = datetime.strptime(billing_str, "%Y%m%d")

    manifest_dict = {
        "assembly_id": assembly_id,
        "billing_period_start_datetime": billing_start,
        "num_total_files": len(manifest.files),
        "provider_id": provider_uuid,
        "export_datetime": manifest_timestamp,
    }
    cr_info = process_cr(manifest, context)

    try:
        cur_manifest, _ = CostUsageReportManifest.objects.get_or_create(**manifest_dict, **cr_info)
    except IntegrityError:
        cur_manifest = CostUsageReportManifest.objects.get(provider_id=provider_uuid, assembly_id=assembly_id)

    return cur_manifest.id


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


def download_payload(request_id, url, context):
    """
    Download the payload from ingress to temporary location.

        Args:
        request_id (String): Identifier associated with the payload
        url (String): URL path to payload in the Insights upload service..
        context (Dict): Context for logging (account, etc)

        Returns:
        Tuple: temp_file (os.PathLike)
    """
    # Create temporary directory for initial file staging and verification in the
    # OpenShift PVC directory so that any failures can be triaged in the event
    # the pod goes down.
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    temp_dir = tempfile.mkdtemp(dir=Config.DATA_DIR)

    # Download file from quarantine bucket as tar.gz
    try:
        download_response = requests.get(url)
        download_response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        shutil.rmtree(temp_dir)
        msg = f"Unable to download file. Error: {str(err)}"
        LOG.warning(log_json(request_id, msg=msg), exc_info=err)
        raise KafkaMsgHandlerError(msg) from err

    sanitized_request_id = re.sub("[^A-Za-z0-9]+", "", request_id)
    temp_file = Path(temp_dir, sanitized_request_id).with_suffix(".tar.gz")
    try:
        temp_file.write_bytes(download_response.content)
    except OSError as error:
        shutil.rmtree(temp_dir)
        msg = f"Unable to write file. Error: {str(error)}"
        LOG.warning(log_json(request_id, msg=msg, context=context), exc_info=error)
        raise KafkaMsgHandlerError(msg) from error

    return temp_file


def extract_payload_contents(request_id, tarball_path, context):
    """
    Extract the payload contents into a temporary location.

        Args:
        request_id (String): Identifier associated with the payload
        tarball_path (os.PathLike): the path to the payload file to extract
        context (Dict): Context for logging (account, etc)

        Returns:
            (String): path to manifest file
    """
    # Extract tarball into temp directory

    if not os.path.isfile(tarball_path):
        msg = f"Unable to find tar file {tarball_path}."
        LOG.warning(log_json(request_id, msg=msg, context=context))
        raise KafkaMsgHandlerError("Extraction failure, file not found.")

    try:
        mytar = TarFile.open(tarball_path, mode="r:gz")
        mytar.extractall(path=tarball_path.parent)
        files = mytar.getnames()
        manifest_path = [manifest for manifest in files if "manifest.json" in manifest]
    except (ReadError, EOFError, OSError) as error:
        msg = f"Unable to untar file {tarball_path}. Reason: {str(error)}"
        LOG.warning(log_json(request_id, msg=msg, context=context))
        shutil.rmtree(tarball_path.parent)
        raise KafkaMsgHandlerError("Extraction failure.")

    if not manifest_path:
        msg = "No manifest found in payload."
        LOG.warning(log_json(request_id, msg=msg, context=context))
        raise KafkaMsgHandlerError("No manifest found in payload.")

    return manifest_path[0], files


def extract_payload(url, request_id, b64_identity, context):  # noqa: C901
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
    payload_path = download_payload(request_id, url, context)
    manifest_path, payload_files = extract_payload_contents(request_id, payload_path, context)

    # Open manifest.json file and build the payload dictionary.
    full_manifest_path = Path(payload_path.parent, manifest_path)
    manifest = utils.parse_manifest(full_manifest_path.parent)

    context |= {
        "request_id": request_id,
        "cluster_id": manifest.cluster_id,
        "manifest_uuid": manifest.uuid,
    }
    LOG.info(
        log_json(
            request_id,
            msg=f"Payload with the request id {request_id} from cluster {manifest.cluster_id}"
            + f" is part of the report with manifest id {manifest.uuid}",
            context=context,
        )
    )
    source = utils.get_source_and_provider_from_cluster_id(manifest.cluster_id)
    if not source:
        msg = f"Recieved unexpected OCP report from {manifest.cluster_id}"
        LOG.warning(log_json(manifest.uuid, msg=msg, context=context))
        shutil.rmtree(payload_path.parent)
        return None, manifest.uuid
    provider: Provider = source.provider
    schema_name = provider.account.get("schema_name")
    context["provider_type"] = provider.type
    context["schema"] = schema_name

    # set the account and org_id based on the provider if the kafka msg don't contain them
    context["account"] = context["account"] or provider.account.get("account_id")
    context["org_id"] = context["org_id"] or provider.account.get("org_id")

    payload = utils.PayloadInfo(
        request_id=request_id,
        manifest=manifest,
        source_id=source.source_id,
        provider_uuid=provider.uuid,
        provider_type=provider.type,
        cluster_alias=provider.name,
        account=context["account"],
        org_id=context["org_id"],
        schema_name=provider.account.get("schema_name"),
    )

    # Create directory tree for report.
    usage_month = utils.month_date_range(manifest.date)
    destination_dir = Path(Config.INSIGHTS_LOCAL_REPORT_DIR, manifest.cluster_id, usage_month)
    os.makedirs(destination_dir, exist_ok=True)

    # Copy manifest
    manifest_destination_path = Path(destination_dir, full_manifest_path.name)
    shutil.copy(full_manifest_path, manifest_destination_path)

    # Save Manifest
    manifest.manifest_id = create_cost_and_usage_report_manifest(provider.uuid, manifest, context)
    ReportManifestDBAccessor().update_manifest_state(ManifestStep.DOWNLOAD, ManifestState.START, manifest.manifest_id)

    # Copy report payload
    report_metas = []
    manifest_ros_files = manifest.resource_optimization_files
    manifest_files = manifest.files
    ros_reports = [
        (ros_file, payload_path.with_name(ros_file)) for ros_file in manifest_ros_files if ros_file in payload_files
    ]
    ros_processor = ROSReportShipper(payload, b64_identity, context)
    try:
        ros_processor.process_manifest_reports(ros_reports)
    except Exception as e:
        # If a ROS report fails to process, this should not prevent Koku processing from continuing.
        msg = f"ROS reports not processed for payload. Reason: {e}"
        LOG.warning(log_json(manifest.uuid, msg=msg, context=context))
    extra_meta_needed_to_process_reports = {
        "schema_name": schema_name,
        "provider_uuid": provider.uuid,
        "provider_type": provider.type,
    }
    for report_file in manifest_files:
        current_meta = manifest.model_dump() | extra_meta_needed_to_process_reports
        payload_source_path = Path(payload_path.parent, report_file)
        payload_destination_path = Path(destination_dir, report_file)
        try:
            shutil.copy(payload_source_path, payload_destination_path)
            current_meta["current_file"] = payload_destination_path
            record_all_manifest_files(manifest.manifest_id, manifest.files, manifest.uuid)
            if record_report_status(manifest.manifest_id, report_file, manifest.uuid, context):
                # Report already processed
                continue
            msg = f"Successfully extracted OCP for {manifest.cluster_id}/{usage_month}"
            LOG.info(log_json(manifest.uuid, msg=msg, context=context))
            split_files = create_daily_archives(payload, payload_destination_path, context)
            current_meta["split_files"] = list(split_files)
            current_meta["ocp_files_to_process"] = {file.stem: meta for file, meta in split_files.items()}
            report_metas.append(current_meta)
        except FileNotFoundError:
            msg = f"File {str(report_file)} has not downloaded yet."
            LOG.debug(log_json(manifest.uuid, msg=msg, context=context))
    # Remove temporary directory and files
    shutil.rmtree(payload_path.parent)
    ReportManifestDBAccessor().update_manifest_state(ManifestStep.DOWNLOAD, ManifestState.END, manifest.manifest_id)
    return report_metas, manifest.uuid


@KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()
def send_confirmation(request_id, status):  # pragma: no cover
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
    producer = get_producer()
    validation = {"request_id": request_id, "validation": status}
    msg = bytes(json.dumps(validation), "utf-8")
    producer.produce(VALIDATION_TOPIC, value=msg, callback=delivery_callback)
    producer.poll(0)


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


    Args:
        kmsg - Upload Service message containing usage payload information.

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
    value = json.loads(kmsg.value().decode("utf-8"))
    request_id = value.get("request_id", "no_request_id")
    account = value.get("account")
    org_id = value.get("org_id")
    context = {"account": account, "org_id": org_id}
    try:
        msg = f"Extracting Payload for msg: {str(value)}"
        LOG.info(log_json(request_id, msg=msg, context=context))
        report_metas, manifest_uuid = extract_payload(value["url"], request_id, value["b64_identity"], context)
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


def summarize_manifest(report_meta, manifest_uuid):
    """
    Kick off manifest summary when all report files have completed line item processing.

    Args:
        manifest_uuid (string) - The id associated with the payload manifest
        report (Dict) - keys: value
                        schema_name: String,
                        manifest_id: Integer,
                        provider_uuid: String,
                        provider_type: String,

    Returns:
        Celery Async UUID.

    """
    manifest_id = report_meta.get("manifest_id")
    schema = report_meta.get("schema_name")
    start_date = report_meta.get("start")
    end_date = report_meta.get("end")

    context = {
        "provider_uuid": report_meta.get("provider_uuid"),
        "schema": schema,
        "cluster_id": report_meta.get("cluster_id"),
        "start_date": start_date,
        "end_date": end_date,
    }

    ocp_processing_queue = get_customer_queue(schema, OCPQueue)

    if not MANIFEST_ACCESSOR.manifest_ready_for_summary(manifest_id):
        return

    new_report_meta = [
        {
            "schema": schema,
            "schema_name": schema,
            "provider_type": report_meta.get("provider_type"),
            "provider_uuid": report_meta.get("provider_uuid"),
            "manifest_id": manifest_id,
            "manifest_uuid": manifest_uuid,
            "start": start_date,
            "end": end_date,
        }
    ]
    if not (start_date or end_date):
        # we cannot process without start and end dates
        LOG.info(
            log_json(manifest_uuid, msg="missing start or end dates - cannot summarize ocp reports", context=context)
        )
        return

    if "0001-01-01 00:00:00+00:00" not in [str(start_date), str(end_date)]:
        dates = {
            datetime.strptime(meta["meta_reportdatestart"], "%Y-%m-%d").date()
            for meta in report_meta["ocp_files_to_process"].values()
        }
        min_date = min(dates)
        max_date = max(dates)
        # if we cross the month boundary, then we need to create 2 manifests:
        # 1 for each month so that we summarize all the data correctly within the month bounds
        if min_date.month != max_date.month:
            dh = DateHelper()
            new_report_meta[0]["start"] = min_date
            new_report_meta[0]["end"] = dh.month_end(min_date)

            new_report_meta.append(
                {
                    "schema": schema,
                    "schema_name": schema,
                    "provider_type": report_meta.get("provider_type"),
                    "provider_uuid": report_meta.get("provider_uuid"),
                    "manifest_id": manifest_id,
                    "manifest_uuid": manifest_uuid,
                    "start": dh.month_start(max_date),
                    "end": max_date,
                }
            )

        # we have valid dates, so we can summarize the payload
        LOG.info(log_json(manifest_uuid, msg="summarizing ocp reports", context=context))
        return summarize_reports.s(new_report_meta, ocp_processing_queue).apply_async(queue=ocp_processing_queue)

    cr_status = report_meta.get("cr_status", {})
    if data_collection_message := cr_status.get("reports", {}).get("data_collection_message", ""):
        # remove potentially sensitive info from the error message
        msg = f"data collection error [operator]: {re.sub('{[^}]+}', '{***}', data_collection_message)}"
        cr_status["reports"]["data_collection_message"] = msg
        # The full CR status is logged below, but we should limit our alert to just the query.
        # We can check the full manifest to get the full error.
        LOG.error(msg)
        LOG.info(log_json(manifest_uuid, msg=msg, context=context))
    LOG.info(
        log_json(
            manifest_uuid,
            msg="cr status for invalid manifest",
            context=context,
            **cr_status,
        )
    )


def process_report(request_id, report):
    """
    Process line item report.

    Returns True when line item processing is complete.  This is important because
    the listen_for_messages -> process_messages path must have a positive acknowledgement
    that line item processing is complete before committing.

    If the service goes down in the middle of processing (SIGTERM) we do not want a
    stray kafka commit to prematurely commit the message before processing has been
    complete.

    Args:
        request_id (Str): The request id
        report (Dict) - keys: value
                        request_id: String,
                        account: String,
                        schema_name: String,
                        manifest_id: Integer,
                        provider_uuid: String,
                        provider_type: String,
                        current_file: String,
                        date: DateTime

    Returns:
        True if line item report processing is complete.

    """
    schema_name = report.get("schema_name")
    manifest_id = report.get("manifest_id")
    provider_uuid = str(report.get("provider_uuid"))
    provider_type = report.get("provider_type")
    date = report.get("date")

    # The create_table flag is used by the ParquetReportProcessor
    # to create a Hive/Trino table.
    report_dict = {
        "file": report.get("current_file"),
        "split_files": report.get("split_files"),
        "ocp_files_to_process": report.get("ocp_files_to_process"),
        "compression": UNCOMPRESSED,
        "manifest_id": manifest_id,
        "provider_uuid": provider_uuid,
        "request_id": request_id,
        "tracing_id": report.get("uuid"),
        "provider_type": "OCP",
        "start_date": date,
        "create_table": True,
    }
    try:
        return _process_report_file(schema_name, provider_type, report_dict)
    except NotImplementedError as err:
        LOG.info(f"NotImplementedError: {str(err)}")
        return True


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
    return all(report_meta.get("process_complete") for report_meta in report_metas)


def process_messages(msg):
    """
    Process messages and send validation status.

    Processing involves:
    1. Downloading, verifying, extracting, and preparing report files for processing.
    2. Line item processing each report file in the payload (downloaded from step 1).
    3. Check if all reports have been processed for the manifest and if so, kick off
       the celery worker task to summarize.
    4. Send payload validation status to ingress service.

    Args:
        msg (ConsumerRecord) - Message from kafka hccm topic.

    Returns:
        None

    """
    process_complete = False
    status, report_metas, manifest_uuid = handle_message(msg)

    value = json.loads(msg.value().decode("utf-8"))
    request_id = value.get("request_id", "no_request_id")
    tracing_id = manifest_uuid or request_id
    if report_metas:
        for report_meta in report_metas:
            if report_meta.get("daily_reports") and len(report_meta.get("files")) != MANIFEST_ACCESSOR.number_of_files(
                report_meta.get("manifest_id")
            ):
                # we have not received all of the daily files yet, so don't process them
                break
            report_meta["process_complete"] = process_report(request_id, report_meta)
            LOG.info(
                log_json(
                    tracing_id,
                    msg=f"Processing: {report_meta.get('current_file')} complete.",
                    ocp_files_to_process=report_meta.get("ocp_files_to_process"),
                )
            )
        process_complete = report_metas_complete(report_metas)
        if summary_task_id := summarize_manifest(report_meta, tracing_id):
            LOG.info(log_json(tracing_id, msg=f"Summarization celery uuid: {summary_task_id}"))

    if status and not settings.DEBUG:
        if report_metas:
            file_list = [meta.get("current_file") for meta in report_metas]
            files_string = ",".join(map(str, file_list))
            LOG.info(log_json(tracing_id, msg=f"Sending Ingress Service confirmation for: {files_string}"))
        else:
            LOG.info(log_json(tracing_id, msg=f"Sending Ingress Service confirmation for: {value}"))
        send_confirmation(value["request_id"], status)

    return process_complete


def listen_for_messages_loop():
    """Wrap listen_for_messages in while true."""
    kafka_conf = {
        "group.id": "hccm-group",
        "queued.max.messages.kbytes": 1024,
        "enable.auto.commit": False,
        "max.poll.interval.ms": 1080000,  # 18 minutes
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

    Args:
        consumer - (Consumer): kafka consumer for HCCM ingress topic.

    Returns:
        None

    """
    offset = msg.offset()
    partition = msg.partition()
    topic_partition = TopicPartition(topic=UPLOAD_TOPIC, partition=partition, offset=offset)
    try:
        LOG.info(f"Processing message offset: {offset} partition: {partition}")
        service = extract_from_header(msg.headers(), "service")
        LOG.debug(f"service: {service} | {msg.headers()}")
        if service == "hccm":
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
    except ReportProcessorError as error:
        LOG.error(f"[listen_for_messages] Report processing error: {str(error)}")
        LOG.debug(f"COMMITTING: message offset: {offset} partition: {partition}")
        consumer.commit()
    except Exception as error:
        LOG.error(f"[listen_for_messages] UNKNOWN error encountered: {type(error).__name__}: {error}", exc_info=True)


def koku_listener_thread():  # pragma: no cover
    """
    Configure Listener listener thread.

    Returns:
        None

    """
    if is_kafka_connected():  # Check that Kafka is running
        LOG.info("Kafka is running.")

    try:
        listen_for_messages_loop()
    except KeyboardInterrupt:
        exit(0)


def initialize_kafka_handler():  # pragma: no cover
    """
    Start Listener thread.

    Args:
        None

    Returns:
        None

    """
    if Config.KAFKA_CONNECT:
        event_loop_thread = threading.Thread(target=koku_listener_thread)
        event_loop_thread.daemon = True
        event_loop_thread.start()
        event_loop_thread.join()
