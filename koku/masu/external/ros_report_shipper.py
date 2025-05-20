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
from kafka_utils.utils import ROS_TOPIC
from koku.feature_flags import UNLEASH_CLIENT
from masu.config import Config as masu_config
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER
from masu.util.ocp import common as utils

LOG = logging.getLogger(__name__)


def get_ros_s3_client():  # pragma: no cover
    """Obtain the ROS s3 session client"""
    config = Config(connect_timeout=settings.S3_TIMEOUT)
    s3_session = boto3.Session(
        aws_access_key_id=settings.S3_ROS_ACCESS_KEY,
        aws_secret_access_key=settings.S3_ROS_SECRET,
        region_name=settings.S3_ROS_REGION,
    )
    return s3_session.client("s3", endpoint_url=settings.S3_ROS_ENDPOINT, config=config)


def generate_s3_object_url(client, upload_key):  # pragma: no cover
    """Generate an accessible URL for an S3 object with an expiration time of 48 hours"""
    return client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": settings.S3_ROS_BUCKET_NAME, "Key": upload_key},
        ExpiresIn=masu_config.ROS_URL_EXPIRATION,
    )


class ROSReportShipper:
    """Class to handle ROS reports from an operator payload and ship them to S3."""

    def __init__(
        self,
        payload_info: utils.PayloadInfo,
        b64_identity: str,
        context: dict,
    ):
        self.b64_identity = b64_identity
        self.manifest_id = payload_info.manifest.manifest_id
        self.context = context | {"manifest_id": self.manifest_id}
        self.source_id = str(payload_info.source_id)
        self.provider_uuid = str(payload_info.provider_uuid)
        self.cluster_alias = payload_info.cluster_alias
        self.request_id = payload_info.request_id
        self.schema_name = payload_info.schema_name

        self.metadata = {
            "account": payload_info.account_id,
            "org_id": payload_info.org_id,
            "source_id": self.source_id,
            "provider_uuid": self.provider_uuid,
            "cluster_uuid": payload_info.manifest.cluster_id,
            "operator_version": payload_info.manifest.operator_version,
        }
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
            msg = "No ROS reports to handle in the current payload."
            LOG.info(log_json(self.request_id, msg=msg, context=self.context))
            return
        msg = "Preparing to upload ROS reports to S3 bucket."
        LOG.info(log_json(self.request_id, msg=msg, context=self.context))
        report_urls = []
        upload_keys = []
        for filename, report in reports_to_upload:
            if upload_tuple := self.copy_local_report_file_to_ros_s3_bucket(filename, report):
                report_urls.append(upload_tuple[0])
                upload_keys.append(upload_tuple[1])
        if not report_urls:
            msg = "ROS reports did not upload cleanly to S3, skipping kafka message."
            LOG.info(log_json(self.request_id, msg=msg, context=self.context))
            return

        if (
            not UNLEASH_CLIENT.is_enabled("cost-management.backend.ros-data-processing", self.context)
            and not settings.ENABLE_ROS_DEBUG
        ):
            msg = "ROS report handling gated by unleash - not sending kafka msg"
            LOG.info(log_json(self.request_id, msg=msg, context=self.context))
            return

        kafka_msg = self.build_ros_msg(report_urls, upload_keys)
        msg = f"{len(report_urls)} reports uploaded to S3 for ROS, sending kafka message."
        LOG.info(log_json(self.request_id, msg=msg, context=self.context))
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
            LOG.warning(log_json(self.request_id, msg=msg))
            return
        return uploaded_obj_url, upload_key

    @KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()
    def send_kafka_message(self, msg):
        """Sends a kafka message to the ROS topic with the S3 keys for the uploaded reports."""
        producer = get_producer()
        producer.produce(ROS_TOPIC, value=msg, callback=delivery_callback)
        producer.poll(0)

    def build_ros_msg(self, presigned_urls, upload_keys):
        """Gathers the relevant information for the kafka message and returns the message to be delivered."""
        ros_json = {
            "request_id": self.request_id,
            "b64_identity": self.b64_identity,
            "metadata": self.metadata | {"cluster_alias": self.cluster_alias},
            "files": presigned_urls,
            "object_keys": upload_keys,
        }
        return bytes(json.dumps(ros_json), "utf-8")
