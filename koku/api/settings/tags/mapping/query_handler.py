#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Query handler for Tag Mappings."""
import dataclasses
import uuid
from collections import OrderedDict
from typing import Union


@dataclasses.dataclass(frozen=True)
class TagKey:
    uuid: str
    key: uuid.UUID
    source_type: str


@dataclasses.dataclass(frozen=True)
class Relationship:
    parent: TagKey
    children: list[TagKey] = dataclasses.field(default_factory=list)

    @classmethod
    def create_list_of_relationships(
        cls, data: list[dict[str : dict[str, Union[uuid.UUID, str]]]]
    ) -> list["Relationship"]:
        result = OrderedDict()

        for item in data:
            parent = TagKey(**item["parent"])
            child = TagKey(**item["child"])
            if parent in result:
                result[parent].children.append(child)
            else:
                result[parent] = Relationship(parent, [child])

        return list(result.values())
