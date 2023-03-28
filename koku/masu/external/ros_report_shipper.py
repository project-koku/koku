#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json
import logging
from functools import cached_property

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError
from django.conf import settings

from api.common import log_json
from api.utils import DateHelper
from kafka_utils.utils import delivery_callback
from kafka_utils.utils import get_producer
from masu.config import Config as masu_config
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER


LOG = logging.getLogger(__name__)


def get_ros_s3_client():  # pragma: no cover
    """Obtain the ROS s3 session client"""
    config = Config(connect_timeout=settings.S3_TIMEOUT)
    s3_session = boto3.Session(
        aws_access_key_id=settings.S3_ROS_ACCESS_KEY,
        aws_secret_access_key=settings.S3_ROS_SECRET,
        region_name=settings.S3_ROS_REGION,
    )
    return s3_session.client("s3", endpoint_url=settings.S3_ENDPOINT, config=config)


def generate_s3_object_url(client, upload_key):  # pragma: no cover
    return client.generate_presigned_url(
        ClientMethod="get_object", Params={"Bucket": settings.S3_ROS_BUCKET_NAME, "Key": upload_key}, ExpiresIn=172800
    )


class ROSReportShipper:
    def __init__(
        self,
        report_meta,
        b64_identity,
        context,
    ):
        self.account_id = context["account"]
        self.b64_identity = b64_identity
        self.context = context
        self.cluster_id = report_meta["cluster_id"]
        self.manifest_id = report_meta["manifest_id"]
        self.org_id = context["org_id"]
        self.provider_uuid = str(report_meta["provider_uuid"])
        self.request_id = report_meta["request_id"]
        self.schema_name = report_meta["schema_name"]
        self.s3_client = get_ros_s3_client()
        self.dh = DateHelper()

    @cached_property
    def ros_s3_path(self):
        """The S3 path to be used for a ROS report upload."""
        return f"{self.schema_name}/source={self.provider_uuid}/date={self.dh.today.date()}"

    def process_manifest_reports(self, reports_to_upload):
        """
        Uploads the ROS reports for a manifest to S3 and sends a kafka message containing
        the uploaded reports and relevant information to the hccm.ros.events topic.
        """
        if not reports_to_upload:
            msg = f"No ROS reports to handle for manifest: {self.manifest_id}."
            LOG.info(log_json(self.request_id, msg, self.context))
            return
        msg = f"Preparing to upload ROS reports to S3 bucket for manifest: {self.manifest_id}."
        LOG.info(log_json(self.request_id, msg, self.context))
        uploaded_reports = []
        for filename, report in reports_to_upload:
            if uploaded_report := self.copy_local_report_file_to_ros_s3_bucket(filename, report):
                uploaded_reports.append(uploaded_report)
        if not uploaded_reports:
            msg = f"ROS reports did not upload cleanly to S3 for manifest: {self.manifest_id}, skipping kafka message."
            LOG.info(log_json(self.request_id, msg, self.context))
            return
        kafka_msg = self.build_ros_msg(uploaded_reports)
        msg = f"{len(uploaded_reports)} reports uploaded to S3 for ROS, sending kafka message."
        LOG.info(log_json(self.request_id, msg, self.context))
        self.send_kafka_message(kafka_msg)

    def copy_local_report_file_to_ros_s3_bucket(self, filename, report):
        """Copy a local report file to the ROS S3 bucket."""
        with open(report, "rb") as fin:
            return self.copy_data_to_ros_s3_bucket(filename, fin)

    def copy_data_to_ros_s3_bucket(self, filename, data):
        """Copies report data to the ROS S3 bucket and returns the upload_key"""
        s3_path = self.ros_s3_path
        extra_args = {"Metadata": {"ManifestId": str(self.manifest_id)}}
        try:
            upload_key = f"{s3_path}/{filename}"
            self.s3_client.upload_fileobj(data, settings.S3_ROS_BUCKET_NAME, upload_key, ExtraArgs=extra_args)
            uploaded_obj_url = generate_s3_object_url(self.s3_client, upload_key)
        except (EndpointConnectionError, ClientError) as err:
            msg = f"Unable to copy data to {upload_key} in bucket {settings.S3_ROS_BUCKET_NAME}.  Reason: {str(err)}"
            LOG.warning(log_json(self.request_id, msg))
            return
        return uploaded_obj_url

    @KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()
    def send_kafka_message(self, msg):
        """Sends a kafka message to the ROS topic with the S3 keys for the uploaded reports."""
        producer = get_producer()
        producer.produce(masu_config.ROS_TOPIC, value=msg, callback=delivery_callback)
        # Wait up to 1 second for events. Callbacks will be invoked during
        # this method call if the message is acknowledged.
        # `flush` makes this process synchronous compared to async with `poll`
        producer.flush(1)

    def build_ros_msg(self, uploaded_reports):
        """Gathers the relevant information for the kafka message and returns the message to be delivered."""
        with ProviderDBAccessor(self.provider_uuid) as provider_accessor:
            cluster_alias = provider_accessor.get_provider_name()
        ros_json = {
            "request_id": self.request_id,
            "b64_identity": self.b64_identity,
            "metadata": {
                "account": self.account_id,
                "org_id": self.org_id,
                "source_id": self.provider_uuid,
                "cluster_uuid": self.cluster_id,
                "cluster_alias": cluster_alias,
            },
            "files": uploaded_reports,
        }
        return bytes(json.dumps(ros_json), "utf-8")
