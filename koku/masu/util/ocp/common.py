#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP utility functions."""
import json
import logging
import os
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from typing import Union

import pandas as pd
from dateutil import parser
from dateutil.relativedelta import relativedelta

from api.common import log_json
from api.models import Provider
from api.utils import DateHelper as dh
from masu.config import Config
from masu.database.provider_auth_db_accessor import ProviderAuthDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor

LOG = logging.getLogger(__name__)


class OCPReportTypes(Enum):
    """Types of OCP report files."""

    UNKNOWN = 0
    CPU_MEM_USAGE = 1
    STORAGE = 2
    NODE_LABELS = 3
    NAMESPACE_LABELS = 4


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

STORAGE_GROUP_BY = [
    "namespace",
    "pod",
    "persistentvolumeclaim",
    "persistentvolume",
    "storageclass",
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

CPU_MEM_USAGE_NEWV_COLUMNS = {
    "node_role",
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
OCP_REPORT_TYPES = {
    "storage_usage": {
        "columns": STORAGE_COLUMNS,
        "enum": OCPReportTypes.STORAGE,
        "group_by": STORAGE_GROUP_BY,
        "agg": STORAGE_AGG,
        "new_required_columns": [],
    },
    "pod_usage": {
        "columns": CPU_MEM_USAGE_COLUMNS,
        "enum": OCPReportTypes.CPU_MEM_USAGE,
        "group_by": POD_GROUP_BY,
        "agg": POD_AGG,
        "new_required_columns": CPU_MEM_USAGE_NEWV_COLUMNS,
    },
    "node_labels": {
        "columns": NODE_LABEL_COLUMNS,
        "enum": OCPReportTypes.NODE_LABELS,
        "group_by": NODE_GROUP_BY,
        "agg": NODE_AGG,
        "new_required_columns": [],
    },
    "namespace_labels": {
        "columns": NAMESPACE_LABEL_COLUMNS,
        "enum": OCPReportTypes.NAMESPACE_LABELS,
        "group_by": NAMESPACE_GROUP_BY,
        "agg": NAMESPACE_AGG,
        "new_required_columns": [],
    },
}


@dataclass
class ReportDetails:
    uuid: str
    cluster_id: str
    request_id: str

    tracing_id: str = ""
    version: str = ""
    usage_month: str = ""
    files: list[str] = field(default_factory=list)
    resource_optimization_files: list[str] = field(default_factory=list)

    cr_status: dict[str, Any] = field(default_factory=dict)
    certified: bool = False
    daily_reports: bool = False
    manifest_path: str = ""

    # post_init variables
    # these are converted to datetimes in post_init:
    date: Union[str, datetime] = ""
    start: Union[str, datetime] = ""
    end: Union[str, datetime] = ""

    destination_dir: str = ""
    manifest_destination_path: str = ""
    provider_uuid: str = ""

    # these are added after the ReportDetails is created
    provider_type: str = ""
    schema: str = ""
    account: str = ""
    org_id: str = ""
    manifest_id: int = 0
    current_file: str = ""
    process_complete: bool = False

    def __post_init__(self):
        self.tracing_id = self.uuid
        self.date = parser.parse(self.date)
        self.usage_month = month_date_range(self.date)
        if payload_start := self.start:
            self.start = parser.parse(self.start)
        if payload_end := self.end and payload_start:
            start = datetime.strptime(payload_start[:10], "%Y-%m-%d")
            end = datetime.strptime(payload_end[:10], "%Y-%m-%d")
            # We override the end date from the first of the next month to the end of current month
            # We do this to prevent summary from triggering unnecessarily on the next month
            if start.month != end.month and end.day == 1:
                payload_end = dh().month_end(start)
            self.end = parser.parse(payload_end)

        self.destination_dir = f"{Config.INSIGHTS_LOCAL_REPORT_DIR}/{self.cluster_id}"
        self.manifest_destination_path = f"{self.destination_dir}/{os.path.basename(self.manifest_path)}"
        self.provider_uuid = get_provider_uuid_from_cluster_id(self.cluster_id)

        if self.files is None:
            self.files = []
        if self.resource_optimization_files is None:
            self.resource_optimization_files = []


class ManifestNotFound(Exception):
    pass


def get_report_details(report_directory, request_id) -> ReportDetails:
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
    manifest_path = f"{report_directory}/manifest.json"

    if not os.path.exists(manifest_path):
        msg = f"no manifest available at {manifest_path}"
        LOG.info(msg)
        raise ManifestNotFound(msg)

    with open(manifest_path) as file:
        payload_dict = json.load(file)

    return ReportDetails(request_id=request_id, manifest_path=manifest_path, **payload_dict)


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
    with ProviderDBAccessor(provider_uuid) as provider_accessor:
        provider_type = provider_accessor.get_type()

    if provider_type not in (Provider.PROVIDER_OCP,):
        err_msg = f"Provider UUID is not an OpenShift type.  It is {provider_type}"
        LOG.warning(err_msg)
        return cluster_id

    with ProviderDBAccessor(provider_uuid=provider_uuid) as provider_accessor:
        credentials = provider_accessor.get_credentials()
        if credentials:
            cluster_id = credentials.get("cluster_id")

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
    auth_id = None
    credentials = {"cluster_id": cluster_id}
    with ProviderAuthDBAccessor(credentials=credentials) as auth_accessor:
        auth_id = auth_accessor.get_auth_id()
        if auth_id:
            with ProviderDBAccessor(auth_id=auth_id) as provider_accessor:
                cluster_alias = provider_accessor.get_provider_name()
    return cluster_alias


def get_provider_uuid_from_cluster_id(cluster_id):
    """
    Return the provider UUID given the cluster ID.

    Args:
        cluster_id (String): OpenShift Cluster ID

    Returns:
        (String): provider UUID

    """
    provider_uuid = None
    credentials = {"cluster_id": cluster_id}
    if provider := Provider.objects.filter(authentication__credentials=credentials).first():
        provider_uuid = str(provider.uuid)
        LOG.info(
            log_json(
                msg="found provider for cluster",
                provider_uuid=provider_uuid,
                cluster_id=cluster_id,
                schema=provider.customer.schema_name,
            )
        )

    return provider_uuid


def poll_ingest_override_for_provider(provider_uuid):
    """
    Return whether or not the OpenShift provider should be treated like a POLLING provider.

    The purpose of this is to continue to support back-door (no upload service) OpenShift
    report ingest.  Used for development and local test automation.

    On the masu-worker if the insights local directory exists for the given provider then
    the masu orchestrator will treat it as a polling provider rather than listening.

    Args:
        provider_uuid (String): Provider UUID.

    Returns:
        (Boolean): True: OCP provider should be treated like a polling provider.

    """
    cluster_id = get_cluster_id_from_provider(provider_uuid)
    local_ingest_path = f"{Config.INSIGHTS_LOCAL_REPORT_DIR}/{str(cluster_id)}"
    return os.path.exists(local_ingest_path)


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
