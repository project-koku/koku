#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the resource reporter module (Inventory API v1beta2)."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "koku.test_settings_lite")

import django  # noqa: E402

django.setup()

from unittest.mock import MagicMock, patch  # noqa: E402

from django.test import SimpleTestCase, override_settings  # noqa: E402


class TestResourceReporterImport(SimpleTestCase):
    """The resource_reporter module must be importable."""

    def test_import_on_resource_created(self):
        from koku_rebac.resource_reporter import on_resource_created

        self.assertTrue(callable(on_resource_created))


class TestResourceReporterNoOp(SimpleTestCase):
    """When backend is rbac, on_resource_created is a no-op."""

    @override_settings(AUTHORIZATION_BACKEND="rbac")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    def test_no_op_when_rbac(self, mock_get_client):
        from koku_rebac.resource_reporter import on_resource_created

        on_resource_created("openshift_cluster", "cluster-1", "org123")
        mock_get_client.assert_not_called()


class TestResourceReporterActive(SimpleTestCase):
    """When backend is rebac, on_resource_created reports to Kessel and creates SpiceDB tuples."""

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter._create_resource_tuples")
    @patch("koku_rebac.resource_reporter.KesselSyncedResource")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    def test_calls_inventory_when_rebac(self, mock_get_client, mock_model, mock_create_tuples):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_model.objects.update_or_create.return_value = (MagicMock(), True)

        from koku_rebac.resource_reporter import on_resource_created

        on_resource_created("openshift_cluster", "cluster-1", "org123")
        mock_client.inventory_stub.ReportResource.assert_called_once()

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter._create_resource_tuples")
    @patch("koku_rebac.resource_reporter.KesselSyncedResource")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    def test_calls_create_tuples_when_rebac(self, mock_get_client, mock_model, mock_create_tuples):
        """on_resource_created must call _create_resource_tuples to make the resource discoverable."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_model.objects.update_or_create.return_value = (MagicMock(), True)

        from koku_rebac.resource_reporter import on_resource_created

        on_resource_created("openshift_cluster", "cluster-1", "org123")
        mock_create_tuples.assert_called_once_with("openshift_cluster", "cluster-1", "org123")

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter._create_resource_tuples")
    @patch("koku_rebac.resource_reporter.KesselSyncedResource")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    def test_grpc_error_still_creates_tuples(self, mock_get_client, mock_model, mock_create_tuples):
        """Both phases are independent; Inventory failure doesn't block tuple creation."""
        import grpc

        mock_client = MagicMock()
        mock_client.inventory_stub.ReportResource.side_effect = grpc.RpcError()
        mock_get_client.return_value = mock_client
        mock_model.objects.update_or_create.return_value = (MagicMock(), True)

        from koku_rebac.resource_reporter import on_resource_created

        on_resource_created("openshift_cluster", "cluster-1", "org123")
        mock_create_tuples.assert_called_once_with("openshift_cluster", "cluster-1", "org123")

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter._create_resource_tuples", return_value=True)
    @patch("koku_rebac.resource_reporter.KesselSyncedResource")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    def test_tracks_kessel_synced_true_when_both_phases_succeed(self, mock_get_client, mock_model, mock_create_tuples):
        """kessel_synced must be True when both ReportResource and tuple creation succeed."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_model.objects.update_or_create.return_value = (MagicMock(), True)

        from koku_rebac.resource_reporter import on_resource_created

        on_resource_created("openshift_cluster", "cluster-1", "org123")
        call_kwargs = mock_model.objects.update_or_create.call_args
        self.assertTrue(call_kwargs[1]["defaults"]["kessel_synced"])

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter._create_resource_tuples", return_value=False)
    @patch("koku_rebac.resource_reporter.KesselSyncedResource")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    def test_tracks_kessel_synced_false_when_both_phases_fail(self, mock_get_client, mock_model, mock_create_tuples):
        """kessel_synced must be False when both ReportResource and tuple creation fail."""
        import grpc

        mock_client = MagicMock()
        mock_client.inventory_stub.ReportResource.side_effect = grpc.RpcError()
        mock_get_client.return_value = mock_client
        mock_model.objects.update_or_create.return_value = (MagicMock(), True)

        from koku_rebac.resource_reporter import on_resource_created

        on_resource_created("openshift_cluster", "cluster-1", "org123")
        call_kwargs = mock_model.objects.update_or_create.call_args
        self.assertFalse(call_kwargs[1]["defaults"]["kessel_synced"])

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter._create_resource_tuples", return_value=False)
    @patch("koku_rebac.resource_reporter.KesselSyncedResource")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    def test_tracks_kessel_synced_false_when_tuple_creation_fails(self, mock_get_client, mock_model, mock_create_tuples):
        """kessel_synced must be False when tuple creation fails even if ReportResource succeeds."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_model.objects.update_or_create.return_value = (MagicMock(), True)

        from koku_rebac.resource_reporter import on_resource_created

        on_resource_created("openshift_cluster", "cluster-1", "org123")
        call_kwargs = mock_model.objects.update_or_create.call_args
        self.assertFalse(call_kwargs[1]["defaults"]["kessel_synced"])

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter._create_resource_tuples")
    @patch("koku_rebac.resource_reporter.KesselSyncedResource.objects")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    def test_idempotent_reporting(self, mock_get_client, mock_objects, mock_create_tuples):
        """Re-reporting the same resource succeeds without errors."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_obj = MagicMock()
        mock_objects.update_or_create.return_value = (mock_obj, False)

        from koku_rebac.resource_reporter import on_resource_created

        on_resource_created("openshift_cluster", "cluster-1", "org-idem")
        on_resource_created("openshift_cluster", "cluster-1", "org-idem")

        self.assertEqual(mock_client.inventory_stub.ReportResource.call_count, 2)
        self.assertEqual(mock_create_tuples.call_count, 2)
        self.assertEqual(mock_objects.update_or_create.call_count, 2)


class TestReportResourceRequest(SimpleTestCase):
    """Verify the ReportResourceRequest proto message structure."""

    def test_request_includes_representations_with_workspace_id(self):
        from koku_rebac.resource_reporter import _build_report_request

        req = _build_report_request("openshift_cluster", "cluster-1", "org-42")
        self.assertEqual(dict(req.representations.common), {"workspace_id": "org-42"})

    def test_request_includes_metadata_fields(self):
        from koku_rebac.resource_reporter import _build_report_request

        req = _build_report_request("aws_account", "acct-1", "org-42")
        self.assertEqual(req.representations.metadata.local_resource_id, "acct-1")
        self.assertTrue(req.representations.metadata.api_href.startswith("/api/cost-management/v1/"))

    def test_ocp_resources_get_write_visibility_immediate(self):
        from kessel.inventory.v1beta2 import write_visibility_pb2
        from koku_rebac.resource_reporter import _build_report_request

        for ocp_type in ("openshift_cluster", "openshift_node", "openshift_project"):
            req = _build_report_request(ocp_type, "id-1", "org-1")
            self.assertEqual(
                req.write_visibility,
                write_visibility_pb2.IMMEDIATE,
                f"{ocp_type} should use IMMEDIATE write visibility",
            )

    def test_non_ocp_resources_no_immediate(self):
        from kessel.inventory.v1beta2 import write_visibility_pb2
        from koku_rebac.resource_reporter import _build_report_request

        for non_immediate_type in ("settings", "custom_report", "unknown_type"):
            req = _build_report_request(non_immediate_type, "id-1", "org-1")
            self.assertNotEqual(
                req.write_visibility,
                write_visibility_pb2.IMMEDIATE,
                f"{non_immediate_type} should NOT use IMMEDIATE write visibility",
            )

    def test_reporter_type_is_cost_management(self):
        from koku_rebac.resource_reporter import _build_report_request

        req = _build_report_request("openshift_cluster", "cluster-1", "org-1")
        self.assertEqual(req.reporter_type, "cost_management")

    def test_type_field_format(self):
        from koku_rebac.resource_reporter import _build_report_request

        req = _build_report_request("openshift_cluster", "cluster-1", "org-1")
        self.assertEqual(req.type, "openshift_cluster")

        req2 = _build_report_request("aws_account", "acct-1", "org-1")
        self.assertEqual(req2.type, "aws_account")

    def test_inventory_id_includes_org_and_type(self):
        from koku_rebac.resource_reporter import _build_report_request

        req = _build_report_request("cost_model", "cm-1", "org-77")
        self.assertEqual(req.inventory_id, "org-77/cost_model/cm-1")


class TestOnResourceDeleted(SimpleTestCase):
    """on_resource_deleted calls DeleteResource, deletes SpiceDB tuples, and removes the tracking row."""

    @override_settings(AUTHORIZATION_BACKEND="rbac")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    def test_no_op_when_rbac(self, mock_get_client):
        from koku_rebac.resource_reporter import on_resource_deleted

        on_resource_deleted("openshift_cluster", "cluster-1", "org123")
        mock_get_client.assert_not_called()

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter._delete_resource_tuples")
    @patch("koku_rebac.resource_reporter.KesselSyncedResource")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    def test_calls_both_cleanup_apis(self, mock_get_client, mock_model, mock_delete_tuples):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        from koku_rebac.resource_reporter import on_resource_deleted

        on_resource_deleted("openshift_cluster", "cluster-1", "org123")
        mock_client.inventory_stub.DeleteResource.assert_called_once()
        mock_delete_tuples.assert_called_once_with("openshift_cluster", "cluster-1")

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter._delete_resource_tuples")
    @patch("koku_rebac.resource_reporter.KesselSyncedResource")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    def test_always_deletes_tracking_row(self, mock_get_client, mock_model, mock_delete_tuples):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        from koku_rebac.resource_reporter import on_resource_deleted

        on_resource_deleted("openshift_cluster", "cluster-1", "org123")
        mock_model.objects.filter.assert_called_once_with(
            resource_type="openshift_cluster", resource_id="cluster-1", org_id="org123"
        )
        mock_model.objects.filter.return_value.delete.assert_called_once()

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter._delete_resource_tuples")
    @patch("koku_rebac.resource_reporter.KesselSyncedResource")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    def test_grpc_error_still_cleans_tuples_and_tracking(self, mock_get_client, mock_model, mock_delete_tuples):
        """Both cleanup steps are independent; Inventory failure doesn't block Relations cleanup."""
        import grpc

        mock_client = MagicMock()
        mock_client.inventory_stub.DeleteResource.side_effect = grpc.RpcError()
        mock_get_client.return_value = mock_client

        from koku_rebac.resource_reporter import on_resource_deleted

        on_resource_deleted("openshift_cluster", "cluster-1", "org123")
        mock_delete_tuples.assert_called_once_with("openshift_cluster", "cluster-1")
        mock_model.objects.filter.return_value.delete.assert_called_once()


class TestDeleteResourceRequest(SimpleTestCase):
    """Verify the DeleteResourceRequest proto message structure."""

    def test_request_has_correct_resource_reference(self):
        from koku_rebac.resource_reporter import _build_delete_request

        req = _build_delete_request("openshift_cluster", "cluster-1")
        self.assertEqual(req.reference.resource_type, "openshift_cluster")
        self.assertEqual(req.reference.resource_id, "cluster-1")

    def test_request_has_reporter_reference(self):
        from koku_rebac.resource_reporter import _build_delete_request

        req = _build_delete_request("openshift_cluster", "cluster-1")
        self.assertEqual(req.reference.reporter.type, "cost_management")
        self.assertEqual(req.reference.reporter.instance_id, "cluster-1")


class TestCleanupOrphanedKesselResources(SimpleTestCase):
    """cleanup_orphaned_kessel_resources handles data expiry cleanup."""

    @override_settings(AUTHORIZATION_BACKEND="rbac")
    def test_returns_zero_when_rbac(self):
        from koku_rebac.resource_reporter import cleanup_orphaned_kessel_resources

        result = cleanup_orphaned_kessel_resources("provider-uuid", "org123")
        self.assertEqual(result, 0)

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    @patch("koku_rebac.resource_reporter.KesselSyncedResource")
    def test_skips_when_provider_still_exists(self, mock_model, mock_get_client):
        from koku_rebac.resource_reporter import cleanup_orphaned_kessel_resources

        with patch("api.models.Provider.objects") as mock_provider_objects:
            mock_provider_objects.filter.return_value.exists.return_value = True
            result = cleanup_orphaned_kessel_resources("provider-uuid", "org123")

        self.assertEqual(result, 0)
        mock_get_client.assert_not_called()

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter._delete_resource_tuples")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    @patch("koku_rebac.resource_reporter.KesselSyncedResource")
    def test_cleans_up_tracked_resources_when_provider_gone(self, mock_model, mock_get_client, mock_delete_tuples):
        from koku_rebac.resource_reporter import cleanup_orphaned_kessel_resources

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        entry1 = MagicMock(resource_type="openshift_cluster", resource_id="cluster-1")
        entry2 = MagicMock(resource_type="openshift_node", resource_id="node-1")
        mock_model.objects.filter.return_value.exists.return_value = True
        mock_model.objects.filter.return_value.iterator.return_value = [entry1, entry2]

        with patch("api.models.Provider.objects") as mock_provider_objects:
            mock_provider_objects.filter.return_value.exists.return_value = False
            result = cleanup_orphaned_kessel_resources("provider-uuid", "org123")

        self.assertEqual(result, 2)
        self.assertEqual(mock_client.inventory_stub.DeleteResource.call_count, 2)
        self.assertEqual(mock_delete_tuples.call_count, 2)
        entry1.delete.assert_called_once()
        entry2.delete.assert_called_once()

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter._delete_resource_tuples")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    @patch("koku_rebac.resource_reporter.KesselSyncedResource")
    def test_partial_grpc_failure_still_cleans_all(self, mock_model, mock_get_client, mock_delete_tuples):
        """Inventory failure is best-effort; cleanup continues for all entries."""
        import grpc

        from koku_rebac.resource_reporter import cleanup_orphaned_kessel_resources

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        entry1 = MagicMock(resource_type="openshift_cluster", resource_id="cluster-1")
        entry2 = MagicMock(resource_type="openshift_node", resource_id="node-1")
        mock_model.objects.filter.return_value.exists.return_value = True
        mock_model.objects.filter.return_value.iterator.return_value = [entry1, entry2]
        mock_client.inventory_stub.DeleteResource.side_effect = [grpc.RpcError(), MagicMock()]

        with patch("api.models.Provider.objects") as mock_provider_objects:
            mock_provider_objects.filter.return_value.exists.return_value = False
            result = cleanup_orphaned_kessel_resources("provider-uuid", "org123")

        self.assertEqual(result, 2)
        self.assertEqual(mock_delete_tuples.call_count, 2)
        entry1.delete.assert_called_once()
        entry2.delete.assert_called_once()

    @override_settings(AUTHORIZATION_BACKEND="rebac")
    @patch("koku_rebac.resource_reporter.get_kessel_client")
    @patch("koku_rebac.resource_reporter.KesselSyncedResource")
    def test_returns_zero_when_no_tracked_resources(self, mock_model, mock_get_client):
        from koku_rebac.resource_reporter import cleanup_orphaned_kessel_resources

        mock_model.objects.filter.return_value.exists.return_value = False

        with patch("api.models.Provider.objects") as mock_provider_objects:
            mock_provider_objects.filter.return_value.exists.return_value = False
            result = cleanup_orphaned_kessel_resources("provider-uuid", "org123")

        self.assertEqual(result, 0)
        mock_get_client.assert_not_called()


class TestDeleteResourceTuples(SimpleTestCase):
    """_delete_resource_tuples calls the Relations API to remove SpiceDB tuples."""

    @override_settings(KESSEL_RELATIONS_URL="http://kessel-relations:8100", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")
    @patch("koku_rebac.resource_reporter.http_requests")
    def test_sends_delete_with_correct_filter_params(self, mock_requests):
        mock_requests.delete.return_value = MagicMock(ok=True)

        from koku_rebac.resource_reporter import _delete_resource_tuples

        result = _delete_resource_tuples("openshift_cluster", "cluster-1")
        self.assertTrue(result)
        mock_requests.delete.assert_called_once()
        call_kwargs = mock_requests.delete.call_args
        self.assertEqual(call_kwargs[0][0], "http://kessel-relations:8100/api/authz/v1beta1/tuples")
        self.assertEqual(call_kwargs[1]["params"]["filter.resource_namespace"], "cost_management")
        self.assertEqual(call_kwargs[1]["params"]["filter.resource_type"], "openshift_cluster")
        self.assertEqual(call_kwargs[1]["params"]["filter.resource_id"], "cluster-1")
        self.assertEqual(call_kwargs[1]["params"]["filter.relation"], "t_workspace")

    @override_settings(KESSEL_RELATIONS_URL="http://kessel-relations:8100", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")
    @patch("koku_rebac.resource_reporter.http_requests")
    def test_returns_false_on_http_error(self, mock_requests):
        mock_requests.delete.return_value = MagicMock(ok=False, status_code=500)

        from koku_rebac.resource_reporter import _delete_resource_tuples

        result = _delete_resource_tuples("openshift_cluster", "cluster-1")
        self.assertFalse(result)

    @override_settings(KESSEL_RELATIONS_URL="http://kessel-relations:8100", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")
    @patch("koku_rebac.resource_reporter.http_requests")
    def test_returns_false_on_connection_error(self, mock_requests):
        import requests as _req

        mock_requests.RequestException = _req.RequestException
        mock_requests.delete.side_effect = _req.ConnectionError("Connection refused")

        from koku_rebac.resource_reporter import _delete_resource_tuples

        result = _delete_resource_tuples("openshift_cluster", "cluster-1")
        self.assertFalse(result)


class TestCreateResourceTuples(SimpleTestCase):
    """_create_resource_tuples calls the Relations API to create SpiceDB tuples."""

    @override_settings(KESSEL_RELATIONS_URL="http://kessel-relations:8100", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")
    @patch("koku_rebac.resource_reporter.http_requests")
    def test_sends_post_with_correct_tuple_payload(self, mock_requests):
        mock_requests.post.return_value = MagicMock(ok=True)

        from koku_rebac.resource_reporter import _create_resource_tuples

        result = _create_resource_tuples("openshift_cluster", "cluster-1", "org123")
        self.assertTrue(result)
        mock_requests.post.assert_called_once()
        call_kwargs = mock_requests.post.call_args
        self.assertEqual(call_kwargs[0][0], "http://kessel-relations:8100/api/authz/v1beta1/tuples")

        payload = call_kwargs[1]["json"]
        self.assertTrue(payload["upsert"])
        self.assertEqual(len(payload["tuples"]), 1)

        t = payload["tuples"][0]
        self.assertEqual(t["resource"]["type"]["namespace"], "cost_management")
        self.assertEqual(t["resource"]["type"]["name"], "openshift_cluster")
        self.assertEqual(t["resource"]["id"], "cluster-1")
        self.assertEqual(t["relation"], "t_workspace")
        self.assertEqual(t["subject"]["subject"]["type"]["namespace"], "rbac")
        self.assertEqual(t["subject"]["subject"]["type"]["name"], "workspace")
        self.assertEqual(t["subject"]["subject"]["id"], "org123")

    @override_settings(KESSEL_RELATIONS_URL="http://kessel-relations:8100", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")
    @patch("koku_rebac.resource_reporter.http_requests")
    def test_returns_false_on_http_error(self, mock_requests):
        mock_requests.post.return_value = MagicMock(ok=False, status_code=500)

        from koku_rebac.resource_reporter import _create_resource_tuples

        result = _create_resource_tuples("openshift_cluster", "cluster-1", "org123")
        self.assertFalse(result)

    @override_settings(KESSEL_RELATIONS_URL="http://kessel-relations:8100", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")
    @patch("koku_rebac.resource_reporter.http_requests")
    def test_returns_false_on_connection_error(self, mock_requests):
        import requests as _req

        mock_requests.RequestException = _req.RequestException
        mock_requests.post.side_effect = _req.ConnectionError("Connection refused")

        from koku_rebac.resource_reporter import _create_resource_tuples

        result = _create_resource_tuples("openshift_cluster", "cluster-1", "org123")
        self.assertFalse(result)

    @override_settings(KESSEL_RELATIONS_URL="http://kessel-relations:8100", KESSEL_TUPLES_PATH="/api/authz/v1beta1/tuples")
    @patch("koku_rebac.resource_reporter.http_requests")
    def test_upsert_treats_409_as_success(self, mock_requests):
        """The upsert flag means 409 (already exists) is treated as success by the API."""
        mock_requests.post.return_value = MagicMock(ok=True, status_code=200)

        from koku_rebac.resource_reporter import _create_resource_tuples

        result = _create_resource_tuples("openshift_cluster", "cluster-1", "org123")
        self.assertTrue(result)
        payload = mock_requests.post.call_args[1]["json"]
        self.assertTrue(payload["upsert"])


class TestRemoveExpiredDataKesselHook(SimpleTestCase):
    """_remove_expired_data calls Kessel cleanup after data purge."""

    @patch("masu.processor._tasks.remove_expired.ExpiredDataRemover")
    @patch("masu.processor._tasks.remove_expired._cleanup_kessel_resources")
    def test_kessel_cleanup_called_when_provider_uuid_set(self, mock_cleanup, mock_remover):
        from masu.processor._tasks.remove_expired import _remove_expired_data

        _remove_expired_data("org123", "OCP", False, provider_uuid="prov-1")
        mock_cleanup.assert_called_once_with("org123", "prov-1")

    @patch("masu.processor._tasks.remove_expired.ExpiredDataRemover")
    @patch("masu.processor._tasks.remove_expired._cleanup_kessel_resources")
    def test_kessel_cleanup_not_called_without_provider_uuid(self, mock_cleanup, mock_remover):
        from masu.processor._tasks.remove_expired import _remove_expired_data

        _remove_expired_data("org123", "OCP", False)
        mock_cleanup.assert_not_called()

    @patch("masu.processor._tasks.remove_expired.ExpiredDataRemover")
    @patch("masu.processor._tasks.remove_expired._cleanup_kessel_resources")
    def test_kessel_cleanup_not_called_when_simulate(self, mock_cleanup, mock_remover):
        from masu.processor._tasks.remove_expired import _remove_expired_data

        _remove_expired_data("org123", "OCP", True, provider_uuid="prov-1")
        mock_cleanup.assert_not_called()
