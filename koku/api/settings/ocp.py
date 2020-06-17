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

    def _build_tag_key(self):
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
            "leftTitle": "Available tags",
            "rightTitle": "Enabled tags",
            "noValueTitle": "No enabled tag keys",
            "noOptionsTitle": "No available tag keys",
            "filterOptionsTitle": "Filter by available tag keys",
            "filterValueTitle": "Filter by enabled tag keys",
            "filterValueText": "Remove your filter to see all enabled tag keys",
            "filterOptionsText": "Remove your filter to see all available tag keys",
            "initialValue": enabled,
        }
        dual_list_name = f"{OPENSHIFT_TAG_MGMT_SETTINGS_PREFIX}.enabled"
        dual_list_select = create_dual_list_select(dual_list_name, **dual_list_options)
        sub_form_name = f"{OPENSHIFT_TAG_MGMT_SETTINGS_PREFIX}.subform"
        sub_form_title = "Enable OpenShift labels"
        sub_form_fields = [tag_key_text, dual_list_select]
        sub_form = create_subform(sub_form_name, sub_form_title, sub_form_fields)

        return sub_form

    def build_settings(self):
        """
        Generate OpenShift settings

        Returns:
            (List) - List of setting items
        """
        openshift_tag_mgmt = self._build_tag_key()
        return [openshift_tag_mgmt]

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
