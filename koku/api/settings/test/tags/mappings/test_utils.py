from unittest.mock import patch

from django_tenants.utils import tenant_context

from api.models import Provider
from api.provider.models import ProviderInfrastructureMap
from api.settings.tags.mapping.utils import resummarize_current_month_by_tag_keys
from api.utils import DateHelper
from masu.processor.tasks import APPLY_TAG_MAPPINGS_TASK
from masu.processor.tasks import UPDATE_SUMMARY_TABLES_TASK
from masu.test import MasuTestCase
from reporting.models import AWSCostEntryBill
from reporting.models import AWSTagsSummary
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping
from reporting.provider.ocp.models import OCPTagsValues
from reporting_common.models import DelayedCeleryTasks


class TestTagMappingUtils(MasuTestCase):
    """Test the utils for Tag mapping"""

    def setUp(self):
        super().setUp()
        self.test_matrix = {
            Provider.PROVIDER_AWS: self.aws_provider.uuid,
            Provider.PROVIDER_AZURE: self.azure_provider.uuid,
            Provider.PROVIDER_GCP: self.gcp_provider.uuid,
            Provider.PROVIDER_OCP: self.ocp_provider.uuid,
        }

    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    def test_find_tag_key_providers(self, _mock_delay_disabled):
        with tenant_context(self.tenant):
            for ptype, uuid in self.test_matrix.items():
                with self.subTest(ptype=ptype, uuid=uuid):
                    uuids = EnabledTagKeys.objects.filter(provider_type=ptype).values_list("uuid", flat=True)
                    resummarize_current_month_by_tag_keys(uuids, self.schema_name)
                    self.assertTrue(DelayedCeleryTasks.objects.filter(provider_uuid=uuid).exists())

    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    def test_multiple_returns(self, _mock_delay_disabled):
        with tenant_context(self.tenant):
            uuids = EnabledTagKeys.objects.all().values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name)
            for uuid in self.test_matrix.values():
                self.assertTrue(DelayedCeleryTasks.objects.filter(provider_uuid=uuid).exists())

    @patch("api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled", return_value=False)
    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    def test_ocp_on_cloud_resummarize(self, _mock_delay_disabled, _mock_flag):
        with tenant_context(self.tenant):
            infra_map = ProviderInfrastructureMap.objects.create(
                infrastructure_type=Provider.PROVIDER_AWS, infrastructure_provider=self.aws_provider
            )
            self.ocp_provider.infrastructure = infra_map
            self.ocp_provider.save()
            uuids = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name)
            # The cloud source refreshes the OCP-on-cloud tables; the OCP source
            # remaps its own daily summary.
            self.assertTrue(DelayedCeleryTasks.objects.filter(provider_uuid=self.aws_provider_uuid).exists())
            self.assertTrue(DelayedCeleryTasks.objects.filter(provider_uuid=self.ocp_provider.uuid).exists())

    @patch("api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled", return_value=False)
    @patch("api.settings.tags.mapping.utils.delayed_summarize_current_month")
    def test_ocp_on_cloud_resummarize_queues_shared_infra_once(self, mock_delayed_summarize, _mock_flag):
        with tenant_context(self.tenant):
            infra_map = ProviderInfrastructureMap.objects.create(
                infrastructure_type=Provider.PROVIDER_AWS, infrastructure_provider=self.aws_provider
            )
            ocp_providers = Provider.objects.filter(type=Provider.PROVIDER_OCP)
            ocp_providers.update(infrastructure=infra_map)
            uuids = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name)

        queued = {call.args[2]: call.args[1] for call in mock_delayed_summarize.call_args_list}
        self.assertEqual(set(queued), {Provider.PROVIDER_OCP, Provider.PROVIDER_AWS})
        self.assertIn(self.ocp_provider.uuid, queued[Provider.PROVIDER_OCP])
        self.assertEqual(queued[Provider.PROVIDER_AWS], [self.aws_provider.uuid])

    @patch("api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled", return_value=True)
    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    def test_ocp_on_cloud_queues_mapping_only_job(self, _mock_delay_disabled, _mock_flag):
        """Flag on: OCP-on-cloud mapping queues the OCP source, not a cloud re-summary."""
        with tenant_context(self.tenant):
            DelayedCeleryTasks.objects.all().delete()
            infra_map = ProviderInfrastructureMap.objects.create(
                infrastructure_type=Provider.PROVIDER_AWS, infrastructure_provider=self.aws_provider
            )
            self.ocp_provider.infrastructure = infra_map
            self.ocp_provider.save()
            uuids = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name)
            ocp_tasks = DelayedCeleryTasks.objects.filter(provider_uuid=self.ocp_provider.uuid)
            self.assertTrue(ocp_tasks.exists())
            self.assertTrue(all(task.task_name == APPLY_TAG_MAPPINGS_TASK for task in ocp_tasks))
            self.assertFalse(
                DelayedCeleryTasks.objects.filter(
                    provider_uuid=self.aws_provider_uuid, task_name=UPDATE_SUMMARY_TABLES_TASK
                ).exists()
            )

    @patch("api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled", return_value=True)
    @patch("api.settings.tags.mapping.utils.delayed_apply_tag_mappings")
    def test_ocp_on_cloud_mapping_job_does_not_queue_shared_infra(self, mock_delayed_apply, _mock_flag):
        with tenant_context(self.tenant):
            infra_map = ProviderInfrastructureMap.objects.create(
                infrastructure_type=Provider.PROVIDER_AWS, infrastructure_provider=self.aws_provider
            )
            ocp_providers = Provider.objects.filter(type=Provider.PROVIDER_OCP)
            ocp_providers.update(infrastructure=infra_map)
            uuids = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name)

        mock_delayed_apply.assert_called_once()
        queued_uuids = mock_delayed_apply.call_args.args[1]
        self.assertIn(self.ocp_provider.uuid, queued_uuids)
        self.assertNotIn(self.aws_provider.uuid, queued_uuids)

    @patch("api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled", return_value=True)
    @patch("api.settings.tags.mapping.utils.delayed_summarize_current_month")
    @patch("api.settings.tags.mapping.utils.delayed_apply_tag_mappings")
    def test_cloud_tag_keys_queue_mapping_only_when_flag_on(
        self, mock_delayed_apply, mock_delayed_summarize, _mock_flag
    ):
        with tenant_context(self.tenant):
            uuids = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS).values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name)
        mock_delayed_apply.assert_called()
        mock_delayed_summarize.assert_not_called()

    @patch("api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled", return_value=True)
    @patch("api.settings.tags.mapping.utils.delayed_summarize_current_month")
    @patch("api.settings.tags.mapping.utils.delayed_apply_tag_mappings")
    def test_restore_unmapped_queues_full_summary_when_flag_on(
        self, mock_delayed_apply, mock_delayed_summarize, _mock_flag
    ):
        """Removals rebuild from parquet even when mapping-only apply is enabled."""
        with tenant_context(self.tenant):
            uuids = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS).values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name, restore_unmapped=True)
        mock_delayed_apply.assert_not_called()
        mock_delayed_summarize.assert_called()

    @patch("api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled", return_value=True)
    @patch("api.settings.tags.mapping.utils.delayed_summarize_current_month")
    @patch("api.settings.tags.mapping.utils.delayed_apply_tag_mappings")
    def test_restore_unmapped_ocp_on_cloud_queues_shared_infra(
        self, mock_delayed_apply, mock_delayed_summarize, _mock_flag
    ):
        with tenant_context(self.tenant):
            infra_map = ProviderInfrastructureMap.objects.create(
                infrastructure_type=Provider.PROVIDER_AWS, infrastructure_provider=self.aws_provider
            )
            Provider.objects.filter(type=Provider.PROVIDER_OCP).update(infrastructure=infra_map)
            uuids = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name, restore_unmapped=True)

        mock_delayed_apply.assert_not_called()
        queued = {call.args[2]: call.args[1] for call in mock_delayed_summarize.call_args_list}
        self.assertEqual(set(queued), {Provider.PROVIDER_OCP, Provider.PROVIDER_AWS})
        self.assertIn(self.ocp_provider.uuid, queued[Provider.PROVIDER_OCP])
        self.assertEqual(queued[Provider.PROVIDER_AWS], [self.aws_provider.uuid])

    def _make_ocp_tag_values(self, key, cluster_id):
        return OCPTagsValues.objects.create(
            key=key,
            value="unit-test",
            cluster_ids=[cluster_id],
            cluster_aliases=[cluster_id],
            namespaces=["default"],
            nodes=["node"],
        )

    @patch("api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled", return_value=True)
    @patch("api.settings.tags.mapping.utils.delayed_summarize_current_month")
    @patch("api.settings.tags.mapping.utils.delayed_apply_tag_mappings")
    def test_restore_unmapped_ocp_queues_only_clusters_with_keys(
        self, mock_delayed_apply, mock_delayed_summarize, _mock_flag
    ):
        """OCP mapping removal rebuilds clusters that have the keys, not every period."""
        with tenant_context(self.tenant):
            targeted_key = EnabledTagKeys.objects.create(
                key="ocp_restore_unmapped_target",
                enabled=True,
                provider_type=Provider.PROVIDER_OCP,
            )
            self._make_ocp_tag_values(targeted_key.key, self.ocp_cluster_id)
            aws_infra = ProviderInfrastructureMap.objects.create(
                infrastructure_type=Provider.PROVIDER_AWS, infrastructure_provider=self.aws_provider
            )
            azure_infra = ProviderInfrastructureMap.objects.create(
                infrastructure_type=Provider.PROVIDER_AZURE, infrastructure_provider=self.azure_provider
            )
            self.ocp_provider.infrastructure = aws_infra
            self.ocp_provider.save()
            self.ocp_on_aws_ocp_provider.infrastructure = azure_infra
            self.ocp_on_aws_ocp_provider.save()
            resummarize_current_month_by_tag_keys([targeted_key.uuid], self.schema_name, restore_unmapped=True)

        mock_delayed_apply.assert_not_called()
        queued = {call.args[2]: set(call.args[1]) for call in mock_delayed_summarize.call_args_list}
        self.assertEqual(queued[Provider.PROVIDER_OCP], {self.ocp_provider.uuid})
        self.assertNotIn(self.ocp_on_aws_ocp_provider.uuid, queued[Provider.PROVIDER_OCP])
        self.assertEqual(queued.get(Provider.PROVIDER_AWS), {self.aws_provider.uuid})
        self.assertNotIn(Provider.PROVIDER_AZURE, queued)

    @patch("api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled", return_value=True)
    @patch("api.settings.tags.mapping.utils.delayed_summarize_current_month")
    @patch("api.settings.tags.mapping.utils.delayed_apply_tag_mappings")
    def test_restore_unmapped_ocp_finds_cluster_by_parent_key_name(
        self, mock_delayed_apply, mock_delayed_summarize, _mock_flag
    ):
        """After mapping, OCP tag values may only have the parent key name."""
        with tenant_context(self.tenant):
            ocp_child = EnabledTagKeys.objects.create(
                key="ocp_child_gone_after_map",
                enabled=True,
                provider_type=Provider.PROVIDER_OCP,
            )
            aws_parent = EnabledTagKeys.objects.create(
                key="aws_parent_only_in_ocp_tag_values",
                enabled=True,
                provider_type=Provider.PROVIDER_AWS,
            )
            self._make_ocp_tag_values(aws_parent.key, self.ocp_cluster_id)
            resummarize_current_month_by_tag_keys(
                [ocp_child.uuid, aws_parent.uuid], self.schema_name, restore_unmapped=True
            )

        mock_delayed_apply.assert_not_called()
        queued = {call.args[2]: set(call.args[1]) for call in mock_delayed_summarize.call_args_list}
        self.assertIn(self.ocp_provider.uuid, queued[Provider.PROVIDER_OCP])
        self.assertNotIn(self.ocp_on_aws_ocp_provider.uuid, queued[Provider.PROVIDER_OCP])

    def _aws_azure_enabled_keys(self):
        aws_child = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS, enabled=True).first()
        azure_parent = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AZURE, enabled=True).first()
        self.assertIsNotNone(aws_child)
        self.assertIsNotNone(azure_parent)
        return aws_child, azure_parent

    def _drop_current_month_aws_tag_summaries(self):
        start = DateHelper().this_month_start
        self.assertTrue(
            AWSCostEntryBill.objects.filter(provider_id=self.aws_provider.uuid, billing_period_start=start).exists()
        )
        AWSTagsSummary.objects.filter(
            cost_entry_bill__provider_id=self.aws_provider.uuid,
            cost_entry_bill__billing_period_start=start,
        ).delete()

    def _queued_provider_uuids(self, mock_delayed_summarize, provider_type):
        queued = {call.args[2]: call.args[1] for call in mock_delayed_summarize.call_args_list}
        self.assertIn(provider_type, queued)
        return queued[provider_type]

    def _create_parent_child_key_name_collision(self):
        """AWS child → Azure parent whose key is also an AWS child of a GCP parent."""
        aws_keys = list(EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS, enabled=True)[:2])
        self.assertGreaterEqual(len(aws_keys), 2)
        aws_child, aws_department = aws_keys
        azure_department = EnabledTagKeys.objects.get(
            provider_type=Provider.PROVIDER_AZURE, key=aws_department.key, enabled=True
        )
        gcp_parent = (
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_GCP, enabled=True)
            .exclude(key=aws_department.key)
            .first()
        )
        self.assertIsNotNone(gcp_parent)
        TagMapping.objects.create(parent=azure_department, child=aws_child)
        TagMapping.objects.create(parent=gcp_parent, child=aws_department)

    def _create_many_to_one_parent_mapping(self):
        """Two AWS children map to the same parent key."""
        aws_keys = list(EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS, enabled=True)[:3])
        self.assertGreaterEqual(len(aws_keys), 3)
        parent, child_a, child_b = aws_keys
        TagMapping.objects.create(parent=parent, child=child_a)
        TagMapping.objects.create(parent=parent, child=child_b)

    @patch("api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled", return_value=True)
    @patch("api.settings.tags.mapping.utils.delayed_summarize_current_month")
    @patch("api.settings.tags.mapping.utils.delayed_apply_tag_mappings")
    def test_restore_unmapped_finds_provider_without_tag_summary_rows(
        self, mock_delayed_apply, mock_delayed_summarize, _mock_flag
    ):
        """Removals discover current-month bills even when mapping left no tag-summary rows."""
        with tenant_context(self.tenant):
            aws_child, azure_parent = self._aws_azure_enabled_keys()
            self._drop_current_month_aws_tag_summaries()
            resummarize_current_month_by_tag_keys(
                [aws_child.uuid, azure_parent.uuid], self.schema_name, restore_unmapped=True
            )

        mock_delayed_apply.assert_not_called()
        queued = self._queued_provider_uuids(mock_delayed_summarize, Provider.PROVIDER_AWS)
        self.assertIn(self.aws_provider.uuid, queued)

    @patch("api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled", return_value=False)
    @patch("api.settings.tags.mapping.utils.delayed_summarize_current_month")
    @patch("api.settings.tags.mapping.utils.delayed_apply_tag_mappings")
    def test_restore_unmapped_finds_provider_without_tag_summary_rows_flag_off(
        self, mock_delayed_apply, mock_delayed_summarize, _mock_flag
    ):
        """Ingest mapping is unconditional, so empty tag summaries must also work with the flag off."""
        with tenant_context(self.tenant):
            aws_child, azure_parent = self._aws_azure_enabled_keys()
            self._drop_current_month_aws_tag_summaries()
            resummarize_current_month_by_tag_keys(
                [aws_child.uuid, azure_parent.uuid], self.schema_name, restore_unmapped=True
            )

        mock_delayed_apply.assert_not_called()
        queued = self._queued_provider_uuids(mock_delayed_summarize, Provider.PROVIDER_AWS)
        self.assertIn(self.aws_provider.uuid, queued)

    @patch("api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled", return_value=True)
    @patch("api.settings.tags.mapping.utils.delayed_summarize_current_month")
    @patch("api.settings.tags.mapping.utils.delayed_apply_tag_mappings")
    def test_key_name_collision_queues_full_summary_when_flag_on(
        self, mock_delayed_apply, mock_delayed_summarize, _mock_flag
    ):
        """Mapping-only apply can remap a generated parent; overlapping key names rebuild instead."""
        with tenant_context(self.tenant):
            self._create_parent_child_key_name_collision()
            uuids = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS).values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name)

        mock_delayed_apply.assert_not_called()
        mock_delayed_summarize.assert_called()
        queued = self._queued_provider_uuids(mock_delayed_summarize, Provider.PROVIDER_AWS)
        self.assertIn(self.aws_provider.uuid, queued)

    @patch("api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled", return_value=True)
    @patch("api.settings.tags.mapping.utils.delayed_summarize_current_month")
    @patch("api.settings.tags.mapping.utils.delayed_apply_tag_mappings")
    def test_many_to_one_parent_queues_full_summary_when_flag_on(
        self, mock_delayed_apply, mock_delayed_summarize, _mock_flag
    ):
        """Mapping-only apply can drop a sibling child; many-to-one parents rebuild instead."""
        with tenant_context(self.tenant):
            self._create_many_to_one_parent_mapping()
            uuids = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS).values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name)

        mock_delayed_apply.assert_not_called()
        mock_delayed_summarize.assert_called()
        queued = self._queued_provider_uuids(mock_delayed_summarize, Provider.PROVIDER_AWS)
        self.assertIn(self.aws_provider.uuid, queued)
