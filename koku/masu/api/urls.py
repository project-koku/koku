#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Describes the urls and patterns for the API application."""
from django.urls import path

from masu.api.views import cleanup
from masu.api.views import crawl_account_hierarchy
from masu.api.views import download_report
from masu.api.views import enabled_tags
from masu.api.views import expired_data
from masu.api.views import get_status
from masu.api.views import report_data
from masu.api.views import running_celery_tasks
from masu.api.views import update_cost_model_costs

urlpatterns = [
    path("status/", get_status, name="server-status"),
    path("download/", download_report, name="report_download"),
    path("enabled_tags/", enabled_tags, name="enabled_tags"),
    path("expired_data/", expired_data, name="expired_data"),
    path("report_data/", report_data, name="report_data"),
    path("source_cleanup/", cleanup, name="cleanup"),
    path("update_cost_model_costs/", update_cost_model_costs, name="update_cost_model_costs"),
    path("crawl_account_hierarchy/", crawl_account_hierarchy, name="crawl_account_hierarchy"),
    path("running_celery_tasks/", running_celery_tasks, name="running_celery_tasks"),
]
