#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the bulk provider details of the GET /sources/ list."""
import copy
from unittest.mock import patch
from uuid import uuid4

from django.core.cache import caches
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django_tenants.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import ProviderInfrastructureMap
from api.provider.models import Sources
from api.provider.provider_manager import bulk_source_details
from api.utils import DateHelper
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from koku.settings import CacheEnum
from reporting_common.models import CostUsageReportManifest
from reporting_common.states import ManifestState
from reporting_common.states import ManifestStep
from sources.api.view import SourcesViewSet


class SourcesBulkDetailsTest(IamTestCase):
    """The bulk path must return exactly what the per-source ProviderManager path returns."""

    def setUp(self):
        super().setUp()
        dh = DateHelper()
        self.aws = self.baker.make(
            Provider, type=Provider.PROVIDER_AWS, customer=self.customer, polling_timestamp=dh.now
        )
        infra = self.baker.make(
            ProviderInfrastructureMap, infrastructure_type=Provider.PROVIDER_AWS, infrastructure_provider=self.aws
        )
        self.ocp = self.baker.make(
            Provider,
            type=Provider.PROVIDER_OCP,
            customer=self.customer,
            infrastructure=infra,
            polling_timestamp=dh.now,
            created_timestamp=dh.now,
            additional_context={"crc_cluster_id": "x"},
        )
        self.ocp_without_data = self.baker.make(Provider, type=Provider.PROVIDER_OCP, customer=self.customer)
        self.baker.make(
            Sources,
            source_id=987654,
            source_uuid=self.aws.uuid,
            koku_uuid=str(self.aws.uuid),
            source_type=Provider.PROVIDER_AWS,
            org_id=self.customer.org_id,
            account_id=self.customer.account_id,
            paused=False,
            status={"availability_status": "available"},
        )
        self.baker.make(
            CostUsageReportManifest,
            provider=self.ocp,
            billing_period_start_datetime=dh.this_month_start,
            creation_datetime=dh.now - dh.one_day,
            completed_datetime=dh.now - dh.one_day,
            operator_version="registry/costmanagement-metrics-operator:v3.9.0",
            state={},
        )
        self.baker.make(
            CostUsageReportManifest,
            provider=self.ocp,
            billing_period_start_datetime=dh.this_month_start,
            creation_datetime=dh.now,
            completed_datetime=None,
            operator_version="registry/costmanagement-metrics-operator:v4.3.0",
            state={
                ManifestStep.DOWNLOAD: {ManifestState.START: "t0", ManifestState.END: "t1", "time_taken_seconds": 3},
                ManifestStep.PROCESSING: {ManifestState.START: "t2"},
            },
        )
        self.baker.make(
            CostUsageReportManifest,
            provider=self.aws,
            billing_period_start_datetime=dh.last_month_start,
            creation_datetime=dh.now - dh.one_day,
            completed_datetime=dh.now - dh.one_day,
            state={ManifestStep.SUMMARY: {ManifestState.START: "t0", ManifestState.FAILED: "t1"}},
        )
        with tenant_context(self.tenant):
            cost_model = self.baker.make(CostModel, name="bulk-test", source_type=Provider.PROVIDER_OCP)
            self.baker.make(CostModelMap, provider_uuid=self.ocp.uuid, cost_model=cost_model)

    def _details(self, uuids, bulk):
        sources = [{"uuid": uuid} for uuid in uuids]
        view = SourcesViewSet()
        # A request runs under the tenant schema (ProviderManager.get_cost_models relies on it).
        with tenant_context(self.tenant):
            if bulk:
                view._add_provider_details_bulk(sources, self.tenant)
            else:
                view._add_provider_details(sources, self.tenant)
        return sources

    def test_bulk_matches_per_source_details(self):
        """Every field matches, including infrastructure, operator context, cost models and unlinked sources."""
        uuids = [*Provider.objects.values_list("uuid", flat=True), uuid4(), None, "not-a-uuid"]
        legacy = self._details(copy.deepcopy(uuids), bulk=False)
        bulk = self._details(copy.deepcopy(uuids), bulk=True)
        self.assertEqual(bulk, legacy)

        by_uuid = {str(source["uuid"]): source for source in bulk}
        ocp = by_uuid[str(self.ocp.uuid)]
        # The branches the comparison above must have exercised.
        self.assertEqual(ocp["infrastructure"]["id"], 987654)
        self.assertEqual(ocp["infrastructure"]["cloud_provider_state"][ManifestStep.SUMMARY]["state"], "failed")
        self.assertEqual(ocp["status"][ManifestStep.PROCESSING]["state"], "in-progress")
        self.assertEqual(
            ocp["additional_context"]["operator_version"], "registry/costmanagement-metrics-operator:v4.3.0"
        )
        self.assertEqual(ocp["cost_models"][0]["name"], "bulk-test")
        self.assertTrue(ocp["current_month_data"])
        self.assertFalse(by_uuid[str(self.ocp_without_data.uuid)]["has_data"])
        self.assertFalse(by_uuid["None"]["provider_linked"])

    def test_bulk_query_count_does_not_grow_with_sources(self):
        """The bulk path issues the same number of queries for one source as for all of them."""
        all_uuids = list(Provider.objects.values_list("uuid", flat=True))
        self.assertGreater(len(all_uuids), 3)
        with CaptureQueriesContext(connection) as one:
            bulk_source_details([self.ocp.uuid], self.tenant)
        with CaptureQueriesContext(connection) as many:
            bulk_source_details(all_uuids, self.tenant)
        self.assertEqual(len(many), len(one))

    def test_bulk_source_details_without_valid_providers(self):
        """Unknown or malformed uuids return no details and run a single query at most."""
        self.assertEqual(bulk_source_details([None, "nope", uuid4()], self.tenant), {})


class SourcesListBulkFlagTest(IamTestCase):
    """The list endpoint chooses the provider-details path by feature flag."""

    def setUp(self):
        super().setUp()
        caches[CacheEnum.api].clear()
        self.addCleanup(caches[CacheEnum.api].clear)

    def _list(self, flag_enabled):
        with (
            patch("sources.api.view.is_feature_flag_enabled_by_schema", return_value=flag_enabled),
            patch.object(SourcesViewSet, "_add_provider_details_bulk") as bulk,
            patch.object(SourcesViewSet, "_add_provider_details") as legacy,
        ):
            response = self.client.get(reverse("sources-list"), **self.request_context["request"].META)
        self.assertEqual(response.status_code, 200)
        return bulk, legacy

    def test_flag_enabled_uses_bulk_details(self):
        bulk, legacy = self._list(flag_enabled=True)
        bulk.assert_called_once()
        legacy.assert_not_called()

    def test_flag_disabled_uses_per_source_details(self):
        bulk, legacy = self._list(flag_enabled=False)
        legacy.assert_called_once()
        bulk.assert_not_called()
