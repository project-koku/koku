#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database subpackage."""

AWS_CUR_TABLE_MAP = {
    "bill": "reporting_awscostentrybill",
    "line_item_daily_summary": "reporting_awscostentrylineitem_daily_summary",
    "ec2_compute_summary": "reporting_awscostentrylineitem_summary_by_ec2_compute_p",
    "tags_summary": "reporting_awstags_summary",
    "category_summary": "reporting_awscategory_summary",
    "ocp_on_aws_daily_summary": "reporting_ocpawscostlineitem_daily_summary_p",
    "ocp_on_aws_project_daily_summary": "reporting_ocpawscostlineitem_project_daily_summary_p",
    "ocp_on_aws_tags_summary": "reporting_ocpawstags_summary",
}

OCP_REPORT_TABLE_MAP = {
    "report_period": "reporting_ocpusagereportperiod",
    "line_item_daily_summary": "reporting_ocpusagelineitem_daily_summary",
    "cost_model": "cost_model",
    "cost_model_map": "cost_model_map",
    "pod_label_summary": "reporting_ocpusagepodlabel_summary",
    "volume_label_summary": "reporting_ocpstoragevolumelabel_summary",
    "cost_summary": "reporting_ocpcosts_summary",
}

AZURE_REPORT_TABLE_MAP = {
    "bill": "reporting_azurecostentrybill",
    "line_item_daily_summary": "reporting_azurecostentrylineitem_daily_summary",
    "tags_summary": "reporting_azuretags_summary",
    "ocp_on_azure_daily_summary": "reporting_ocpazurecostlineitem_daily_summary_p",
    "ocp_on_azure_project_daily_summary": "reporting_ocpazurecostlineitem_project_daily_summary_p",
    "ocp_on_azure_tags_summary": "reporting_ocpazuretags_summary",
}

GCP_REPORT_TABLE_MAP = {
    "line_item_daily_summary": "reporting_gcpcostentrylineitem_daily_summary",
    "tags_summary": "reporting_gcptags_summary",
    "bill": "reporting_gcpcostentrybill",
    "ocp_on_gcp_daily_summary": "reporting_ocpgcpcostlineitem_daily_summary_p",
    "ocp_on_gcp_project_daily_summary": "reporting_ocpgcpcostlineitem_project_daily_summary_p",
    "ocp_on_gcp_tags_summary": "reporting_ocpgcptags_summary",
}
