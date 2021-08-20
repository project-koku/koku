#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Sources URL Configuration.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
"""
from django.conf import settings
from django.conf.urls import include
from django.urls import path


API_PATH_PREFIX = settings.API_PATH_PREFIX
if API_PATH_PREFIX != "":
    if API_PATH_PREFIX.startswith("/"):
        API_PATH_PREFIX = API_PATH_PREFIX[1:]
    if not API_PATH_PREFIX.endswith("/"):
        API_PATH_PREFIX = API_PATH_PREFIX + "/"

urlpatterns = [path(f"{API_PATH_PREFIX}v1/", include("sources.api.urls"))]
