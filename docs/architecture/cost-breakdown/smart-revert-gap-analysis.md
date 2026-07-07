# RTU Smart Revert — SQL Gap Analysis

**Branch:** `smart_revert_rtu` · 25 legacy/RTU file pairs analyzed across 3 SQL directories

> **Summary:** Only 1 gap introduces materially different cost values on the legacy path — GAP-1, which affects
> Trino/SaaS customers with monthly VM core tag-based rates. The remaining gaps are NULL-vs-omitted column
> differences or a pre-existing cross-path inconsistency. All 9 PostgreSQL `sql/` pairs and the entire
> on-prem `self_hosted_sql/` set are functionally clean.

| Metric | Count |
|---|---|
| File pairs analyzed | 25 |
| Clean — no functional gap | 20 |
| Gaps found | 5 |

---

## All 25 File Pairs

Each legacy file compared against its `*_rtu.sql` counterpart for filtering logic, source tables, calculation formulas, and output columns.

| Directory | Legacy file | Status | Gap |
|---|---|---|---|
| `sql/` | `infrastructure_tag_rates.sql` | Clean | |
| `sql/` | `supplementary_tag_rates.sql` | Clean | |
| `sql/` | `default_infrastructure_tag_rates.sql` | Clean | |
| `sql/` | `default_supplementary_tag_rates.sql` | Clean | |
| `sql/` | `monthly_cost_cluster_and_node.sql` | Clean | |
| `sql/` | `monthly_cost_persistentvolumeclaim.sql` | Clean | |
| `sql/` | `monthly_cost_persistentvolumeclaim_by_tag.sql` | Clean | |
| `sql/` | `monthly_cost_virtual_machine.sql` | Clean | |
| `sql/` | `node_cost_by_tag.sql` | Clean | |
| `trino_sql/` | `hourly_cost_virtual_machine.sql` | Clean | |
| `trino_sql/` | `hourly_cost_vm_tag_based.sql` | **Gap** | GAP-4 |
| `trino_sql/` | `hourly_vm_core.sql` | Clean | |
| `trino_sql/` | `hourly_vm_core_tag_based.sql` | Clean | |
| `trino_sql/` | `monthly_cost_gpu.sql` | **Gap** | GAP-2 |
| `trino_sql/` | `monthly_project_tag_based.sql` | **Gap** | GAP-3 |
| `trino_sql/` | `monthly_vm_core.sql` | Clean | |
| `trino_sql/` | `monthly_vm_core_tag_based.sql` | **Gap** | GAP-1 |
| `self_hosted_sql/` | `hourly_cost_virtual_machine.sql` | Clean | |
| `self_hosted_sql/` | `hourly_cost_vm_tag_based.sql` | Clean | |
| `self_hosted_sql/` | `hourly_vm_core.sql` | Clean | |
| `self_hosted_sql/` | `hourly_vm_core_tag_based.sql` | Clean | |
| `self_hosted_sql/` | `monthly_cost_gpu.sql` | **Gap** | GAP-2 |
| `self_hosted_sql/` | `monthly_project_tag_based.sql` | Clean | |
| `self_hosted_sql/` | `monthly_vm_core.sql` | Clean | |
| `self_hosted_sql/` | `monthly_vm_core_tag_based.sql` | Clean | |

---

## Gaps — Detailed Analysis

### GAP-1 — CRITICAL · `trino_sql/` · `monthly_vm_core_tag_based.sql`

**Issue:** Different cost formula AND different source table vs RTU

| | Legacy path | RTU path |
|---|---|---|
| Source table | `openshift_vm_usage_line_items` (non-daily, interval-level rows) | `openshift_vm_usage_line_items_daily` (daily aggregated rows) |
| CTE | Computes `vm_interval_hours = sum(uptime_seconds) / 3600` | No `vm_interval_hours` in CTE |
| Cost formula | `vm_cpu_cores × rate × vm_interval_hours` (time-weighted) | `(vm_cpu_cores × rate) / amortized_denominator` (daily amortized) |

**Risk on legacy path:** Customers on SaaS/Trino with monthly VM core tag-based rates get materially different costs after revert. A VM running half the month would see ~50% of the RTU cost. On-prem (self-hosted) legacy already uses the correct amortized formula — only Trino is affected.

**Affects:** SaaS (Trino)

---

### GAP-2 — MEDIUM · `trino_sql/ + self_hosted_sql/` · `monthly_cost_gpu.sql`

**Issue:** GPU unallocated block: `cost_category_id` omitted from INSERT column list

| | Legacy path | RTU path |
|---|---|---|
| First INSERT (pod GPU costs) | Includes `cost_category_id` from `cat_ns` join | Same |
| Second INSERT (GPU unallocated) | `cost_category_id` not in column list — defaults to database NULL | Explicitly sets `CAST(NULL AS integer) AS cost_category_id` |

**Risk on legacy path:** No functional regression — NULL is the correct value for the synthetic 'GPU unallocated' namespace. Both paths produce NULL for this column.

**Affects:** SaaS (Trino), On-prem (self-hosted)

---

### GAP-3 — MEDIUM · `trino_sql/` · `monthly_project_tag_based.sql`

**Issue:** `cost_category_id` column entirely absent from INSERT column list

| | Legacy path | RTU path |
|---|---|---|
| `cost_category_id` | Not in INSERT column list at all — defaults to database NULL | Explicitly inserts `CAST(NULL AS integer) AS cost_category_id` |

**Risk on legacy path:** No functional regression. Self-hosted legacy and both RTU variants produce NULL. Functionally identical.

**Affects:** SaaS (Trino)

---

### GAP-4 — LOW · `trino_sql/` · `hourly_cost_vm_tag_based.sql`

**Issue:** `monthly_cost_type` value differs: legacy sets `'Tag'`, RTU sets `NULL`

| | Legacy path | RTU path |
|---|---|---|
| `monthly_cost_type` | `'Tag'` (inserted directly to LIDS) | `CAST(NULL AS varchar)` (inserted to `rates_to_usage`) |

**Risk on legacy path:** Verify that distribution SQL in `distribute_cost/` does not filter on `monthly_cost_type IS NULL` for rows that need to be distributed. Hourly VM tag rows will have `monthly_cost_type = 'Tag'` on LIDS in the legacy path. This is correct behavior only if distribution is not supposed to touch them.

**Affects:** SaaS (Trino)

---

### GAP-5 — INFO · `trino_sql/ vs self_hosted_sql/` · `monthly_cost_gpu.sql` (cross-path)

**Issue:** Vendor filter operator differs between Trino and self-hosted in both legacy and RTU

| | Self-hosted | Trino |
|---|---|---|
| Filter | `gpu_vendor_name = '{{tag_key}}'` (exact match) | `gpu_vendor_name LIKE '{{tag_key}}%'` (prefix match) |

**Risk on legacy path:** Pre-existing cross-path inconsistency. On-prem GPU costs only match exact vendor names; SaaS matches any vendor starting with the `tag_key` prefix. RTU variants have the same divergence — not introduced by the smart revert. Track separately.

**Affects:** Cross-path (pre-existing)

---

## GAP-1 Deep Dive — Cost Formula Comparison

The only gap with materially different cost values. Relevant to customers with monthly VM core tag-based cost model rates on Trino/SaaS.

### Legacy (`trino_sql/`) — time-weighted

**Source table:** `openshift_vm_usage_line_items` (non-daily, interval-level rows)

**CTE `vm_usage_summary`:**
```sql
sum(vm_uptime_total_seconds) / 3600
  AS vm_interval_hours
```

**Cost formula:**
```sql
vm_cpu_cores
  × rate
  × vm_interval_hours
```

A VM running 12 h/day for 30 days = 360 `vm_interval_hours`. Cost is proportional to actual uptime — VMs that run part of the month pay proportionally less.

### RTU variant + self-hosted legacy — amortized

**Source table:** `openshift_vm_usage_line_items_daily` (daily aggregated rows)

**CTE `vm_usage_summary`:**
```sql
vm_cpu_cores only
  (no vm_interval_hours)
```

**Cost formula:**
```sql
(vm_cpu_cores × rate)
  / amortized_denominator
```

Fixed daily slice: rate ÷ days_in_month per core per day. Cost is uniform across each day the VM appears regardless of actual uptime within that day.

> **Note:** The self-hosted (on-prem) `monthly_vm_core_tag_based.sql` already uses
> `openshift_vm_usage_line_items_daily` with the amortized formula — matching both RTU variants.
> Only the Trino legacy file has the divergent formula. Backport the daily-table + amortized
> formula to fix GAP-1.

---

## Recommended Actions

### 1. Fix GAP-1 — backport amortized formula to Trino legacy · **Must fix before merge**

Update `trino_sql/openshift/cost_model/monthly_vm_core_tag_based.sql` to use
`openshift_vm_usage_line_items_daily` and the formula `(vm_cpu_cores × rate) / amortized_denominator`,
matching the self-hosted legacy and both RTU variants. This is a pre-Phase-3 bug in the Trino legacy file.

### 2. Verify distribution SQL compatibility with GAP-4 · **Verify before merge**

Confirm that the distribution SQL in `sql/openshift/cost_model/distribute_cost/` does not gate on
`monthly_cost_type IS NULL` for rows that need distribution. In the legacy path, hourly VM tag rows
land on LIDS with `monthly_cost_type = 'Tag'`. This is correct behavior only if distribution is not
supposed to touch them.

### 3. Accept GAP-2 and GAP-3 — NULL is correct · **Document and close**

The missing `cost_category_id` in the GPU unallocated block (GAP-2) and project tag-based file (GAP-3)
produce NULL — identical to RTU behavior. Add a clarifying comment in the SQL files and close as non-issues.

### 4. GAP-5 — GPU vendor filter cross-path inconsistency · **Track separately**

The `=` vs `LIKE %` difference between self-hosted and Trino GPU vendor filtering is pre-existing and
present in both legacy and RTU. Not a regression introduced by the smart revert. File a separate issue.
