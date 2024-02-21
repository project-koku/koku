from django_tenants.utils import tenant_context

from api.models import Provider
from api.settings.tags.mapping.utils import FindTagKeyProviders
from masu.test import MasuTestCase
from reporting.provider.all.models import EnabledTagKeys


class TestTagMappingUtils(MasuTestCase):
    """Test the utils for Tag mapping"""

    def setUp(self):
        super().setUp()
        self.provider_types = [
            Provider.PROVIDER_AWS,
            Provider.PROVIDER_AZURE,
            Provider.PROVIDER_GCP,
            Provider.PROVIDER_OCI,
            Provider.PROVIDER_OCP,
        ]

    def test_find_tag_key_providers(self):
        with tenant_context(self.tenant):
            for ptype in self.provider_types:
                with self.subTest(ptype=ptype):
                    keys = list(EnabledTagKeys.objects.filter(provider_type=ptype))
                    finder = FindTagKeyProviders(keys)
                    mapping = finder.create_provider_type_to_uuid_mapping()
                    self.assertTrue(mapping)
                    for type, uuid_list in mapping.items():
                        self.assertEqual(ptype, type)
                        self.assertEqual(len(uuid_list), 1)
                        test_class_var = f"{ptype.lower()}_provider"
                        expected_provider = getattr(self, test_class_var, None)
                        self.assertEqual([expected_provider.uuid], uuid_list)

    def test_multiple_returns(self):
        with tenant_context(self.tenant):
            keys = list(EnabledTagKeys.objects.all())
            finder = FindTagKeyProviders(keys)
            mapping = finder.create_provider_type_to_uuid_mapping()
            self.assertTrue(mapping)
            for provider_type, uuid_list in mapping.items():
                self.assertIn(provider_type, self.provider_types)
                test_class_var = f"{provider_type.lower()}_provider"
                expected_provider = getattr(self, test_class_var, None)
                self.assertEqual([expected_provider.uuid], uuid_list)
