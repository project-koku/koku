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
from django.db.models import F
from django_tenants.utils import schema_context

from api.common import log_json
from api.iam.models import Customer
from api.provider.models import Provider
from kafka_utils.utils import delivery_callback
from kafka_utils.utils import get_producer
from kafka_utils.utils import SUBS_TOPIC
from masu.prometheus_stats import KAFKA_CONNECTION_ERRORS_COUNTER
from masu.prometheus_stats import RHEL_ELS_SYSTEMS_PROCESSED
from masu.prometheus_stats import RHEL_ELS_VCPU_HOURS
from masu.util.aws.common import get_s3_resource
from reporting.models import SubsLastProcessed

LOG = logging.getLogger(__name__)

HPC_ROLE = "Red Hat Enterprise Linux Compute Node"
SAP_ROLE = "SAP"
RHEL_7 = "69"
RHEL_8 = "479"
ELS = "204"
RHEL_7_HPC_ID = "76"
RHEL_7_SAP_ID = "146"
RHEL_8_HPC_ID = "479"
RHEL_8_SAP_ID = "241"


class SUBSDataMessenger:
    def __init__(self, context, schema_name, tracing_id):
        self.provider_type = context["provider_type"].removesuffix("-local")
        self.context = context
        self.tracing_id = tracing_id
        self.schema_name = schema_name
        self.s3_resource = get_s3_resource(
            access_key=settings.S3_SUBS_ACCESS_KEY,
            secret_key=settings.S3_SUBS_SECRET,
            region=settings.S3_SUBS_REGION,
            endpoint_url=settings.S3_SUBS_ENDPOINT,
        )
        subs_cust = Customer.objects.get(schema_name=schema_name)
        self.account_id = subs_cust.account_id
        self.org_id = subs_cust.org_id
        self.download_path = mkdtemp(prefix="subs")
        self.instance_map = {}
        self.date_map = defaultdict(dict)
        self.resources_event_sent = set()

    def mark_last_processed_sent(self):
        """
        Update the last processed table to include the timestamp the
        resource was sent to the Subscription team.
        """
        if not self.resources_event_sent:
            return
        with schema_context(self.schema_name):
            # If the sent timestamp ever stops being updated
            # it is more helpful for us to know the last processed time
            # that was sent. We could recreate events
            # based off that information.
            SubsLastProcessed.objects.filter(resource_id__in=self.resources_event_sent).update(
                latest_event_sent=F("latest_processed_time")
            )

    def determine_azure_instance_and_tenant_id(self, row, instance_key):
        """Build the instance id string and get the tenant for Azure."""

        if instance_key in self.instance_map:
            return self.instance_map.get(instance_key)
        prov = Provider.objects.get(uuid=row["source"])
        credentials = prov.account.get("credentials")
        tenant_id = credentials.get("tenant_id")
        if row["subs_instance"] != "":
            instance_id = row["subs_instance"]
        else:
            instance_id = instance_key
        self.instance_map[instance_key] = (instance_id, tenant_id)
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
                            row["subs_rhel_version"],
                            row["subs_sla"],
                            row["subs_usage"],
                            row["subs_role"],
                            row["subs_conversion"],
                            row["subs_addon_id"],
                        )
                        self.send_kafka_message(subs_dict)
                        msg_count += 1
                        RHEL_ELS_SYSTEMS_PROCESSED.labels(provider_type=Provider.PROVIDER_AWS).inc()
                        try:
                            RHEL_ELS_VCPU_HOURS.labels(provider_type=Provider.PROVIDER_AWS).inc(
                                amount=float(row["subs_vcpu"])
                            )
                        except ValueError:
                            LOG.info(
                                log_json(
                                    self.tracing_id,
                                    msg=f"vCPU amount could not be cast to a float {row['subs_vcpu']}",
                                    context=self.context,
                                )
                            )
            LOG.info(
                log_json(
                    self.tracing_id,
                    msg=f"sent {msg_count} kafka messages for subs",
                    context=self.context,
                )
            )
            os.remove(csv_path)
        self.mark_last_processed_sent()

    @KAFKA_CONNECTION_ERRORS_COUNTER.count_exceptions()
    def send_kafka_message(self, subs_dict):
        """Sends a kafka message to the SUBS topic with the S3 keys for the uploaded reports."""
        if instance_id := subs_dict.get("instance_id"):
            self.resources_event_sent.add(instance_id)
            msg = bytes(json.dumps(subs_dict), "utf-8")
            producer = get_producer()
            producer.produce(SUBS_TOPIC, key=self.org_id, value=msg, callback=delivery_callback)
            producer.poll(0)
        else:
            LOG.info("Message not sent missing instance id for subs.")

    def build_base_subs_dict(
        self, instance_id, tstamp, expiration, cpu_count, version, sla, usage, role, conversion, addon
    ):
        """Gathers the relevant information for the kafka message and returns a filled dictionary of information."""
        product_ids = self.determine_product_ids(version, addon, role)
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
            "measurements": [{"value": cpu_count, "metric_id": "vCPUs"}],
            "cloud_provider": self.provider_type,
            "hardware_type": "Cloud",
            "product_ids": product_ids,
            "sla": sla,
            "usage": usage,
            "billing_provider": self.provider_type.lower(),
        }
        if conversion == "true":
            subs_dict["conversion"] = True
        else:
            subs_dict["conversion"] = False
        # SAP is identified only through product ids and does not have an associated Role
        if role != SAP_ROLE:
            subs_dict["role"] = role
        return subs_dict

    def build_aws_subs_dict(
        self,
        instance_id,
        billing_account_id,
        tstamp,
        expiration,
        cpu_count,
        version,
        sla,
        usage,
        role,
        conversion,
        addon,
    ):
        """Adds AWS specific fields to the base subs dict."""
        subs_dict = self.build_base_subs_dict(
            instance_id, tstamp, expiration, cpu_count, version, sla, usage, role, conversion, addon
        )
        subs_dict["billing_account_id"] = billing_account_id
        return subs_dict

    def build_azure_subs_dict(
        self,
        instance_id,
        billing_account_id,
        tstamp,
        expiration,
        cpu_count,
        version,
        sla,
        usage,
        role,
        conversion,
        addon,
        tenant_id,
        vm_name,
    ):
        """Adds Azure specific fields to the base subs dict."""
        subs_dict = self.build_base_subs_dict(
            instance_id, tstamp, expiration, cpu_count, version, sla, usage, role, conversion, addon
        )
        subs_dict["azure_subscription_id"] = billing_account_id
        subs_dict["azure_tenant_id"] = tenant_id
        subs_dict["display_name"] = vm_name
        return subs_dict

    def process_azure_row(self, row):
        """Process an Azure row into subs kafka messages."""
        msg_count = 0
        # Azure can unexplicably generate strange records with a second entry per day
        # these two values should sum to the total usage so we need to track what was already
        # sent for a specific instance so we get the full usage amount
        range_start = 0
        start_time = row["subs_start_time"]
        usage = int(row["subs_usage_quantity"])
        sub_id = row["subs_account"]
        rg = row["resourcegroup"]
        vm = row["subs_vmname"]
        instance_key = f"{sub_id}:{rg}:{vm}"
        if self.date_map.get(start_time):
            range_start = self.date_map.get(start_time).get(instance_key) or 0
        self.date_map[start_time] = {instance_key: usage + range_start}
        instance_id, tenant_id = self.determine_azure_instance_and_tenant_id(row, instance_key)
        if not instance_id:
            return msg_count
        # Azure is daily records but subs need hourly records
        start = parser.parse(start_time)
        # if data for the day was previously sent, start at hour following previous events
        start = start + timedelta(hours=range_start)
        for i in range(range_start, range_start + usage):
            end = start + timedelta(hours=1)
            subs_dict = self.build_azure_subs_dict(
                instance_id,
                row["subs_account"],
                start.isoformat(),
                end.isoformat(),
                row["subs_vcpu"],
                row["subs_rhel_version"],
                row["subs_sla"],
                row["subs_usage"],
                row["subs_role"],
                row["subs_conversion"],
                row["subs_addon_id"],
                tenant_id,
                row["subs_vmname"],
            )
            # move to the next hour in the range
            start = end
            self.send_kafka_message(subs_dict)
            msg_count += 1
            RHEL_ELS_SYSTEMS_PROCESSED.labels(provider_type=Provider.PROVIDER_AZURE).inc()
            try:
                RHEL_ELS_VCPU_HOURS.labels(provider_type=Provider.PROVIDER_AZURE).inc(
                    amount=(float(row["subs_vcpu"]) * usage)
                )
            except ValueError:
                LOG.info(
                    log_json(
                        self.tracing_id,
                        msg=f"vCPU amount could not be cast to a float {row['subs_vcpu']}",
                        context=self.context,
                    )
                )
        return msg_count

    def determine_product_ids(self, rhel_version, addon, role):
        """Determine the appropriate product id's based on the RHEL version, addon and role.

        HPC variants overwrite the product id's and are handled via ROLE.
        SAP variants are additional product id's.
        """
        product_ids = []
        if rhel_version == RHEL_7:
            if role == HPC_ROLE:
                return [RHEL_7_HPC_ID]
            elif role == SAP_ROLE:
                product_ids.append(RHEL_7_SAP_ID)
            product_ids.append(RHEL_7)
        elif rhel_version == RHEL_8:
            if role == HPC_ROLE:
                return [RHEL_8_HPC_ID]
            elif role == SAP_ROLE:
                product_ids.append(RHEL_8_SAP_ID)
            product_ids.append(RHEL_8)

        if addon == ELS:
            product_ids.append(ELS)

        return product_ids
