#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import csv
import json
import logging
import os
import uuid
from collections import defaultdict
from datetime import timedelta
from tempfile import mkdtemp

from dateutil import parser
from django.conf import settings

from api.common import log_json
from api.iam.models import Customer
from api.provider.models import Provider
from kafka_utils.utils import delivery_callback
from kafka_utils.utils import get_producer
from kafka_utils.utils import SUBS_TOPIC
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER
from masu.util.aws.common import get_s3_resource
from providers.azure.client import AzureClientFactory


LOG = logging.getLogger(__name__)


class SUBSDataMessenger:
    def __init__(self, context, schema_name, tracing_id):
        self.provider_type = context["provider_type"].removesuffix("-local")
        # Local azure providers shouldnt attempt to query Azure
        if context["provider_type"] == Provider.PROVIDER_AZURE_LOCAL:
            self.local_prov = True
        else:
            self.local_prov = False
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
        self.instance_map = {}
        self.date_map = defaultdict(list)

    def determine_azure_instance_and_tenant_id(self, row):
        """For Azure we have to query the instance id if its not provided by a tag and the tenant_id."""
        if row["subs_resource_id"] in self.instance_map:
            return self.instance_map.get(row["subs_resource_id"])
        prov = Provider.objects.get(uuid=row["source"])
        credentials = prov.account.get("credentials")
        tenant_id = credentials.get("tenant_id")
        if row["subs_instance"] != "":
            instance_id = row["subs_instance"]
        # attempt to query azure for instance id
        else:
            # if its a local Azure provider, don't query Azure
            if self.local_prov:
                return "", tenant_id
            subscription_id = credentials.get("subscription_id")
            client_id = credentials.get("client_id")
            client_secret = credentials.get("client_secret")
            _factory = AzureClientFactory(subscription_id, tenant_id, client_id, client_secret)
            compute_client = _factory.compute_client
            resource_group = row["resourcegroup"] if row.get("resourcegroup") else row["resourcegroupname"]
            response = compute_client.virtual_machines.get(
                resource_group_name=resource_group,
                vm_name=row["subs_resource_id"],
            )
            instance_id = response.vm_id

        self.instance_map[row["subs_resource_id"]] = (instance_id, tenant_id)
        return instance_id, tenant_id

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
                    if self.provider_type == Provider.PROVIDER_AZURE:
                        msg_count += self.process_azure_row(row)
                    else:
                        # row["subs_product_ids"] is a string of numbers separated by '-' to be sent as a list
                        subs_dict = self.build_aws_subs_dict(
                            row["subs_resource_id"],
                            row["subs_account"],
                            row["subs_start_time"],
                            row["subs_end_time"],
                            row["subs_vcpu"],
                            row["subs_sla"],
                            row["subs_usage"],
                            row["subs_role"],
                            row["subs_product_ids"].split("-"),
                        )
                        msg = bytes(json.dumps(subs_dict), "utf-8")
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
        """Sends a kafka message to the SUBS topic with the S3 keys for the uploaded reports."""
        producer = get_producer()
        producer.produce(SUBS_TOPIC, value=msg, callback=delivery_callback)
        producer.poll(0)

    def build_base_subs_dict(self, instance_id, tstamp, expiration, cpu_count, sla, usage, role, product_ids):
        """Gathers the relevant information for the kafka message and returns a filled dictionary of information."""
        subs_dict = {
            "event_id": str(uuid.uuid4()),
            "event_source": "cost-management",
            "event_type": "snapshot",
            "account_number": self.account_id,
            "org_id": self.org_id,
            "service_type": "RHEL System",
            "instance_id": instance_id,
            "timestamp": tstamp,
            "expiration": expiration,
            "measurements": [{"value": cpu_count, "uom": "vCPUs"}],
            "cloud_provider": self.provider_type,
            "hardware_type": "Cloud",
            "product_ids": product_ids,
            "sla": sla,
            "usage": usage,
            "billing_provider": self.provider_type.lower(),
            "conversion": True,
        }
        # SAP is identified only through product ids and does not have an associated Role
        if role != "SAP":
            subs_dict["role"] = role
        return subs_dict

    def build_aws_subs_dict(
        self, instance_id, billing_account_id, tstamp, expiration, cpu_count, sla, usage, role, product_ids
    ):
        """Adds AWS specific fields to the base subs dict."""
        subs_dict = self.build_base_subs_dict(
            instance_id, tstamp, expiration, cpu_count, sla, usage, role, product_ids
        )
        subs_dict["billing_account_id"] = billing_account_id
        return subs_dict

    def build_azure_subs_dict(
        self, instance_id, billing_account_id, tstamp, expiration, cpu_count, sla, usage, role, product_ids, tenant_id
    ):
        """Adds Azure specific fields to the base subs dict."""
        subs_dict = self.build_base_subs_dict(
            instance_id, tstamp, expiration, cpu_count, sla, usage, role, product_ids
        )
        subs_dict["azure_subscription_id"] = billing_account_id
        subs_dict["azure_tenant_id"] = tenant_id
        return subs_dict

    def process_azure_row(self, row):
        """Process an Azure row into subs kafka messages."""
        msg_count = 0
        # Azure can unexplicably generate strange records with a second entry per day
        # so we track the resource ids we've seen for a specific day so we don't send a record twice
        if self.date_map.get(row["subs_start_time"]) and row["subs_resource_id"] in self.date_map.get(
            row["subs_start_time"]
        ):
            return msg_count
        self.date_map[row["subs_start_time"]].append(row["subs_resource_id"])
        instance_id, tenant_id = self.determine_azure_instance_and_tenant_id(row)
        if not instance_id:
            return msg_count
        # Azure is daily records but subs need hourly records
        start = parser.parse(row["subs_start_time"])
        for i in range(int(row["subs_usage_quantity"])):
            end = start + timedelta(hours=1)
            subs_dict = self.build_azure_subs_dict(
                instance_id,
                row["subs_account"],
                start.isoformat(),
                end.isoformat(),
                row["subs_vcpu"],
                row["subs_sla"],
                row["subs_usage"],
                row["subs_role"],
                row["subs_product_ids"].split("-"),
                tenant_id,
            )
            msg = bytes(json.dumps(subs_dict), "utf-8")
            # move to the next hour in the range
            start = end
            self.send_kafka_message(msg)
            msg_count += 1
        return msg_count
