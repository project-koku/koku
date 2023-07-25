#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import csv
import json
import logging
import os
import uuid
from tempfile import mkdtemp

from django.conf import settings

from api.common import log_json
from api.iam.models import Customer
from kafka_utils.utils import delivery_callback
from kafka_utils.utils import get_producer
from masu.config import Config as masu_config
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER
from masu.util.aws.common import get_s3_resource

LOG = logging.getLogger(__name__)


class SUBSDataMessenger:
    def __init__(self, context, schema_name, tracing_id):
        self.context = context
        self.tracing_id = tracing_id
        self.schema_name = schema_name
        self.s3_resource = get_s3_resource(
            settings.S3_SUBS_ACCESS_KEY, settings.S3_SUBS_SECRET, settings.S3_SUBS_REGION
        )
        subs_cust = Customer.objects.get(schema_name=schema_name)
        self.account_id = subs_cust.account_id
        self.org_id = subs_cust.org_id
        self.download_path = mkdtemp(prefix="subs")

    def process_and_send_subs_message(self, upload_keys):
        """
        Takes a list of object keys, reads the objects from the S3 bucket and processes a message to kafka.
        """
        for i, obj_key in enumerate(upload_keys):
            csv_path = f"{self.download_path}/subs_{self.tracing_id}_{i}.csv"
            self.s3_resource.Bucket(settings.S3_SUBS_BUCKET_NAME).download_file(obj_key, csv_path)
            with open(csv_path) as csv_file:
                reader = csv.DictReader(csv_file)
                LOG.info(
                    log_json(
                        self.tracing_id,
                        msg="iterating over records and sending kafka messages",
                        context=self.context,
                    )
                )
                msg_count = 0
                for row in reader:
                    # row["subs_product_ids"] is a string of numbers separated by '-' to be sent as a list
                    msg = self.build_subs_msg(
                        row["lineitem_resourceid"],
                        row["lineitem_usageaccountid"],
                        row["lineitem_usagestartdate"],
                        row["lineitem_usageenddate"],
                        row["product_vcpu"],
                        row["subs_sla"],
                        row["subs_usage"],
                        row["subs_role"],
                        row["subs_product_ids"].split("-"),
                    )
                    self.send_kafka_message(msg)
                    msg_count += 1
            LOG.info(
                log_json(
                    self.tracing_id,
                    msg=f"sent {msg_count} kafka messages for subs",
                    context=self.context,
                )
            )
            os.remove(csv_path)

    @KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()
    def send_kafka_message(self, msg):
        """Sends a kafka message to the ROS topic with the S3 keys for the uploaded reports."""
        producer = get_producer()
        producer.produce(masu_config.SUBS_TOPIC, value=msg, callback=delivery_callback)
        producer.poll(0)

    def build_subs_msg(
        self, instance_id, billing_account_id, tstamp, expiration, cpu_count, sla, usage, role, product_ids
    ):
        """Gathers the relevant information for the kafka message and returns the message to be delivered."""
        subs_json = {
            "event_id": str(uuid.uuid4()),
            "event_source": "cost-management",
            "event_type": "Snapshot",
            "account_number": self.account_id,
            "org_id": self.org_id,
            "service_type": "RHEL System",
            "instance_id": instance_id,
            "timestamp": tstamp,
            "expiration": expiration,
            "measurements": [{"value": cpu_count, "uom": "vCPUs"}],
            "cloud_provider": "AWS",
            "hardware_type": "Cloud",
            "product_ids": product_ids,
            "role": role,
            "sla": sla,
            "usage": usage,
            "billing_provider": "aws",
            "billing_account_id": billing_account_id,
        }
        return bytes(json.dumps(subs_json), "utf-8")
