#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Query handler for Tag Mappings."""
from dataclasses import dataclass
from dataclasses import field
from typing import List

from rest_framework.response import Response

from api.settings.tags.mapping.serializers import AddChildSerializer
from api.settings.tags.mapping.utils import FindTagKeyProviders
from api.settings.utils import delayed_summarize_current_month
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping


def format_tag_mapping_relationship(original_response):
    original_data = original_response.data
    formatted_data = {"meta": original_data["meta"], "links": original_data["links"], "data": []}
    parent_dict = {}

    for item in original_data["data"]:
        parent_data = item["parent"]
        child_data = item["child"]
        parent_uuid = parent_data["uuid"]
        if parent_uuid not in parent_dict:
            parent_dict[parent_uuid] = parent_data
            parent_dict[parent_uuid]["children"] = [child_data]
        else:
            parent_dict[parent_uuid]["children"].append(child_data)

    formatted_data["data"] = [{"parent": parent_data} for parent_data in parent_dict.values()]
    formatted_response = Response(formatted_data)

    return formatted_response


@dataclass
class AddChildQueryHandler:
    serializer: AddChildSerializer
    children_rows: List[EnabledTagKeys] = field(default_factory=list)
    parent_row: EnabledTagKeys = field(init=False)

    def __post_init__(self):
        """Collects the enabled tag keys rows for the parent & children."""
        self.parent_row = EnabledTagKeys.objects.get(uuid=self.serializer.data.get("parent"))
        self.children_rows = list(EnabledTagKeys.objects.filter(uuid__in=self.serializer.data.get("children")))

    def bulk_create_tag_mappings(self, schema_name):
        """Bulk creates the tag mapping relationships."""
        tag_mappings = [TagMapping(parent=self.parent_row, child=child_row) for child_row in self.children_rows]
        TagMapping.objects.bulk_create(tag_mappings)
        finder = FindTagKeyProviders(self.children_rows)
        provider_type_to_uuid_mapping = finder.create_provider_type_to_uuid_mapping()
        for provider_type, provider_uuids in provider_type_to_uuid_mapping.items():
            delayed_summarize_current_month(schema_name, provider_uuids, provider_type)
