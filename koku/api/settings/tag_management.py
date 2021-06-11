#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Data Driven Component Generation for Tag Management Settings."""
from django.test import RequestFactory
from rest_framework.serializers import ValidationError
from tenant_schemas.utils import schema_context

from api.common import error_obj
from api.provider.models import Provider
from api.query_params import QueryParameters
from api.settings.utils import create_dual_list_select
from api.settings.utils import create_plain_text
from api.settings.utils import create_plain_text_with_doc
from api.settings.utils import create_subform
from api.settings.utils import generate_doc_link
from api.settings.utils import SETTINGS_PREFIX
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.aws.view import AWSTagView
from api.tags.azure.queries import AzureTagQueryHandler
from api.tags.azure.view import AzureTagView
from api.tags.gcp.queries import GCPTagQueryHandler
from api.tags.gcp.view import GCPTagView
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.ocp.view import OCPTagView
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from masu.util.common import update_enabled_keys
from reporting.models import AWSEnabledTagKeys
from reporting.models import AzureEnabledTagKeys
from reporting.models import GCPEnabledTagKeys
from reporting.models import OCPEnabledTagKeys


obtainTagKeysProvidersParams = {
    "openshift": {
        "provider": Provider.PROVIDER_OCP,
        "title": "OpenShift labels",
        "leftLabel": "Available labels",
        "rightLabel": "Labels for reporting",
        "tag_view": OCPTagView,
        "query_handler": OCPTagQueryHandler,
        "enabled_tag_keys": OCPEnabledTagKeys,
    },
    "aws": {
        "provider": Provider.PROVIDER_AWS,
        "title": "Amazon Web Services tags",
        "leftLabel": "Available tags",
        "rightLabel": "Tags for reporting",
        "tag_view": AWSTagView,
        "query_handler": AWSTagQueryHandler,
        "enabled_tag_keys": AWSEnabledTagKeys,
    },
    "azure": {
        "provider": Provider.PROVIDER_AZURE,
        "title": "Azure tags",
        "leftLabel": "Available tags",
        "rightLabel": "Tags for reporting",
        "tag_view": AzureTagView,
        "query_handler": AzureTagQueryHandler,
        "enabled_tag_keys": AzureEnabledTagKeys,
    },
    "gcp": {
        "provider": Provider.PROVIDER_GCP,
        "title": "Google Cloud Platform tags",
        "leftLabel": "Available tags",
        "rightLabel": "Tags for reporting",
        "tag_view": GCPTagView,
        "query_handler": GCPTagQueryHandler,
        "enabled_tag_keys": GCPEnabledTagKeys,
    },
}


class TagManagementSettings:
    """Class for generating tag management settings."""

    def __init__(self, request):
        """Initialize settings object with incoming request."""
        self.request = request
        self.factory = RequestFactory()
        self.schema = request.user.customer.schema_name

    def _get_tag_management_prefix(self, providerName):
        return f"{SETTINGS_PREFIX}.tag-management.{providerName}"

    def _obtain_tag_keys(self, tag_view_kls, tag_handler_kls, tag_keys_kls):
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
        query_params = QueryParameters(tag_request, tag_view_kls)
        handler = tag_handler_kls(query_params)
        query_output = handler.execute_query()
        avail_data = query_output.get("data")
        all_tags_set = set(avail_data)
        enabled = []
        with schema_context(self.schema):
            if tag_keys_kls == AWSEnabledTagKeys:
                enabled_tags = tag_keys_kls.objects.filter(enabled=True).all()
            else:
                enabled_tags = tag_keys_kls.objects.all()
            enabled = [enabled_tag.key for enabled_tag in enabled_tags]
            all_tags_set.update(enabled)

        return all_tags_set, enabled

    def _build_tag_key(self):
        """
        Generate tag management form component

        Returns:
            (Dict) - Tab Item
        """
        tag_key_text_name = f"{SETTINGS_PREFIX}.tag_management.form-text"
        tag_key_text_context = (
            "Enable your data source labels to be used as tag keys for report grouping and filtering."
            + " Changes will be reflected within 24 hours. <link>Learn more</link>"
        )
        doc_link = dict(
            href=generate_doc_link(
                "html-single/managing_cost_data_using_tagging/index"
                + "#assembly-configuring-tags-and-labels-in-cost-management"
            )
        )
        tag_key_text = create_plain_text_with_doc(tag_key_text_name, tag_key_text_context, doc_link)
        components = []
        for providerName in obtainTagKeysProvidersParams:
            tag_view = obtainTagKeysProvidersParams[providerName]["tag_view"]
            query_handler = obtainTagKeysProvidersParams[providerName]["query_handler"]
            enabled_tag_keys = obtainTagKeysProvidersParams[providerName]["enabled_tag_keys"]
            available, enabled = self._obtain_tag_keys(tag_view, query_handler, enabled_tag_keys)
            avail_objs = [{"value": tag_key, "label": tag_key} for tag_key in available]
            dual_list_options = {
                "options": avail_objs,
                "leftTitle": obtainTagKeysProvidersParams[providerName]["leftLabel"],
                "rightTitle": obtainTagKeysProvidersParams[providerName]["rightLabel"],
                "noValueTitle": "No enabled tag keys",
                "noOptionsTitle": "No available tag keys",
                "filterOptionsTitle": "Filter by available tag keys",
                "filterValueTitle": "Filter by enabled tag keys",
                "filterValueText": "Remove your filter to see all enabled tag keys",
                "filterOptionsText": "Remove your filter to see all available tag keys",
                "initialValue": enabled,
                "clearedValue": [],
            }
            dual_list_name = f"{self._get_tag_management_prefix(providerName)}.enabled"
            dual_list_title = obtainTagKeysProvidersParams[providerName]["title"]
            components.append(create_plain_text(f"{SETTINGS_PREFIX}.{providerName}.title", dual_list_title, "h2"))
            components.append(create_dual_list_select(dual_list_name, **dual_list_options))
        sub_form_name = f"{SETTINGS_PREFIX}.tag_managment.subform"
        sub_form_title = "Enable tags and labels"
        sub_form_fields = [tag_key_text]
        sub_form_fields.extend(components)
        sub_form = create_subform(sub_form_name, sub_form_title, sub_form_fields)

        return sub_form

    def build_settings(self):
        """
        Generate tag management settings

        Returns:
            (List) - List of setting items
        """
        settings = self._build_tag_key()
        return [settings]

    def _tag_key_handler(self, settings):
        """
        Handle setting results

        Args:
            (String) name - unique name for switch.

        Returns:
            (Bool) - True, if a setting had an effect, False otherwise
        """
        updated = [False] * len(obtainTagKeysProvidersParams)
        for ix, providerName in enumerate(obtainTagKeysProvidersParams):
            provider_in_settings = settings.get(providerName)
            if provider_in_settings is None:
                continue
            enabled_tags = provider_in_settings.get("enabled", [])
            tag_view = obtainTagKeysProvidersParams[providerName]["tag_view"]
            query_handler = obtainTagKeysProvidersParams[providerName]["query_handler"]
            enabled_tag_keys = obtainTagKeysProvidersParams[providerName]["enabled_tag_keys"]
            provider = obtainTagKeysProvidersParams[providerName]["provider"]
            available, _ = self._obtain_tag_keys(tag_view, query_handler, enabled_tag_keys)
            invalid_keys = [tag_key for tag_key in enabled_tags if tag_key not in available]
            if invalid_keys:
                key = "settings"
                message = f"Invalid tag keys provided: {', '.join(invalid_keys)}."
                raise ValidationError(error_obj(key, message))
            if "aws" in providerName:
                updated[ix] = update_enabled_keys(self.schema, enabled_tag_keys, enabled_tags)
            else:
                remove_tags = []
                with schema_context(self.schema):
                    existing_enabled_tags = enabled_tag_keys.objects.all()
                    for existing_tag in existing_enabled_tags:
                        if existing_tag.key in enabled_tags:
                            enabled_tags.remove(existing_tag.key)
                        else:
                            remove_tags.append(existing_tag)
                            updated[ix] = True
                    for rm_tag in remove_tags:
                        rm_tag.delete()
                    for new_tag in enabled_tags:
                        enabled_tag_keys.objects.create(key=new_tag)
                        updated[ix] = True

            if updated[ix]:
                invalidate_view_cache_for_tenant_and_source_type(self.schema, provider)

        return any(updated)

    def handle_settings(self, settings):
        """
        Handle setting results

        Args:
            (String) name - unique name for switch.

        Returns:
            (Bool) - True, if a setting had an effect, False otherwise
        """
        tg_mgmt_settings = settings.get("api", {}).get("settings", {}).get("tag-management", {})
        return self._tag_key_handler(tg_mgmt_settings)
