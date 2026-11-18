#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Masu endpoint: evaluate Unleash feature flags for a tenant schema."""
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.iam.models import Tenant
from masu.processor import APPLY_TAG_MAPPINGS_FLAG
from masu.processor import is_feature_flag_enabled_by_schema
from masu.processor import OCP_TAG_MAPPING_DIAGNOSTICS_FLAG
from masu.processor import OCP_TAG_MAPPING_MATERIALIZED_CANDIDATES_FLAG
from masu.processor import OCP_TAG_MAPPING_PRE_ANALYZE_FLAG
from masu.processor import OCP_TAG_MAPPING_STATEMENT_TIMEOUT_FLAG
from masu.processor import TAG_QUERY_RATE_LIMIT_FLAG

# Ops-oriented defaults for incident triage. Schema-scoped flags only.
# Strings without a module constant match existing UNLEASH_CLIENT call sites.
DEFAULT_SCHEMA_FEATURE_FLAGS = (
    APPLY_TAG_MAPPINGS_FLAG,
    "cost-management.backend.disable-cloud-source-processing",
    "cost-management.backend.disable-cost-model-processing",
    "cost-management.backend.disable-ocp-on-cloud-summary",
    "cost-management.backend.disable-summary-processing",
    "cost-management.backend.large-customer",
    "cost-management.backend.large-customer.rate-limit",
    "cost-management.backend.penalty-customer",
    OCP_TAG_MAPPING_DIAGNOSTICS_FLAG,
    OCP_TAG_MAPPING_MATERIALIZED_CANDIDATES_FLAG,
    OCP_TAG_MAPPING_PRE_ANALYZE_FLAG,
    OCP_TAG_MAPPING_STATEMENT_TIMEOUT_FLAG,
    TAG_QUERY_RATE_LIMIT_FLAG,
)


def _parse_flags_param(raw_flags):
    """Split an optional comma-separated flags query into a de-duplicated list.

    Omitting the parameter (None) uses DEFAULT_SCHEMA_FEATURE_FLAGS. An explicit
    empty or whitespace-only ``flags`` value is rejected with ValidationError.
    """
    if raw_flags is None:
        return list(DEFAULT_SCHEMA_FEATURE_FLAGS)
    flags = []
    seen = set()
    for part in raw_flags.split(","):
        name = part.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        flags.append(name)
    if not flags:
        raise ValidationError({"flags": "Provide at least one flag name, or omit the parameter."})
    return flags


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def schema_feature_flags(request):
    """Return whether selected Unleash flags are enabled for a tenant schema.

    Query parameters:
        schema - tenant schema name (required), e.g. acct5910538
        flags  - optional comma-separated Unleash flag names; defaults to a
                 curated ops list (penalty, rate-limit, OCP tag-mapping, etc.)

    Evaluation uses context ``{"schema": <schema>}``, matching schema-scoped
    Unleash strategies. This does not list every flag in the Unleash project.
    """
    schema = request.query_params.get("schema")
    if not schema:
        raise ValidationError({"schema": "This parameter is required."})
    if not Tenant.objects.filter(schema_name=schema).exists():
        raise ValidationError({"schema": f"Schema '{schema}' does not exist."})

    flag_names = _parse_flags_param(request.query_params.get("flags"))
    flags = {name: is_feature_flag_enabled_by_schema(schema, name) for name in flag_names}
    return Response({"schema": schema, "flags": flags})
