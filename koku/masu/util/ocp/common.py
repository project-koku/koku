#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP utility functions."""
import json
import logging
import os
from datetime import datetime
from datetime import UTC
from decimal import Decimal
from enum import Enum
from math import ceil
from pathlib import Path
from typing import Any
from typing import Self

import pandas as pd
from dateutil.relativedelta import relativedelta
from packaging.version import Version
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import field_validator
from pydantic import model_validator
from pydantic import UUID4
from pydantic import ValidationError
from pydantic import ValidationInfo

from api.common import log_json
from api.provider.models import Provider
from api.provider.models import Sources
from api.utils import DateHelper as dh

LOG = logging.getLogger(__name__)


class OCPReportTypes(Enum):
    """Types of OCP report files."""

    UNKNOWN = 0
    CPU_MEM_USAGE = 1
    STORAGE = 2
    NODE_LABELS = 3
    NAMESPACE_LABELS = 4


OPERATOR_VERSIONS = {
    "8e957a5b174639642809df0317b39593532d6fb7": "costmanagement-metrics-operator:3.3.2",
    "6b4d72a4a629527c1de086b416faf6d226fe587a": "costmanagement-metrics-operator:3.3.1",
    "8c10aa090b2be3d2aea7553ce2cb62e78844ce6f": "costmanagement-metrics-operator:3.3.0",
    "212f944b3b1d7cfbf6e48a63c4ed74bfe942bbe1": "costmanagement-metrics-operator:3.2.1",
    "9d463e92ba69d82513d8ec53edc5242658623840": "costmanagement-metrics-operator:3.2.0",
    "e3ab976307639acff6cc86e25f90f242c45d7210": "costmanagement-metrics-operator:3.1.0",
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
    "1dd2f05c51daa7487ea53b1f3f4894316b1759e1": "koku-metrics-operator:v3.3.2",
    "b0731873d0c54aa1d016b8b3463b29c23c9e852c": "koku-metrics-operator:v3.3.1",
    "1650a9fa9f353efee534dde6030ece40e6a9a1ee": "koku-metrics-operator:v3.3.0",
    "631434d278be57cfedaa5ad0000cb3a3dfb69a76": "koku-metrics-operator:v3.2.1",
    "06f3ed1c48b889f64ecec09e55f0bd7c2f09fe54": "koku-metrics-operator:v3.2.0",
    "b3525a536a402d5bed9b5bbd739fb6a89c8e92e0": "koku-metrics-operator:v3.1.0",
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

STORAGE_COLUMNS = {
    "report_period_start",
    "report_period_end",
    "interval_start",
    "interval_end",
    "namespace",
    "pod",
    "persistentvolumeclaim",
    "persistentvolume",
    "storageclass",
    "persistentvolumeclaim_capacity_bytes",
    "persistentvolumeclaim_capacity_byte_seconds",
    "volume_request_storage_byte_seconds",
    "persistentvolumeclaim_usage_byte_seconds",
    "persistentvolume_labels",
    "persistentvolumeclaim_labels",
}

STORAGE_NEWV_COLUMNS_AND_TYPES = {
    "node": pd.StringDtype(storage="pyarrow"),
    "csi_driver": pd.StringDtype(storage="pyarrow"),
    "csi_volume_handle": pd.StringDtype(storage="pyarrow"),
}

STORAGE_GROUP_BY = [
    "namespace",
    "node",
    "pod",
    "persistentvolumeclaim",
    "persistentvolume",
    "storageclass",
    "csi_driver",
    "csi_volume_handle",
    "persistentvolume_labels",
    "persistentvolumeclaim_labels",
]

STORAGE_AGG = {
    "report_period_start": ["max"],
    "report_period_end": ["max"],
    "persistentvolumeclaim_capacity_bytes": ["max"],
    "persistentvolumeclaim_capacity_byte_seconds": ["sum"],
    "volume_request_storage_byte_seconds": ["sum"],
    "persistentvolumeclaim_usage_byte_seconds": ["sum"],
}

CPU_MEM_USAGE_COLUMNS = {
    "report_period_start",
    "report_period_end",
    "pod",
    "namespace",
    "node",
    "resource_id",
    "interval_start",
    "interval_end",
    "pod_usage_cpu_core_seconds",
    "pod_request_cpu_core_seconds",
    "pod_limit_cpu_core_seconds",
    "pod_usage_memory_byte_seconds",
    "pod_request_memory_byte_seconds",
    "pod_limit_memory_byte_seconds",
    "node_capacity_cpu_cores",
    "node_capacity_cpu_core_seconds",
    "node_capacity_memory_bytes",
    "node_capacity_memory_byte_seconds",
    "pod_labels",
}

CPU_MEM_USAGE_NEWV_COLUMNS_AND_TYPES = {
    "node_role": pd.StringDtype(storage="pyarrow"),
}

POD_GROUP_BY = ["namespace", "node", "pod", "pod_labels"]

POD_AGG = {
    "report_period_start": ["max"],
    "report_period_end": ["max"],
    "resource_id": ["max"],
    "pod_usage_cpu_core_seconds": ["sum"],
    "pod_request_cpu_core_seconds": ["sum"],
    "pod_effective_usage_cpu_core_seconds": ["sum"],
    "pod_limit_cpu_core_seconds": ["sum"],
    "pod_usage_memory_byte_seconds": ["sum"],
    "pod_request_memory_byte_seconds": ["sum"],
    "pod_effective_usage_memory_byte_seconds": ["sum"],
    "pod_limit_memory_byte_seconds": ["sum"],
    "node_capacity_cpu_cores": ["max"],
    "node_capacity_cpu_core_seconds": ["sum"],
    "node_capacity_memory_bytes": ["max"],
    "node_capacity_memory_byte_seconds": ["sum"],
    "node_role": ["max"],
}

NODE_LABEL_COLUMNS = {
    "report_period_start",
    "report_period_end",
    "node",
    "interval_start",
    "interval_end",
    "node_labels",
}

NODE_GROUP_BY = ["node", "node_labels"]

NODE_AGG = {"report_period_start": ["max"], "report_period_end": ["max"]}

NAMESPACE_LABEL_COLUMNS = {
    "report_period_start",
    "report_period_end",
    "interval_start",
    "interval_end",
    "namespace",
    "namespace_labels",
}

NAMESPACE_GROUP_BY = ["namespace", "namespace_labels"]

NAMESPACE_AGG = {"report_period_start": ["max"], "report_period_end": ["max"]}

# new_required_columns are columns that appear in new operator reports.
# today, we cannot guarantee that all reports received will contain all
# of these new columns, so this field is used to add the necessary columns
# to the data frames.
#
# NEWV_COLUMNS_AND_TYPES should be a dict where the keys are the column name and
# the value are the pandas dtypes that column is expected to be.
OCP_REPORT_TYPES = {
    "storage_usage": {
        "columns": STORAGE_COLUMNS,
        "enum": OCPReportTypes.STORAGE,
        "group_by": STORAGE_GROUP_BY,
        "agg": STORAGE_AGG,
        "new_required_columns": STORAGE_NEWV_COLUMNS_AND_TYPES,
    },
    "pod_usage": {
        "columns": CPU_MEM_USAGE_COLUMNS,
        "enum": OCPReportTypes.CPU_MEM_USAGE,
        "group_by": POD_GROUP_BY,
        "agg": POD_AGG,
        "new_required_columns": CPU_MEM_USAGE_NEWV_COLUMNS_AND_TYPES,
    },
    "node_labels": {
        "columns": NODE_LABEL_COLUMNS,
        "enum": OCPReportTypes.NODE_LABELS,
        "group_by": NODE_GROUP_BY,
        "agg": NODE_AGG,
        "new_required_columns": {},
    },
    "namespace_labels": {
        "columns": NAMESPACE_LABEL_COLUMNS,
        "enum": OCPReportTypes.NAMESPACE_LABELS,
        "group_by": NAMESPACE_GROUP_BY,
        "agg": NAMESPACE_AGG,
        "new_required_columns": {},
    },
}


class Manifest(BaseModel):
    model_config = ConfigDict(validate_default=True, validate_assignment=True)
    uuid: UUID4
    manifest_id: int = 0
    cluster_id: str
    version: str = ""
    operator_version: str = ""
    date: datetime
    files: list[str]
    resource_optimization_files: list[str] = []
    start: datetime | None = None
    end: datetime | None = None
    certified: bool = False
    daily_reports: bool = False
    cr_status: dict = {}
    hours_per_day: dict = {}

    @field_validator("operator_version", mode="after")
    @classmethod
    def get_operator_version(cls, value: str, info: ValidationInfo) -> str:
        v = info.data["version"]
        return OPERATOR_VERSIONS.get(v, v)

    @model_validator(mode="after")
    def validate_start_and_end(self) -> Self:
        print(self)
        if not (self.start and self.end):
            return self
        if self.start.month != self.end.month and self.end.day == 1:
            # We override the end date from the first of the next month to the end of current month
            # We do this to prevent summary from triggering unnecessarily on the next month
            self.end = dh().month_end(self.start)
        return self

    def model_post_init(self, context: Any, /) -> None:
        print(self)
        if not (self.start and self.end):
            return
        hours_per_day = {}
        current_date = self.start.date()
        while current_date <= self.end.date():
            start_of_day = datetime.combine(current_date, datetime.min.time(), tzinfo=UTC)
            end_of_day = datetime.combine(current_date + relativedelta(days=1), datetime.min.time(), tzinfo=UTC)
            start = max(self.start, start_of_day)
            end = min(self.end, end_of_day)
            duration = end - start
            hours = duration.total_seconds() / 3600
            hours_per_day[current_date.strftime("%Y-%m-%d")] = ceil(hours)
            current_date += relativedelta(days=1)
        self.hours_per_day = hours_per_day


class PayloadInfo(BaseModel):
    request_id: str
    manifest: Manifest
    source_id: int
    provider_uuid: UUID4
    provider_type: str
    cluster_alias: str
    account: str
    org_id: str
    schema_name: str


def parse_manifest(manifest_path) -> Manifest | None:
    """
    Get OCP usage report details from manifest file.

    Date range is aligned on the first day of the current
    month and ends on the first day of the next month from the
    specified date.

    Args:
        report_directory (String): base directory for report.

    Returns:
        (Dict): keys: value
            "file: String,
             cluster_id: String,
             payload_date: DateTime,
             manifest_path: String,
             uuid: String,
             manifest_path: String",
             start: DateTime,
             end: DateTime

    """
    if not os.path.exists(manifest_path):
        LOG.info(log_json(msg="no manifest available", manifest_path=manifest_path))
        return
    json_string = Path(manifest_path).read_text()
    try:
        manifest = Manifest.model_validate_json(json_string)
    except ValidationError as err:
        LOG.error("unable to extract manifest data", exc_info=err)
        raise err

    """
    try:
        with open(manifest_path) as file:
            payload_dict = json.load(file)
            payload_dict["date"] = parser.parse(payload_dict["date"])
    except (OSError, KeyError) as exc:
        LOG.error("unable to extract manifest data", exc_info=exc)
        return {}

    payload_dict["manifest_path"] = Path(manifest_path)
    # parse start and end dates if in manifest
    if payload_start := payload_dict.get("start"):
        payload_dict["start"] = parser.parse(payload_start)
        if "0001-01-01 00:00:00+00:00" not in payload_start:
            # if we have a valid start date, set the date to the start
            # so that a manifest created at midnight on the first of the month
            # will associate the data with the correct reporting month
            payload_dict["date"] = payload_dict["start"]
    if payload_start and (payload_end := payload_dict.get("end")):
        payload_dict["end"] = parser.parse(payload_end)
        start = datetime.strptime(payload_start[:10], "%Y-%m-%d")
        end = datetime.strptime(payload_end[:10], "%Y-%m-%d")
        # We override the end date from the first of the next month to the end of current month
        # We do this to prevent summary from triggering unnecessarily on the next month
        if start.month != end.month and end.day == 1:
            payload_dict["end"] = dh().month_end(start)
    return payload_dict
    """
    return manifest


def month_date_range(for_date_time):
    """
    Get a formatted date range string for the given date.

    Date range is aligned on the first day of the current
    month and ends on the first day of the next month from the
    specified date.

    Args:
        for_date_time (DateTime): The starting datetime object

    Returns:
        (String): "YYYYMMDD-YYYYMMDD", example: "19701101-19701201"

    """
    start_month = for_date_time.replace(day=1)
    end_month = start_month + relativedelta(months=+1)
    timeformat = "%Y%m%d"
    return f"{start_month.strftime(timeformat)}-{end_month.strftime(timeformat)}"


def get_local_file_name(file_path):
    """
    Return the local file name for a given report path.

    Args:
        file_path (String): report file path from manifest.

    Returns:
        (String): file name for the local file.

    """
    filename = file_path.split("/")[-1]
    date_range = file_path.split("/")[-2]
    local_file_name = f"{date_range}_{filename}"
    return local_file_name


def get_cluster_id_from_provider(provider_uuid):
    """
    Return the cluster ID given a provider UUID.

    Args:
        provider_uuid (String): provider UUID.

    Returns:
        (String): OpenShift Cluster ID

    """
    cluster_id = None
    if provider := Provider.objects.filter(uuid=provider_uuid).first():
        if not provider.authentication:
            LOG.warning(
                f"cannot find cluster-id for provider-uuid: {provider_uuid} because it does not have credentials"
            )
            return cluster_id
        cluster_id = provider.authentication.credentials.get("cluster_id")
        LOG.info(f"found cluster_id: {cluster_id} for provider-uuid: {provider_uuid}")
    return cluster_id


def get_cluster_alias_from_cluster_id(cluster_id):
    """
    Return the cluster alias of a given cluster id.

    Args:
        cluster_id (String): OpenShift Cluster ID

    Returns:
        (String): OpenShift Cluster Alias

    """
    cluster_alias = None
    credentials = {"cluster_id": cluster_id}
    if provider := Provider.objects.filter(authentication__credentials=credentials).first():
        cluster_alias = provider.name
        LOG.info(f"found cluster_alias: {cluster_alias} for cluster-id: {cluster_id}")

    return cluster_alias


def get_source_and_provider_from_cluster_id(cluster_id):
    """Return the provider given the cluster ID."""
    source = None
    credentials = {"cluster_id": cluster_id}
    if (
        source := Sources.objects.select_related("provider")
        .filter(provider__authentication__credentials=credentials)
        .first()
    ):
        context = {"provider_uuid": source.koku_uuid, "cluster_id": cluster_id}
        LOG.info(log_json("", msg="found provider for cluster-id", context=context))
    return source


def detect_type(report_path):
    """
    Detects the OCP report type.
    """
    columns = pd.read_csv(report_path, nrows=0).columns
    for report_type, report_def in OCP_REPORT_TYPES.items():
        report_columns = report_def.get("columns")
        if report_columns.issubset(columns):
            return report_type, report_def.get("enum")
    return None, OCPReportTypes.UNKNOWN


def match_openshift_labels(tag_dict, matched_tags):
    """Match AWS data by OpenShift label associated with OpenShift cluster."""
    tag_dict = json.loads(tag_dict)
    tag_matches = []
    for key, value in tag_dict.items():
        if not value:
            continue
        lower_tag = {key.lower(): value.lower()}
        if lower_tag in matched_tags:
            tag = json.dumps(lower_tag).replace("{", "").replace("}", "")
            tag_matches.append(tag)
    return ",".join(tag_matches)


def get_amortized_monthly_cost_model_rate(monthly_rate, start_date):
    """Given a monthly rate, determine the per-day amortized rate."""
    if monthly_rate is None:
        return None

    days_in_month = dh().days_in_month(start_date)
    return Decimal(monthly_rate) / days_in_month


def get_latest_operator_version():
    """Get s the latest operator version we have released based on OPERATOR_VERSIONS dict"""
    latest_version_num = None
    for version in OPERATOR_VERSIONS.values():
        version_num = version.split(":")[-1]
        version_num = version_num.lstrip("v")
        if latest_version_num is None or Version(version_num) > Version(latest_version_num):
            latest_version_num = version_num
    return latest_version_num
