#
# Copyright 2018 Red Hat, Inc.
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
"""Database subpackage."""

AWS_CUR_TABLE_MAP = {
    "cost_entry": "reporting_awscostentry",
    "bill": "reporting_awscostentrybill",
    "line_item": "reporting_awscostentrylineitem",
    "line_item_daily": "reporting_awscostentrylineitem_daily",
    "line_item_daily_summary": "reporting_awscostentrylineitem_daily_summary",
    "product": "reporting_awscostentryproduct",
    "pricing": "reporting_awscostentrypricing",
    "reservation": "reporting_awscostentryreservation",
    "tags_summary": "reporting_awstags_summary",
    "enabled_tag_keys": "reporting_awsenabledtagkeys",
    "ocp_on_aws_daily_summary": "reporting_ocpawscostlineitem_daily_summary",
    "ocp_on_aws_project_daily_summary": "reporting_ocpawscostlineitem_project_daily_summary",
    "ocp_on_aws_tags_summary": "reporting_ocpawstags_summary",
}

OCP_REPORT_TABLE_MAP = {
    "report_period": "reporting_ocpusagereportperiod",
    "report": "reporting_ocpusagereport",
    "line_item": "reporting_ocpusagelineitem",
    "line_item_daily": "reporting_ocpusagelineitem_daily",
    "line_item_daily_summary": "reporting_ocpusagelineitem_daily_summary",
    "cost_model": "cost_model",
    "cost_model_map": "cost_model_map",
    "pod_label_summary": "reporting_ocpusagepodlabel_summary",
    "storage_line_item": "reporting_ocpstoragelineitem",
    "storage_line_item_daily": "reporting_ocpstoragelineitem_daily",
    "volume_label_summary": "reporting_ocpstoragevolumelabel_summary",
    "cost_summary": "reporting_ocpcosts_summary",
    "node_label_line_item": "reporting_ocpnodelabellineitem",
    "node_label_line_item_daily": "reporting_ocpnodelabellineitem_daily",
}

AZURE_REPORT_TABLE_MAP = {
    "bill": "reporting_azurecostentrybill",
    "product": "reporting_azurecostentryproductservice",
    "meter": "reporting_azuremeter",
    "line_item": "reporting_azurecostentrylineitem_daily",
    "line_item_daily_summary": "reporting_azurecostentrylineitem_daily_summary",
    "tags_summary": "reporting_azuretags_summary",
    "enabled_tag_keys": "reporting_azureenabledtagkeys",
    "ocp_on_azure_daily_summary": "reporting_ocpazurecostlineitem_daily_summary",
    "ocp_on_azure_project_daily_summary": "reporting_ocpazurecostlineitem_project_daily_summary",
    "ocp_on_azure_tags_summary": "reporting_ocpazuretags_summary",
}

GCP_REPORT_TABLE_MAP = {
    "line_item": "reporting_gcpcostentrylineitem",
    "line_item_daily": "reporting_gcpcostentrylineitem_daily",
    "line_item_daily_summary": "reporting_gcpcostentrylineitem_daily_summary",
    "tags_summary": "reporting_gcptags_summary",
    "bill": "reporting_gcpcostentrybill",
    "product": "reporting_gcpcostentryproductservice",
    "project": "reporting_gcpproject",
}
