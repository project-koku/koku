#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPCloudReportSummaryUpdaterTest."""
import datetime
import decimal
from unittest import skip
from unittest.mock import Mock
from unittest.mock import patch

from django.db import connection
from django.db.models import Sum
from model_bakery import baker
from tenant_schemas.utils import schema_context

from api.models import Provider
from api.utils import DateHelper
from koku.database import get_model
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.processor.ocp.ocp_cloud_summary_updater import OCPCloudReportSummaryUpdater
from masu.test import MasuTestCase
from reporting.models import AWSCostEntryBill
from reporting_common.models import CostUsageReportManifest


class OCPCloudReportSummaryUpdaterTest(MasuTestCase):
    """Test cases for the OCPCloudReportSummaryUpdaterTest class."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.dh = DateHelper()

    def setUp(self):
        """Set up tests."""
        super().setUp()
        self.today = self.dh.today

    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase.get_infra_map_from_providers")
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_ui_summary_tables"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_daily_summary"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_project_daily_summary"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_cost_daily_summary")
    def test_update_summary_tables_with_ocp_provider(
        self, mock_ocp_on_aws, mock_ocpall_proj_summ, mock_ocpall_summ, mock_ocpall_persp, mock_map
    ):
        """Test that summary tables are properly run for an OCP provider."""
        start_date = self.dh.today
        end_date = start_date + datetime.timedelta(days=1)

        cluster_id = self.ocp_on_aws_ocp_provider.authentication.credentials.get("cluster_id")
        manifest = CostUsageReportManifest.objects.filter(
            provider=self.ocp_on_aws_ocp_provider, billing_period_start_datetime=self.dh.this_month_start
        )
        mock_map.return_value = {
            str(self.ocp_on_aws_ocp_provider.uuid): (self.aws_provider_uuid, Provider.PROVIDER_AWS)
        }
        updater = OCPCloudReportSummaryUpdater(
            schema=self.schema, provider=self.ocp_on_aws_ocp_provider, manifest=manifest
        )
        updater.update_summary_tables(
            start_date, end_date, self.ocp_on_aws_ocp_provider.uuid, self.aws_provider.uuid, Provider.PROVIDER_AWS
        )

        with schema_context(self.schema):
            bill = AWSCostEntryBill.objects.filter(
                provider=self.aws_provider, billing_period_start=self.dh.this_month_start
            ).first()

        mock_ocp_on_aws.assert_called_with(
            start_date.date(), end_date.date(), cluster_id, [str(bill.id)], decimal.Decimal(0)
        )

    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase.get_infra_map_from_providers")
    @patch("masu.processor.ocp.ocp_cloud_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_cost_daily_summary")
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_ui_summary_tables"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_daily_summary"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_project_daily_summary"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_summary_updater.aws_get_bills_from_provider")
    def test_update_summary_tables_with_aws_provider(
        self, mock_utility, mock_ocpall_proj_summ, mock_ocpall_summ, mock_ocpall_persp, mock_ocp_on_aws, mock_map
    ):
        """Test that summary tables are properly run for an OCP provider."""
        fake_bills = [Mock(), Mock()]
        fake_bills[0].id = 1
        fake_bills[1].id = 2
        bill_ids = [str(bill.id) for bill in fake_bills]
        mock_utility.return_value = fake_bills
        start_date = self.dh.today
        end_date = start_date + datetime.timedelta(days=1)
        with ProviderDBAccessor(self.aws_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with ProviderDBAccessor(self.ocp_on_aws_ocp_provider.uuid) as provider_accessor:
            credentials = provider_accessor.get_credentials()
        cluster_id = credentials.get("cluster_id")
        mock_map.return_value = {self.ocp_test_provider_uuid: (self.aws_provider_uuid, Provider.PROVIDER_AWS)}
        updater = OCPCloudReportSummaryUpdater(schema="org1234567", provider=provider, manifest=None)
        updater.update_summary_tables(
            start_date, end_date, self.ocp_on_aws_ocp_provider.uuid, self.aws_provider.uuid, Provider.PROVIDER_AWS
        )
        mock_ocp_on_aws.assert_called_with(
            start_date.date(), end_date.date(), cluster_id, bill_ids, decimal.Decimal(0)
        )

    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_ui_summary_tables"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_daily_summary"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_project_daily_summary"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_cost_daily_summary")
    def test_update_summary_tables_no_ocp_on_aws(
        self, mock_ocp_on_aws, mock_ocpall_proj_summ, mock_ocpall_summ, mock_ocpall_persp
    ):
        """Test that summary tables do not run when OCP-on-AWS does not exist."""
        new_aws_provider = baker.make("Provider", type="AWS")
        new_ocp_provider = baker.make("Provider", type="OCP")
        test_provider_list = [str(new_aws_provider.uuid), str(new_ocp_provider.uuid)]

        for provider_uuid in test_provider_list:
            start_date = self.dh.today
            end_date = start_date + datetime.timedelta(days=1)
            start_date_str = start_date.strftime("%Y-%m-%d")
            end_date_str = end_date.strftime("%Y-%m-%d")

            with ProviderDBAccessor(provider_uuid) as provider_accessor:
                provider = provider_accessor.get_provider()

            updater = OCPCloudReportSummaryUpdater(schema="org1234567", provider=provider, manifest=None)
            infra_map = updater.get_infra_map(start_date_str, end_date_str)
            for openshift_provider_uuid, infrastructure_tuple in infra_map.items():
                updater.update_summary_tables(
                    start_date_str,
                    end_date_str,
                    openshift_provider_uuid,
                    infrastructure_tuple[0],
                    infrastructure_tuple[1],
                )
            mock_ocp_on_aws.assert_not_called()

    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_ui_summary_tables"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_daily_summary"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_project_daily_summary"  # noqa: E501
    )
    @patch("masu.database.cost_model_db_accessor.CostModelDBAccessor.cost_model")
    def test_update_markup_cost(self, mock_cost_model, mock_ocpall_proj_summ, mock_ocpall_summ, mock_ocpall_persp):
        """Test that summary tables are updated correctly."""
        markup = {"value": 10, "unit": "percent"}
        markup_dec = decimal.Decimal(markup.get("value") / 100)
        mock_cost_model.markup = markup

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end
        manifest = CostUsageReportManifest.objects.filter(
            provider=self.ocp_on_aws_ocp_provider, billing_period_start_datetime=start_date
        ).first()
        updater = OCPCloudReportSummaryUpdater(
            schema=self.schema, provider=self.ocp_on_aws_ocp_provider, manifest=manifest
        )

        updater.update_summary_tables(
            start_date, end_date, self.ocp_on_aws_ocp_provider.uuid, self.aws_provider.uuid, Provider.PROVIDER_AWS
        )

        summary_table_name = AWS_CUR_TABLE_MAP["ocp_on_aws_daily_summary"]
        with AWSReportDBAccessor(self.schema) as aws_accessor:
            query = (
                aws_accessor._get_db_obj_query(summary_table_name)
                .filter(cost_entry_bill__billing_period_start=start_date)
                .all()
            )
            for item in query:
                self.assertAlmostEqual(item.markup_cost, item.unblended_cost * markup_dec)

    def test_get_infra_map_from_providers(self):
        """Test that an infrastructure map is returned."""
        updater = OCPCloudReportSummaryUpdater(
            schema=self.schema, provider=self.ocp_on_aws_ocp_provider, manifest=None
        )

        expected_mapping = (self.aws_provider_uuid, Provider.PROVIDER_AWS_LOCAL)
        infra_map = updater.get_infra_map_from_providers()
        self.assertEqual(len(infra_map.keys()), 1)
        self.assertIn(str(self.ocp_on_aws_ocp_provider.uuid), infra_map)
        self.assertEqual(infra_map.get(str(self.ocp_on_aws_ocp_provider.uuid)), expected_mapping)

        updater = OCPCloudReportSummaryUpdater(schema=self.schema, provider=self.aws_provider, manifest=None)

        infra_map = updater.get_infra_map_from_providers()

        self.assertEqual(len(infra_map.keys()), 1)
        self.assertIn(str(self.ocp_on_aws_ocp_provider.uuid), infra_map)
        self.assertEqual(infra_map.get(str(self.ocp_on_aws_ocp_provider.uuid)), expected_mapping)

    # @patch(
    #     "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_ui_summary_tables"  # noqa: E501
    # )
    # @patch(
    #     "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_daily_summary"  # noqa: E501
    # )
    # @patch(
    #     "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_project_daily_summary"  # noqa: E501
    # )
    @skip("Revisit this test")
    @patch("masu.database.cost_model_db_accessor.CostModelDBAccessor.cost_model")
    def test_update_summary_tables_azure(
        self, mock_cost_model, mock_ocpall_proj_summ, mock_ocpall_summ, mock_ocpall_persp
    ):
        """Test that summary tables are updated correctly."""

        markup = {"value": 10, "unit": "percent"}
        mock_cost_model.markup = markup

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end

        updater = OCPCloudReportSummaryUpdater(schema=self.schema, provider=self.azure_provider, manifest=None)

        updater.update_summary_tables(
            start_date,
            end_date,
            self.ocp_on_azure_ocp_provider.uuid,
            self.azure_provider.uuid,
            Provider.PROVIDER_AZURE,
        )

        summary_table_name = AZURE_REPORT_TABLE_MAP["ocp_on_azure_daily_summary"]
        with AzureReportDBAccessor(self.schema) as azure_accessor:
            query = azure_accessor._get_db_obj_query(summary_table_name).filter(
                cost_entry_bill__billing_period_start=start_date
            )
            markup_cost = query.aggregate(Sum("markup_cost"))["markup_cost__sum"]
            pretax_cost = query.aggregate(Sum("pretax_cost"))["pretax_cost__sum"]

        self.assertAlmostEqual(markup_cost, pretax_cost * decimal.Decimal(markup.get("value") / 100), places=5)

        daily_summary_table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        with OCPReportDBAccessor(self.schema) as ocp_accessor:
            query = ocp_accessor._get_db_obj_query(daily_summary_table_name).filter(
                report_period__provider=self.ocp_on_azure_ocp_provider,
                report_period__report_period_start=self.dh.this_month_start,
            )
            infra_cost = query.aggregate(Sum("infrastructure_raw_cost"))["infrastructure_raw_cost__sum"]
            project_infra_cost = query.aggregate(Sum("infrastructure_project_raw_cost"))[
                "infrastructure_project_raw_cost__sum"
            ]

        self.assertIsNotNone(infra_cost)
        self.assertIsNotNone(project_infra_cost)
        self.assertNotEqual(infra_cost, decimal.Decimal(0))
        self.assertNotEqual(project_infra_cost, decimal.Decimal(0))

    def test_partition_handler_str_table(self):
        new_table_sql = f"""
create table {self.schema}._eek_pt0 (usage_start date not null, id int) partition by range (usage_start);
"""
        with schema_context(self.schema):
            with connection.cursor() as cur:
                cur.execute(new_table_sql)

            partable = get_model("PartitionedTable")
            default_part = partable(
                schema_name=self.schema,
                table_name="_eek_pt0_default",
                partition_of_table_name="_eek_pt0",
                partition_type=partable.RANGE,
                partition_col="usage_start",
                partition_parameters={"default": True},
                active=True,
            )
            default_part.save()

            ocrsu = OCPCloudReportSummaryUpdater(self.schema, self.ocp_on_aws_ocp_provider, None)
            num_eek = partable.objects.filter(schema_name=self.schema, partition_of_table_name="_eek_pt0").count()
            self.assertEqual(num_eek, 1)

            ocrsu._handle_partitions(self.schema, "_eek_pt0", datetime.date(1970, 10, 1), datetime.date(1970, 12, 1))
            eek_p = partable.objects.filter(
                schema_name=self.schema, partition_of_table_name="_eek_pt0", partition_parameters__default=False
            ).all()
            self.assertEqual(len(eek_p), 3)

            eek_p.delete()
            default_part.delete()

            with connection.cursor() as cur:
                cur.execute(f"drop table {self.schema}._eek_pt0 ;")
