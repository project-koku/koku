#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
##########################################################################################
# Script to collect cost/usage reports from OCI and replicate them to another bucket
#
# Pre-req's you must have a service account or other for this script to gain access to oci
#
# NOTE! You must update the vars below for this script to work correctly
#
# user: ocid of user that has correct permissions for bucket objects
# key_file: Location of auth file for defind user
# fingerprint: Users fingerprint
# tenancy: Tenancy for collecting/copying cost/usage reports
# region: Home Region of your tenancy
# bucket: Name of Bucket reports will be replicated to
# namespace: Object Storage Namespace
# filename: Name of json file to store last report downloaded default hre is fine
##########################################################################################
import datetime
import io
import json
import logging

import oci
from fdk import response


def connect_oci_storage_client(config):
    # Connect to OCI SDK
    try:
        object_storage = oci.object_storage.ObjectStorageClient(config)
        return object_storage
    except (Exception, ValueError) as ex:
        logging.getLogger().info("Error connecting to OCI SDK CLIENT please check credentials: " + str(ex))


def fetch_reports_file(object_storage, namespace, bucket, filename):
    # Fetch last download report file from bucket
    last_reports_file = None
    try:
        last_reports_file = object_storage.get_object(namespace, bucket, filename)
    except (Exception, ValueError) as ex:
        logging.getLogger().info("Object file does not exist, will attempt to create it: " + str(ex))

    if last_reports_file:
        json_acceptable_string = last_reports_file.data.text.replace("'", '"')
        try:
            last_reports = json.loads(json_acceptable_string)
        except (Exception, ValueError) as ex:
            logging.getLogger().info(
                "Json string file not formatted correctly and cannont be parsed, creating fresh file. " + str(ex)
            )
            last_reports = {"cost": "", "usage": ""}
    else:
        last_reports = {"cost": "", "usage": ""}

    return last_reports


def get_report_list(object_storage, reporting_namespace, reporting_bucket, prefix, last_file):
    # Create a list of cost reports
    report_list = object_storage.list_objects(
        reporting_namespace, reporting_bucket, prefix=prefix, start_after=last_file, fields="timeCreated"
    )
    logging.getLogger().info("Fetching list of cost csv files")
    return report_list


def copy_reports_to_bucket(
    object_storage,
    report_type,
    report_list,
    bucket,
    namespace,
    region,
    reporting_namespace,
    reporting_bucket,
    last_reports,
):
    # Iterate through cost reports list and copy them to new bucket
    # Start from current month
    start_from = datetime.date.today().replace(day=1)

    if report_list.data.objects != []:
        for report in report_list.data.objects:
            if report.time_created.date() > start_from:
                try:
                    copy_object_details = oci.object_storage.models.CopyObjectDetails(
                        destination_bucket=bucket,
                        destination_namespace=namespace,
                        destination_object_name=report.name,
                        destination_region=region,
                        source_object_name=report.name,
                    )
                    object_storage.copy_object(
                        namespace_name=reporting_namespace,
                        bucket_name=reporting_bucket,
                        copy_object_details=copy_object_details,
                    )
                except (Exception, ValueError) as ex:
                    logging.getLogger().info(f"Failed to copy {report.name} to bucket: {bucket}. " + str(ex))
        last_reports[report_type] = report.name
    else:
        logging.getLogger().info(f"No new {report_type} reports to copy to bucket: {bucket}.")
    return last_reports


def handler(ctx, data: io.BytesIO = None):
    name = "OCI-cost-mgmt-report-replication-function"
    try:
        body = json.loads(data.getvalue())
        name = body.get("name")
    except (Exception, ValueError) as ex:
        logging.getLogger().info("Error parsing json payload: " + str(ex))

    logging.getLogger().info("Inside Python OCI reporting copy function")

    # PLEASE CHANGE THIS!!!! #
    user = "ocid1.user.oc1..aaaaaa"  # CHANGEME
    key_file = "auth_files/service-account.pem"  # CHANGEME
    fingerprint = "00.00.00"  # CHANGEME
    tenancy = "ocid1.tenancy.oc1..aaaaaaa"  # CHANGEME
    region = "region"  # CHANGEME
    bucket = "cost-mgmt-bucket"  # CHANGEME
    namespace = "namespace"  # CHANGEME
    filename = "last_reports.json"

    # Get the list of reports
    # https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clienvironmentvariables.htm!!!
    config = {
        "user": user,
        "key_file": key_file,
        "fingerprint": fingerprint,
        "tenancy": tenancy,
        "region": region,
    }
    # The Object Storage namespace used for OCI reports is bling; the bucket name is the tenancy OCID.
    reporting_namespace = "bling"
    reporting_bucket = config["tenancy"]
    region = config["region"]

    # Connect to OCI
    object_storage = connect_oci_storage_client(config)

    # Grab reports json and set previously downloaded file values
    last_reports = fetch_reports_file(object_storage, namespace, bucket, filename)
    last_cost_file = last_reports.get("cost")
    last_usage_file = last_reports.get("usage")

    # Get list of cost/usage files
    cost_report_list = get_report_list(
        object_storage, reporting_namespace, reporting_bucket, "reports/cost-csv", last_cost_file
    )
    usage_report_list = get_report_list(
        object_storage, reporting_namespace, reporting_bucket, "reports/usage-csv", last_usage_file
    )

    # Copy cost/usage files to new bucket
    last_reports = copy_reports_to_bucket(
        object_storage,
        "cost",
        cost_report_list,
        bucket,
        namespace,
        region,
        reporting_namespace,
        reporting_bucket,
        last_reports,
    )
    last_reports = copy_reports_to_bucket(
        object_storage,
        "usage",
        usage_report_list,
        bucket,
        namespace,
        region,
        reporting_namespace,
        reporting_bucket,
        last_reports,
    )

    # Save updated filenames to bucket object as string
    object_storage.put_object(namespace, bucket, filename, str(last_reports))

    return response.Response(
        ctx,
        response_data=json.dumps(
            {
                "message": "Last reports saved from {}, Cost: {}, Usage: {}".format(
                    name, last_reports["cost"], last_reports["usage"]
                )
            }
        ),
        headers={"Content-Type": "application/json"},
    )
