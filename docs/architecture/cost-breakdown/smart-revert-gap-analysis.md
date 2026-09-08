# RTU Smart Revert — SQL Gap Analysis

**Branch:** `smart_revert_rtu` · 25 legacy/RTU file pairs analyzed across 3 SQL directories

> **Summary:** No gaps introduce materially different cost values on the legacy path. All gaps are NULL-vs-omitted
> column differences or a pre-existing cross-path inconsistency. All 9 PostgreSQL `sql/` pairs, the entire
> on-prem `self_hosted_sql/` set, and all `trino_sql/` pairs are functionally clean on cost calculations.

| Metric | Count |
|---|---|
| File pairs analyzed | 25 |
| Clean — no functional gap | 21 |
| Gaps found | 4 |

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
| `trino_sql/` | `monthly_vm_core_tag_based.sql` | Clean | |
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

## Recommended Actions

### 1. Verify distribution SQL compatibility with GAP-4 · **Verify before merge**

Confirm that the distribution SQL in `sql/openshift/cost_model/distribute_cost/` does not gate on
`monthly_cost_type IS NULL` for rows that need distribution. In the legacy path, hourly VM tag rows
land on LIDS with `monthly_cost_type = 'Tag'`. This is correct behavior only if distribution is not
supposed to touch them.

### 2. Accept GAP-2 and GAP-3 — NULL is correct · **Document and close**

The missing `cost_category_id` in the GPU unallocated block (GAP-2) and project tag-based file (GAP-3)
produce NULL — identical to RTU behavior. Add a clarifying comment in the SQL files and close as non-issues.

### 3. GAP-5 — GPU vendor filter cross-path inconsistency · **Track separately**

The `=` vs `LIKE %` difference between self-hosted and Trino GPU vendor filtering is pre-existing and
present in both legacy and RTU. Not a regression introduced by the smart revert. File a separate issue.
