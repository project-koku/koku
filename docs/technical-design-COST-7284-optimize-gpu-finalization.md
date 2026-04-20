# Technical Design: COST-7284 — Optimize GPU Finalization to Prevent Redundant Triggers

## Problem Statement

GPU unallocated cost distribution (`GPU_UNALLOCATED`) requires **full-month data** to calculate
proportional distribution across namespaces. Because of this, the system uses a calendar-based
trigger: on day 2 of each month (UTC), any incoming OCP payload for the **current month** causes
the system to process GPU distribution for the **previous month**.

The problem: there is no check to determine if the previous month has already been finalized.
For customers sending hourly payloads, this results in **~24 redundant executions** of the same
expensive operation on day 2 — each one running a full Trino distribution query and refreshing
all UI summary tables for the previous month.

## Current Flow

The GPU finalization is triggered inside `OCPReportDBAccessor.populate_distributed_cost_sql()`:

```
Payload arrives (current month)
  → update_summary_tables
    → update_cost_model_costs
      → distribute_costs_and_update_ui_summary
        → populate_distributed_cost_sql
          → For GPU_UNALLOCATED (requires_full_month=True):
              IF is_current_month AND now_utc.day == 2:
                1. _delete_monthly_cost_model_rate_type_data (DELETE gpu_distributed rows from daily_summary)
                2. Execute distribute_unallocated_gpu_cost.sql (INSERT gpu_distributed rows via Trino)
                3. populate_ui_summary_tables (DELETE/INSERT all UI tables for previous month)
              ELSE:
                skip
```

Key code (`ocp_report_db_accessor.py` lines 647–661):

```python
if config.requires_full_month:
    if summary_range.is_current_month:
        if dh.now_utc.day == 2:
            sql_params["start_date"] = summary_range.start_of_previous_month
            sql_params["end_date"] = summary_range.end_of_previous_month
            summary_range.summarize_previous_month = True
        else:
            continue  # skip GPU distribution on all other days
    else:
        # "Natural" finalization: processing data that IS from the previous month
        sql_params["start_date"] = summary_range.start_of_month
        sql_params["end_date"] = summary_range.end_of_month
```

### "Artificial" vs "Natural" Finalization

- **Artificial**: Triggered on day 2 when processing current-month payloads. The code redirects
  the date range to the previous month. This is the safety net — ensures GPU distribution happens
  even if no late data arrives.

- **Natural**: Triggered when late-arriving data from the previous month is processed. The
  `summary_range` already covers the previous month, so `is_current_month` is `False` and the
  code enters the `else` branch — no day-of-month restriction.

### The Redundancy Problem

Every OCP payload that arrives on day 2 triggers the full cycle:
1. DELETE all `gpu_distributed` rows from `reporting_ocpusagelineitem_daily_summary`
2. Re-INSERT them via expensive Trino query
3. DELETE/INSERT all UI summary tables for the previous month

Since the previous month's data hasn't changed, **every execution after the first produces
identical results**. For a customer sending hourly payloads: ~24 identical heavy operations.

## Proposed Solutions

### Option A: Check for Existing Distributed Data (Recommended)

**Approach**: Before running the GPU distribution, check if `gpu_distributed` rows already exist
in `OCPUsageLineItemDailySummary` for the target provider and month. If they do, skip the
entire distribution + UI refresh cycle.

**Where to check**: `reporting_ocpusagelineitem_daily_summary` (the daily summary table), NOT
`reporting_ocp_gpu_summary_p` (the GPU UI table) — because the UI table SQL explicitly excludes
`gpu_distributed` rows (`AND cost_model_rate_type != 'gpu_distributed'`).

**Implementation**:

Add a method to `OCPReportDBAccessor`:

```python
def _gpu_distribution_exists_for_month(self, provider_uuid: str, start_date, end_date) -> bool:
    """Check if GPU distributed costs already exist in daily summary for the period."""
    return OCPUsageLineItemDailySummary.objects.filter(
        source_uuid=provider_uuid,
        usage_start__gte=start_date,
        usage_start__lte=end_date,
        cost_model_rate_type="gpu_distributed",
    ).exists()
```

Modify `populate_distributed_cost_sql()` — add the check **before**
`_delete_monthly_cost_model_rate_type_data()`:

```python
if config.requires_full_month:
    if summary_range.is_current_month:
        if dh.now_utc.day == 2:  # or expanded window
            sql_params["start_date"] = summary_range.start_of_previous_month
            sql_params["end_date"] = summary_range.end_of_previous_month

            # NEW: Skip if already finalized
            if self._gpu_distribution_exists_for_month(
                provider_uuid, sql_params["start_date"], sql_params["end_date"]
            ):
                LOG.info(log_json(
                    msg="Skipping GPU distribution - previous month already finalized",
                    context={"schema": self.schema, "provider_uuid": str(provider_uuid)},
                ))
                continue

            summary_range.summarize_previous_month = True
        else:
            continue
```

**Critical detail**: The check MUST happen before `_delete_monthly_cost_model_rate_type_data()`
(line 675), because that method deletes the very rows we're checking for. Current code flow:
delete first → then insert. We need: check first → if exists, skip both delete and insert.

**Schema context note**: No explicit `schema_context` is needed for this ORM query.
`OCPReportDBAccessor` inherits from `ReportDBAccessorBase`, which sets the tenant schema via
`connection.set_schema(self.schema)` in its `__enter__` method. All ORM queries within the
accessor automatically operate in the correct tenant schema.

**Pros**:
- Zero migrations — no model changes
- Zero reset logic — no state to manage
- Source of truth: checks the actual data, not a proxy flag
- `EXISTS` query is fast with existing indexes on `source_uuid` + `usage_start`
- Mostly self-correcting for natural finalization: late-arriving data triggers the "natural"
  path which calls `_delete_monthly_cost_model_rate_type_data()` + re-inserts, so subsequent
  artificial triggers correctly see the updated data

**Cons**:
- Queries `OCPUsageLineItemDailySummary` which is a large partitioned table (but `EXISTS` with
  indexed columns short-circuits on first match — should be negligible)

**Known limitation — cost model updates on finalization day**: If a cost model is updated on the
same day that GPU distribution already ran (e.g., day 2), the `exists()` check will see the
old distributed rows and skip re-distribution with the new rates. In practice, this is a narrow
edge case because:
1. Cost model updates triggered via API use `start_date = this_month_start`, so the GPU
   `requires_full_month` path is only entered on the finalization day anyway.
2. The current code (without this change) already skips GPU distribution on all days except
   day 2 — so a cost model update on day 3+ would NOT re-distribute the previous month either.
3. If this edge case needs to be addressed, the cost model update flow could explicitly delete
   `gpu_distributed` rows for the previous month's report period before triggering
   `update_cost_model_costs`, ensuring the `exists()` check returns `False`.

**Window expansion**: With this check in place, the day-of-month restriction (`day == 2`) can
safely be expanded (e.g., `day <= 5`, or even removed entirely). The first payload of the month
would trigger the finalization, and all subsequent ones would skip via the EXISTS check.

**Natural finalization compatibility**: The "natural" path (late data for previous month) enters
the `else` branch which does NOT go through this check — it always reprocesses. Additionally,
natural finalization goes through `_delete_monthly_cost_model_rate_type_data()` which clears the
old distributed rows before re-inserting, so the next artificial trigger would correctly detect
the updated data already exists.

---

### Option B: New Field on `OCPUsageReportPeriod`

**Approach**: Add a `gpu_finalized_datetime` field to `OCPUsageReportPeriod`. Set it after
successful GPU distribution. Check it before running distribution.

**Implementation**:

1. **Migration** — add nullable DateTimeField:

```python
migrations.AddField(
    model_name="ocpusagereportperiod",
    name="gpu_finalized_datetime",
    field=models.DateTimeField(null=True, blank=True),
)
```

2. **Set after distribution** — in `populate_distributed_cost_sql()`, after executing the GPU
   distribution SQL:

```python
if cost_model_key == metric_constants.GPU_UNALLOCATED:
    report_period.gpu_finalized_datetime = timezone.now()
    report_period.save(update_fields=["gpu_finalized_datetime"])
```

3. **Check before distribution** — in the `requires_full_month` block:

```python
if summary_range.is_current_month:
    if dh.now_utc.day == 2:  # or expanded window
        prev_report_period = self.report_periods_for_provider_uuid(
            provider_uuid, summary_range.start_of_previous_month
        )
        if prev_report_period and prev_report_period.gpu_finalized_datetime:
            LOG.info(log_json(msg="Skipping GPU - already finalized", ...))
            continue
        ...
```

4. **Reset the flag** — must be done in multiple places:
   - When cost model is updated via API (rates/distribution changed)
   - When natural finalization occurs (late data arrives for the previous month)
   - When a manual `update_cost_model_costs` is triggered via Masu API

**Pros**:
- Very fast check — `OCPUsageReportPeriod` is a tiny table, already queried in this flow
- Clear semantic meaning
- Follows existing patterns (`derived_cost_datetime`, `finalized_datetime` on AWS/Azure/GCP bills)

**Cons**:
- Requires a migration (simple `AddField`, but still a schema change)
- Requires reset logic in multiple code paths — risk of forgetting a path and leaving stale state
- Flag can get out of sync with actual data (e.g., if distribution SQL fails mid-execution but
  flag was already set, or if flag reset is missed somewhere)
- More code to maintain across cost model update, natural finalization, and manual trigger paths

---

## Recommendation

**Option A** is recommended because:

1. It requires **zero migrations** and **zero state management**
2. It checks the **actual data** rather than a proxy flag — no risk of flag/data desync
3. It's **mostly self-correcting**: natural finalization (late data) clears and re-inserts
   distributed rows, so subsequent artificial triggers correctly see up-to-date data
4. The performance cost of `EXISTS` on an indexed partitioned table is negligible
5. It's simpler to implement, test, and reason about
6. The one known limitation (cost model update on finalization day) is a narrow edge case
   that can be addressed separately if needed (see Option A cons)

Option B is a valid alternative if the team prefers explicit state tracking and wants the
check to be a simple field lookup rather than a table scan — but the added complexity of
managing flag resets across multiple code paths makes it more error-prone.

## Additional Consideration: Window Expansion

The spike AC mentions potentially expanding the artificial finalization window beyond day 2.
With either solution, this becomes safe:

```python
# Current: only day 2
if dh.now_utc.day == 2:

# Expanded: first 5 days
if dh.now_utc.day <= 5:

# Aggressive: every payload (maximum safety, negligible cost with the check)
# Simply remove the day check entirely
```

The recommendation is to expand to **every payload** (remove the day-of-month check) once the
finalization guard is in place. This eliminates the risk of a month going unfinalized due to
OCP payload outages or system downtime on the specific trigger day.

## Files to Modify

| File | Change |
|------|--------|
| `masu/database/ocp_report_db_accessor.py` | Add `_gpu_distribution_exists_for_month()`, modify `populate_distributed_cost_sql()` |
| `masu/test/database/test_ocp_report_db_accessor.py` | Tests for the new check + skip behavior |

For Option B, additionally:
| File | Change |
|------|--------|
| `reporting/provider/ocp/models.py` | Add `gpu_finalized_datetime` to `OCPUsageReportPeriod` |
| `reporting/migrations/NNNN_*.py` | New migration for the field |
| `masu/processor/ocp/ocp_cost_model_cost_updater.py` | Reset flag on reprocessing |
| `api/provider/` or `cost_models/` | Reset flag on cost model update |

## Implementation

Option A was implemented and validated (unit tests + manual end-to-end testing with data ingestion).

**Pull Request**: [#6012 — COST-7284: Add guard to prevent redundant GPU finalization](https://github.com/project-koku/koku/pull/6012)
