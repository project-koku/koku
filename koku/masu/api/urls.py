# Copyright 2019 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Describes the urls and patterns for the API application."""
from django.urls import path

from masu.api.views import crawl_account_hierarchy
from masu.api.views import download_report
from masu.api.views import enabled_tags
from masu.api.views import expired_data
from masu.api.views import get_status
from masu.api.views import report_data
from masu.api.views import update_cost_model_costs
from masu.api.views import upload_normalized_data

urlpatterns = [
    path("status/", get_status, name="server-status"),
    path("download/", download_report, name="report_download"),
    path("enabled_tags/", enabled_tags, name="enabled_tags"),
    path("expired_data/", expired_data, name="expired_data"),
    path("report_data/", report_data, name="report_data"),
    path("update_cost_model_costs/", update_cost_model_costs, name="update_cost_model_costs"),
    path("upload_normalized_data/", upload_normalized_data, name="upload_normalized_data"),
    path("crawl_account_hierarchy/", crawl_account_hierarchy, name="crawl_account_hierarchy"),
]
