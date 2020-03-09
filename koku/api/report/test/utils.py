import os
import pkgutil
import shutil
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from jinja2 import Template
from model_bakery import baker
from nise.__main__ import run

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


def load_openshift_data():
    """Load OpenShift data into the database."""
    schema = "acct10001"
    cluster_id = "test-cluster"
    provider_type = "OCP"
    provider = baker.make("Provider", type=provider_type, authentication__provider_resource_name=cluster_id)
    dh = DateHelper()
    static_data = pkgutil.get_data("api.report.test", "ocp_aws_static_data.yml")
    template = Template(static_data.decode("utf8"))
    static_data_path = f"/tmp/{provider_type}_static_data.yml"
    # nise_data_path = "/tmp/nise/ocp_data"
    nise_data_path = Config.TMP_DIR
    if not os.path.exists(nise_data_path):
        os.makedirs(nise_data_path)

    dates = get_test_data_dates()

    for start_date, end_date, bill_date in dates:
        manifest = baker.make("CostUsageReportManifest", _fill_optional=True, provider=provider)
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
            baker.make("CostUsageReportStatus", manifest=manifest, report_name=report)
            ReportProcessor(schema, report, "PLAIN", provider_type, provider.uuid, manifest.id).process()
    with patch("masu.processor.tasks.chain"):
        update_summary_tables(schema, provider_type, provider.uuid, dh.last_month_start, dh.today)
    update_cost_model_costs(schema, provider.uuid, dh.last_month_start, dh.today)
    refresh_materialized_views(schema, provider_type)
    shutil.rmtree(desired_path, ignore_errors=True)


def load_aws_data():
    """Load AWS data into the database."""
    dh = DateHelper()
    schema = "acct10001"
    provider_type = "AWS-local"
    nise_provider_type = provider_type.replace("-local", "")
    report_name = "Test"
    provider_resource_name = "arn:aws:iam::111111111117:role/CostManagement"
    provider = baker.make(
        "Provider", type=provider_type, authentication__provider_resource_name=provider_resource_name
    )
    static_data = pkgutil.get_data("api.report.test", "aws_static_data.yml")
    template = Template(static_data.decode("utf8"))
    static_data_path = f"/tmp/{provider_type}_static_data.yml"
    # nise_data_path = "/tmp/nise/ocp_data"
    nise_data_path = Config.TMP_DIR
    if not os.path.exists(nise_data_path):
        os.makedirs(nise_data_path)

    dates = get_test_data_dates()

    for start_date, end_date, bill_date in dates:
        manifest = baker.make("CostUsageReportManifest", _fill_optional=True, provider=provider)
        with open(static_data_path, "w") as f:
            f.write(template.render(start_date=start_date, end_date=end_date))
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
                    baker.make("CostUsageReportStatus", manifest=manifest, report_name=report)
                    ReportProcessor(schema, report, "GZIP", provider_type, provider.uuid, manifest.id).process()
    with patch("masu.processor.tasks.chain"):
        update_summary_tables(schema, provider_type, provider.uuid, dh.last_month_start, dh.today)
    update_cost_model_costs(schema, provider.uuid, dh.last_month_start, dh.today)
    refresh_materialized_views(schema, provider_type)
    shutil.rmtree(base_path, ignore_errors=True)


def load_azure_data():
    """Load Azure data into the database."""
    dh = DateHelper()
    schema = "acct10001"
    provider_type = "Azure-local"
    nise_provider_type = provider_type.replace("-local", "")
    report_name = "Test"

    provider_resource_name = "arn:aws:iam::111111111117:role/CostManagement"
    provider = baker.make(
        "Provider", type=provider_type, authentication__provider_resource_name=provider_resource_name
    )
    static_data = pkgutil.get_data("api.report.test", "aws_static_data.yml")
    template = Template(static_data.decode("utf8"))
    static_data_path = f"/tmp/{provider_type}_static_data.yml"
    # nise_data_path = "/tmp/nise/ocp_data"
    nise_data_path = Config.TMP_DIR
    if not os.path.exists(nise_data_path):
        os.makedirs(nise_data_path)

    dates = get_test_data_dates()

    for start_date, end_date, bill_date in dates:
        manifest = baker.make("CostUsageReportManifest", _fill_optional=True, provider=provider)
        with open(static_data_path, "w") as f:
            f.write(template.render(start_date=start_date, end_date=end_date))
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
                    baker.make("CostUsageReportStatus", manifest=manifest, report_name=report)
                    ReportProcessor(schema, report, "GZIP", provider_type, provider.uuid, manifest.id).process()
    with patch("masu.processor.tasks.chain"):
        update_summary_tables(schema, provider_type, provider.uuid, dh.last_month_start, dh.today)
    update_cost_model_costs(schema, provider.uuid, dh.last_month_start, dh.today)
    refresh_materialized_views(schema, provider_type)
    shutil.rmtree(base_path, ignore_errors=True)
