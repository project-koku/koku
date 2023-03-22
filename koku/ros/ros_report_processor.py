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
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.util.ocp import common as utils


LOG = logging.getLogger(__name__)


def is_ros_report(file_path):
    _, enum = utils.detect_type(file_path)
    return enum == utils.OCPReportTypes.ROS_METRICS


def get_ros_s3_resource():  # pragma: no cover
    """
    Obtain the ROS s3 session client
    """
    config = Config(connect_timeout=settings.S3_TIMEOUT)
    aws_session = boto3.Session(
        aws_access_key_id=settings.S3_ROS_ACCESS_KEY,
        aws_secret_access_key=settings.S3_ROS_SECRET,
        region_name=settings.S3_REGION,
    )
    s3_resource = aws_session.resource("s3", endpoint_url=settings.S3_ENDPOINT, config=config)
    return s3_resource


class RosReportProcessor:
    def __init__(self, cluster_id, manifest_id, provider_uuid, request_id, schema_name):
        self.cluster_id = cluster_id
        self.dh = DateHelper()
        self.manifest_id = manifest_id
        self.provider_uuid = str(provider_uuid)
        self.reports_to_upload = []
        self.request_id = request_id
        self.schema_name = schema_name

    @cached_property
    def ros_s3_path(self):
        return f"{self.schema_name}/source={self.provider_uuid}/{self.dh.today.date()}"

    def process_manifest_reports(self):
        if not self.reports_to_upload:
            return
        uploaded_reports = [
            self.copy_local_report_file_to_ros_s3_bucket(filename, report)
            for filename, report in self.reports_to_upload
        ]
        # fire off the kafka message
        self.send_kafka_confirmation(uploaded_reports)

    def add_report_to_manifest(self, filename, report_path):
        self.reports_to_upload.append((filename, report_path))

    def copy_local_report_file_to_ros_s3_bucket(self, filename, report):
        with open(report, "rb") as fin:
            return self.copy_data_to_ros_s3_bucket(filename, fin)

    def copy_data_to_ros_s3_bucket(self, filename, data):
        s3_path = self.ros_s3_path
        extra_args = {"Metadata": {"ManifestId": str(self.manifest_id)}}
        try:
            upload_key = f"{s3_path}/{filename}"
            s3_resource = get_ros_s3_resource()
            s3_obj = {"bucket_name": settings.S3_ROS_BUCKET_NAME, "key": upload_key}
            upload = s3_resource.Object(**s3_obj)
            upload.upload_fileobj(data, ExtraArgs=extra_args)
        except (EndpointConnectionError, ClientError) as err:
            msg = f"Unable to copy data to {upload_key} in bucket {settings.S3_ROS_BUCKET_NAME}.  Reason: {str(err)}"
            LOG.warning(log_json(self.request_id, msg))
        return upload_key

    def send_kafka_confirmation(self, uploaded_reports):
        producer = get_producer()
        msg = self.build_ros_json(uploaded_reports)
        producer.produce(masu_config.ROS_TOPIC, value=msg, callback=delivery_callback)
        # Wait up to 1 second for events. Callbacks will be invoked during
        # this method call if the message is acknowledged.
        # `flush` makes this process synchronous compared to async with `poll`
        producer.flush(1)

    def build_ros_json(self, uploaded_reports):
        source = Sources.objects.get(koku_uuid=self.provider_uuid)
        with ProviderDBAccessor(self.provider_uuid) as provider_accessor:
            account_id = provider_accessor.get_account_id()
            org_id = provider_accessor.get_org_id()

        ros_json = {
            "request_id": self.request_id,
            "b64_identity": source.auth_header,
            "metadata": {
                "account": account_id,
                "org_id": org_id,
                "source_id": self.provider_uuid,
                "cluster_uuid": self.cluster_id,
                "cluster_alias": source.name,
            },
            "files": uploaded_reports,
        }
        msg = bytes(json.dumps(ros_json), "utf-8")
        return msg
