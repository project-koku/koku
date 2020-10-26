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
"""Utilities for Settings."""
from koku.settings import OPENSHIFT_DOC_VERSION

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
    prefix = f"https://access.redhat.com/documentation/en-us/openshift_container_platform/{OPENSHIFT_DOC_VERSION}/html"
    return f"{prefix}/{path}"


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
