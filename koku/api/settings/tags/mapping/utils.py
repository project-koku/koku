#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Query handler for Tag Mappings."""
from django.db import connection

from koku.cache import get_cached_tag_rate_map
from koku.cache import set_cached_tag_rate_map


def retrieve_tag_rate_mapping(schema_name):
    """Retrieves the tag rate mapping."""
    tag_rate_map = get_cached_tag_rate_map(schema_name)
    if tag_rate_map:
        return tag_rate_map
    with connection.cursor() as cursor:
        sql = """
            WITH cte_ocp_cost_model_rates AS (
                SELECT
                    uuid,
                    rate->'tag_rates'->>'tag_key' AS tag_key
                FROM
                    cost_model,
                    LATERAL jsonb_array_elements(rates) rate
                WHERE
                    source_type = 'OCP'
            ),
            cte_cost_model_mapping AS (
                SELECT
                    cm_tag_keys.uuid AS cost_model_uuid,
                    cost_model_map.provider_uuid AS provider_uuid,
                    ARRAY_AGG(cm_tag_keys.tag_key) AS tag_keys
                FROM cte_ocp_cost_model_rates AS cm_tag_keys
                LEFT JOIN cost_model_map ON cm_tag_keys.uuid = cost_model_map.cost_model_id
                WHERE cm_tag_keys IS NOT NULL GROUP BY cost_model_uuid, provider_uuid
            )
            SELECT
                cost_model_uuid as cost_model_id,
                provider_uuid as provider_uuid,
                enabled_keys.key as enabled_key
            FROM cte_cost_model_mapping AS cm_mapping
            LEFT JOIN reporting_enabledtagkeys AS enabled_keys
                ON enabled_keys.key = ANY (cm_mapping.tag_keys)
            WHERE enabled_keys.provider_type = 'OCP'
                AND enabled_keys.enabled = TRUE;
        """
        cursor.execute(sql)
        tag_rate_map = cursor.fetchall()
    tag_rate_mapping = {}
    for row in tag_rate_map:
        cost_model_id, provider_uuid, tag_key = row
        tag_rate_mapping[tag_key] = {"provider_uuid": str(provider_uuid), "cost_model_id": str(cost_model_id)}
    set_cached_tag_rate_map(schema_name, tag_rate_mapping)
    return tag_rate_mapping
