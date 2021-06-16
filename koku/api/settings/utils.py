#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Utilities for Settings."""
SETTINGS_PREFIX = "api.settings"
OPENSHIFT_SETTINGS_PREFIX = f"{SETTINGS_PREFIX}.openshift"
OPENSHIFT_TAG_MGMT_SETTINGS_PREFIX = f"{OPENSHIFT_SETTINGS_PREFIX}.tag-management"


def create_subform(name, title, fields):
    """
    Create a subfrom for the settings.

    Args:
        (String) name - unique name for subform.
        (String) title - Display title.
        (List) fields - List of field components.

    Returns:
        (Dict) - Subform component.
    """
    subform = {"title": title, "name": name, "fields": fields, "component": "sub-form"}
    return subform


def create_plain_text(name, label, variant):
    """
    Create a plain text field for the settings.

    Args:
        (String) name - unique name for switch.
        (String) label - Display text.
        (String) variant - plain text variant. I have no idea why they call it that way.
                           But, it is actually HTML element that will wrap the text (label).

    Returns:
        [Dict] - plain text component.
    """
    plain_text = {"label": label, "name": name, "variant": variant, "component": "plain-text"}
    return plain_text


def create_plain_text_with_doc(name, label, doc_link):
    """
    Create a plain text field with links for the settings.

    Args:
        (String) name - unique name for switch.
        (String) label - Display text.
        (Dict) doc_link - documentation props.

    Returns:
        [Dict] - plain text with links component.
    """
    plain_text = {"component": "plain-text-with-links", "text": label, "linkProps": [doc_link], "name": name}
    return plain_text


def generate_doc_link(path):
    """
    Generate cost management link to a given path.

    Args:
        (String) path - path to the documentation.
    """
    return f"https://access.redhat.com/documentation/en-us/cost_management_service/2021/{path}"


def create_dual_list_select(name, left_options=[], right_options=[], **kwargs):
    """
    Create a dual-list-select for the settings.

    Args:
        (String) name - unique name for switch.
        (List) left_options - List of dictionaries.
        (List) right_options - List of dictionaries.

    Returns:
        [Dict] - Subform component.
    """
    dual_list_select = {"component": "dual-list-select", "name": name}
    dual_list_select.update(**kwargs)
    return dual_list_select
