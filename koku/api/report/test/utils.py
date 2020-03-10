import os
import pkgutil
import shutil
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from jinja2 import Template
from model_bakery import baker
from nise.__main__ import run
from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.config import Config
from masu.processor.report_processor import ReportProcessor
from masu.processor.tasks import refresh_materialized_views
from masu.processor.tasks import update_cost_model_costs
from masu.processor.tasks import update_summary_tables


def get_test_data_dates():
    """Return a list of tuples with dates for nise data."""
    dh = DateHelper()
    end_date = dh.today
    ten_days_ago = dh.n_days_ago(end_date, 10)
    start_date = ten_days_ago
    if dh.this_month_start > ten_days_ago:
        start_date = dh.this_month_start

    prev_month_start = start_date - relativedelta(months=1)
    prev_month_end = end_date - relativedelta(months=1)

    return [(prev_month_start, prev_month_end, dh.last_month_start), (start_date, end_date, dh.this_month_start)]


def load_openshift_data(customer, static_data_file, cluster_id):
    """Load OpenShift data into the database."""
    schema = "acct10001"
    # cluster_id = "test-cluster"
    provider_type = "OCP"
    provider = baker.make(
        "Provider",
        type=provider_type,
        authentication__provider_resource_name=cluster_id,
        billing_source__bucket="",
        customer=customer,
    )
    dh = DateHelper()
    static_data = pkgutil.get_data("api.report.test", static_data_file)
    template = Template(static_data.decode("utf8"))
    static_data_path = f"/tmp/{provider_type}_static_data.yml"
    # nise_data_path = "/tmp/nise/ocp_data"
    nise_data_path = Config.TMP_DIR
    if not os.path.exists(nise_data_path):
        os.makedirs(nise_data_path)

    dates = get_test_data_dates()

    for start_date, end_date, bill_date in dates:
        manifest = baker.make(
            "CostUsageReportManifest", _fill_optional=True, provider=provider, billing_period_start_datetime=bill_date
        )
        with open(static_data_path, "w") as f:
            f.write(template.render(start_date=start_date, end_date=end_date))
        options = {
            "static_report_file": static_data_path,
            "insights_upload": nise_data_path,
            "ocp_cluster_id": cluster_id,
        }
        run(provider_type.lower(), options)
        this_month_str = bill_date.strftime("%Y%m%d")
        next_month = bill_date + relativedelta(months=1)
        next_month_str = next_month.strftime("%Y%m%d")
        desired_path = f"{nise_data_path}/{cluster_id}"
        ocp_path = f"{desired_path}/{this_month_str}-{next_month_str}"
        for report in os.scandir(ocp_path):
            shutil.move(report.path, f"{desired_path}/{report.name}")
        for report in [f.path for f in os.scandir(desired_path)]:
            if os.path.isdir(report):
                continue
            elif "manifest" in report.lower():
                continue
            print(report)
            status = baker.make("CostUsageReportStatus", manifest=manifest, report_name=report)
            status.last_started_datetime = dh.now
            ReportProcessor(schema, report, "PLAIN", provider_type, provider.uuid, manifest.id).process()
            status.last_completed_datetime = dh.now
            status.save()
        with patch("masu.processor.tasks.chain"):
            update_summary_tables(schema, provider_type, provider.uuid, start_date, end_date, manifest_id=manifest.id)
    update_cost_model_costs(schema, provider.uuid, dh.last_month_start, dh.today)
    refresh_materialized_views(schema, provider_type)
    shutil.rmtree(desired_path, ignore_errors=True)


def load_aws_data(customer):
    """Load AWS data into the database."""
    dh = DateHelper()
    schema = "acct10001"
    provider_type = "AWS-local"
    account_id = "9999999999999"
    nise_provider_type = provider_type.replace("-local", "")
    report_name = "Test"
    provider_resource_name = "arn:aws:iam::111111111117:role/CostManagement"
    provider = baker.make(
        "Provider",
        type=provider_type,
        authentication__provider_resource_name=provider_resource_name,
        customer=customer,
        billing_source__bucket="test-bucket",
    )
    static_data = pkgutil.get_data("api.report.test", "aws_static_data.yml")
    template = Template(static_data.decode("utf8"))
    static_data_path = f"/tmp/{provider_type}_static_data.yml"
    # nise_data_path = "/tmp/nise/ocp_data"
    nise_data_path = Config.TMP_DIR
    if not os.path.exists(nise_data_path):
        os.makedirs(nise_data_path)

    dates = get_test_data_dates()
    with schema_context(schema):
        baker.make("AWSAccountAlias", account_id=account_id, account_alias="Test Account")

    for start_date, end_date, bill_date in dates:
        manifest = baker.make(
            "CostUsageReportManifest", _fill_optional=True, provider=provider, billing_period_start_datetime=bill_date
        )
        with open(static_data_path, "w") as f:
            f.write(template.render(start_date=start_date, end_date=end_date, account_id=account_id))
        options = {
            "static_report_file": static_data_path,
            "aws_report_name": report_name,
            "aws_bucket_name": nise_data_path,
        }
        run(nise_provider_type.lower(), options)
        this_month_str = bill_date.strftime("%Y%m%d")
        next_month = bill_date + relativedelta(months=1)
        next_month_str = next_month.strftime("%Y%m%d")
        base_path = f"{nise_data_path}/{report_name}"
        desired_path = f"{base_path}/{this_month_str}-{next_month_str}"
        for report in os.scandir(desired_path):
            if os.path.isdir(report):
                for report in [f.path for f in os.scandir(f"{desired_path}/{report.name}")]:
                    if os.path.isdir(report):
                        continue
                    elif "manifest" in report.lower():
                        continue
                    print(report)
                    status = baker.make("CostUsageReportStatus", manifest=manifest, report_name=report)
                    status.last_started_datetime = dh.now
                    ReportProcessor(schema, report, "GZIP", provider_type, provider.uuid, manifest.id).process()
                    status.last_completed_datetime = dh.now
                    status.save()
        with patch("masu.processor.tasks.chain"):
            update_summary_tables(schema, provider_type, provider.uuid, start_date, end_date, manifest_id=manifest.id)
    update_cost_model_costs(schema, provider.uuid, dh.last_month_start, dh.today)
    refresh_materialized_views(schema, provider_type)
    shutil.rmtree(base_path, ignore_errors=True)


def load_azure_data(customer):
    """Load Azure data into the database."""
    dh = DateHelper()
    schema = "acct10001"
    provider_type = "Azure-local"
    nise_provider_type = provider_type.replace("-local", "")
    report_name = "Test"

    credentials = {
        "subscription_id": "11111111-1111-1111-1111-11111111",
        "tenant_id": "22222222-2222-2222-2222-22222222",
        "client_id": "33333333-3333-3333-3333-33333333",
        "client_secret": "MyPassW0rd!",
    }
    data_source = {"resource_group": "resourcegroup1", "storage_account": "storageaccount1"}

    provider = baker.make(
        "Provider",
        type=provider_type,
        authentication__credentials=credentials,
        customer=customer,
        billing_source__data_source=data_source,
    )
    static_data = pkgutil.get_data("api.report.test", "azure_static_data.yml")
    template = Template(static_data.decode("utf8"))
    static_data_path = f"/tmp/{provider_type}_static_data.yml"
    # nise_data_path = "/tmp/nise/ocp_data"
    nise_data_path = Config.TMP_DIR
    if not os.path.exists(nise_data_path):
        os.makedirs(nise_data_path)

    dates = get_test_data_dates()

    for start_date, end_date, bill_date in dates:
        manifest = baker.make(
            "CostUsageReportManifest", _fill_optional=True, provider=provider, billing_period_start_datetime=bill_date
        )
        with open(static_data_path, "w") as f:
            f.write(template.render(start_date=start_date, end_date=end_date))
        options = {
            "static_report_file": static_data_path,
            "azure_report_name": report_name,
            "azure_container_name": nise_data_path,
        }
        run(nise_provider_type.lower(), options)
        this_month_str = bill_date.strftime("%Y%m%d")
        next_month = bill_date + relativedelta(months=1) - relativedelta(days=1)
        next_month_str = next_month.strftime("%Y%m%d")
        base_path = f"{nise_data_path}/{report_name}"
        desired_path = f"{base_path}/{this_month_str}-{next_month_str}"
        for report in os.scandir(desired_path):
            if os.path.isdir(report):
                continue
            elif "manifest" in report.name.lower():
                continue
            print(report)
            status = baker.make("CostUsageReportStatus", manifest=manifest, report_name=report.name)
            status.last_started_datetime = dh.now
            ReportProcessor(schema, report.path, "PLAIN", provider_type, provider.uuid, manifest.id).process()
            status.last_completed_datetime = dh.now
            status.save()
        with patch("masu.processor.tasks.chain"):
            update_summary_tables(schema, provider_type, provider.uuid, start_date, end_date, manifest_id=manifest.id)
    update_cost_model_costs(schema, provider.uuid, dh.last_month_start, dh.today)
    refresh_materialized_views(schema, provider_type)
    shutil.rmtree(base_path, ignore_errors=True)
