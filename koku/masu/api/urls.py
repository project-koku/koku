#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Describes the urls and patterns for the API application."""
from django.urls import path

from masu.api.manifest.views import ManifestView
from masu.api.views import celery_queue_lengths
from masu.api.views import cleanup
from masu.api.views import crawl_account_hierarchy
from masu.api.views import download_report
from masu.api.views import enabled_tags
from masu.api.views import expired_data
from masu.api.views import gcp_invoice_monthly_cost
from masu.api.views import get_status
from masu.api.views import hcs_report_data
from masu.api.views import report_data
from masu.api.views import running_celery_tasks
from masu.api.views import update_cost_model_costs
from masu.api.views import update_exchange_rates

urlpatterns = [
    path("status/", get_status, name="server-status"),
    path("download/", download_report, name="report_download"),
    path("update_exchange_rates/", update_exchange_rates, name="update_exchange_rates"),
    path("enabled_tags/", enabled_tags, name="enabled_tags"),
    path("expired_data/", expired_data, name="expired_data"),
    path("hcs_report_data/", hcs_report_data, name="hcs_report_data"),
    path("report_data/", report_data, name="report_data"),
    path("source_cleanup/", cleanup, name="cleanup"),
    path("update_cost_model_costs/", update_cost_model_costs, name="update_cost_model_costs"),
    path("crawl_account_hierarchy/", crawl_account_hierarchy, name="crawl_account_hierarchy"),
    path("running_celery_tasks/", running_celery_tasks, name="running_celery_tasks"),
    path("celery_queue_lengths/", celery_queue_lengths, name="celery_queue_lengths"),
    path("manifests/", ManifestView.as_view({"get": "get_all_manifests"}), name="all_manifests"),
    path(
        "manifests/<str:source_uuid>/",
        ManifestView.as_view({"get": "get_manifests_by_source"}),
        name="sources_manifests",
    ),
    path(
        "manifests/<str:source_uuid>/<int:manifest_id>/",
        ManifestView.as_view({"get": "get_manifest"}),
        name="manifest",
    ),
    path(
        "manifests/<str:source_uuid>/<int:manifest_id>/files/",
        ManifestView.as_view({"get": "get_manifest_files"}),
        name="manifest_files",
    ),
    path(
        "manifests/<str:source_uuid>/<int:manifest_id>/files/<int:id>/",
        ManifestView.as_view({"get": "get_one_manifest_file"}),
        name="get_one_manifest_file",
    ),
    path("gcp_invoice_monthly_cost/", gcp_invoice_monthly_cost, name="gcp_invoice_monthly_cost"),
]
