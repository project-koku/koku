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
from typing import Annotated
from typing import Any
from typing import Literal
from typing import Self

import pandas as pd
from dateutil.relativedelta import relativedelta
from pydantic import AfterValidator
from pydantic import BaseModel
from pydantic import BeforeValidator
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator
from pydantic import UUID4
from pydantic import ValidationError
from pydantic import ValidationInfo

from api.common import log_json
from api.provider.models import Provider
from api.provider.models import Sources
from api.utils import DateHelper as dh
from masu.util.common import trino_table_exists
from masu.util.ocp.operator_versions import OPERATOR_VERSIONS

LOG = logging.getLogger(__name__)


class OCPReportTypes(Enum):
    """Types of OCP report files."""

    UNKNOWN = 0
    CPU_MEM_USAGE = 1
    STORAGE = 2
    NODE_LABELS = 3
    NAMESPACE_LABELS = 4
    VM_USAGE = 5
    GPU_USAGE = 6


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

VM_USAGE_COLUMNS = {
    "report_period_start",
    "report_period_end",
    "interval_start",
    "interval_end",
    "node",
    "namespace",
    "vm_name",
    "resource_id",
    "vm_instance_type",
    "vm_os",
    "vm_guest_os_arch",
    "vm_guest_os_name",
    "vm_guest_os_version",
    "vm_uptime_total_seconds",
    "vm_cpu_limit_cores",
    "vm_cpu_limit_core_seconds",
    "vm_cpu_request_cores",
    "vm_cpu_request_core_seconds",
    "vm_cpu_request_sockets",
    "vm_cpu_request_socket_seconds",
    "vm_cpu_request_threads",
    "vm_cpu_request_thread_seconds",
    "vm_cpu_usage_total_seconds",
    "vm_memory_limit_bytes",
    "vm_memory_limit_byte_seconds",
    "vm_memory_request_bytes",
    "vm_memory_request_byte_seconds",
    "vm_memory_usage_byte_seconds",
    "vm_device",
    "vm_volume_mode",
    "vm_persistentvolumeclaim_name",
    "vm_disk_allocated_size_byte_seconds",
    "vm_labels",
}

VM_GROUP_BY = ["namespace", "node", "vm_name", "vm_labels"]

VM_AGG = {
    "report_period_start": ["max"],
    "report_period_end": ["max"],
    "resource_id": ["max"],
    "vm_instance_type": ["max"],
    "vm_os": ["max"],
    "vm_guest_os_arch": ["max"],
    "vm_guest_os_name": ["max"],
    "vm_guest_os_version": ["max"],
    "vm_uptime_total_seconds": ["sum"],
    "vm_cpu_limit_cores": ["max"],
    "vm_cpu_limit_core_seconds": ["sum"],
    "vm_cpu_request_cores": ["max"],
    "vm_cpu_request_core_seconds": ["sum"],
    "vm_cpu_request_sockets": ["max"],
    "vm_cpu_request_socket_seconds": ["sum"],
    "vm_cpu_request_threads": ["max"],
    "vm_cpu_request_thread_seconds": ["sum"],
    "vm_cpu_usage_total_seconds": ["sum"],
    "vm_memory_limit_bytes": ["max"],
    "vm_memory_limit_byte_seconds": ["sum"],
    "vm_memory_request_bytes": ["max"],
    "vm_memory_request_byte_seconds": ["sum"],
    "vm_memory_usage_byte_seconds": ["sum"],
    "vm_device": ["max"],
    "vm_volume_mode": ["max"],
    "vm_persistentvolumeclaim_name": ["max"],
    "vm_disk_allocated_size_byte_seconds": ["sum"],
}

GPU_USAGE_COLUMNS = {
    "report_period_start",
    "report_period_end",
    "interval_start",
    "interval_end",
    "node",
    "namespace",
    "pod",
    "gpu_uuid",
    "gpu_model_name",
    "gpu_vendor_name",
    "gpu_memory_capacity_mib",
    "gpu_pod_uptime",
}

GPU_GROUP_BY = ["node", "namespace", "pod", "gpu_uuid"]

GPU_AGG = {
    "report_period_start": ["max"],
    "report_period_end": ["max"],
    "gpu_model_name": ["max"],
    "gpu_vendor_name": ["max"],
    "gpu_memory_capacity_mib": ["max"],
    "gpu_pod_uptime": ["sum"],
}

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
    "vm_usage": {
        "columns": VM_USAGE_COLUMNS,
        "enum": OCPReportTypes.VM_USAGE,
        "group_by": VM_GROUP_BY,
        "agg": VM_AGG,
        "new_required_columns": {},
    },
    "gpu_usage": {
        "columns": GPU_USAGE_COLUMNS,
        "enum": OCPReportTypes.GPU_USAGE,
        "group_by": GPU_GROUP_BY,
        "agg": GPU_AGG,
        "new_required_columns": {},
    },
}

# 1,000,000,000,000,000,000 is a reasonable value that should remove most anomalies from bad data
THRESHOLD_MAP = {
    1e18: [
        "pod_usage_cpu_core_seconds",
        "pod_request_cpu_core_seconds",
        "pod_limit_cpu_core_seconds",
        "node_capacity_cpu_core_seconds",
        "pod_usage_memory_byte_seconds",
        "pod_request_memory_byte_seconds",
        "pod_limit_memory_byte_seconds",
        "node_capacity_memory_byte_seconds",
        "node_capacity_memory_bytes",
        "persistentvolumeclaim_capacity_bytes",
        "persistentvolumeclaim_capacity_byte_seconds",
        "volume_request_storage_byte_seconds",
        "persistentvolumeclaim_usage_byte_seconds",
    ],
}
THRESHOLDS = {col: thresh for thresh, cols in THRESHOLD_MAP.items() for col in cols}


ForceAwareDatetime = Annotated[
    datetime,
    AfterValidator(lambda x: x if x.tzinfo else x.replace(tzinfo=UTC)),
]

NoneToList = Annotated[list[str], BeforeValidator(lambda x: [] if x is None else x)]


class Manifest(BaseModel):
    model_config = ConfigDict(validate_default=True, validate_assignment=True)
    uuid: UUID4
    manifest_id: int = 0
    cluster_id: str
    version: str = ""
    operator_version: str = ""
    date: ForceAwareDatetime
    files: NoneToList = []
    resource_optimization_files: NoneToList = []
    start: ForceAwareDatetime | None = None
    end: ForceAwareDatetime | None = None
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
        if not (self.start and self.end):
            return self
        if self.start.month != self.end.month and self.end.day == 1:
            # We override the end date from the first of the next month to the end of current month
            # We do this to prevent summary from triggering unnecessarily on the next month
            self.end = dh().month_end(self.start)
        return self

    def model_post_init(self, context: Any, /) -> None:
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
    account_id: str
    org_id: str
    schema_name: str
    trino_schema: str

    @field_validator("trino_schema", mode="after")
    @classmethod
    def get_trino_schema(cls, value: str) -> str:
        return value.lstrip("acct")


def parse_manifest(report_directory) -> Manifest:
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
    manifest_path = os.path.join(report_directory, "manifest.json")
    json_string = Path(manifest_path).read_text()
    try:
        manifest = Manifest.model_validate_json(json_string)
    except ValidationError as err:
        LOG.error("unable to extract manifest data", exc_info=err)
        raise err
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


def get_source_and_provider_from_cluster_id(cluster_id, org_id):
    """Return the provider given the cluster ID."""
    source = None
    credentials = {"cluster_id": cluster_id}
    if (
        source := Sources.objects.select_related("provider")
        .filter(provider__authentication__credentials=credentials)
        .filter(org_id=org_id)
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
        if value is None:
            continue
        lower_tag = {str(key).lower(): str(value).lower()}
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


class DistributionConfig(BaseModel):
    """Configuration for cost distribution SQL execution.

    Consolidates all metadata needed to execute a distribution:
    - SQL file path
    - Whether to distribute by default (without cost model)
    - Cost model rate type for deletion
    - Query engine type (PostgreSQL vs Trino)
    - Optional required table for Trino queries
    """

    sql_file: str = Field(..., description="SQL file name (without path)")
    cost_model_rate_type: str = Field(..., description="Rate type identifier for cost model")
    distribute_by_default: bool = Field(
        default=False, description="Whether to distribute when no cost model is present"
    )
    requires_full_month: bool = Field(
        default=False, description="Requires a full month of data before distribution can happen."
    )
    query_type: Literal["postgresql", "trino"] = Field(
        default="postgresql", description="Query engine to use for execution"
    )
    required_table: str | None = Field(
        default=None,
        description="Optional Trino table name that must exist before running query. Only valid for Trino queries.",
    )

    class Config:
        frozen = True  # Immutable

    @field_validator("sql_file")
    @classmethod
    def validate_sql_file(cls, v: str) -> str:
        """Ensure SQL file has .sql extension."""
        if not v.endswith(".sql"):
            raise ValueError(f"SQL file must end with .sql, got: {v}")
        return v

    @model_validator(mode="after")
    def validate_required_table(self) -> "DistributionConfig":
        """Ensure required_table is only specified for Trino queries."""
        if self.required_table is not None and self.query_type != "trino":
            raise ValueError(
                f"required_table can only be specified for Trino queries. "
                f"Got query_type='{self.query_type}' with required_table='{self.required_table}'"
            )
        return self

    @property
    def is_trino(self) -> bool:
        """Check if this is a Trino query."""
        return self.query_type == "trino"

    @property
    def is_postgresql(self) -> bool:
        """Check if this is a PostgreSQL query."""
        return self.query_type == "postgresql"

    @property
    def has_table_requirement(self) -> bool:
        """Check if this distribution requires a specific table to exist."""
        return self.required_table is not None

    def get_full_path(self) -> str:
        """Get full path to SQL file relative to masu.database."""
        if self.is_trino:
            from django.conf import settings

            # For Trino queries, use self_hosted_sql in ONPREM mode, otherwise trino_sql
            sql_folder = "self_hosted_sql" if getattr(settings, "ONPREM", False) else "trino_sql"
            base_path = f"{sql_folder}/openshift/cost_model/distribute_cost/"
        else:
            # For PostgreSQL queries, always use sql/
            base_path = "sql/openshift/cost_model/distribute_cost/"
        return f"{base_path}{self.sql_file}"

    def table_exists(self, schema: str) -> bool:
        """Check if the required table exists in the given schema.

        Args:
            schema: The schema name to check for table existence

        Returns:
            True if no required_table is specified or if the table exists.
            False if required_table is specified but doesn't exist.
        """
        if not self.has_table_requirement:
            return True
        return trino_table_exists(schema, self.required_table)
