import json
import logging
from functools import cached_property

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError
from django.conf import settings

from api.common import log_json
from api.provider.models import Sources
from api.utils import DateHelper
from kafka_utils.utils import delivery_callback
from kafka_utils.utils import get_producer
from masu.config import Config as masu_config
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER
from masu.util.ocp import common as utils


LOG = logging.getLogger(__name__)


def is_ros_report(file_path):
    """Determine if a specified report is a ROS_METRICS report."""
    _, enum = utils.detect_type(file_path)
    return enum == utils.OCPReportTypes.ROS_METRICS


def get_ros_s3_resource():  # pragma: no cover
    """Obtain the ROS s3 session client"""
    config = Config(connect_timeout=settings.S3_TIMEOUT)
    aws_session = boto3.Session(
        aws_access_key_id=settings.S3_ROS_ACCESS_KEY,
        aws_secret_access_key=settings.S3_ROS_SECRET,
        region_name=settings.S3_REGION,
    )
    s3_resource = aws_session.resource("s3", endpoint_url=settings.S3_ENDPOINT, config=config)
    return s3_resource


class RosReportProcessor:
    def __init__(self, account_id, cluster_id, manifest_id, org_id, provider_uuid, request_id, schema_name):
        self.account_id = account_id
        self.cluster_id = cluster_id
        self.dh = DateHelper()
        self.manifest_id = manifest_id
        self.org_id = org_id
        self.provider_uuid = str(provider_uuid)
        self.request_id = request_id
        self.schema_name = schema_name

    @cached_property
    def ros_s3_path(self):
        """The S3 path to be used for a ROS report upload."""
        return f"{self.schema_name}/source={self.provider_uuid}/{self.dh.today.date()}"

    def process_manifest_reports(self, reports_to_upload):
        """
        Uploads the ROS reports for a manifest to S3 and sends a kafka message containing
        the uploaded reports and relevant information to the hccm.ros.events topic.
        """
        self.mark_reports_as_started(reports_to_upload)
        if not reports_to_upload:
            return
        uploaded_reports = [
            self.copy_local_report_file_to_ros_s3_bucket(filename, report) for filename, report in reports_to_upload
        ]
        self.send_kafka_confirmation(uploaded_reports)
        self.mark_reports_as_completed(reports_to_upload)

    def copy_local_report_file_to_ros_s3_bucket(self, filename, report):
        """Copy a local report file to the ROS S3 bucket."""
        with open(report, "rb") as fin:
            return self.copy_data_to_ros_s3_bucket(filename, fin)

    def copy_data_to_ros_s3_bucket(self, filename, data):
        """Copies report data to the ROS S3 bucket and returns the upload_key"""
        s3_path = self.ros_s3_path
        extra_args = {"Metadata": {"ManifestId": str(self.manifest_id)}}
        upload_key = None
        try:
            s3_resource = get_ros_s3_resource()
            upload_key = f"{s3_path}/{filename}"
            s3_obj = {"bucket_name": settings.S3_ROS_BUCKET_NAME, "key": upload_key}
            upload = s3_resource.Object(**s3_obj)
            upload.upload_fileobj(data, ExtraArgs=extra_args)
        except (EndpointConnectionError, ClientError) as err:
            msg = f"Unable to copy data to {upload_key} in bucket {settings.S3_ROS_BUCKET_NAME}.  Reason: {str(err)}"
            LOG.warning(log_json(self.request_id, msg))
        return upload_key

    @KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()
    def send_kafka_confirmation(self, uploaded_reports):
        """Sends a kafka message to the ROS topic with the S3 keys for the uploaded reports."""
        producer = get_producer()
        msg = self.build_ros_json(uploaded_reports)
        LOG.info(f"Sending Kafka Message for ROS reports. \n{msg}")
        producer.produce(masu_config.ROS_TOPIC, value=msg, callback=delivery_callback)
        # Wait up to 1 second for events. Callbacks will be invoked during
        # this method call if the message is acknowledged.
        # `flush` makes this process synchronous compared to async with `poll`
        producer.flush(1)

    def build_ros_json(self, uploaded_reports):
        """Gathers the relevant information for the kafka message and returns the message to be delivered."""
        source = Sources.objects.get(koku_uuid=self.provider_uuid)

        ros_json = {
            "request_id": self.request_id,
            "b64_identity": source.auth_header,
            "metadata": {
                "account": self.account_id,
                "org_id": self.org_id,
                "source_id": self.provider_uuid,
                "cluster_uuid": self.cluster_id,
                "cluster_alias": source.name,
            },
            "files": uploaded_reports,
        }
        msg = bytes(json.dumps(ros_json), "utf-8")
        return msg

    def mark_reports_as_completed(self, reports_to_upload):
        """Marks all ROS files for the manifest as processed."""
        for file_name, _ in reports_to_upload:
            with ReportStatsDBAccessor(file_name, self.manifest_id) as stats_recorder:
                stats_recorder.log_last_completed_datetime()

    def mark_reports_as_started(self, reports_to_upload):
        """Marks all ROS files for the manifest as processing started."""
        for file_name, _ in reports_to_upload:
            with ReportStatsDBAccessor(file_name, self.manifest_id) as stats_recorder:
                stats_recorder.log_last_started_datetime()
