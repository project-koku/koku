from unittest.mock import patch

from django_tenants.utils import tenant_context

from api.models import Provider
from api.provider.models import ProviderInfrastructureMap
from api.settings.tags.mapping.utils import resummarize_current_month_by_tag_keys
from masu.processor.tasks import APPLY_TAG_MAPPINGS_TASK
from masu.processor.tasks import UPDATE_SUMMARY_TABLES_TASK
from masu.test import MasuTestCase
from reporting.provider.all.models import EnabledTagKeys
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

    @patch(
        "api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled",
        return_value=False,
    )
    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    def test_ocp_on_cloud_resummarize(self, _mock_delay_disabled, _mock_flag):
        with tenant_context(self.tenant):
            infra_map = ProviderInfrastructureMap.objects.create(
                infrastructure_type=Provider.PROVIDER_AWS,
                infrastructure_provider=self.aws_provider,
            )
            self.ocp_provider.infrastructure = infra_map
            self.ocp_provider.save()
            uuids = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name)
            # The cloud source refreshes the OCP-on-cloud tables; the OCP source
            # remaps its own daily summary.
            self.assertTrue(DelayedCeleryTasks.objects.filter(provider_uuid=self.aws_provider_uuid).exists())
            self.assertTrue(DelayedCeleryTasks.objects.filter(provider_uuid=self.ocp_provider.uuid).exists())

    @patch(
        "api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled",
        return_value=False,
    )
    @patch("api.settings.tags.mapping.utils.delayed_summarize_current_month")
    def test_ocp_on_cloud_resummarize_queues_shared_infra_once(self, mock_delayed_summarize, _mock_flag):
        with tenant_context(self.tenant):
            infra_map = ProviderInfrastructureMap.objects.create(
                infrastructure_type=Provider.PROVIDER_AWS,
                infrastructure_provider=self.aws_provider,
            )
            ocp_providers = Provider.objects.filter(type=Provider.PROVIDER_OCP)
            ocp_providers.update(infrastructure=infra_map)
            uuids = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name)

        queued = {call.args[2]: call.args[1] for call in mock_delayed_summarize.call_args_list}
        self.assertEqual(set(queued), {Provider.PROVIDER_OCP, Provider.PROVIDER_AWS})
        self.assertIn(self.ocp_provider.uuid, queued[Provider.PROVIDER_OCP])
        self.assertEqual(queued[Provider.PROVIDER_AWS], [self.aws_provider.uuid])

    @patch(
        "api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled",
        return_value=True,
    )
    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    def test_ocp_on_cloud_queues_mapping_only_job(self, _mock_delay_disabled, _mock_flag):
        """Flag on: OCP-on-cloud mapping queues the OCP source, not a cloud re-summary."""
        with tenant_context(self.tenant):
            DelayedCeleryTasks.objects.all().delete()
            infra_map = ProviderInfrastructureMap.objects.create(
                infrastructure_type=Provider.PROVIDER_AWS,
                infrastructure_provider=self.aws_provider,
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
                    provider_uuid=self.aws_provider_uuid,
                    task_name=UPDATE_SUMMARY_TABLES_TASK,
                ).exists()
            )

    @patch(
        "api.settings.tags.mapping.utils.is_apply_tag_mappings_enabled",
        return_value=True,
    )
    @patch("api.settings.tags.mapping.utils.delayed_apply_tag_mappings")
    def test_ocp_on_cloud_mapping_job_does_not_queue_shared_infra(self, mock_delayed_apply, _mock_flag):
        with tenant_context(self.tenant):
            infra_map = ProviderInfrastructureMap.objects.create(
                infrastructure_type=Provider.PROVIDER_AWS,
                infrastructure_provider=self.aws_provider,
            )
            ocp_providers = Provider.objects.filter(type=Provider.PROVIDER_OCP)
            ocp_providers.update(infrastructure=infra_map)
            uuids = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name)

        mock_delayed_apply.assert_called_once()
        queued_uuids = mock_delayed_apply.call_args.args[1]
        self.assertIn(self.ocp_provider.uuid, queued_uuids)
        self.assertNotIn(self.aws_provider.uuid, queued_uuids)
