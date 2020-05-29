#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Data Driven Component Generation for OpenShift Settings."""
from django.test import RequestFactory
from rest_framework.serializers import ValidationError
from tenant_schemas.utils import schema_context

from api.common import error_obj
from api.query_params import QueryParameters
from api.settings.utils import create_dual_list_select
from api.settings.utils import create_plain_text
from api.settings.utils import create_subform
from api.settings.utils import create_tab_item
from api.settings.utils import OPENSHIFT_TAG_MGMT_SETTINGS_PREFIX
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.ocp.view import OCPTagView
from reporting.models import OCPEnabledTagKeys


class OpenShiftSettings:
    """Class for generating OpenShift settings."""

    def __init__(self, request):
        """Initialize settings object with incoming request."""
        self.request = request
        self.factory = RequestFactory()
        self.schema = request.user.customer.schema_name

    def _obtain_tag_keys(self):
        """
        Collect the available tag keys for the customer.

        Returns:
            (List) - List of available tag keys objects
            (List) - List of enabled tag keys strings
        """
        url = (
            "?filter[time_scope_units]=month&filter[time_scope_value]=-1"
            "&filter[resolution]=monthly&key_only=True&filter[enabled]=False"
        )
        tag_request = self.factory.get(url)
        tag_request.user = self.request.user
        query_params = QueryParameters(tag_request, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        query_output = handler.execute_query()
        avail_data = query_output.get("data")
        all_tags_set = set(avail_data)
        enabled = []
        with schema_context(self.schema):
            enabled_tags = OCPEnabledTagKeys.objects.all()
            enabled = [enabled_tag.key for enabled_tag in enabled_tags]
            all_tags_set.update(enabled)

        return all_tags_set, enabled

    def _build_tag_key_tab(self):
        """
        Generate tag_key tab component

        Returns:
            (Dict) - Tab Item
        """
        tag_key_text_name = f"{OPENSHIFT_TAG_MGMT_SETTINGS_PREFIX}.form-text"
        tag_key_text_context = (
            "Enable your OpenShift label names to be used as tag keys for report grouping and filtering."
        )
        tag_key_text = create_plain_text(tag_key_text_name, tag_key_text_context)
        available, enabled = self._obtain_tag_keys()
        avail_objs = [{"value": tag_key, "label": tag_key} for tag_key in available]
        dual_list_options = {
            "options": avail_objs,
            "leftTitle": "Available Tag Keys",
            "rightTitle": "Enabled Tag Keys",
            "noValueTitle": "No enabled tag keys",
            "noOptionsTitle": "No available tag keys",
            "filterOptionsTitle": "Filter available",
            "filterValueTitle": "Filter enabled",
            "filterValueText": "Remove your filter to see all enabled tag keys",
            "filterOptionsText": "Remove your filter to see all available tag keys",
            "initialValue": enabled,
        }
        tab_dual_list_name = f"{OPENSHIFT_TAG_MGMT_SETTINGS_PREFIX}.enabled"
        tab_dual_list_select = create_dual_list_select(tab_dual_list_name, **dual_list_options)
        tab_sub_form_name = f"{OPENSHIFT_TAG_MGMT_SETTINGS_PREFIX}.subform"
        tab_sub_form_title = "Tag Key Enablement"
        tab_sub_form_fields = [tag_key_text, tab_dual_list_select]
        tab_sub_form = create_subform(tab_sub_form_name, tab_sub_form_title, tab_sub_form_fields)

        tab_item_name = f"{OPENSHIFT_TAG_MGMT_SETTINGS_PREFIX}.tab-item"
        tab_item_title = "OpenShift Tag Management"
        tab_item_description = "OpenShift Tag Management Setting tab"
        tab_item_fields = tab_sub_form
        tab_item = create_tab_item(tab_item_name, tab_item_title, tab_item_description, tab_item_fields)
        return tab_item

    def build_tabs(self):
        """
        Generate OpenShift tabs

        Returns:
            (List) - List of Tab Items
        """
        openshift_tag_mgmt_tab = self._build_tag_key_tab()
        return [openshift_tag_mgmt_tab]

    def _tag_key_handler(self, settings):
        """
        Handle setting results

        Args:
            (String) name - unique name for switch.

        Returns:
            (Bool) - True, if a setting had an effect, False otherwise
        """
        updated = False
        enabled_tags = settings.get("tag-management", {}).get("enabled", [])
        remove_tags = []
        available, _ = self._obtain_tag_keys()
        invalid_keys = [tag_key for tag_key in enabled_tags if tag_key not in available]
        if invalid_keys:
            key = "settings"
            message = f"Invalid tag keys provided: {', '.join(invalid_keys)}."
            raise ValidationError(error_obj(key, message))

        with schema_context(self.schema):
            existing_enabled_tags = OCPEnabledTagKeys.objects.all()
            for existing_tag in existing_enabled_tags:
                if existing_tag.key in enabled_tags:
                    enabled_tags.remove(existing_tag.key)
                else:
                    remove_tags.append(existing_tag)
                    updated = True
            for rm_tag in remove_tags:
                rm_tag.delete()
            for new_tag in enabled_tags:
                OCPEnabledTagKeys.objects.create(key=new_tag)
                updated = True

        return updated

    def handle_settings(self, settings):
        """
        Handle setting results

        Args:
            (String) name - unique name for switch.

        Returns:
            (Bool) - True, if a setting had an effect, False otherwise
        """
        openshift_settings = settings.get("api", {}).get("settings", {}).get("openshift", {})
        return self._tag_key_handler(openshift_settings)
