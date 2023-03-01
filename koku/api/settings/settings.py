#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Data Driven Component Generation for Tag Management Settings."""
import logging
import re

from django.test import RequestFactory
from rest_framework.serializers import ValidationError
from tenant_schemas.utils import schema_context

from api.common import error_obj
from api.provider.models import Provider
from api.settings.utils import create_dual_list_select
from api.settings.utils import create_plain_text
from api.settings.utils import create_plain_text_with_doc
from api.settings.utils import create_select
from api.settings.utils import create_subform
from api.settings.utils import generate_doc_link
from api.settings.utils import get_cost_type_options
from api.settings.utils import get_currency_options
from api.settings.utils import get_selected_cost_type_or_setup
from api.settings.utils import get_selected_currency_or_setup
from api.settings.utils import set_cost_type
from api.settings.utils import set_currency
from api.settings.utils import SETTINGS_PREFIX
from koku.cache import invalidate_view_cache_for_tenant_and_all_source_types
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from koku.feature_flags import fallback_development_true
from koku.feature_flags import UNLEASH_CLIENT
from masu.util.common import update_enabled_keys
from reporting.models import AWSEnabledTagKeys
from reporting.models import AzureEnabledTagKeys
from reporting.models import GCPEnabledTagKeys
from reporting.models import OCIEnabledTagKeys
from reporting.models import OCPEnabledTagKeys

LOG = logging.getLogger(__name__)

obtainTagKeysProvidersParams = {
    "openshift": {
        "provider": Provider.PROVIDER_OCP,
        "title": "OpenShift labels",
        "leftLabel": "Available labels",
        "rightLabel": "Labels for reporting",
        "enabled_tag_keys": OCPEnabledTagKeys,
    },
    "aws": {
        "provider": Provider.PROVIDER_AWS,
        "title": "Amazon Web Services tags",
        "leftLabel": "Available tags",
        "rightLabel": "Tags for reporting",
        "enabled_tag_keys": AWSEnabledTagKeys,
    },
    "azure": {
        "provider": Provider.PROVIDER_AZURE,
        "title": "Azure tags",
        "leftLabel": "Available tags",
        "rightLabel": "Tags for reporting",
        "enabled_tag_keys": AzureEnabledTagKeys,
    },
    "gcp": {
        "provider": Provider.PROVIDER_GCP,
        "title": "Google Cloud Platform tags",
        "leftLabel": "Available tags",
        "rightLabel": "Tags for reporting",
        "enabled_tag_keys": GCPEnabledTagKeys,
    },
    "oci": {
        "provider": Provider.PROVIDER_OCI,
        "title": "Oracle Cloud Infrastructure tags",
        "leftLabel": "Available tags",
        "rightLabel": "Tags for reporting",
        "enabled_tag_keys": OCIEnabledTagKeys,
    },
}


class Settings:
    """Class for generating Cost Management settings."""

    def __init__(self, request):
        """Initialize settings object with incoming request."""
        self.request = request
        self.factory = RequestFactory()
        self.schema = request.user.customer.schema_name

        self.unleash_context = {"userId": re.sub(r"\D+", "", self.schema)}

    def _get_tag_management_prefix(self, providerName):
        return f"{SETTINGS_PREFIX}.tag-management.{providerName}"

    def _obtain_tag_keys(self, tag_keys_kls):
        """
        Collect the available tag keys for the customer.

        Returns:
            (List) - List of available tag keys objects
            (List) - List of enabled tag keys strings
        """
        enabled = set()
        all_tags_set = set()
        with schema_context(self.schema):
            for tag_key in tag_keys_kls.objects.all():
                all_tags_set.add(tag_key.key)
                if tag_key.enabled:
                    enabled.add(tag_key.key)
        return all_tags_set, enabled

    def _build_components(self):
        """
        Generate cost management form component
        """
        tag_key_text_name = f"{SETTINGS_PREFIX}.tag_management.form-text"

        sub_form_fields = []
        if UNLEASH_CLIENT.is_enabled("cost-management.ui.currency", self.unleash_context, fallback_development_true):
            currency_select_name = "api.settings.currency"
            currency_text_context = "Select the preferred currency view for your organization."
            currency_title = create_plain_text(currency_select_name, "Currency", "h2")
            currency_select_text = create_plain_text(currency_select_name, currency_text_context, "p")
            currency_options = {
                "options": get_currency_options(),
                "initialValue": get_selected_currency_or_setup(self.schema),
                "FormGroupProps": {"style": {"width": "400px"}},
            }
            currency = create_select(currency_select_name, **currency_options)
            sub_form_fields = [currency_title, currency_select_text, currency]

        enable_tags_title = create_plain_text(tag_key_text_name, "Enable tags and labels", "h2")
        tag_key_text_context = (
            "Enable your data source labels to be used as tag keys for report grouping and filtering."
            + " Changes will be reflected within 24 hours. <link>Learn more</link>"
        )
        doc_link = dict(
            href=generate_doc_link(
                "html/managing_cost_data_using_tagging/assembly-configuring-tags-and-labels-in-cost-management"
            )
        )
        tag_key_text = create_plain_text_with_doc(tag_key_text_name, tag_key_text_context, doc_link)

        avail_objs = []
        enabled_objs = []
        for providerName in obtainTagKeysProvidersParams:
            enabled_tag_keys_class = obtainTagKeysProvidersParams[providerName]["enabled_tag_keys"]
            available, enabled = self._obtain_tag_keys(enabled_tag_keys_class)
            avail_objs.append(
                {
                    "label": obtainTagKeysProvidersParams[providerName]["title"],
                    "hasBadge": "true",
                    "children": [
                        {"value": "".join([providerName, "-", tag_key]), "label": tag_key} for tag_key in available
                    ],
                }
            )
            if enabled:
                enabled_objs.extend("".join([providerName, "-", tag_key]) for tag_key in enabled)

        dual_list_options = {
            "isTree": "true",
            "options": avail_objs,
            "leftTitle": "Disabled tags/labels",
            "rightTitle": "Enabled tags/labels",
            "initialValue": enabled_objs,
            "clearedValue": [],
        }

        dual_list_name = "api.settings.tag-management.enabled"
        tags_and_labels = create_dual_list_select(dual_list_name, **dual_list_options)

        sub_form_fields.extend([enable_tags_title, tag_key_text, tags_and_labels])

        customer = self.request.user.customer
        customer_specific_providers = Provider.objects.filter(customer=customer)
        has_aws_providers = customer_specific_providers.filter(type__icontains=Provider.PROVIDER_AWS).exists()

        # cost_type plan settings
        if has_aws_providers:
            cost_type_select_name = "api.settings.cost_type"
            cost_type_text_context = (
                "Select the preferred way of calculating upfront costs, either through savings "
                "plans or subscription fees. This feature is available for Amazon Web Services cost only."
            )
            cost_type_title = create_plain_text(cost_type_select_name, "Show cost as (Amazon Web Services Only)", "h2")
            cost_type_select_text = create_plain_text(cost_type_select_name, cost_type_text_context, "p")
            cost_type_options = {
                "options": get_cost_type_options(),
                "initialValue": get_selected_cost_type_or_setup(self.schema),
                "FormGroupProps": {"style": {"width": "400px"}},
            }
            cost_type = create_select(cost_type_select_name, **cost_type_options)
            sub_form_fields.extend([cost_type_title, cost_type_select_text, cost_type])

        sub_form_name = f"{SETTINGS_PREFIX}.settings.subform"
        sub_form_title = ""
        return create_subform(sub_form_name, sub_form_title, sub_form_fields)

    def _tag_key_handler(self, settings):
        tag_delimiter = "-"
        updated = [False] * len(obtainTagKeysProvidersParams)

        with schema_context(self.schema):
            for ix, provider_name in enumerate(obtainTagKeysProvidersParams):
                enabled_tags_no_abbr = set()
                enabled_tag_keys_class = obtainTagKeysProvidersParams[provider_name]["enabled_tag_keys"]
                provider = obtainTagKeysProvidersParams[provider_name]["provider"]
                available, enabled = self._obtain_tag_keys(enabled_tag_keys_class)

                # build a list of enabled tags for a given provider, removing the provider name prefix
                for enabled_tag in settings.get("enabled", []):
                    if enabled_tag.startswith(provider_name + tag_delimiter):
                        enabled_tags_no_abbr.add(enabled_tag.split(tag_delimiter, 1)[1])

                invalid_keys = {tag_key for tag_key in enabled_tags_no_abbr if tag_key not in available}

                if invalid_keys:
                    key = "settings"
                    message = f"Invalid tag keys provided: {', '.join(invalid_keys)}."
                    raise ValidationError(error_obj(key, message))

                if enabled_tags_no_abbr != enabled:
                    updated[ix] = update_enabled_keys(self.schema, enabled_tag_keys_class, enabled_tags_no_abbr)

                if updated[ix]:
                    invalidate_view_cache_for_tenant_and_source_type(self.schema, provider)

        return any(updated)

    def _currency_handler(self, settings):
        if settings is None:
            return False
        else:
            currency = settings

        try:
            stored_currency = get_selected_currency_or_setup(self.schema)
        except Exception as exp:
            LOG.warning(f"Failed to retrieve currency for schema {self.schema}. Reason: {exp}")
            return False

        if stored_currency == currency:
            return False

        try:
            LOG.info(f"Updating currency to: " + settings)
            set_currency(self.schema, settings)
        except Exception as exp:
            LOG.warning(f"Failed to store new currency settings for schema {self.schema}. Reason: {exp}")
            return False

        invalidate_view_cache_for_tenant_and_all_source_types(self.schema)
        return True

    def _cost_type_handler(self, settings):
        if settings is None:
            return False
        else:
            cost_type = settings

        try:
            stored_cost_type = get_selected_cost_type_or_setup(self.schema)
        except Exception as exp:
            LOG.warning(f"Failed to retrieve cost_type for schema {self.schema}. Reason: {exp}")
            return False

        if stored_cost_type == cost_type:
            return False

        try:
            LOG.info(f"Updating cost_type to: " + settings)
            set_cost_type(self.schema, settings)
        except Exception as exp:
            LOG.warning(f"Failed to store new cost_type settings for schema {self.schema}. Reason: {exp}")
            return False

        invalidate_view_cache_for_tenant_and_source_type(self.schema, Provider.PROVIDER_AWS)
        return True

    def build_settings(self):
        """
        Generate tag management settings

        Returns:
            (List) - List of setting items
        """
        settings = self._build_components()
        return [settings]

    def handle_settings(self, settings):
        """
        Handle setting results

        Args:
            (String) name - unique name for switch.

        Returns:
            (Bool) - True, if a setting had an effect, False otherwise
        """
        currency_settings = settings.get("api", {}).get("settings", {}).get("currency", None)
        currency_change = self._currency_handler(currency_settings)

        cost_type_settings = settings.get("api", {}).get("settings", {}).get("cost_type", None)
        cost_type_change = self._cost_type_handler(cost_type_settings)

        tg_mgmt_settings = settings.get("api", {}).get("settings", {}).get("tag-management", {})
        tags_change = self._tag_key_handler(tg_mgmt_settings)

        if tags_change or currency_change or cost_type_change:
            return True

        return False
