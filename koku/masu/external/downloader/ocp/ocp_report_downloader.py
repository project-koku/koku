#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Report Downloader."""
import logging
import os
from datetime import datetime

import pandas as pd
from django.db import IntegrityError
from django.db import transaction

from api.common import log_json
from api.provider.models import Provider
from masu.config import Config
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.common import get_path_prefix
from masu.util.ocp import common as utils
from reporting_common.models import CostUsageReportManifest

DATA_DIR = Config.TMP_DIR
REPORTS_DIR = Config.INSIGHTS_LOCAL_REPORT_DIR

LOG = logging.getLogger(__name__)

OPERATOR_VERSIONS = {
    "b5a2c05255069215eb564dcc5c4ec6ca4b33325d": "costmanagement-metrics-operator:3.0.1",
    "47ddcdbbdf3e445536ea3fa8346df0dac3adc3ed": "costmanagement-metrics-operator:3.0.0",
    "5806b175a7b31e6ee112c798fa4222cc652b40a6": "costmanagement-metrics-operator:2.0.0",
    "e3450f6e3422b6c39c582028ec4ce19b8d09d57d": "costmanagement-metrics-operator:1.2.0",
    "61099eb07331b140cf66104bc1056c3f3211c94e": "costmanagement-metrics-operator:1.1.9",
    "6d38c76be52e5981eaf19377a559dc681f1be405": "costmanagement-metrics-operator:1.1.8",
    "0159d5e55ce6a5a18f989e6f04146f47983ebdf3": "costmanagement-metrics-operator:1.1.7",
    "2a702a3aac89f724a08b08650b77a0bd33f5b5e5": "costmanagement-metrics-operator:1.1.6",
    "f8d1f7c5d8685f758ecc36a14aca3b6b86614613": "costmanagement-metrics-operator:1.1.5",
    "77ec351f8d332796dc522e5623f1200c2fab4042": "costmanagement-metrics-operator:1.1.4",
    "084bca2e1c48caab18c237453c17ceef61747fe2": "costmanagement-metrics-operator:1.1.3",
    "6f10d07e3af3ea4f073d4ffda9019d8855f52e7f": "costmanagement-metrics-operator:1.1.0",
    "fd764dcd7e9b993025f3e05f7cd674bb32fad3be": "costmanagement-metrics-operator:1.0.0",
    "8737fb075bdbd63c02e82e6f89056380e9c1e6b6": "koku-metrics-operator:v3.0.1",
    "3a6df53f18e574286a1666e1d26586dc729f0568": "koku-metrics-operator:v3.0.0",
    "26502d500672019af5c11319b558dec873409e38": "koku-metrics-operator:v2.0.0",
    "2acd43ccec2d6fe6ec292aece951b3cf0b869071": "koku-metrics-operator:v1.2.0",
    "ebe8dab6aebfeacf9a3428d66cc8be7da682c2ad": "koku-metrics-operator:v1.1.9",
    "ccc78b4fd4b63a6cb1516574d5e38a9b1078ea16": "koku-metrics-operator:v1.1.8",
    "2003f0ea23efc49b7ba1337a16b1c90c6899824b": "koku-metrics-operator:v1.1.7",
    "45cc7a72ced124a267acf0976d90504f134e1076": "koku-metrics-operator:v1.1.6",
    "2c52da1481d0c90099e130f6989416cdd3cd7b5a": "koku-metrics-operator:v1.1.5",
    "12b9463a9501f8e9acecbfa4f7e7ae7509d559fa": "koku-metrics-operator:v1.1.4",
    "3430d17b8ad52ee912fc816da6ed31378fd28367": "koku-metrics-operator:v1.1.3",
    "02f315aa5a7f0bf5adecd3668b0a769799b54be8": "koku-metrics-operator:v1.1.2",
    "7c413e966e2ec0a709f5a25cbf5a487c646306d1": "koku-metrics-operator:v1.1.1",
    "f73a992e7b2fc19028b31c7fb87963ae19bba251": "koku-metrics-operator:v0.9.8",
    "d37e6d6fd90d65b0d6794347f5fe00a472ce9d33": "koku-metrics-operator:v0.9.7",
    "1019682a6aa1eeb7533724b07d98cfb54dbe0e94": "koku-metrics-operator:v0.9.6",
    "513e7dffddb6ecc090b9e8f20a2fba2fe8ec6053": "koku-metrics-operator:v0.9.5",
    "eaef8ea323b3531fa9513970078a55758afea665": "koku-metrics-operator:v0.9.4",
    "4f1cc5580da20a11e6dfba50d04d8ae50f2e5fa5": "koku-metrics-operator:v0.9.2",
    "0419bb957f5cdfade31e26c0f03b755528ec0d7f": "koku-metrics-operator:v0.9.1",
    "bfdc1e54e104c2a6c8bf830ab135cf56a97f41d2": "koku-metrics-operator:v0.9.0",
}


def divide_csv_daily(file_path: os.PathLike, manifest_id: int):
    """
    Split local file into daily content.
    """
    daily_files = []

    try:
        data_frame = pd.read_csv(file_path)
    except Exception as error:
        LOG.error(f"File {file_path} could not be parsed. Reason: {str(error)}")
        raise error

    report_type, _ = utils.detect_type(file_path)
    unique_times = data_frame.interval_start.unique()
    days = list({cur_dt[:10] for cur_dt in unique_times})
    daily_data_frames = [
        {"data_frame": data_frame[data_frame.interval_start.str.contains(cur_day)], "date": cur_day}
        for cur_day in days
    ]

    for daily_data in daily_data_frames:
        day = daily_data.get("date")
        df = daily_data.get("data_frame")
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
                "num_hours": len(df.interval_start.unique()),
            }
        )
    return daily_files


def create_daily_archives(tracing_id, account, provider_uuid, filepath, manifest_id, start_date, context={}):
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
    manifest = CostUsageReportManifest.objects.get(id=manifest_id)
    daily_file_names = {}
    if manifest.operator_version and not manifest.operator_daily_reports:
        # operator_version and NOT operator_daily_reports is used for payloads received from
        # cost-mgmt-metrics-operators that are not generating daily reports
        # These reports are additive and cannot be split
        daily_files = [{"filepath": filepath, "date": start_date, "num_hours": 0}]
    else:
        # we call divide_csv_daily for really old operators (those still relying on metering)
        # or for operators sending daily files
        daily_files = divide_csv_daily(filepath, manifest.id)

    if not daily_files:
        daily_files = [{"filepath": filepath, "date": start_date, "num_hours": 0}]

    for daily_file in daily_files:
        # Push to S3
        s3_csv_path = get_path_prefix(
            account, Provider.PROVIDER_OCP, provider_uuid, daily_file.get("date"), Config.CSV_DATA_TYPE
        )
        filepath = daily_file.get("filepath")
        copy_local_report_file_to_s3_bucket(
            tracing_id,
            s3_csv_path,
            filepath,
            filepath.name,
            manifest_id,
            context,
        )
        daily_file_names[filepath] = {
            "meta_reportdatestart": str(daily_file["date"].date()),
            "meta_reportnumhours": str(daily_file["num_hours"]),
        }
    return daily_file_names


def process_cr(report_meta):
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
    LOG.info(log_json(report_meta.get("tracing_id"), msg="Processing the manifest"))

    version = report_meta.get("version")
    manifest_info = {
        "cluster_id": report_meta.get("cluster_id"),
        "operator_certified": report_meta.get("certified"),
        "operator_version": OPERATOR_VERSIONS.get(
            version, version  # if version is not defined in OPERATOR_VERSIONS, fallback to what is in the report-meta
        ),
        "cluster_channel": None,
        "operator_airgapped": None,
        "operator_errors": None,
        "operator_daily_reports": report_meta.get("daily_reports", False),
    }
    if cr_status := report_meta.get("cr_status"):
        manifest_info["cluster_channel"] = cr_status.get("clusterVersion")
        manifest_info["operator_airgapped"] = not cr_status.get("upload", {}).get("upload")
        errors = {}
        for case in ["authentication", "packaging", "upload", "prometheus", "source"]:
            if err := cr_status.get(case, {}).get("error"):
                errors[case + "_error"] = err
        manifest_info["operator_errors"] = errors or None

    return manifest_info


def create_cost_and_usage_report_manifest(provider_uuid, manifest):
    """Prepare to insert or update the manifest DB record."""
    assembly_id = manifest.get("uuid")
    manifest_timestamp = manifest.get("date")

    start = (
        manifest.get("start") or manifest_timestamp
    )  # old manifests may not have a 'start', so fallback to the datetime when the manifest was created  # noqa: E501
    date_range = utils.month_date_range(start)
    billing_str = date_range.split("-")[0]
    billing_start = datetime.strptime(billing_str, "%Y%m%d")

    manifest_dict = {
        "assembly_id": assembly_id,
        "billing_period_start_datetime": billing_start,
        "num_total_files": len(manifest.get("files") or []),
        "provider_uuid": provider_uuid,
        "manifest_modified_datetime": manifest_timestamp,
    }
    cr_info = process_cr(manifest)

    try:
        manifest, _ = CostUsageReportManifest.objects.get_or_create(**manifest_dict, **cr_info)
    except IntegrityError:
        manifest = CostUsageReportManifest.objects.get(provider_id=provider_uuid, assembly_id=assembly_id)

    return manifest.id
