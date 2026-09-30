#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Turn a stored OCP ingress tarball into line items.

This is the slow path: extract the archive, write daily CSVs, update manifest
records, and run report processing. With ingress staging enabled, the listener
does not call this module. The ingress worker does, after the raw tarball is
durable.

The listener still imports this module when INGRESS_STAGING_LISTENER_FLAG is
off. This file and ``process_staged`` can be combined once
``legacy_message_processing`` is removed.
"""
import hashlib
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from tarfile import FilterError
from tarfile import ReadError
from tarfile import TarFile

import pandas as pd
from django.db import IntegrityError

import masu.util.ocp.ocp_data_validator  # noqa: F401
from api.common import log_json
from api.iam.models import Customer
from api.provider.models import Provider
from api.settings.utils import get_data_retention_months
from api.utils import DateHelper
from common.queues import get_customer_queue
from common.queues import OCPQueue
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.downloader.ocp.download import read_manifest_from_tarball
from masu.external.downloader.ocp.exceptions import KafkaMsgHandlerError
from masu.external.ros_report_shipper import ROSReportShipper
from masu.processor import CROSS_ORG_CLUSTER_LOOKUP_FLAG
from masu.processor import is_feature_flag_enabled_by_schema
from masu.processor._tasks.process import _process_report_file
from masu.processor.tasks import record_all_manifest_files
from masu.processor.tasks import record_report_status
from masu.processor.tasks import summarize_reports
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.common import get_path_prefix
from masu.util.ocp import common as utils
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus
from reporting_common.states import CombinedChoices
from reporting_common.states import ManifestState
from reporting_common.states import ManifestStep

LOG = logging.getLogger(__name__)
_DAY_SLICE_DIGEST_LENGTH = 12
MANIFEST_ACCESSOR = ReportManifestDBAccessor()


class EmptyPayloadFileError(pd.errors.EmptyDataError):
    """Empty payload file error."""


def get_data_frame(file_path: os.PathLike):
    """Read CSV into dataframe, validate/sanitize for SQLi/XSS, and write back to file."""
    try:
        df = pd.read_csv(file_path, dtype=pd.StringDtype(storage="pyarrow"), on_bad_lines="warn")

        df, issues = df.ocp.validate_and_sanitize()

        if issues:
            LOG.warning(
                log_json(
                    msg="Validation issues found in payload - data has been sanitized",
                    file=str(file_path),
                    issue_count=len(issues),
                )
            )

        # Write sanitized data back for S3 upload
        df.to_csv(file_path, index=False, header=True)
        return df
    except pd.errors.EmptyDataError as error:
        LOG.warning(f"File {file_path} is empty.")
        raise EmptyPayloadFileError("File is empty.") from error
    except Exception as error:
        LOG.error(f"File {file_path} could not be parsed. Reason: {str(error)}")
        raise error


def _day_slice_csv_name(report_type: str, day: str, manifest_id: int, data_frame: pd.DataFrame) -> tuple[str, str]:
    """Return a stable day-slice filename and the CSV text it names.

    The digest is a hash of that slice's CSV bytes. An identical replay writes the
    same object key. Different slices do not share a name, so the manifest
    ``report_tracker`` counter and its row lock are not needed.
    """
    csv_text = data_frame.to_csv(index=False, header=True)
    digest = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()[:_DAY_SLICE_DIGEST_LENGTH]
    return f"{report_type}.{day}.{manifest_id}.{digest}.csv", csv_text


def divide_csv_daily(file_path: os.PathLike, manifest_id: int, hour_dict: dict, data_frame: pd.DataFrame = None):
    """Split local file into daily content.

    Args:
        file_path: Path to the CSV file.
        manifest_id: The manifest ID for tracking.
        hour_dict: Dictionary mapping dates to hour counts.
        data_frame: Optional pre-loaded and validated DataFrame.
                   If not provided, the file will be read and validated.
    """
    if data_frame is None:
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
        day_file, csv_text = _day_slice_csv_name(report_type, day, manifest_id, df)
        day_filepath = file_path.parent.joinpath(day_file)
        day_filepath.write_text(csv_text)
        daily_files.append(
            {
                "filepath": day_filepath,
                "date": datetime.strptime(day, "%Y-%m-%d"),
                "num_hours": hour_dict.get(day) or len(df.interval_start.unique()),
            }
        )
    return daily_files


def create_daily_archives(payload_info: utils.PayloadInfo, filepath: Path, context):
    """Create daily CSVs from incoming report and archive to S3."""
    manifest = payload_info.manifest
    cur_manifest = CostUsageReportManifest.objects.get(id=manifest.manifest_id)

    # Validate/sanitize data before any branching
    data_frame = get_data_frame(filepath)
    daily_file_names = {}
    if cur_manifest.operator_version and not cur_manifest.operator_daily_reports:
        # operator_version and NOT operator_daily_reports is used for payloads received from
        # cost-mgmt-metrics-operators that are not generating daily reports
        # These reports are additive and cannot be split
        daily_files = [{"filepath": filepath, "date": manifest.date, "num_hours": 0}]
    else:
        # we call divide_csv_daily for operators sending daily files
        # or for really old operators (those still relying on metering)
        # Pass the already-validated DataFrame to avoid re-reading and re-validating
        daily_files = divide_csv_daily(filepath, manifest.manifest_id, manifest.hours_per_day, data_frame)

    if not daily_files:
        # Fallback: use the original file (already sanitized by get_data_frame)
        daily_files = [{"filepath": filepath, "date": manifest.date, "num_hours": 0}]

    for daily_file in daily_files:
        # Push to S3
        s3_csv_path = get_path_prefix(
            payload_info.trino_schema,
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
            "s3_key": f"{s3_csv_path}/{filepath.name}" if s3_csv_path else None,
        }
    return daily_file_names


def process_cr(manifest: utils.Manifest, context: dict) -> dict:
    """Process the manifest cr-status info."""
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


def extract_tarball_to_directory(request_id, tarball_path, context) -> list[str]:
    """Extract tarball members into the tarball parent directory using PEP 706 data filter."""
    try:
        with TarFile.open(tarball_path, mode="r:gz") as mytar:
            mytar.extractall(path=tarball_path.parent, filter="data")
            return mytar.getnames()
    except (ReadError, EOFError, OSError, FilterError) as error:
        msg = f"Unable to untar file {tarball_path}. Reason: {str(error)}"
        LOG.warning(log_json(request_id, msg=msg, context=context))
        raise KafkaMsgHandlerError("Extraction failure.") from error


def extract_payload_contents(request_id, tarball_path, context):
    """Extract the payload contents into a temporary location."""
    payload_files = extract_tarball_to_directory(request_id, tarball_path, context)
    try:
        manifest_path = utils.get_manifest_member_name(payload_files)
    except ValueError as error:
        msg = "No manifest found in payload."
        LOG.warning(log_json(request_id, msg=msg, context=context))
        raise KafkaMsgHandlerError("No manifest found in payload.") from error

    return manifest_path, payload_files


def extract_payload(payload_path, request_id, b64_identity, context):  # noqa: C901
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

    Once the files are downloaded:
    1. manifest.json is read and validated from the archive before any files are extracted.
    2. Provider account is retrieved for the cluster id.  If no account is found we return.
    3. Archive members are extracted using the tarfile data filter (PEP 706).
    4. Manifest database record is created which will establish the assembly_id and number of files
    5. Report stats database record is created and is used as a filter to determine if the file
       has already been processed.
    6. All report files that have not been processed will have the local path to that report file
       added to the report_meta context dictionary for that file.
    7. Report file context dictionaries that require processing is added to a list which will be
       passed to the report processor.  All context from report_meta is used by the processor.
    """
    manifest = read_manifest_from_tarball(request_id, payload_path, context)
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
    org_id = context["org_id"]
    source = utils.get_source_and_provider_from_cluster_id(manifest.cluster_id, org_id=org_id)
    if not source:
        schema_name_for_flag = Customer.objects.filter(org_id=org_id).values_list("schema_name", flat=True).first()
        if schema_name_for_flag and is_feature_flag_enabled_by_schema(
            schema_name_for_flag, CROSS_ORG_CLUSTER_LOOKUP_FLAG
        ):
            source = utils.get_source_and_provider_from_cluster_id(
                manifest.cluster_id, org_id=org_id, skip_org_id_filter=True
            )
            if source:
                LOG.warning(
                    log_json(
                        manifest.uuid,
                        msg="cross-org cluster lookup bypass used",
                        context={
                            **context,
                            "requesting_org_id": org_id,
                            "source_org_id": source.org_id,
                            "cluster_id": manifest.cluster_id,
                            "provider_uuid": str(source.koku_uuid),
                        },
                    )
                )
    if not source:
        msg = f"Received unexpected OCP report from {manifest.cluster_id}"
        LOG.warning(log_json(manifest.uuid, msg=msg, context=context))
        return None, manifest.uuid

    provider: Provider = source.provider
    schema_name: str = provider.account.get("schema_name")
    context["provider_type"] = provider.type
    context["schema"] = schema_name
    context["account"] = context["account"] or provider.account.get("account_id") or "no_account"

    retention = get_data_retention_months(schema_name) or Config.MASU_RETAIN_NUM_MONTHS
    dh = DateHelper()
    manifest_end = manifest.end or dh.month_end(manifest.date)
    if manifest_end < dh.relative_month_end(-retention):
        msg = f"Received OCP data outside our retention period for {manifest.cluster_id}, skipping processing"
        LOG.warning(log_json(manifest.uuid, msg=msg, context=context))
        return None, manifest.uuid

    payload_files = extract_tarball_to_directory(request_id, payload_path, context)
    manifest_path = utils.get_manifest_member_name(payload_files)
    full_manifest_path = utils.resolve_path_within_base(payload_path.parent, manifest_path)

    payload = utils.PayloadInfo(
        request_id=request_id,
        manifest=manifest,
        source_id=source.source_id,
        provider_uuid=provider.uuid,
        provider_type=provider.type,
        cluster_alias=provider.name,
        account_id=context["account"],
        org_id=context["org_id"],
        schema_name=schema_name,
        trino_schema=schema_name,
    )

    # Create directory tree for report.
    usage_month = utils.month_date_range(manifest.date)
    destination_dir = utils.resolve_path_within_base(
        Config.INSIGHTS_LOCAL_REPORT_DIR, manifest.cluster_id, usage_month
    )
    os.makedirs(destination_dir, exist_ok=True)

    # Copy manifest
    manifest_destination_path = destination_dir / full_manifest_path.name
    shutil.copy(full_manifest_path, manifest_destination_path)

    # Save Manifest
    manifest.manifest_id = create_cost_and_usage_report_manifest(provider.uuid, manifest, context)
    ReportManifestDBAccessor().update_manifest_state(ManifestStep.DOWNLOAD, ManifestState.START, manifest.manifest_id)

    # Copy report payload
    report_metas = []
    manifest_ros_files = manifest.resource_optimization_files
    manifest_files = manifest.files
    ros_reports = [
        (ros_file, utils.resolve_path_within_base(payload_path.parent, ros_file))
        for ros_file in manifest_ros_files
        if ros_file in payload_files
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
    record_all_manifest_files(manifest.manifest_id, manifest.files, manifest.uuid)
    for report_file in manifest_files:
        current_meta = manifest.model_dump() | extra_meta_needed_to_process_reports
        payload_source_path = utils.resolve_path_within_base(payload_path.parent, report_file)
        payload_destination_path = utils.resolve_path_within_base(destination_dir, report_file)
        try:
            shutil.copy(payload_source_path, payload_destination_path)
            current_meta["current_file"] = payload_destination_path
            if record_report_status(manifest.manifest_id, report_file, manifest.uuid, context):
                # Report already processed
                continue
            msg = f"Successfully extracted OCP for {manifest.cluster_id}/{usage_month}"
            LOG.info(log_json(manifest.uuid, msg=msg, context=context))
            split_files = create_daily_archives(payload, payload_destination_path, context)
            current_meta["split_files"] = list(split_files)
            current_meta["ocp_files_to_process"] = {file.stem: meta for file, meta in split_files.items()}
            report_metas.append(current_meta)
        except EmptyPayloadFileError:
            CostUsageReportStatus.objects.get(report_name=report_file, manifest_id=manifest.manifest_id).update_status(
                CombinedChoices.DONE
            )
            current_meta["process_complete"] = True
            report_metas.append(current_meta)
            msg = f"File {str(report_file)} is empty."
            LOG.warning(log_json(manifest.uuid, msg=msg, context=context))
        except FileNotFoundError:
            msg = f"File {str(report_file)} has not downloaded yet."
            LOG.debug(log_json(manifest.uuid, msg=msg, context=context))
    ReportManifestDBAccessor().update_manifest_state(ManifestStep.DOWNLOAD, ManifestState.END, manifest.manifest_id)
    return report_metas, manifest.uuid


def summarize_manifest(report_meta, manifest_uuid):
    """Kick off manifest summary when all report files have completed line item processing."""
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
    """
    return all(report_meta.get("process_complete") for report_meta in report_metas)


def process_extracted_reports(request_id, report_metas, tracing_id):
    """Run line-item processing for an extracted tarball and maybe enqueue summarization.

    Returns True when every report meta is marked process_complete. Files already
    marked complete are not processed again.
    """
    if not report_metas:
        return False
    valid_report_meta = None
    for report_meta in report_metas:
        if report_meta.get("daily_reports") and len(report_meta.get("files")) != MANIFEST_ACCESSOR.number_of_files(
            report_meta.get("manifest_id")
        ):
            # we have not received all of the daily files yet, so don't process them
            break
        if report_meta.get("process_complete"):
            # probably an empty file, so skip it
            continue
        report_meta["process_complete"] = process_report(request_id, report_meta)
        LOG.info(
            log_json(
                tracing_id,
                msg=f"Processing: {report_meta.get('current_file')} complete.",
                ocp_files_to_process=report_meta.get("ocp_files_to_process"),
            )
        )
        # Keep track of a valid report_meta for summarization
        if valid_report_meta is None:
            valid_report_meta = report_meta
    process_complete = report_metas_complete(report_metas)
    # Use valid_report_meta if available, otherwise fall back to the last report_meta
    report_meta = valid_report_meta or report_meta
    if summary_task_id := summarize_manifest(report_meta, tracing_id):
        LOG.info(log_json(tracing_id, msg=f"Summarization celery uuid: {summary_task_id}"))
    return process_complete
