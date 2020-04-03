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
from django.conf.urls import url

from masu.api.views import download_report
from masu.api.views import enabled_tags
from masu.api.views import expired_data
from masu.api.views import get_status
from masu.api.views import report_data
from masu.api.views import update_cost_model_costs
from masu.api.views import upload_normalized_data

urlpatterns = [
    url(r"^status/$", get_status, name="server-status"),
    url(r"^download/$", download_report, name="report_download"),
    url(r"^enabled_tags/$", enabled_tags, name="enabled_tags"),
    url(r"^expired_data/$", expired_data, name="expired_data"),
    url(r"^report_data/$", report_data, name="report_data"),
    url(r"^update_cost_model_costs/$", update_cost_model_costs, name="update_cost_model_costs"),
    url(r"^upload_normalized_data/$", upload_normalized_data, name="upload_normalized_data"),
]
