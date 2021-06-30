#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP utility functions."""
import copy
import json
import logging
import os
from enum import Enum

import ciso8601
import pandas as pd
from dateutil import parser
from dateutil.relativedelta import relativedelta

from api.models import Provider
from masu.config import Config
from masu.database.provider_auth_db_accessor import ProviderAuthDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.util.common import safe_float

LOG = logging.getLogger(__name__)


class OCPReportTypes(Enum):
    """Types of OCP report files."""

    UNKNOWN = 0
    CPU_MEM_USAGE = 1
    STORAGE = 2
    NODE_LABELS = 3
    NAMESPACE_LABELS = 4


STORAGE_COLUMNS = [
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
]

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

CPU_MEM_USAGE_COLUMNS = [
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
]

POD_GROUP_BY = ["namespace", "node", "pod", "pod_labels"]

POD_AGG = {
    "report_period_start": ["max"],
    "report_period_end": ["max"],
    "resource_id": ["max"],
    "pod_usage_cpu_core_seconds": ["sum"],
    "pod_request_cpu_core_seconds": ["sum"],
    "pod_limit_cpu_core_seconds": ["sum"],
    "pod_usage_memory_byte_seconds": ["sum"],
    "pod_request_memory_byte_seconds": ["sum"],
    "pod_limit_memory_byte_seconds": ["sum"],
    "node_capacity_cpu_cores": ["max"],
    "node_capacity_cpu_core_seconds": ["sum"],
    "node_capacity_memory_bytes": ["max"],
    "node_capacity_memory_byte_seconds": ["sum"],
}

NODE_LABEL_COLUMNS = [
    "report_period_start",
    "report_period_end",
    "node",
    "interval_start",
    "interval_end",
    "node_labels",
]

NODE_GROUP_BY = ["node", "node_labels"]

NODE_AGG = {"report_period_start": ["max"], "report_period_end": ["max"]}


NAMESPACE_LABEL_COLUMNS = [
    "report_period_start",
    "report_period_end",
    "interval_start",
    "interval_end",
    "namespace",
    "namespace_labels",
]

NAMESPACE_GROUP_BY = ["namespace", "namespace_labels"]

NAMESPACE_AGG = {"report_period_start": ["max"], "report_period_end": ["max"]}

REPORT_TYPES = {
    "storage_usage": {
        "columns": STORAGE_COLUMNS,
        "enum": OCPReportTypes.STORAGE,
        "group_by": STORAGE_GROUP_BY,
        "agg": STORAGE_AGG,
    },
    "pod_usage": {
        "columns": CPU_MEM_USAGE_COLUMNS,
        "enum": OCPReportTypes.CPU_MEM_USAGE,
        "group_by": POD_GROUP_BY,
        "agg": POD_AGG,
    },
    "node_labels": {
        "columns": NODE_LABEL_COLUMNS,
        "enum": OCPReportTypes.NODE_LABELS,
        "group_by": NODE_GROUP_BY,
        "agg": NODE_AGG,
    },
    "namespace_labels": {
        "columns": NAMESPACE_LABEL_COLUMNS,
        "enum": OCPReportTypes.NAMESPACE_LABELS,
        "group_by": NAMESPACE_GROUP_BY,
        "agg": NAMESPACE_AGG,
    },
}


def get_report_details(report_directory):
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
    manifest_path = "{}/{}".format(report_directory, "manifest.json")

    payload_dict = {}
    try:
        with open(manifest_path) as file:
            payload_dict = json.load(file)
            payload_dict["date"] = parser.parse(payload_dict["date"])
            payload_dict["manifest_path"] = manifest_path
            # parse start and end dates if in manifest
            for field in ["start", "end"]:
                if payload_dict.get(field):
                    payload_dict[field] = parser.parse(payload_dict[field])
    except (OSError, IOError, KeyError) as exc:
        LOG.error("Unable to extract manifest data: %s", exc)

    return payload_dict


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
    return "{}-{}".format(start_month.strftime(timeformat), end_month.strftime(timeformat))


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
    provider = Provider.objects.filter(authentication__credentials=credentials).first()
    if provider:
        provider_uuid = str(provider.uuid)
        LOG.info(f"Found provider: {str(provider_uuid)} for Cluster ID: {str(cluster_id)}")

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
    local_ingest_path = "{}/{}".format(Config.INSIGHTS_LOCAL_REPORT_DIR, str(cluster_id))
    return os.path.exists(local_ingest_path)


def detect_type(report_path):
    """
    Detects the OCP report type.
    """
    sorted_columns = sorted(pd.read_csv(report_path, nrows=0).columns)
    for report_type, report_def in REPORT_TYPES.items():
        report_columns = sorted(report_def.get("columns"))
        report_enum = report_def.get("enum")
        if report_columns == sorted_columns:
            return report_type, report_enum
    return None, OCPReportTypes.UNKNOWN


def process_openshift_datetime(val):
    """
    Convert the date time from the Metering operator reports to a consumable datetime.
    """
    result = None
    try:
        datetime_str = str(val).replace(" +0000 UTC", "")
        result = ciso8601.parse_datetime(datetime_str)
    except parser.ParserError:
        pass
    return result


def process_openshift_labels(label_string):
    """Convert the report string to a JSON dictionary.

    Args:
        label_string (str): The raw report string of pod labels

    Returns:
        (dict): The JSON dictionary made from the label string

    """
    labels = label_string.split("|") if label_string else []
    label_dict = {}

    for label in labels:
        try:
            key, value = label.split(":")
            key = key.replace("label_", "")
            label_dict[key] = value
        except ValueError as err:
            LOG.warning(err)
            LOG.warning("%s could not be properly split", label)
            continue

    return label_dict


def process_openshift_labels_to_json(label_val):
    return json.dumps(process_openshift_labels(label_val))


def get_column_converters():
    """Return source specific parquet column converters."""
    return {
        "report_period_start": process_openshift_datetime,
        "report_period_end": process_openshift_datetime,
        "interval_start": process_openshift_datetime,
        "interval_end": process_openshift_datetime,
        "pod_usage_cpu_core_seconds": safe_float,
        "pod_request_cpu_core_seconds": safe_float,
        "pod_limit_cpu_core_seconds": safe_float,
        "pod_usage_memory_byte_seconds": safe_float,
        "pod_request_memory_byte_seconds": safe_float,
        "pod_limit_memory_byte_seconds": safe_float,
        "node_capacity_cpu_cores": safe_float,
        "node_capacity_cpu_core_seconds": safe_float,
        "node_capacity_memory_bytes": safe_float,
        "node_capacity_memory_byte_seconds": safe_float,
        "persistentvolumeclaim_capacity_bytes": safe_float,
        "persistentvolumeclaim_capacity_byte_seconds": safe_float,
        "volume_request_storage_byte_seconds": safe_float,
        "persistentvolumeclaim_usage_byte_seconds": safe_float,
        "pod_labels": process_openshift_labels_to_json,
        "persistentvolume_labels": process_openshift_labels_to_json,
        "persistentvolumeclaim_labels": process_openshift_labels_to_json,
        "node_labels": process_openshift_labels_to_json,
        "namespace_labels": process_openshift_labels_to_json,
    }


def ocp_generate_daily_data(data_frame, report_type):
    """Given a dataframe, group the data to create daily data."""
    # usage_start = data_frame["lineitem_usagestartdate"]
    # usage_start_dates = usage_start.apply(lambda row: row.date())
    # data_frame["usage_start"] = usage_start_dates
    if data_frame.empty:
        return data_frame
    group_bys = copy.deepcopy(REPORT_TYPES.get(report_type, {}).get("group_by", []))
    group_bys.append(pd.Grouper(key="interval_start", freq="D"))
    aggs = copy.deepcopy(REPORT_TYPES.get(report_type, {}).get("agg", {}))
    daily_data_frame = data_frame.groupby(group_bys, dropna=False).agg(aggs)

    columns = daily_data_frame.columns.droplevel(1)
    daily_data_frame.columns = columns

    daily_data_frame.reset_index(inplace=True)

    return daily_data_frame


def match_openshift_labels(tag_dict, matched_tags, cluster_topology):
    """Match AWS data by OpenShift label associated with OpenShift cluster."""
    tag_dict = json.loads(tag_dict)
    cluster_id = cluster_topology.get("cluster_id").lower()
    cluster_alias = cluster_topology.get("cluster_alias").lower()
    nodes = [node.lower() for node in cluster_topology.get("nodes", [])]
    projects = [project.lower() for project in cluster_topology.get("projects", [])]
    tag_matches = []
    for key, value in tag_dict.items():
        tag = json.dumps({key.lower(): value.lower()}).replace("{", "").replace("}", "")
        if {key.lower(): value.lower()} in matched_tags:
            tag_matches.append(tag)
        elif key.lower() == "openshift_project" and value.lower() in projects:
            return tag
        elif key.lower() == "openshift_node" and value.lower() in nodes:
            return tag
        elif key.lower() == "openshift_cluster" and value.lower() in (cluster_id, cluster_alias):
            return tag
    return ",".join(tag_matches)
