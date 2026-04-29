# Price Lists — Calculation and Resolution

How an effective price list is chosen for a calendar day and how Masu
components consume (or bypass) that resolution.

During the **dual-write** period (see [README.md § Dual-write transition](./README.md#dual-write-transition-product-plan)),
OCP month processing already prefers **`PriceList.rates`** via
`price_list_effective_on`; `CostModel.rates` remains for API/UI parity and
for code paths that pass `price_list_effective_on=None`. Removing JSON rates
is a later milestone tied to the price list UI.

---

## Resolution algorithm

[`PriceListManager.get_effective_price_list(cost_model_uuid, effective_date)`](../../../koku/cost_models/price_list_manager.py):

1. Query `PriceListCostModelMap` for the cost model.
2. Filter to lists where
   `effective_start_date <= effective_date <= effective_end_date`.
3. `order_by("priority")` — **first row wins** (lowest priority number).
4. Return that `PriceList` or `None`.

**Disabled lists**: still returned if they are mapped and the date falls in
their window — `enabled` only gates **new attachments**, not historical
calculation (see docstring on the same method).

---

## `CostModelDBAccessor` — the single read adapter

[`CostModelDBAccessor.__init__`](../../../koku/masu/database/cost_model_db_accessor.py)
accepts `price_list_effective_on: date | None`.

**Unleash kill-switch**: on construction, the accessor checks the
`cost-management.backend.disable_price_list` Unleash flag
([`DISABLE_PRICE_LIST_UNLEASH_FLAG`](../../../koku/masu/processor/__init__.py)).
If the flag is **enabled for the schema**, `price_list_effective_on` is
forced to `None` regardless of what the caller passed, reverting the entire
schema to legacy `CostModel.rates` behavior. This is an operational escape
hatch for per-tenant rollback without a code deploy.

[`effective_rates`](../../../koku/masu/database/cost_model_db_accessor.py):

| `price_list_effective_on` | Source of `effective_rates` |
|---------------------------|------------------------------|
| `None` | `CostModel.rates` (legacy path). |
| set | Rates from `get_effective_price_list`; if **no** match, `{}`. |

Downstream properties (`infrastructure_rates`, `tag_infrastructure_rates`,
`price_list`, etc.) are derived from `effective_rates`, so an empty dict
propagates as “no tiered/tag rates” for that invocation.

**Context manager**: `__enter__` sets the DB schema to the tenant;
`__exit__` resets to `public`. Call sites that need the tenant schema for
**subsequent** ORM work in the same function sometimes avoid `with` and
instantiate the accessor directly (see GPU path below).

---

## OCP monthly cost application

[`OCPCostModelCostUpdater.update_summary_cost_model_costs`](../../../koku/masu/processor/ocp/ocp_cost_model_cost_updater.py)
iterates `summary_range.iter_summary_range_by_month()`. For each month:

1. [`_load_rates(start_date)`](../../../koku/masu/processor/ocp/ocp_cost_model_cost_updater.py)
   opens `CostModelDBAccessor` with
   `price_list_effective_on=start_date`
   (month boundary date — **one resolution per month** in the loop).
2. Usage, tag, and monthly SQL steps use the cached `_infra_rates` / tag maps
   loaded in that call.

So within a month, **all days in that month’s processing batch** share the
same resolved list (the list effective on the month’s `start_date`).

---

## Known split paths

These paths intentionally use `price_list_effective_on=None` so behavior
continues to follow **`CostModel.rates`** (and related JSON-only assumptions):

| Location | Purpose |
|----------|---------|
| [`OCPCostModelCostUpdater.__init__`](../../../koku/masu/processor/ocp/ocp_cost_model_cost_updater.py) | Distribution type and `distribution_info` from accessor. |
| [`_update_markup_cost`](../../../koku/masu/processor/ocp/ocp_cost_model_cost_updater.py) | Markup JSON still read from cost model via legacy accessor path. |

GPU “usage only” UI summary population uses **date-aware** resolution:
[`OCPReportDBAccessor._populate_gpu_ui_summary_table_with_usage_only`](../../../koku/masu/database/ocp_report_db_accessor.py)
builds `CostModelDBAccessor(..., price_list_effective_on=parse_to_date(start_date))`
to decide whether GPU monthly metrics apply — without using the `with`
context manager (comment in file explains schema reset interaction).

---

## Cloud provider cost models

AWS / Azure / GCP cost model updaters use `CostModelDBAccessor` for markup
and related fields; they do not implement the same per-day price list loop as
OCP. See grep results for `CostModelDBAccessor(` under
`masu/processor/aws|azure|gcp` when extending list-based behavior there.

---

## Celery entrypoint

[`update_cost_model_costs`](../../../koku/masu/processor/tasks.py) (and the
queue dispatch from `PriceListManager._trigger_recalculation`) drives
reprocessing for a `(schema, provider_uuid, start_date, end_date)` window.
That task eventually constructs the OCP updater and hits the monthly
`_load_rates` path above.

For full pipeline placement, keep [cost-models.md § Cost Calculation Pipeline](../cost-models.md#cost-calculation-pipeline)
as the authoritative narrative; this doc only details **where** list
resolution plugs in.
