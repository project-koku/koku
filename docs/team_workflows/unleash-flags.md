# Unleash Feature Flag Policy

Team policy for Unleash flags in koku. Agent summaries live in
[`CLAUDE.md`](../../CLAUDE.md) and [`AGENTS.md`](../../AGENTS.md); this document
is the source of truth for polarity, lifecycle, catalog, and maintenance.

## Goals

1. New feature flags use **enablement** polarity (ON = new path), not disablement.
2. Every flag in code is cataloged here and kept in sync with PRs.
3. The team has a routine flow to review and clean up flags.

## Flag types

| Type | Polarity | When to use | Naming |
|------|----------|-------------|--------|
| **Feature enablement** | ON enables new/extra path | New features, SQL/pipeline changes, risky data-path changes | `cost-management.backend.<feature>` or `enable-<feature>` |
| **Ops kill-switch** | ON stops or freezes something | Incident response, migration windows, per-tenant emergency stops | `disable-*` / `is_*_disabled` allowed |
| **Ops classification** | ON marks tenant for special handling | Large/penalty customers, rate limits | descriptive (`large-customer`, …) |

**Rule:** do **not** create kill-switch / `disable-*` flags for feature rollout.
New product work must be enablement-style with default OFF in stage/prod.

## When a flag is required

Gate behind Unleash when the change could negatively affect production:

- New or changed SQL INSERT/UPDATE/DELETE templates in the pipeline
- New pipeline steps or cost-model update flow changes
- New tables, FK relationships, or FK `on_delete` behavior changes
- Changes to data written to reporting/summary tables

Purely additive API changes (new endpoints, optional fields) that do not affect
data processing may skip a flag.

## Code pattern

```python
# 1. Constant in koku/masu/processor/__init__.py
MY_FEATURE_UNLEASH_FLAG = "cost-management.backend.my_feature_name"

# 2. Gate (enablement)
from masu.processor import is_feature_flag_enabled_by_schema, MY_FEATURE_UNLEASH_FLAG

if is_feature_flag_enabled_by_schema(schema, MY_FEATURE_UNLEASH_FLAG, dev_fallback=True):
    # new path
else:
    # legacy path — must remain functional and tested
```

### `dev_fallback`

Implemented in [`koku/masu/processor/__init__.py`](../../koku/masu/processor/__init__.py)
via `fallback_development_true` in [`koku/koku/feature_flags.py`](../../koku/koku/feature_flags.py).

| Value | Behavior when Unleash is down / flag unknown |
|-------|-----------------------------------------------|
| `True` (preferred for new features) | ON only if client `environment` is `development`; OFF in stage/prod |
| `False` (default of helper) | Always OFF — use for rollback-sensitive paths (e.g. RTU) |

`dev_fallback=True` is **not** “default ON in production”.

### On-prem defaults

When `ONPREM=True`, Unleash is replaced by `MockUnleashClient`. Add an entry to
`ONPREM_FLAG_DEFAULTS` in `feature_flags.py` only when on-prem needs a value
different from the generic fallback.

### Multi-call-site helpers

If a flag is checked from many places, expose a named helper in
`masu/processor/__init__.py` (e.g. `is_customer_large()`) instead of inlining
the string everywhere.

## Lifecycle

1. **Create** — constant + gate + catalog row in this file (same PR).
2. **Roll out** — OFF → selective schema enablement → broad stage → prod.
3. **Validate** — keep legacy path until the flag has been ON in production for
   at least one full billing cycle.
4. **Remove** — delete flag usage, legacy path, constant, on-prem default, and
   this catalog row (same PR). Open a cleanup ticket if needed (template below).

Also update this catalog when deprecating endpoints that still reference flags
(see [`deprecating_an_endpoint.md`](deprecating_an_endpoint.md)).

## Catalog

Polarity is inferred from code. **Live ON/OFF in Unleash stage/prod is not
tracked here** — check Unleash during monthly maintenance.

**Aligns with enablement convention?** `yes` = suitable pattern for new feature
flags. `no (ops …)` = allowed exception; do not copy this pattern for new
product work.

### Feature enablement

| Unleash flag | Constant / helper | Aligns? | Code default | On-prem default | Purpose | Primary refs |
|--------------|-------------------|---------|--------------|-----------------|---------|--------------|
| `cost-management.backend.ocp_gpu_cost_model` | `OCP_GPU_COST_MODEL_UNLEASH_FLAG` | yes | `dev_fallback=True` | `True` | GPU cost model / metrics / API | `ocp_report_db_accessor.py`, `api/metrics/constants.py`, `api/report/ocp/view.py` |
| `cost-management.backend.unattributed_storage_gcp` | `GCP_UNATTRIBUTED_STORAGE_UNLEASH_FLAG` | yes | `dev_fallback=True` | — | GCP unattributed storage path | `gcp_report_db_accessor.py` |
| `cost-management.backend.cost_breakdown_rates_to_usage` | `COST_BREAKDOWN_RTU_UNLEASH_FLAG` | yes | `dev_fallback=False` | — | Rates-to-usage cost breakdown (rollback-sensitive) | `ocp_cost_model_cost_updater.py` |
| `cost-management.backend.constant-currency` | `CONSTANT_CURRENCY_FLAG` | yes | omitted (`False`) | `False` | Constant currency reporting/forecast | `api/query_handler.py`, `forecast/forecast.py`, report handlers |
| `cost-management.backend.ocp_post_write_parquet_dedup` | `OCP_POST_WRITE_PARQUET_DEDUP_FLAG` | yes | omitted (`False`) | — | OCP parquet post-write dedup | `parquet_report_processor.py` |
| `cost-management.backend.is_cross_org_cluster_lookup_enabled` | `CROSS_ORG_CLUSTER_LOOKUP_FLAG` | yes | omitted (`False`) | — | Cross-org cluster lookup | `kafka_msg_handler.py` |
| `cost-management.backend.feature-4403-enable-ec2-compute-processing` | `is_feature_cost_4403_ec2_compute_cost_enabled` | yes | `fallback_development_true` | — | EC2 per-VM compute cost | `aws_report_parquet_summary_updater.py`, `api/report/aws/view.py` |
| `cost-management.backend.rate-limit-tag-queries` | `TAG_QUERY_RATE_LIMIT_FLAG` | yes | omitted (`False`) | — | Enable tag-query throttling | `api/common/throttling.py` |
| `cost-management.backend.enable-purge-turnpike` | `is_purge_trino_files_enabled` | yes | omitted (`False`) | — | Allow Trino/S3 purge tasks | `masu/celery/tasks.py` |
| `cost-management.backend.enable_data_validation` | `is_validation_enabled` | yes | omitted (`False`) | — | Enable data validation tasks | `masu/processor/tasks.py` |
| `cost-management.backend.override_customer_group_by_limit` | `check_group_by_limit` | yes | omitted (`False`) | `False` | Raise group_by limit for tenant | `api/report/serializers.py` |
| `cost-management.backend.ingress-rbac-grace-period-enabled` | `is_ingress_rbac_grace_period_enabled` | yes | omitted (`False`) | — | Ingress RBAC grace period | `api/common/permissions/ingress_access.py` |
| `cost-management.backend.hcs-data-processor` | inline in `hcs/tasks.py` | yes | omitted (`False`) | — | HCS data processor (or `ENABLE_HCS_DEBUG`) | `hcs/tasks.py` |
| `cost-management.backend.subs-data-extraction` | inline in `subs/tasks.py` | yes | omitted (`False`) | — | SUBS extraction (or debug/metered) | `subs/tasks.py` |
| `cost-management.backend.subs-data-messaging` | inline in `subs/tasks.py` | yes | omitted (`False`) | — | SUBS messaging (or `ENABLE_SUBS_DEBUG`) | `subs/tasks.py` |

### Ops kill-switch (does **not** align with enablement convention)

| Unleash flag | Constant / helper | Aligns? | Purpose | Primary refs |
|--------------|-------------------|---------|---------|--------------|
| `cost-management.backend.disable-cloud-source-processing` | `is_cloud_source_processing_disabled` | no (ops kill-switch) | Stop cloud source processing for schema | `orchestrator.py` |
| `cost-management.backend.disable-summary-processing` | `is_summary_processing_disabled` | no (ops kill-switch) | Stop summary processing for schema | `masu/processor/tasks.py` |
| `cost-management.backend.disable-ocp-on-cloud-summary` | `is_ocp_on_cloud_summary_disabled` | no (ops kill-switch) | Stop OCP-on-cloud summary | `masu/processor/tasks.py` |
| `cost-management.backend.disable-source` | `is_source_disabled` | no (ops kill-switch) | Stop processing for a `source_uuid` | `masu/processor/tasks.py` |
| `cost-management.backend.disable-cost-model-writes` | `COST_MODEL_WRITE_FREEZE_FLAG` / `is_cost_model_writes_disabled` | no (ops kill-switch) | Freeze cost-model API writes (migrations) | `cost_models/price_list_serializer.py` |
| `cost-management.backend.disable_price_list` | `DISABLE_PRICE_LIST_UNLEASH_FLAG` | no (ops kill-switch) | Force price list ineffective | `cost_model_db_accessor.py` |
| `cost-management.backend.is_tag_processing_disabled` | `is_tag_processing_disabled` | no (ops kill-switch) | Skip tag processing for schema | AWS/Azure/GCP report accessors |
| `cost-management.backend.disable-ingress-rate-limit` | `is_ingress_rate_limiting_disabled` | no (ops kill-switch) | ON = ingress rate limiting off | ingress serializers; on-prem default `True` |

### Ops classification (does **not** align with enablement convention)

| Unleash flag | Helper | Aligns? | Purpose | Primary refs |
|--------------|--------|---------|---------|--------------|
| `cost-management.backend.large-customer` | `is_customer_large` | no (ops classification) | Route/treat tenant as large | `orchestrator.py` |
| `cost-management.backend.penalty-customer` | `is_customer_penalty` | no (ops classification) | Penalty customer handling | `__init__.py` helper |
| `cost-management.backend.large-customer.rate-limit` | `is_rate_limit_customer_large` | no (ops classification) | Rate-limit large customer work | `masu/processor/tasks.py` |

### Dev-only templates (not production flags)

Defined in [`dev/scripts/setup_unleash.py`](../../dev/scripts/setup_unleash.py) for local Unleash bootstrap:

- `cost-management.backend.schema-flag-template`
- `cost-management.backend.source-uuid-flag-template`

## Routine maintenance

**Cadence:** monthly (or once per tech-debt review in the sprint).

**Checklist:**

1. Open Unleash (stage + prod). List `cost-management.backend.*` flags.
2. Diff against this catalog — add missing rows or remove stale ones via PR.
3. For **enablement** flags ON in prod for ≥1 billing cycle with no issues: open
   cleanup tickets to remove flag + legacy path.
4. For **kill-switches** unexpectedly ON: investigate and clear or document why.
5. Note flags still using `dev_fallback` omitted/`False` that should probably be
   `True` for new feature work (do not blindly flip rollback-sensitive flags).

## Related docs

- [`CLAUDE.md`](../../CLAUDE.md) — short always-on agent rules
- [`AGENTS.md`](../../AGENTS.md) — Cursor / cross-tool agent guide
- [`deprecating_an_endpoint.md`](deprecating_an_endpoint.md) — remove unused flags when deprecating APIs
- [`docs/devtools.md`](../devtools.md) — local Unleash credentials
