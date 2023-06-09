#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Describes the urls and patterns for the API application."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from masu.api.manifest.views import ManifestView
from masu.api.sources.views import SourcesViewSet
from masu.api.trino import trino_ui
from masu.api.views import additional_context
from masu.api.views import bigquery_cost
from masu.api.views import celery_queue_lengths
from masu.api.views import cleanup
from masu.api.views import clear_celery_queues
from masu.api.views import clear_statement_statistics
from masu.api.views import crawl_account_hierarchy
from masu.api.views import db_performance_redirect
from masu.api.views import dbsettings
from masu.api.views import download_report
from masu.api.views import EnabledTagView
from masu.api.views import expired_data
from masu.api.views import explain_query
from masu.api.views import get_status
from masu.api.views import hcs_report_data
from masu.api.views import hcs_report_finalization
from masu.api.views import lockinfo
from masu.api.views import notification
from masu.api.views import pg_cancel_backend
from masu.api.views import pg_engine_version
from masu.api.views import pg_terminate_backend
from masu.api.views import process_openshift_on_cloud
from masu.api.views import purge_trino_files
from masu.api.views import report_data
from masu.api.views import running_celery_tasks
from masu.api.views import schema_sizes
from masu.api.views import stat_activity
from masu.api.views import stat_statements
from masu.api.views import trino_query
from masu.api.views import update_cost_model_costs
from masu.api.views import update_exchange_rates
from masu.api.views import update_openshift_on_cloud

ROUTER = DefaultRouter()
ROUTER.register(r"sources", SourcesViewSet, basename="sources")

urlpatterns = [
    path("status/", get_status, name="server-status"),
    path("download/", download_report, name="report_download"),
    path("update_exchange_rates/", update_exchange_rates, name="update_exchange_rates"),
    path("enabled_tags/", EnabledTagView.as_view(), name="enabled_tags"),
    path("expired_data/", expired_data, name="expired_data"),
    path("hcs_report_data/", hcs_report_data, name="hcs_report_data"),
    path("hcs_report_finalization/", hcs_report_finalization, name="hcs_report_finalization"),
    path("report_data/", report_data, name="report_data"),
    path("source_cleanup/", cleanup, name="cleanup"),
    path("trino/query/", trino_query, name="trino_query"),
    path("trino/api/", trino_ui, name="trino_ui"),
    path("notification/", notification, name="notification"),
    path("update_cost_model_costs/", update_cost_model_costs, name="update_cost_model_costs"),
    path("report/process/openshift_on_cloud/", process_openshift_on_cloud, name="process_openshift_on_cloud"),
    path("report/summarize/openshift_on_cloud/", update_openshift_on_cloud, name="update_openshift_on_cloud"),
    path("crawl_account_hierarchy/", crawl_account_hierarchy, name="crawl_account_hierarchy"),
    path("additional_context/", additional_context, name="additional_context"),
    path("running_celery_tasks/", running_celery_tasks, name="running_celery_tasks"),
    path("celery_queue_lengths/", celery_queue_lengths, name="celery_queue_lengths"),
    path("clear_celery_queues/", clear_celery_queues, name="clear_celery_queues"),
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
    path(
        "gcp_invoice_monthly_cost/", bigquery_cost, name="gcp_invoice_monthly_cost"
    ),  # TODO: Remove once iqe is updated
    path("bigquery_cost/", bigquery_cost, name="bigquery_cost"),
    path("purge_trino_files/", purge_trino_files, name="purge_trino_files"),
    path("db-performance", db_performance_redirect, name="db_perf_no_slash_redirect"),
    path("db-performance/", db_performance_redirect, name="db_perf_slash_redirect"),
    path("db-performance/db-settings/", dbsettings, name="db_settings"),
    path("db-performance/lock-info/", lockinfo, name="lock_info"),
    path("db-performance/stat-activity/", stat_activity, name="conn_activity"),
    path("db-performance/stat-statements/", stat_statements, name="stmt_stats"),
    path("db-performance/db-version/", pg_engine_version, name="db_version"),
    path("db-performance/explain-query/", explain_query, name="explain_query"),
    path("db-performance/db-version/", pg_engine_version, name="db_version"),
    path("db-performance/schema-sizes/", schema_sizes, name="schema_sizes"),
    path("db-performance/cancel-backend-pid/", pg_cancel_backend, name="db_cancel_connection"),
    path("db-performance/terminate-backend-pid/", pg_terminate_backend, name="db_terminate_connection"),
    path("db-performance/stat-statements-reset/", clear_statement_statistics, name="clear_statement_statistics"),
]

urlpatterns += ROUTER.urls
