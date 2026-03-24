# Retention Pipeline Changes

**Parent**: [README.md](README.md) · **Status**: Draft

---

## Overview

This document covers three changes to the data retention pipeline:

1. **Read path refactor** — all consumers read retention from the new
   helper instead of `settings.RETAIN_NUM_MONTHS` directly.
2. **Calendar-month fix** — `_calculate_expiration_date()` switches from
   `months × 30 days` to `relativedelta(months=N)`.
3. **Kafka ingest gate** — updated to use the same helper.

---

## 1. Read Path Refactor

### Current Call Sites

Every consumer currently reads a static value cached at startup:

| Consumer | Current Source | File |
|----------|---------------|------|
| `ExpiredDataRemover.__init__` | `Config.MASU_RETAIN_NUM_MONTHS` | `masu/processor/expired_data_remover.py:51` |
| `kafka_msg_handler` | `Config.MASU_RETAIN_NUM_MONTHS` | `masu/external/kafka_msg_handler.py:391` |
| `materialized_view_month_start` | `settings.RETAIN_NUM_MONTHS` | `api/utils.py:514` |
| `masu/api/status.py` | `Config.MASU_RETAIN_NUM_MONTHS` | `masu/api/status.py:55` |

### Proposed Change

All call sites switch to `get_data_retention_months(schema_name)`,
defined in [data-model.md § Read Helper](data-model.md#read-helper).

```
Before:  Config.MASU_RETAIN_NUM_MONTHS  (static int, one value for all tenants)
After:   get_data_retention_months(schema_name)  (per-tenant, DB-backed)
```

**Impact on `Config.MASU_RETAIN_NUM_MONTHS`**: This attribute is no
longer the primary source of truth. It remains as a module-level
fallback for code paths that do not have a `schema_name` in scope
(e.g., `masu/api/status.py` for operational visibility). The env-var
override logic in the helper handles this transparently.

### `materialized_view_month_start` Change

This function is called from report serializers where `request.user`
is available:

```python
# api/utils.py (modified)

def materialized_view_month_start(dh=DateHelper(), schema_name=None):
    """Datetime of midnight on the first of the month where
    materialized summary starts."""
    months = (
        get_data_retention_months(schema_name)
        if schema_name
        else settings.RETAIN_NUM_MONTHS
    )
    return dh.this_month_start - relativedelta(months=months - 1)
```

Callers in report serializers pass `schema_name` from the request
context. The fallback to `settings.RETAIN_NUM_MONTHS` preserves
backwards compatibility for callers that don't have a schema.

---

## 2. Calendar-Month Expiration Fix

### Current Bug

```python
# masu/processor/expired_data_remover.py (current)

def _calculate_expiration_date(self):
    months = self._months_to_keep
    today = DateHelper().today
    middle_of_current_month = today.replace(day=15)
    num_of_days_to_expire_date = months * timedelta(days=30)  # ← BUG
    middle_of_expire_date_month = middle_of_current_month - num_of_days_to_expire_date
    expiration_date = datetime(
        year=middle_of_expire_date_month.year,
        month=middle_of_expire_date_month.month,
        day=1,
        tzinfo=settings.UTC,
    )
    return expiration_date
```

**Problem**: `months × 30 days` is an approximation. For 12 months it
computes 360 days instead of a full calendar year. The PRD explicitly
states: *"approximating 1 month = 30 days is not valid"*.

**Example**: With `data_retention_months = 12` and today = March 10, 2026:
- Current: `12 × 30 = 360 days` → expiration ≈ April 1, 2025
- Correct: `relativedelta(months=12)` → March 1, 2025

### Proposed Fix

```python
# masu/processor/expired_data_remover.py (proposed)

def _calculate_expiration_date(self):
    months = self._months_to_keep
    today = DateHelper().today
    expiration_ref = today - relativedelta(months=months)
    expiration_date = datetime(
        year=expiration_ref.year,
        month=expiration_ref.month,
        day=1,
        tzinfo=settings.UTC,
    )
    msg = f"Report data expiration is {expiration_date} "
          f"for a {months} month retention policy"
    LOG.info(msg)
    return expiration_date
```

**Semantics**: Retain `N` full calendar months. The expiration date is
the first of the month that is `N` months before today. All data in
the current partial month and the previous `N-1` complete months is
retained.

Example with `data_retention_months = 12` and today = March 10, 2026:
- `today - 12 months` = March 10, 2025
- Expiration date = **March 1, 2025**
- Retained: March 2025 through March 2026 (current month)

### ExpiredDataRemover Constructor Change

The constructor accepts `schema_name` so it can call the helper:

```python
# masu/processor/expired_data_remover.py (proposed)

def __init__(self, customer_schema, provider, ..., schema_name=None):
    ...
    self._months_to_keep = num_of_months_to_keep
    if self._months_to_keep is None:
        if schema_name:
            self._months_to_keep = get_data_retention_months(schema_name)
        else:
            self._months_to_keep = Config.MASU_RETAIN_NUM_MONTHS
```

The `schema_name` is available in the Celery task that creates the
`ExpiredDataRemover` — it is passed as the first argument (`schema`).

---

## 3. Kafka Ingest Gate

### Current Code

```python
# masu/external/kafka_msg_handler.py:389-395

dh = DateHelper()
manifest_end = manifest.end or dh.month_end(manifest.date)
if manifest_end < dh.relative_month_end(-Config.MASU_RETAIN_NUM_MONTHS):
    msg = f"Received OCP data outside our retention period ..."
    LOG.warning(...)
    shutil.rmtree(payload_path.parent)
    return None, manifest.uuid
```

### Proposed Change

```python
schema_name = ...  # resolved from manifest → provider → customer
retention_months = get_data_retention_months(schema_name)

dh = DateHelper()
manifest_end = manifest.end or dh.month_end(manifest.date)
if manifest_end < dh.relative_month_end(-retention_months):
    ...
```

**Schema resolution**: The `kafka_msg_handler` has access to the
`CostUsageReportManifest` which links to a `Provider` which links
to a `Customer` (and therefore `schema_name`). The schema can be
resolved from the manifest's provider.

---

## Purge Flow Diagram (After Changes)

```mermaid
sequenceDiagram
    participant Beat as Celery Beat
    participant Task as remove_expired_data
    participant Orch as Orchestrator
    participant EDR as ExpiredDataRemover
    participant DB as tenant_settings
    participant Clean as Provider Cleaner

    Beat->>Task: 1st of month (cron)
    Task->>Orch: remove_expired_report_data()
    loop Each schema / provider
        Orch->>EDR: new(schema, provider)
        EDR->>DB: get_data_retention_months(schema)
        DB-->>EDR: data_retention_months (or env override)
        EDR->>EDR: _calculate_expiration_date()<br/>using relativedelta
        EDR->>Clean: purge_expired_report_data(expiration_date)
        Clean->>Clean: DELETE partitions < expiration_date
    end
```

---

## Files Changed

| File | Change |
|------|--------|
| `masu/processor/expired_data_remover.py` | Calendar-month fix + read from helper |
| `masu/external/kafka_msg_handler.py` | Read retention from helper |
| `api/utils.py` | `materialized_view_month_start` accepts `schema_name` |
| `masu/config.py` | `MASU_RETAIN_NUM_MONTHS` becomes fallback only |
| `masu/processor/_tasks/remove_expired.py` | Pass `schema_name` to `ExpiredDataRemover` |

---

## Risks

| ID | Risk | Severity | Mitigation |
|----|------|----------|------------|
| R4 | Calendar-month change shifts expiration date — could delete or retain more data than before on first run | Medium | Compare old vs new expiration dates in tests; log both during transition |
| R5 | Kafka handler schema resolution adds a DB query per message | Low | The manifest → provider → customer chain is already loaded; schema is cached on the provider |

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-11 | Initial draft |
