#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report Queries."""
from django_tenants.utils import tenant_context

from api.functions import JSONBObjectKeys
from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.ocp.view import OCPTagView
from api.utils import DateHelper
from reporting.models import OCPStorageVolumeLabelSummary
from reporting.models import OCPUsageLineItemDailySummary
from reporting.models import OCPUsagePodLabelSummary
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.ocp.models import OCPTagsValues


class OCPTagQueryHandlerTest(IamTestCase):
    """Tests for the OCP report query handler."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()

    def test_execute_query_no_query_parameters(self):
        """Test that the execute query runs properly with no query."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_wildcard_value_parameters(self):
        """Test that get tag values runs properly with value query as wildcard."""
        key = "version"
        value = "*"
        url = f"?filter[value]={value}"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        handler.key = key
        with tenant_context(self.tenant):
            storage_tags = (
                OCPTagsValues.objects.filter(key__exact=key, value__icontains="").values("value").distinct().all()
            )
            tag_values = [tag.get("value") for tag in storage_tags]
        expected = {"key": key, "values": tag_values}
        result = handler.get_tag_values()
        self.assertEqual(result[0].get("key"), expected.get("key"))
        self.assertEqual(sorted(result[0].get("values")), sorted(expected.get("values")))

    def test_execute_query_10_day_parameters(self):
        """Test that the execute query runs properly with 10 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_30_day_parameters(self):
        """Test that the execute query runs properly with 30 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-30&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -30)

    def test_execute_query_10_day_parameters_only_keys(self):
        """Test that the execute query runs properly with 10 day query."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily&key_only=True"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_execute_query_month_parameters(self):
        """Test that the execute query runs properly with single month query."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -1)

    def test_execute_query_two_month_parameters(self):
        """Test that the execute query runs properly with two month query."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "month")
        self.assertEqual(handler.time_scope_value, -2)

    def test_execute_query_for_project(self):
        """Test that the execute query runs properly with project query."""
        namespace = None
        with tenant_context(self.tenant):
            namespace_obj = OCPUsageLineItemDailySummary.objects.values("namespace").first()
            namespace = namespace_obj.get("namespace")

        url = f"?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily&filter[project]={namespace}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertEqual(handler.time_scope_units, "day")
        self.assertEqual(handler.time_scope_value, -10)

    def test_get_tag_keys_filter_true(self):
        """Test that not all tag keys are returned with a filter."""
        url = (
            "?filter[time_scope_units]=month&filter[time_scope_value]=-2"
            "&filter[resolution]=monthly&filter[enabled]=True"
        )
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)

        with tenant_context(self.tenant):
            usage_tag_keys = list(
                OCPUsageLineItemDailySummary.objects.filter(usage_start__lte=self.dh.this_month_start)
                .annotate(tag_keys=JSONBObjectKeys("pod_labels"))
                .values_list("tag_keys", flat=True)
                .distinct()
                .all()
            )
            storage_tag_keys = list(
                OCPUsageLineItemDailySummary.objects.filter(usage_start__lte=self.dh.this_month_start)
                .annotate(tag_keys=JSONBObjectKeys("volume_labels"))
                .values_list("tag_keys", flat=True)
                .distinct()
                .all()
            )
            tag_keys = list(set(usage_tag_keys + storage_tag_keys))

        result = handler.get_tag_keys(filters=True)
        self.assertEqual(sorted(result), sorted(tag_keys))
        self.assertNotIn("disabled", result)
        self.assertNotIn("disabled", tag_keys)
        self.assertIn("app", result)
        self.assertIn("app", tag_keys)

        url = (
            "?filter[time_scope_units]=month&filter[time_scope_value]=-2"
            "&filter[resolution]=monthly&filter[enabled]=true"
        )
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        result = handler.get_tag_keys(filters=True)
        self.assertEqual(sorted(result), sorted(tag_keys))

    def test_get_tag_keys_filter_false(self):
        """Test that all tag keys are returned with no filter."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)

        with tenant_context(self.tenant):
            usage_tag_keys = list(
                OCPUsageLineItemDailySummary.objects.annotate(tag_keys=JSONBObjectKeys("pod_labels"))
                .values_list("tag_keys", flat=True)
                .distinct()
                .all()
            )
            storage_tag_keys = list(
                OCPUsageLineItemDailySummary.objects.annotate(tag_keys=JSONBObjectKeys("volume_labels"))
                .values_list("tag_keys", flat=True)
                .distinct()
                .all()
            )
            tag_keys = list(set(usage_tag_keys + storage_tag_keys))

        result = handler.get_tag_keys(filters=False)
        self.assertEqual(sorted(result), sorted(tag_keys))
        self.assertNotIn("disabled", result)
        self.assertNotIn("disabled", tag_keys)
        self.assertIn("app", result)
        self.assertIn("app", tag_keys)

    def test_get_tag_type_filter_pod(self):
        """Test that all usage tags are returned with pod type filter."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly&filter[type]=pod"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)

        with tenant_context(self.tenant):
            tag_keys = list(
                OCPUsageLineItemDailySummary.objects.annotate(tag_keys=JSONBObjectKeys("pod_labels"))
                .values_list("tag_keys", flat=True)
                .distinct()
                .all()
            )

        result = handler.get_tag_keys(filters=False)
        self.assertEqual(sorted(result), sorted(tag_keys))
        self.assertNotIn("disabled", result)
        self.assertNotIn("disabled", tag_keys)
        self.assertIn("app", result)
        self.assertIn("app", tag_keys)

        result = handler.get_tag_keys(filters=True)
        self.assertEqual(sorted(result), sorted(tag_keys))

    def test_get_tag_type_filter_storage(self):
        """Test that all storage tags are returned with storage type filter."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly&filter[type]=storage"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)

        with tenant_context(self.tenant):
            tag_keys = list(OCPStorageVolumeLabelSummary.objects.values_list("key", flat=True).distinct().all())

        result = handler.get_tag_keys(filters=False)
        self.assertEqual(sorted(result), sorted(tag_keys))

    def test_get_tag_cluster_filter(self):
        """Test that tags from a cluster are returned with the cluster filter."""
        # Note: By default the OCP tag handler only grabs enabled keys
        url = "?filter[cluster]=OCP-on-AWS&filter[type]=storage"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)

        with tenant_context(self.tenant):
            storage_tag_keys = list(
                OCPStorageVolumeLabelSummary.objects.filter(report_period__cluster_id__contains="OCP-on-AWS")
                .values_list("key", flat=True)
                .distinct()
                .all()
            )
            enabled = list(EnabledTagKeys.objects.filter(provider_type="OCP").values_list("key", flat=True).all())
            tag_keys = [tag for tag in storage_tag_keys if tag in enabled]

        result = handler.get_tag_keys()
        self.assertEqual(sorted(result), sorted(tag_keys))

    def test_get_tags_for_key_filter(self):
        """Test that get tags runs properly with key query."""
        key = "app"
        url = f"?filter[key]={key}"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        with tenant_context(self.tenant):
            storage_tags = (
                OCPStorageVolumeLabelSummary.objects.filter(key__exact=key).values("values").distinct().all()
            )
            storage_values = [value for tag in storage_tags for value in tag.get("values")]
            usage_tags = OCPUsagePodLabelSummary.objects.filter(key__exact=key).values("values").distinct().all()
            usage_values = [value for tag in usage_tags for value in tag.get("values")]
            # remove duplicates from the values
            tag_values = list(dict.fromkeys(storage_values + usage_values))
        expected = {"key": key, "values": tag_values}
        result = handler.get_tags()
        self.assertEqual(result[0].get("key"), expected.get("key"))
        self.assertEqual(sorted(result[0].get("values")), sorted(expected.get("values")))

    def test_get_tag_values_for_value_filter(self):
        """Test that get tag values runs properly with value query."""
        key = "version"
        value = "Andromeda"
        url = f"?filter[value]={value}"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        handler.key = key
        with tenant_context(self.tenant):
            storage_tags = (
                OCPTagsValues.objects.filter(key__exact=key, value__icontains=value).values("value").distinct().all()
            )
            tag_values = [tag.get("value") for tag in storage_tags]
        expected = {"key": key, "values": tag_values}
        result = handler.get_tag_values()
        self.assertEqual(result[0].get("key"), expected.get("key"))
        self.assertEqual(sorted(result[0].get("values")), sorted(expected.get("values")))

    def test_get_tag_values_for_value_filter_partial_match(self):
        """Test that the execute query runs properly with value query."""
        key = "version"
        value = "a"
        url = f"/version/?filter[value]={value}"
        query_params = self.mocked_query_params(url, OCPTagView)
        # the mocked query parameters dont include the key from the url so it needs to be added
        query_params.kwargs = {"key": key}
        handler = OCPTagQueryHandler(query_params)
        with tenant_context(self.tenant):
            storage_tags = (
                OCPTagsValues.objects.filter(key__exact=key, value__icontains=value).values("value").distinct().all()
            )
            storage_values = [tag.get("value") for tag in storage_tags]
            usage_tags = (
                OCPTagsValues.objects.filter(key__exact=key, value__icontains=value).values("value").distinct().all()
            )
            usage_values = [tag.get("value") for tag in usage_tags]
            # remove duplicates from the values
            tag_values = list(dict.fromkeys(storage_values + usage_values))
        expected = {"key": key, "values": tag_values}
        result = handler.get_tag_values()
        self.assertEqual(result[0].get("key"), expected.get("key"))
        self.assertEqual(sorted(result[0].get("values")), sorted(expected.get("values")))

    @RbacPermissions({"openshift.node": {"read": ["aws_compute1"]}})
    def test_get_tag_values_for_value_filter_RBAC_node(self):
        """Test that the execute query runs properly with value query and an RBAC restriction on node."""
        key = "app"
        value = "c"
        url = f"/app/?filter[value]={value}"
        query_params = self.mocked_query_params(url, OCPTagView)
        # the mocked query parameters dont include the key from the url so it needs to be added
        query_params.kwargs = {"key": key}
        handler = OCPTagQueryHandler(query_params)
        with tenant_context(self.tenant):
            tags = (
                OCPTagsValues.objects.filter(key__exact=key, value__icontains=value).values("value").distinct().all()
            )
            tag_values = [tag.get("value") for tag in tags]

        expected = {"key": key, "values": tag_values}
        result = handler.get_tag_values()
        self.assertEqual(result[0].get("key"), expected.get("key"))
        self.assertEqual(sorted(result[0].get("values")), sorted(expected.get("values")))

    @RbacPermissions({"openshift.cluster": {"read": ["my-ocp-cluster-2"]}})
    def test_get_tag_values_for_value_filter_RBAC_cluster(self):
        """Test that the execute query runs properly with value query and an RBAC restriction on cluster."""
        key = "app"
        value = "b"
        url = f"/app/?filter[value]={value}"
        query_params = self.mocked_query_params(url, OCPTagView)
        # the mocked query parameters dont include the key from the url so it needs to be added
        query_params.kwargs = {"key": key}
        handler = OCPTagQueryHandler(query_params)
        with tenant_context(self.tenant):
            tags = (
                OCPTagsValues.objects.filter(key__exact=key, value__icontains=value).values("value").distinct().all()
            )
            tag_values = [tag.get("value") for tag in tags]

        expected = {"key": key, "values": tag_values}
        result = handler.get_tag_values()
        self.assertEqual(result[0].get("key"), expected.get("key"))
        self.assertEqual(sorted(result[0].get("values")), sorted(expected.get("values")))

    def test_set_access_filters(self):
        """Test that the execute query runs properly with value query and an RBAC restriction on cluster."""
        key = "app"
        value = "b"
        url = f"/app/?filter[value]={value}"
        query_params = self.mocked_query_params(url, OCPTagView)
        # the mocked query parameters dont include the key from the url so it needs to be added
        query_params.kwargs = {"key": key}
        handler = OCPTagQueryHandler(query_params)
        access = ["aws_compute1"]
        filt = {"field": "nodes", "operation": "contained_by"}
        filters = QueryFilterCollection()
        handler.set_access_filters(access, filt, filters)
        expected = [QueryFilter(field="nodes", operation="contained_by", parameter=["aws_compute1"])]
        self.assertEqual(filters._filters, expected)

    def test_set_access_filters_with_list(self):
        """Test that the execute query runs properly with value query and an RBAC restriction on cluster."""
        key = "app"
        value = "b"
        url = f"/app/?filter[value]={value}"
        query_params = self.mocked_query_params(url, OCPTagView)
        # the mocked query parameters dont include the key from the url so it needs to be added
        query_params.kwargs = {"key": key}
        handler = OCPTagQueryHandler(query_params)
        access = ["my-ocp-cluster-2"]
        filt = [
            {"field": "report_period__cluster_id", "operation": "icontains", "composition_key": "cluster_filter"},
            {"field": "report_period__cluster_alias", "operation": "icontains", "composition_key": "cluster_filter"},
        ]
        filters = QueryFilterCollection()
        handler.set_access_filters(access, filt, filters)
        expected = []
        expected.append(
            QueryFilter(field="report_period__cluster_id", operation="icontains", parameter=["my-ocp-cluster-2"])
        )
        expected.append(
            QueryFilter(field="report_period__cluster_alias", operation="icontains", parameter=["my-ocp-cluster-2"])
        )
        self.assertEqual(filters._filters, expected)

    def test_category_filter(self):
        """Test that we can filter by category on the tags endpoint."""
        categories = {
            "Platform": [
                {"enabled": True, "key": "app", "values": ["mobile", "temperature"]},
                {"enabled": True, "key": "storageclass", "values": ["Ruby"]},
            ],
            "FAKE_CATEGORY": [],
            "*": [],
        }
        for category in categories.keys():
            with self.subTest(category=category):
                with tenant_context(self.tenant):
                    query_params = self.mocked_query_params(f"?filter[category]={category}", OCPTagView)
                    handler = OCPTagQueryHandler(query_params)
                    result_value = handler.execute_query().get("data")
                    if category == "*":
                        self.assertNotEqual(result_value, categories[category])
                    else:
                        self.assertEqual(result_value, categories[category])
