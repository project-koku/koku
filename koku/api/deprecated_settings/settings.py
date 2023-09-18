#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Data Driven Component Generation for Tag Management Settings."""
import logging

from django.test import RequestFactory
from django_tenants.utils import schema_context
from rest_framework.serializers import ValidationError

from api.common import error_obj
from api.common import log_json
from api.deprecated_settings.utils import create_dual_list_select
from api.deprecated_settings.utils import create_plain_text
from api.deprecated_settings.utils import create_plain_text_with_doc
from api.deprecated_settings.utils import create_select
from api.deprecated_settings.utils import create_subform
from api.deprecated_settings.utils import generate_doc_link
from api.deprecated_settings.utils import get_cost_type_options
from api.deprecated_settings.utils import get_currency_options
from api.deprecated_settings.utils import get_selected_cost_type_or_setup
from api.deprecated_settings.utils import get_selected_currency_or_setup
from api.deprecated_settings.utils import set_cost_type
from api.deprecated_settings.utils import set_currency
from api.deprecated_settings.utils import SETTINGS_PREFIX
from api.provider.models import Provider
from koku.cache import invalidate_view_cache_for_tenant_and_all_source_types
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from reporting.models import AWSEnabledCategoryKeys
from reporting.models import EnabledTagKeys


def update_enabled_keys(schema, enabled_keys_model, enabled_keys, provider_type=None):  # noqa: C901
    ctx = {"schema": schema, "model": enabled_keys_model._meta.model_name, "enabled_keys": enabled_keys}
    LOG.info(log_json(msg="updating enabled tag keys records", context=ctx))
    changed = False

    enabled_keys_set = set(enabled_keys)
    update_keys_enabled = []
    update_keys_disabled = []

    with schema_context(schema):
        if provider_type:
            key_objects = enabled_keys_model.objects.filter(provider_type=provider_type)
        else:
            key_objects = enabled_keys_model.objects.all()
        for key in key_objects:
            if key.key in enabled_keys_set:
                if not key.enabled:
                    update_keys_enabled.append(key.key)
            else:
                update_keys_disabled.append(key.key)

        # When we are in create mode, we do not want to change the state of existing keys
        if update_keys_enabled or update_keys_disabled:
            changed = True
            if update_keys_enabled:
                LOG.info(
                    log_json(msg="updating keys to ENABLED", keys_to_update=len(update_keys_enabled), context=ctx)
                )
                if provider_type:
                    enabled_keys_model.objects.filter(key__in=update_keys_enabled, provider_type=provider_type).update(
                        enabled=True
                    )
                else:
                    enabled_keys_model.objects.filter(key__in=update_keys_enabled).update(enabled=True)

            if update_keys_disabled:
                LOG.info(
                    log_json(msg="updating keys to DISABLED", keys_to_update=len(update_keys_disabled), context=ctx)
                )
                if provider_type:
                    enabled_keys_model.objects.filter(
                        key__in=update_keys_disabled, provider_type=provider_type
                    ).update(enabled=False)
                else:
                    enabled_keys_model.objects.filter(key__in=update_keys_disabled).update(enabled=False)

    if not changed:
        LOG.info(log_json(msg="no enabled keys updated", context=ctx))

    return changed


LOG = logging.getLogger(__name__)

obtainCategoryKeysParams = {
    "aws": {
        "provider": Provider.PROVIDER_AWS,
        "title": "Amazon Web Services Categories",
        "leftLabel": "Available category keys",
        "rightLabel": "Category keys for reporting",
        "enabled_model": AWSEnabledCategoryKeys,
    }
}

obtainTagKeysProvidersParams = {
    "openshift": {
        "provider": Provider.PROVIDER_OCP,
        "title": "OpenShift labels",
        "leftLabel": "Available labels",
        "rightLabel": "Labels for reporting",
        "enabled_model": EnabledTagKeys,
    },
    "aws": {
        "provider": Provider.PROVIDER_AWS,
        "title": "Amazon Web Services tags",
        "leftLabel": "Available tags",
        "rightLabel": "Tags for reporting",
        "enabled_model": EnabledTagKeys,
    },
    "azure": {
        "provider": Provider.PROVIDER_AZURE,
        "title": "Azure tags",
        "leftLabel": "Available tags",
        "rightLabel": "Tags for reporting",
        "enabled_model": EnabledTagKeys,
    },
    "gcp": {
        "provider": Provider.PROVIDER_GCP,
        "title": "Google Cloud Platform tags",
        "leftLabel": "Available tags",
        "rightLabel": "Tags for reporting",
        "enabled_model": EnabledTagKeys,
    },
    "oci": {
        "provider": Provider.PROVIDER_OCI,
        "title": "Oracle Cloud Infrastructure tags",
        "leftLabel": "Available tags",
        "rightLabel": "Tags for reporting",
        "enabled_model": EnabledTagKeys,
    },
}

enabledKeyFormUI = {
    "tag": {
        "params": obtainTagKeysProvidersParams,
        "title": "Enable tag keys and labels",
        "key_text_context": (
            f"Enable your data source labels to be used as tag keys for report grouping and filtering."
            + " Changes will be reflected within 24 hours. <link>Learn more</link>"
        ),
        "leftTitle": "Disabled tags/labels",
        "rightTitle": "Enabled tags/labels",
        "doc_link": "html/managing_cost_data_using_tagging/assembly-configuring-tags-and-labels-in-cost-management",
        "api_settings_name": "tag",
    },
    "aws_category": {
        "params": obtainCategoryKeysParams,
        "title": "Enable AWS category keys",
        "key_text_context": (
            f"Enable your data source labels to be used as AWS category keys for report grouping and filtering."
            + " Changes will be reflected within 24 hours."
        ),
        "leftTitle": "Disabled AWS category keys",
        "rightTitle": "Enabled AWS category keys",
        "api_settings_name": "aws-category",
    },
}


class Settings:
    """Class for generating Cost Management settings."""

    def __init__(self, request):
        """Initialize settings object with incoming request."""
        self.request = request
        self.factory = RequestFactory()
        self.schema = request.user.customer.schema_name

    def _get_tag_management_prefix(self, providerName):
        return f"{SETTINGS_PREFIX}.tag-management.{providerName}"

    def _build_disabled_tag_form(self, sub_form_fields):
        title = "Enable tag keys and labels (DISABLED)"
        key_text_name = f"{SETTINGS_PREFIX}.disabled_management.form-text"
        enabled_key_title = create_plain_text(key_text_name, title, "h2")
        key_text_content = "This feature is currently disabled for schedule maintaince."
        key_text = create_plain_text(key_text_name, key_text_content, "p")
        dual_list_options = {
            "isTree": "true",
            "options": [],
            "leftTitle": "",
            "rightTitle": "",
            "initialValue": [],
            "clearedValue": [],
        }
        dual_list_name = f"api.deprecated_settings.disabled-management.enabled"
        keys_and_labels = create_dual_list_select(dual_list_name, **dual_list_options)
        sub_form_fields.extend([enabled_key_title, key_text, keys_and_labels])
        return sub_form_fields

    def _obtain_enabled_keys(self, keys_class, provider_type=None):
        """
        Collect the available tag keys for the customer.

        Returns:
            (List) - List of available tag keys objects
            (List) - List of enabled tag keys strings
        """
        enabled = set()
        all_keys_set = set()
        with schema_context(self.schema):
            if provider_type:
                key_objects = keys_class.objects.filter(provider_type=provider_type)
            else:
                key_objects = keys_class.objects.all()
            for key in key_objects:
                all_keys_set.add(key.key)
                if key.enabled:
                    enabled.add(key.key)
        return all_keys_set, enabled

    def _build_enable_key_form(self, sub_form_fields, key_type):
        """Builds an enabled key form."""
        provider_params = enabledKeyFormUI[key_type]["params"]
        key_text_name = f"{SETTINGS_PREFIX}.{key_type}_management.form-text"
        enabled_key_title = create_plain_text(key_text_name, enabledKeyFormUI[key_type]["title"], "h2")
        if doc_link := enabledKeyFormUI[key_type].get("doc_link"):
            key_text = create_plain_text_with_doc(
                key_text_name, enabledKeyFormUI[key_type]["key_text_context"], dict(href=generate_doc_link(doc_link))
            )
        else:
            key_text = create_plain_text(key_text_name, enabledKeyFormUI[key_type]["key_text_context"], "p")

        avail_objs = []
        enabled_objs = []
        for providerName in provider_params:
            enabled_key_model = provider_params[providerName]["enabled_model"]
            if key_type == "tag":
                available, enabled = self._obtain_enabled_keys(
                    enabled_key_model, provider_params[providerName]["provider"]
                )
            else:
                available, enabled = self._obtain_enabled_keys(enabled_key_model)
            avail_objs.append(
                {
                    "label": provider_params[providerName]["title"],
                    "hasBadge": "true",
                    "children": [{"value": "".join([providerName, "-", key]), "label": key} for key in available],
                }
            )
            if enabled:
                enabled_objs.extend("".join([providerName, "-", key]) for key in enabled)

        if not avail_objs and not enabled_objs:
            return sub_form_fields

        dual_list_options = {
            "isTree": "true",
            "options": avail_objs,
            "leftTitle": enabledKeyFormUI[key_type]["leftTitle"],
            "rightTitle": enabledKeyFormUI[key_type]["rightTitle"],
            "initialValue": enabled_objs,
            "clearedValue": [],
        }
        dual_list_name = (
            f"api.deprecated_settings.{enabledKeyFormUI[key_type]['api_settings_name']}-management.enabled"
        )
        keys_and_labels = create_dual_list_select(dual_list_name, **dual_list_options)

        sub_form_fields.extend([enabled_key_title, key_text, keys_and_labels])
        return sub_form_fields

    def _build_components(self):
        """
        Generate cost management form component
        """

        sub_form_fields = []
        currency_select_name = "api.deprecated_settings.currency"
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
        sub_form_fields = self._build_enable_key_form(sub_form_fields, "tag")
        customer = self.request.user.customer
        customer_specific_providers = Provider.objects.filter(customer=customer)
        has_aws_providers = customer_specific_providers.filter(type__icontains=Provider.PROVIDER_AWS).exists()

        # cost_type plan settings
        if has_aws_providers:
            cost_type_select_name = "api.deprecated_settings.cost_type"
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
            sub_form_fields = self._build_enable_key_form(sub_form_fields, "aws_category")

        sub_form_name = f"{SETTINGS_PREFIX}.settings.subform"
        sub_form_title = ""
        return create_subform(sub_form_name, sub_form_title, sub_form_fields)

    def _enable_key_handler(self, settings, params, key_type):
        enabled_delimiter = "-"
        updated = [False] * len(params)

        with schema_context(self.schema):
            for ix, provider_name in enumerate(params):
                enabled_keys_no_abbr = set()
                enabled_keys_class = params[provider_name]["enabled_model"]
                provider = params[provider_name]["provider"]
                if key_type == "tag":
                    available, enabled = self._obtain_enabled_keys(
                        enabled_keys_class, params[provider_name]["provider"]
                    )
                else:
                    available, enabled = self._obtain_enabled_keys(enabled_keys_class)

                # build a list of enabled tags for a given provider, removing the provider name prefix
                for enabled_tag in settings.get("enabled", []):
                    if enabled_tag.startswith(provider_name + enabled_delimiter):
                        enabled_keys_no_abbr.add(enabled_tag.split(enabled_delimiter, 1)[1])

                invalid_keys = {enabled_key for enabled_key in enabled_keys_no_abbr if enabled_key not in available}

                if invalid_keys:
                    key = "settings"
                    message = f"Invalid {key_type} keys provided: {', '.join(invalid_keys)}."
                    raise ValidationError(error_obj(key, message))

                if enabled_keys_no_abbr != enabled:
                    if key_type == "tag":
                        updated[ix] = update_enabled_keys(
                            self.schema, enabled_keys_class, enabled_keys_no_abbr, params[provider_name]["provider"]
                        )
                    else:
                        updated[ix] = update_enabled_keys(self.schema, enabled_keys_class, enabled_keys_no_abbr)

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
        results = []
        currency_settings = settings.get("api", {}).get("settings", {}).get("currency", None)
        results.append(self._currency_handler(currency_settings))

        cost_type_settings = settings.get("api", {}).get("settings", {}).get("cost_type", None)
        results.append(self._cost_type_handler(cost_type_settings))
        if not is_ddf_tag_form_disabled():
            tg_mgmt_settings = settings.get("api", {}).get("settings", {}).get("tag-management", {})
            results.append(self._enable_key_handler(tg_mgmt_settings, obtainTagKeysProvidersParams, "tag"))

        category_settings = settings.get("api", {}).get("settings", {}).get("aws-category-management", {})
        results.append(self._enable_key_handler(category_settings, obtainCategoryKeysParams, "AWS category"))

        return any(results)
