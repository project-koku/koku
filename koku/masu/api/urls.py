#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Describes the urls and patterns for the API application."""
from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter

from masu.api.sources.views import SourcesViewSet
from masu.api.trino import trino_ui
from masu.api.views import additional_context
from masu.api.views import bigquery_cost
from masu.api.views import celery_queue_lengths
from masu.api.views import celery_queue_tasks
from masu.api.views import cleanup
from masu.api.views import clear_celery_queues
from masu.api.views import crawl_account_hierarchy
from masu.api.views import db_performance_redirect
from masu.api.views import dbsettings
from masu.api.views import download_report
from masu.api.views import EnabledTagView
from masu.api.views import expired_data
from masu.api.views import expired_trino_partitions
from masu.api.views import explain_query
from masu.api.views import get_status
from masu.api.views import hcs_report_data
from masu.api.views import hcs_report_finalization
from masu.api.views import ingest_ocp_payload
from masu.api.views import ingress_reports
from masu.api.views import invalidate_cache
from masu.api.views import lockinfo
from masu.api.views import ManifestStatusViewSet
from masu.api.views import notification
from masu.api.views import pg_engine_version
from masu.api.views import purge_trino_files
from masu.api.views import recheck_infra_map
from masu.api.views import report_data
from masu.api.views import running_celery_tasks
from masu.api.views import schema_sizes
from masu.api.views import stat_activity
from masu.api.views import stat_statements
from masu.api.views import trino_query
from masu.api.views import update_azure_storage_capacity
from masu.api.views import update_cost_model_costs
from masu.api.views import update_exchange_rates
from masu.api.views import validate_cost_data

ROUTER = DefaultRouter()
ROUTER.register(r"sources", SourcesViewSet, basename="sources")
ROUTER.register(r"manifests", ManifestStatusViewSet, basename="manifests")


urlpatterns = [
    path("status/", get_status, name="server-status"),
    path("download/", download_report, name="report_download"),
    path("ingress_reports/", ingress_reports, name="ingress_reports"),
    path("update_exchange_rates/", update_exchange_rates, name="update_exchange_rates"),
    path("update_azure_storage_capacity/", update_azure_storage_capacity, name="update_azure_storage_capacity"),
    path("enabled_tags/", EnabledTagView.as_view(), name="enabled_tags"),
    path("expired_trino_partitions/", expired_trino_partitions, name="expired_trino_partitions"),
    path("expired_data/", expired_data, name="expired_data"),
    path("hcs_report_data/", hcs_report_data, name="hcs_report_data"),
    path("hcs_report_finalization/", hcs_report_finalization, name="hcs_report_finalization"),
    path("report_data/", report_data, name="report_data"),
    path("source_cleanup/", cleanup, name="cleanup"),
    path("trino/query/", trino_query, name="trino_query"),
    path("trino/api/", trino_ui, name="trino_ui"),
    path("notification/", notification, name="notification"),
    path("recheck_infra_map/", recheck_infra_map, name="recheck_infra_map"),
    path("update_cost_model_costs/", update_cost_model_costs, name="update_cost_model_costs"),
    path("crawl_account_hierarchy/", crawl_account_hierarchy, name="crawl_account_hierarchy"),
    path("additional_context/", additional_context, name="additional_context"),
    path("running_celery_tasks/", running_celery_tasks, name="running_celery_tasks"),
    path("celery_queue_tasks/", celery_queue_tasks, name="celery_queue_tasks"),
    path("celery_queue_lengths/", celery_queue_lengths, name="celery_queue_lengths"),
    path("clear_celery_queues/", clear_celery_queues, name="clear_celery_queues"),
    path("bigquery_cost/<uuid:source_uuid>/", bigquery_cost, name="bigquery_cost"),
    path("purge_trino_files/", purge_trino_files, name="purge_trino_files"),
    path("validate_cost_data/", validate_cost_data, name="validate_cost_data"),
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
    path("invalidate_cache/", invalidate_cache, name="invalidate_cache"),
]

if settings.DEBUG:
    urlpatterns += [
        path("ingest_ocp_payload/", ingest_ocp_payload, name="local ocp ingress"),
    ]

urlpatterns += ROUTER.urls
