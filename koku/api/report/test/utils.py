#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test utilities."""
import os
import pkgutil
import shutil
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.test.utils import override_settings
from django_tenants.utils import schema_context
from jinja2 import Template
from model_bakery import baker
from nise.__main__ import run

from api.models import Provider
from api.provider.models import ProviderBillingSource
from api.utils import DateHelper
from masu.config import Config
from masu.processor.report_processor import ReportProcessor
from masu.processor.tasks import refresh_materialized_views
from masu.processor.tasks import update_cost_model_costs
from masu.processor.tasks import update_summary_tables


class NiseDataLoader:
    """Loads nise generated test data for different source types."""

    def __init__(self, schema, num_days=4):
        """Initialize the data loader."""
        self.dh = DateHelper()
        self.schema = schema
        self.nise_data_path = Config.TMP_DIR
        if not os.path.exists(self.nise_data_path):
            os.makedirs(self.nise_data_path)
        self.dates = self.get_test_data_dates(num_days)

    def get_test_data_dates(self, num_days):
        """Return a list of tuples with dates for nise data."""
        end_date = self.dh.today
        if end_date.day == 1:
            end_date += relativedelta(days=1)
        n_days_ago = self.dh.n_days_ago(end_date, num_days)
        start_date = n_days_ago
        if self.dh.this_month_start > n_days_ago:
            start_date = self.dh.this_month_start

        prev_month_start = start_date - relativedelta(months=1)
        prev_month_end = end_date - relativedelta(months=1)

        return [
            (prev_month_start, prev_month_end, self.dh.last_month_start),
            (start_date, end_date, self.dh.this_month_start),
        ]

    def prepare_template(self, provider_type, static_data_file):
        """Prepare the Jinja template for static data."""
        static_data = pkgutil.get_data("api.report.test", static_data_file)
        template = Template(static_data.decode("utf8"))
        static_data_path = f"/tmp/{provider_type}_static_data.yml"
        return template, static_data_path

    def build_report_path(self, provider_type, bill_date, base_path):
        """Build a path to report files."""
        this_month_str = bill_date.strftime("%Y%m%d")
        next_month = bill_date + relativedelta(months=1)
        if provider_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            next_month = next_month - relativedelta(days=1)
        next_month_str = next_month.strftime("%Y%m%d")
        return f"{base_path}/{this_month_str}-{next_month_str}"

    def process_report(self, report, compression, provider_type, provider, manifest):
        """Run the report processor on a report."""
        status = baker.make("CostUsageReportStatus", manifest=manifest, report_name=report)
        status.last_started_datetime = self.dh.now
        ReportProcessor(self.schema, report, compression, provider_type, provider.uuid, manifest.id).process()
        status.last_completed_datetime = self.dh.now
        status.save()

    def load_openshift_data(self, customer, static_data_file, cluster_id):
        """Load OpenShift data into the database."""
        provider_type = Provider.PROVIDER_OCP
        credentials = {"cluster_id": cluster_id}
        with override_settings(AUTO_DATA_INGEST=False):
            ocp_billing_source, _ = ProviderBillingSource.objects.get_or_create(data_source={})
            provider = baker.make(
                "Provider",
                type=provider_type,
                authentication__credentials=credentials,
                billing_source=ocp_billing_source,
                customer=customer,
            )
        template, static_data_path = self.prepare_template(provider_type, static_data_file)
        options = {
            "static_report_file": static_data_path,
            "insights_upload": self.nise_data_path,
            "ocp_cluster_id": cluster_id,
        }
        base_path = f"{self.nise_data_path}/{cluster_id}"

        for start_date, end_date, bill_date in self.dates:
            manifest = baker.make(
                "CostUsageReportManifest",
                _fill_optional=True,
                provider=provider,
                billing_period_start_datetime=bill_date,
                num_total_files=3,
            )
            with open(static_data_path, "w") as f:
                f.write(template.render(start_date=start_date, end_date=end_date))

            run(provider_type.lower(), options)

            report_path = self.build_report_path(provider_type, bill_date, base_path)
            for report in os.scandir(report_path):
                shutil.move(report.path, f"{base_path}/{report.name}")
            for report in [f.path for f in os.scandir(base_path)]:
                if os.path.isdir(report):
                    continue
                elif "manifest" in report.lower():
                    continue
                self.process_report(report, "PLAIN", provider_type, provider, manifest)
            with patch("masu.processor.tasks.chain"):
                update_summary_tables(
                    self.schema, provider_type, provider.uuid, start_date, end_date, manifest_id=manifest.id
                )
        update_cost_model_costs.s(
            self.schema, provider.uuid, self.dh.last_month_start, self.dh.today, synchronous=True
        ).apply()
        refresh_materialized_views.s(self.schema, provider_type, provider_uuid=provider.uuid, synchronous=True).apply()
        shutil.rmtree(report_path, ignore_errors=True)

    def load_aws_data(self, customer, static_data_file, account_id=None, role_arn=None):
        """Load AWS data into the database."""
        provider_type = Provider.PROVIDER_AWS_LOCAL
        if account_id is None:
            account_id = "9999999999999"
        if role_arn is None:
            role_arn = "arn:aws:iam::999999999999:role/CostManagement"
        nise_provider_type = provider_type.replace("-local", "")
        report_name = "Test"
        credentials = {"role_arn": role_arn}
        data_source = {"bucket": "test-bucket"}
        with patch.object(settings, "AUTO_DATA_INGEST", False):
            provider = baker.make(
                "Provider",
                type=provider_type,
                authentication__credentials=credentials,
                billing_source__data_source=data_source,
                customer=customer,
            )
        template, static_data_path = self.prepare_template(provider_type, static_data_file)
        options = {
            "static_report_file": static_data_path,
            "aws_report_name": report_name,
            "aws_bucket_name": self.nise_data_path,
        }
        base_path = f"{self.nise_data_path}/{report_name}"

        with schema_context(self.schema):
            baker.make("AWSAccountAlias", account_id=account_id, account_alias="Test Account")

        for start_date, end_date, bill_date in self.dates:
            manifest = baker.make(
                "CostUsageReportManifest",
                _fill_optional=True,
                provider=provider,
                billing_period_start_datetime=bill_date,
            )
            with open(static_data_path, "w") as f:
                f.write(template.render(start_date=start_date, end_date=end_date, account_id=account_id))

            run(nise_provider_type.lower(), options)

            report_path = self.build_report_path(provider_type, bill_date, base_path)
            for report in os.scandir(report_path):
                if os.path.isdir(report):
                    for report in [f.path for f in os.scandir(f"{report_path}/{report.name}")]:
                        if os.path.isdir(report):
                            continue
                        elif "manifest" in report.lower():
                            continue
                        self.process_report(report, "GZIP", provider_type, provider, manifest)
            with patch("masu.processor.tasks.chain"), patch.object(settings, "AUTO_DATA_INGEST", False):
                update_summary_tables(
                    self.schema, provider_type, provider.uuid, start_date, end_date, manifest_id=manifest.id
                )
        update_cost_model_costs.s(
            self.schema, provider.uuid, self.dh.last_month_start, self.dh.today, synchronous=True
        ).apply()
        refresh_materialized_views.s(self.schema, provider_type, provider_uuid=provider.uuid, synchronous=True).apply()
        shutil.rmtree(base_path, ignore_errors=True)

    def load_azure_data(self, customer, static_data_file, credentials=None, data_source=None):
        """Load Azure data into the database."""
        provider_type = Provider.PROVIDER_AZURE_LOCAL
        nise_provider_type = provider_type.replace("-local", "")
        report_name = "Test"

        if credentials is None:
            credentials = {
                "subscription_id": "11111111-1111-1111-1111-11111111",
                "tenant_id": "22222222-2222-2222-2222-22222222",
                "client_id": "33333333-3333-3333-3333-33333333",
                "client_secret": "MyPassW0rd!",
            }
        if data_source is None:
            data_source = {"resource_group": "resourcegroup1", "storage_account": "storageaccount1"}

        with patch.object(settings, "AUTO_DATA_INGEST", False):
            provider = baker.make(
                "Provider",
                type=provider_type,
                authentication__credentials=credentials,
                billing_source__data_source=data_source,
                customer=customer,
            )
        template, static_data_path = self.prepare_template(provider_type, static_data_file)
        options = {
            "static_report_file": static_data_path,
            "azure_report_name": report_name,
            "azure_container_name": self.nise_data_path,
        }
        base_path = f"{self.nise_data_path}/{report_name}"

        for start_date, end_date, bill_date in self.dates:
            manifest = baker.make(
                "CostUsageReportManifest",
                _fill_optional=True,
                provider=provider,
                billing_period_start_datetime=bill_date,
            )
            with open(static_data_path, "w") as f:
                f.write(template.render(start_date=start_date, end_date=end_date))

            run(nise_provider_type.lower(), options)

            report_path = self.build_report_path(provider_type, bill_date, base_path)
            for report in os.scandir(report_path):
                if os.path.isdir(report):
                    continue
                elif "manifest" in report.name.lower():
                    continue
                self.process_report(report, "PLAIN", provider_type, provider, manifest)
            with patch("masu.processor.tasks.chain"), patch.object(settings, "AUTO_DATA_INGEST", False):
                update_summary_tables(
                    self.schema, provider_type, provider.uuid, start_date, end_date, manifest_id=manifest.id
                )
        update_cost_model_costs.s(
            self.schema, provider.uuid, self.dh.last_month_start, self.dh.today, synchronous=True
        ).apply()
        refresh_materialized_views.s(self.schema, provider_type, provider_uuid=provider.uuid, synchronous=True).apply()
        shutil.rmtree(base_path, ignore_errors=True)
