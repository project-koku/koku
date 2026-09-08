from unittest.mock import patch

from django_tenants.utils import tenant_context

from api.models import Provider
from api.provider.models import ProviderInfrastructureMap
from api.settings.tags.mapping.utils import resummarize_current_month_by_tag_keys
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

    @patch("masu.processor.tasks.is_celery_task_delay_disabled", return_value=False)
    def test_ocp_on_cloud_resummarize(self, _mock_delay_disabled):
        with tenant_context(self.tenant):
            infra_map = ProviderInfrastructureMap.objects.create(
                infrastructure_type=Provider.PROVIDER_AWS, infrastructure_provider=self.aws_provider
            )
            self.ocp_provider.infrastructure = infra_map
            self.ocp_provider.save()
            uuids = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).values_list("uuid", flat=True)
            resummarize_current_month_by_tag_keys(uuids, self.schema_name)
            self.assertTrue(DelayedCeleryTasks.objects.filter(provider_uuid=self.aws_provider_uuid).exists())
