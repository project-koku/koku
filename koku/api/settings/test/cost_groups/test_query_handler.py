import unittest
from unittest.mock import Mock
from unittest.mock import patch

from django.db.models import Q

from api.query_params import QueryParameters
from api.settings.cost_groups.query_handler import CostGroupsQueryHandler
from api.settings.cost_groups.query_handler import delete_openshift_namespaces
from api.settings.cost_groups.query_handler import put_openshift_namespaces
from reporting.provider.ocp.models import OpenshiftCostCategory
from reporting.provider.ocp.models import OpenshiftCostCategoryNamespace


class TestCostGroupQueryHandler(unittest.TestCase):
    def setUp(self):
        self.mock_parameters = Mock(spec=QueryParameters)
        self.mock_parameters.get_filter.return_value = []
        self.mock_parameters.get_exclude.return_value = []
        self.mock_parameters._parameters = {"order_by": {"project_name": "asc"}}
        self.mock_parameters.caller = Mock()

    def test_put_and_delete_openshift_namespaces(self):
        original_record_count = OpenshiftCostCategoryNamespace.objects.all().count()
        projects = ["project1", "project2"]
        put_openshift_namespaces(projects, category_name="Platform")
        new_record_count = OpenshiftCostCategoryNamespace.objects.all().count()
        self.assertNotEqual(original_record_count, new_record_count)
        new_records = new_record_count - original_record_count
        self.assertEqual(new_records, len(projects))
        delete_openshift_namespaces(projects)
        delete_record_count = OpenshiftCostCategoryNamespace.objects.all().count()
        self.assertEqual(original_record_count, delete_record_count)

    @patch("reporting.provider.ocp.models.OpenshiftCostCategoryNamespace.objects.filter")
    @patch("reporting.provider.ocp.models.OpenshiftCostCategoryNamespace.objects.exclude")
    def test_delete_openshift_namespaces(self, mock_exclude, mock_filter, mock_log):
        projects = ["project1", "project2"]
        platform_category = OpenshiftCostCategory.objects.create(name="Platform")
        mock_exclude.return_value.delete.return_value = (2, {})

        delete_openshift_namespaces(projects, category_name="Platform")

        mock_filter.assert_called_once_with(Q(cost_category=platform_category, namespace__in=projects))
        mock_exclude.assert_called_once_with(system_default=True)
        mock_log.info.assert_called_once_with("Deleted 2 namespace records from openshift cost groups.")

    @patch("reporting.provider.ocp.models.OpenshiftCostCategoryNamespace.objects.filter")
    def test_cost_groups_query_handler(self, mock_filter):
        mock_filter.return_value.exclude.return_value = None
        mock_filter.return_value.filter.return_value = None
        mock_filter.return_value.order_by.return_value = None

        handler = CostGroupsQueryHandler(self.mock_parameters)
        handler.execute_query()

        mock_filter.assert_called()
        mock_filter.return_value.exclude.assert_called()
        mock_filter.return_value.filter.assert_called()
        mock_filter.return_value.order_by.assert_called()

    @patch("reporting.provider.ocp.models.OpenshiftCostCategoryNamespace.objects.filter")
    def test_cost_groups_query_handler_with_exclusion(self, mock_filter):
        mock_filter.return_value.exclude.return_value = "exclusion"
        mock_filter.return_value.filter.return_value = None
        mock_filter.return_value.order_by.return_value = None

        self.mock_parameters.get_exclude.return_value = {"group": "test"}

        handler = CostGroupsQueryHandler(self.mock_parameters)
        handler.execute_query()

        mock_filter.assert_called()
        mock_filter.return_value.exclude.assert_called()
        mock_filter.return_value.filter.assert_not_called()
        mock_filter.return_value.order_by.assert_not_called()
