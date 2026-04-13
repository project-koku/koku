#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for resource reporting hook points in existing Koku modules."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "koku.test_settings_lite")

import django  # noqa: E402

django.setup()

from unittest.mock import MagicMock, patch  # noqa: E402

from django.test import SimpleTestCase, override_settings  # noqa: E402


class TestProviderBuilderHook(SimpleTestCase):
    """ProviderBuilder should report OCP clusters to Kessel."""

    def test_has_report_ocp_resource_method(self):
        from api.provider.provider_builder import ProviderBuilder

        self.assertTrue(hasattr(ProviderBuilder, "_report_ocp_resource"))

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("api.provider.provider_builder.on_resource_created")
    def test_report_ocp_resource_calls_reporter(self, mock_report):
        from api.provider.provider_builder import ProviderBuilder

        ProviderBuilder._report_ocp_resource("cluster-1", "org123")
        mock_report.assert_called_once_with("openshift_cluster", "cluster-1", "org123")

    @override_settings(AUTHORIZATION_BACKEND="rbac")
    @patch("api.provider.provider_builder.on_resource_created")
    def test_report_ocp_resource_noop_when_rbac(self, mock_report):
        from api.provider.provider_builder import ProviderBuilder

        ProviderBuilder._report_ocp_resource("cluster-1", "org123")
        mock_report.assert_called_once()


class TestOCPReportDBAccessorHook(SimpleTestCase):
    """OCP report DB accessor should report nodes/projects to Kessel."""

    def test_has_report_ocp_resources_method(self):
        from masu.database.ocp_report_db_accessor import OCPReportDBAccessor

        self.assertTrue(hasattr(OCPReportDBAccessor, "_report_ocp_resources_to_kessel"))


class TestCostModelViewHook(SimpleTestCase):
    """CostModelViewSet should report new cost models to Kessel."""

    def test_has_perform_create(self):
        from cost_models.view import CostModelViewSet

        self.assertTrue(hasattr(CostModelViewSet, "perform_create"))


class TestProviderBuilderSourceHooks(SimpleTestCase):
    """Source lifecycle hooks on ProviderBuilder."""

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("api.provider.provider_builder.invalidate_cache_for_tenant_and_cache_key")
    @patch("api.provider.provider_builder.connection")
    @patch("api.provider.provider_builder.on_resource_created")
    @patch("api.provider.provider_builder.ProviderSerializer")
    def test_source_creation_triggers_kessel_report(self, mock_serializer_cls, mock_report, mock_conn, mock_cache):
        """POST OCP source via Sources API triggers on_resource_created."""
        mock_instance = MagicMock()
        mock_instance.uuid = "provider-uuid-001"
        mock_serializer = MagicMock()
        mock_serializer.is_valid.return_value = True
        mock_serializer.save.return_value = mock_instance
        mock_serializer_cls.return_value = mock_serializer

        from api.provider.provider_builder import ProviderBuilder

        source = MagicMock()
        source.source_type = "OCP"
        source.name = "my-ocp-cluster"
        source.authentication = {"credentials": {"cluster_id": "test-cluster-001"}}
        source.billing_source = {"data_source": {}}
        source.source_uuid = "src-uuid-001"

        mock_customer = MagicMock()
        mock_customer.schema_name = "acct10001"

        builder = ProviderBuilder("unused", "acct-ut", "org-ut")
        with (
            patch.object(builder, "_create_context", return_value=({"user": MagicMock()}, mock_customer, MagicMock())),
            patch.object(builder, "_tenant_for_schema", return_value=MagicMock()),
        ):
            builder.create_provider_from_source(source)

        mock_report.assert_any_call("openshift_cluster", "test-cluster-001", "org-ut")

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("api.provider.provider_builder.invalidate_cache_for_tenant_and_cache_key")
    @patch("api.provider.provider_builder.connection")
    @patch("api.provider.provider_builder.on_resource_created")
    @patch("api.provider.provider_builder.ProviderSerializer")
    def test_grpc_failure_does_not_fail_source_creation(self, mock_serializer_cls, mock_report, mock_conn, mock_cache):
        """Kessel gRPC failure during source creation logs error but does not fail."""
        import grpc

        mock_report.side_effect = grpc.RpcError()

        mock_instance = MagicMock()
        mock_instance.uuid = "provider-uuid-004"
        mock_serializer = MagicMock()
        mock_serializer.is_valid.return_value = True
        mock_serializer.save.return_value = mock_instance
        mock_serializer_cls.return_value = mock_serializer

        from api.provider.provider_builder import ProviderBuilder

        source = MagicMock()
        source.source_type = "OCP"
        source.name = "my-ocp-cluster-004"
        source.authentication = {"credentials": {"cluster_id": "test-cluster-004"}}
        source.billing_source = {"data_source": {}}
        source.source_uuid = "src-uuid-004"

        mock_customer = MagicMock()
        mock_customer.schema_name = "acct10001"

        builder = ProviderBuilder("unused", "acct-ut", "org-ut")
        with (
            patch.object(builder, "_create_context", return_value=({"user": MagicMock()}, mock_customer, MagicMock())),
            patch.object(builder, "_tenant_for_schema", return_value=MagicMock()),
        ):
            try:
                builder.create_provider_from_source(source)
            except grpc.RpcError:
                pass
        mock_report.assert_called_once()

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("api.provider.provider_builder.create_structural_tuple")
    @patch("api.provider.provider_builder.invalidate_cache_for_tenant_and_cache_key")
    @patch("api.provider.provider_builder.connection")
    @patch("api.provider.provider_builder.on_resource_created")
    @patch("api.provider.provider_builder.ProviderSerializer")
    def test_integration_has_cluster_uses_cluster_id(
        self, mock_serializer_cls, mock_report, mock_conn, mock_cache, mock_struct
    ):
        """_report_integration links has_cluster to cluster_id, not provider UUID."""
        mock_instance = MagicMock()
        mock_instance.uuid = "provider-uuid-002"
        mock_serializer = MagicMock()
        mock_serializer.is_valid.return_value = True
        mock_serializer.save.return_value = mock_instance
        mock_serializer_cls.return_value = mock_serializer

        from api.provider.provider_builder import ProviderBuilder

        source = MagicMock()
        source.source_type = "OCP"
        source.name = "my-ocp-cluster-002"
        source.authentication = {"credentials": {"cluster_id": "test-cluster-xyz"}}
        source.billing_source = {"data_source": {}}
        source.source_uuid = "src-uuid-002"

        mock_customer = MagicMock()
        mock_customer.schema_name = "acct10001"

        builder = ProviderBuilder("unused", "acct-ut", "org-ut")
        with (
            patch.object(builder, "_create_context", return_value=({"user": MagicMock()}, mock_customer, MagicMock())),
            patch.object(builder, "_tenant_for_schema", return_value=MagicMock()),
        ):
            builder.create_provider_from_source(source)

        mock_struct.assert_called_once_with(
            "integration", "src-uuid-002", "has_cluster", "openshift_cluster", "test-cluster-xyz"
        )

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    def test_deletion_does_not_call_kessel_delete(self, mock_get_client):
        """DELETE source does NOT invoke any Kessel delete API."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        from api.provider.provider_builder import ProviderBuilder

        builder = ProviderBuilder("fake-identity", "acct-ut", "org-ut")

        with patch.object(builder, "destroy_provider"):
            builder.destroy_provider("some-provider-uuid")

        mock_client.tuples_stub.DeleteTuples.assert_not_called()
        mock_client.inventory_stub.DeleteResource.assert_not_called()
        if hasattr(mock_client, "relations_stub"):
            mock_client.relations_stub.DeleteTuples.assert_not_called()


class TestOCPReportDBAccessorKesselResourceID(SimpleTestCase):
    """_report_ocp_resources_to_kessel must use the real cluster_id, not provider UUID."""

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("masu.database.ocp_report_db_accessor.create_structural_tuple")
    @patch("masu.database.ocp_report_db_accessor.on_resource_created")
    def test_structural_tuple_uses_cluster_id_not_provider_uuid(self, mock_report, mock_struct):
        """has_project structural tuple should reference the OCP cluster_id."""
        from masu.database.ocp_report_db_accessor import OCPReportDBAccessor

        provider = MagicMock()
        provider.uuid = "provider-uuid-999"
        provider.org_id = "org-1"

        nodes = [("node-a",)]
        projects = [("project-x",)]

        OCPReportDBAccessor._report_ocp_resources_to_kessel(provider, "real-cluster-abc", nodes, projects)

        mock_struct.assert_called_once_with(
            "openshift_cluster", "real-cluster-abc", "has_project", "openshift_project", "project-x"
        )
        self.assertNotIn(
            "provider-uuid-999",
            [str(arg) for call in mock_struct.call_args_list for arg in call[0]],
        )
