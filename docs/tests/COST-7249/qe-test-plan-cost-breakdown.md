# QE Test Plan: Cost Breakdown and Rate Filtering

**Jira:** COST-7320
**Features:** COST-7249 (Cost Breakdown), COST-7439 (Rate Filtering)
**Execution:** `iqe-cost-management-plugin` (IQE black-box API tests)
**Author:** Jordi Gil
**Date:** 2026-06-09

---

## 1. Overview

This test plan defines black-box API test scenarios for two features:

1. **Cost Breakdown (COST-7249 Phase 4)** — A new endpoint that decomposes
   OpenShift costs into a per-rate tree structure, showing how each rate in a
   cost model contributes to project and overhead costs.

2. **Rate Filtering and Pagination (COST-7439)** — A new sub-endpoint on price
   lists that returns paginated, filterable rates with human-readable labels.

All tests hit the Koku REST API through the IQE `call_api()` helper and
validate response contracts, data correctness, and regressions. No internal
database, model, or SQL knowledge is assumed.

### Scope

**In scope:**
- `GET /api/cost-management/v1/breakdown/openshift/cost/` (flat and tree views)
- `GET /api/cost-management/v1/price-lists/{uuid}/rates/` (paginated rates)
- `GET /api/cost-management/v1/price-lists/` with `filter[cost_model]`
- Filters, group_by, order_by, pagination, validation, RBAC

**Out of scope:**
- UI rendering (covered by COST-7321)
- Internal SQL pipeline or orchestration details
- Migration mechanics
- Performance benchmarks

---

## 2. IQE Artifacts

New files and constants needed in `iqe-cost-management-plugin`:

| Artifact | Location | Description |
|----------|----------|-------------|
| `BREAKDOWN_PATH` | `fixtures/constants.py` | `"/breakdown/openshift/cost/"` |
| `test_api_breakdown_cost.py` | `tests/rest_api/v1/` | Cost breakdown API tests |
| `test_api_price_list_rates.py` | `tests/rest_api/v1/` | Rate filtering API tests |
| `breakdown_fixtures.py` | `fixtures/` | Source + cost model fixtures for breakdown |
| `cost_breakdown` requirement | `conf/requirements.yaml` | Test requirement metadata |

### Marker registration

```yaml
# conf/requirements.yaml
cost_breakdown:
  summary: Cost breakdown per-rate tree endpoint
  priority: high
  description: Validates the per-rate cost breakdown API for OpenShift
```

### Fixture pattern

Fixtures follow the existing `OcpSource` + `create_cost_model()` pattern:

```python
@pytest.fixture(scope="session")
def cost_breakdown_source(application, request):
    """OCP source with a multi-rate cost model for breakdown testing."""
    rates = [
        {"metric": {"name": "cpu_core_usage_per_hour"},
         "tiered_rates": [{"unit": "USD", "value": "1.50",
                           "usage": {"usage_start": None, "usage_end": None}}]},
        {"metric": {"name": "memory_gb_usage_per_hour"},
         "tiered_rates": [{"unit": "USD", "value": "0.50",
                           "usage": {"usage_start": None, "usage_end": None}}]},
    ]
    with OcpSource(application, request, "breakdown_cluster", "breakdown_cluster",
                   static_file="ocp_report_basic_template.yml",
                   cost_model=rates, ingest=True, check_time=True) as prov:
        yield prov
```

---

## 3. Test Scenarios — Cost Breakdown (COST-7249)

### T1 — API Contract (P0)

| ID | Scenario | Markers | call_api Pattern | Assertions |
|----|----------|---------|------------------|------------|
| BD-01 | Endpoint returns valid envelope | `smoke`, `cost_required`, `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app)` | Response has `meta`, `links`, `data[]` keys |
| BD-02 | Each value has required fields | `cost_required`, `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app)` | Each value in `data[].values[]` has `depth`, `path`, `parent_path`, `cost_value`, `custom_name` |
| BD-03 | `view=tree` returns nested children | `cost_required`, `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app, other_params={"view": "tree"})` | Each date group has `tree` key with nested `children` arrays |
| BD-04 | `group_by[project]=*` groups by namespace | `smoke`, `cost_required`, `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app, group_by={"project": "*"})` | Each line item has `project` key; distinct namespaces appear |
| BD-05 | `group_by[node]=*` groups by node | `cost_required`, `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app, group_by={"node": "*"})` | Each line item has `node` key |
| BD-06 | `group_by[cluster]=*` groups by cluster | `cost_required`, `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app, group_by={"cluster": "*"})` | Each line item has `cluster` key |
| BD-07 | Time scope filters work | `cost_ocp_on_prem` | Parametrize with `all_time_filters` | Response 200; `data` reflects requested time range |
| BD-08 | Daily resolution returns per-day values | `cost_ocp_on_prem` | `filter={"resolution": "daily", "time_scope_units": "month", "time_scope_value": "-1"}` | Each `data` entry has a unique date |
| BD-09 | Monthly resolution returns per-month values | `cost_ocp_on_prem` | `filter={"resolution": "monthly", ...}` | `data` entries are monthly |
| BD-10 | `filter[path]` narrows to subtree | `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app, filter={"path": "project.usage_cost"})` | All returned paths start with `project.usage_cost` |
| BD-11 | `filter[depth]` returns specific depth | `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app, filter={"depth": "4"})` | All values have `depth == 4` |
| BD-12 | `filter[top_category]` filters by category | `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app, filter={"top_category": "project"})` | All values have `top_category == "project"` |
| BD-13 | `order_by[cost_value]=desc` orders correctly | `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app, other_params={"order_by[cost_value]": "desc"})` | Values sorted by `cost_value` descending |
| BD-14 | `order_by[distributed_cost]=desc` orders correctly | `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app, other_params={"order_by[distributed_cost]": "desc"})` | Values sorted by `distributed_cost` descending |

**Negative / Validation:**

| ID | Scenario | Markers | Pattern | Assertions |
|----|----------|---------|---------|------------|
| BD-15 | Invalid `group_by` returns error | `cost_required`, `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app, group_by={"bogus": "*"})` | `ApiException` raised |
| BD-16 | Max 2 `group_by` options enforced | `cost_ocp_on_prem` | `group_by={"project": "*", "node": "*", "cluster": "*"}` | `ApiException` with message about max 2 |
| BD-17 | Unknown query params return 400 | `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH + "?bogus=value", app)` | `ApiException` |
| BD-18 | Tag filter silently dropped (not 400) | `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app, filter={"tag:app": "web"})` | Response 200 (tag ignored, not rejected) |
| BD-19 | `exclude[cluster]` excludes values | `cost_ocp_on_prem` | `call_api(BREAKDOWN_PATH, app, exclude={"cluster": "test"}, group_by={"cluster": "*"})` | Excluded cluster not in results |

```python
# Example test function (BD-01)
@pytest.mark.cost_ocp_on_prem
@pytest.mark.smoke
@pytest.mark.cost_required
def test_api_breakdown_endpoint_accessible(application, tenant_create):
    """Verify the breakdown endpoint returns a valid envelope.

    metadata:
        requirements: cost_breakdown
        importance: critical
    """
    report = call_api(BREAKDOWN_PATH, application)
    assert "meta" in report
    assert "links" in report
    assert "data" in report
    assert isinstance(report["data"], list)
```

### T2 — Data Correctness (P0)

| ID | Scenario | Fixture | Assertions |
|----|----------|---------|------------|
| BD-20 | Cost conservation: sum of leaves == parent at every depth | `cost_breakdown_source` | Walk tree view; at each node, `sum(child.cost_value) == parent.cost_value` within `tolerance_value` |
| BD-21 | Breakdown total matches cost explorer total | `cost_breakdown_source` | `meta.total` from breakdown == `meta.total.cost.total.value` from `/reports/openshift/costs/` within tolerance |
| BD-22 | Per-rate leaves correspond to cost model rates | `cost_breakdown_source` | Each leaf `custom_name` maps to a rate metric in the assigned cost model |
| BD-23 | Overhead distribution: platform costs distributed correctly | `cost_breakdown_overhead_source` | Sum of `distributed_cost` at depth 5 == sum of platform costs |
| BD-24 | Multi-rate model: each rate appears as separate leaf | `cost_breakdown_source` | Count of depth-4 leaves == number of rates in cost model that have usage |
| BD-25 | Tag-rate leaf appears when tag rate is in cost model | `cost_breakdown_tag_source` | A leaf exists with `cost_model_rate_type == "tag"` |

```python
# Example test function (BD-20)
@pytest.mark.cost_ocp_on_prem
@pytest.mark.cost_required
def test_api_breakdown_cost_conservation(application, cost_breakdown_source):
    """Verify sum of child cost_value equals parent at every depth.

    metadata:
        requirements: cost_breakdown
        importance: critical
    """
    report = call_api(BREAKDOWN_PATH, application, other_params={"view": "tree"})
    for date_group in report["data"]:
        for tree_root in date_group.get("tree", []):
            _assert_cost_conservation(tree_root)

def _assert_cost_conservation(node):
    """Recursively verify cost conservation in the breakdown tree."""
    children = node.get("children", [])
    if not children:
        return
    child_sum = sum(c.get("cost_value", 0) or 0 for c in children)
    parent_cost = node.get("cost_value", 0) or 0
    tolerance_value(parent_cost, child_sum)
    for child in children:
        _assert_cost_conservation(child)
```

### T3 — Edge Cases (P1)

| ID | Scenario | Assertions |
|----|----------|------------|
| BD-30 | Empty cluster (no usage data) returns empty data, not error | Response 200; `data` is empty list or values are empty |
| BD-31 | Cluster with no cost model returns breakdown with zero costs | Response 200; cost values are 0 or null |
| BD-32 | Previous month data via `time_scope_value=-2` | Response 200; data dates are from 2 months ago |
| BD-33 | Multi-currency breakdown respects rate currency | `raw_currency` field matches the rate's currency |
| BD-34 | GPU metrics appear when GPU rates are in cost model | Leaf with GPU metric_type exists |
| BD-35 | `exclude[project]` + `exclude[node]` work | Excluded values absent from results |

---

## 4. Test Scenarios — Rate Filtering (COST-7439)

### T1 — API Contract (P0)

| ID | Scenario | Markers | Pattern | Assertions |
|----|----------|---------|---------|------------|
| RT-01 | `/rates/` returns paginated envelope | `smoke`, `cost_required` | `call_api(f"/price-lists/{uuid}/rates/", app)` | Response has `meta.count`, `links`, `data[]` |
| RT-02 | `meta.count` reflects total rate count | `cost_required` | Same | `meta["count"]` equals total rates in price list |
| RT-03 | Pagination: `limit=2&offset=0` returns 2 items | `cost_required` | `other_params={"limit": 2, "offset": 0}` | `len(data) == 2` |
| RT-04 | Pagination: `offset` beyond count returns empty | `cost_required` | `other_params={"limit": 10, "offset": 999}` | `len(data) == 0` |
| RT-05 | `filter[metric_type]=cpu` returns CPU rates only | `smoke`, `cost_required` | `filter={"metric_type": "cpu"}` | All returned rates have CPU-related metric |
| RT-06 | `filter[name]=usage` substring match | `cost_required` | `filter={"name": "usage"}` | All returned rate names contain "usage" (case-insensitive) |
| RT-07 | `filter[measurement]=Usage` reverse-maps | `cost_required` | `filter={"measurement": "Usage"}` | All returned rates have measurement matching "Usage" |
| RT-08 | `filter[cost_type]=Infrastructure` case-insensitive | `cost_required` | `filter={"cost_type": "Infrastructure"}` | All returned rates have `cost_type == "Infrastructure"` |
| RT-09 | Combined filters apply AND logic | `cost_required` | `filter={"metric_type": "cpu", "cost_type": "Infrastructure"}` | Returned rates satisfy both filters |
| RT-10 | Multi-value same filter applies OR logic | `cost_required` | `filter={"metric_type": "cpu,memory"}` | Returned rates are either CPU or memory |
| RT-11 | Each rate includes metric labels | `cost_required` | Any `/rates/` call | Each rate has `metric.label_metric`, `metric.label_measurement`, `metric.label_measurement_unit` |
| RT-12 | Tiered rates include `tiered_rates` ladder | `cost_required` | Create price list with tiered rate | Tiered rate has `tiered_rates` list with `value`, `unit`, `usage` |
| RT-13 | Tag rates include `tag_key` + `tag_values` | `cost_required` | Create price list with tag rate | Tag rate has `tag_key` string and `tag_values` list |

```python
# Example test function (RT-01)
@pytest.mark.smoke
@pytest.mark.cost_required
def test_api_price_list_rates_endpoint(application, cost_model_ocp):
    """Verify rates sub-endpoint returns paginated envelope.

    metadata:
        requirements: cost_breakdown,cost_price_list_enhancements
        importance: critical
    """
    price_list_uuid = cost_model_ocp.uuid
    rates = call_api(f"/price-lists/{price_list_uuid}/rates/", application)
    assert "meta" in rates
    assert "count" in rates["meta"]
    assert "links" in rates
    assert "data" in rates
    assert isinstance(rates["data"], list)
```

### T2 — Validation (P0)

| ID | Scenario | Pattern | Assertions |
|----|----------|---------|------------|
| RT-20 | Unknown top-level param returns 400 | `call_api(f"/price-lists/{uuid}/rates/?bogus=1", app)` | `ApiException` with 400 |
| RT-21 | `filter[cost_model]=not-a-uuid` returns 400 | `call_api("/price-lists/?filter[cost_model]=not-a-uuid", app)` | `ApiException` with 400 |
| RT-22 | Nonexistent price list UUID returns 404 | `call_api("/price-lists/00000000-.../rates/", app)` | `ApiException` with 404 |
| RT-23 | Empty price list returns `{data: [], meta: {count: 0}}` | Create price list with no rates, query `/rates/` | `data == []`, `meta["count"] == 0` |

```python
# Example test function (RT-20)
@pytest.mark.cost_required
def test_api_price_list_rates_unknown_param_400(application, cost_model_ocp):
    """Unknown top-level params must return 400.

    metadata:
        requirements: cost_breakdown,cost_price_list_enhancements
        importance: high
    """
    price_list_uuid = cost_model_ocp.uuid
    with pytest.raises(ApiException, match="400"):
        call_api(f"/price-lists/{price_list_uuid}/rates/?bogus=bogus", application)
```

### T3 — Regression (P1)

| ID | Scenario | Assertions |
|----|----------|------------|
| RT-30 | Cost model CRUD still works | Existing `test_api_cost_model_ocp_crud` passes |
| RT-31 | Price list lifecycle unchanged | Create, update, duplicate, delete, assign cost model — all succeed |
| RT-32 | Cost explorer totals unchanged | `/reports/openshift/costs/` `meta.total` same before/after feature merge |

---

## 5. Test Data Recipes

Each recipe is a reproducible setup that a QE engineer can follow.

### Recipe 1 — Basic CPU/Memory breakdown

1. Create OCP source using `OcpSource` with `ocp_report_basic_template.yml`
2. Create cost model with 2 tiered rates:
   - `cpu_core_usage_per_hour` at $1.50/core-hour
   - `memory_gb_usage_per_hour` at $0.50/GB-hour
3. Assign cost model to source via `source_uuids`
4. Wait for processing: `wait_for_ingest` + `wait_for_recalc`
5. Query breakdown endpoint — expect 2 per-rate leaves under `project.usage_cost`

### Recipe 2 — Multi-rate with tag rates

1. Create OCP source with `ocp_for_aws_report_basic_template.yml`
2. Create cost model with 5 rates:
   - CPU usage (tiered), CPU request (tiered), memory usage (tiered),
     storage usage (tiered), CPU tag rate keyed on `environment=production`
3. Use `RATES_TYPE_1_COMBINED` constant as reference for rate structure
4. Assign and process
5. Query breakdown — expect tag rate leaf alongside tiered rate leaves

### Recipe 3 — Overhead distribution

1. Create OCP source with `ocp_for_aws_report_user_projects_2.yml`
2. Create cost model with `node_cost_per_month` (platform cost) and `cpu_core_usage_per_hour`
3. Configure cost categories so some namespaces are "Platform"
4. Process and query breakdown
5. Expect `overhead.platform_distributed` subtree with per-rate distribution leaves

### Recipe 4 — Rate filtering

1. Create cost model with 6+ rates of different metric types (CPU, memory, storage, node, cluster, PVC)
2. Query `/price-lists/{uuid}/rates/` with no filters — all rates returned
3. Apply `filter[metric_type]=cpu` — only CPU rates returned
4. Apply `filter[cost_type]=Infrastructure` — only infra rates returned
5. Combine filters — AND logic applied
6. Test pagination with `limit=2&offset=0`, `limit=2&offset=2`

### Recipe 5 — Empty/error states

1. Create cost model with no rates (markup only)
2. Query breakdown — expect empty data or zero costs
3. Query rates on nonexistent price list UUID — expect 404
4. Query rates with `filter[cost_model]=not-a-uuid` — expect 400

---

## 6. IQE Marker Matrix

| Marker Expression | Scenarios |
|-------------------|-----------|
| `cost_required` | BD-01 through BD-06, BD-15, BD-20, RT-01 through RT-04, RT-20 |
| `cost_ocp_on_prem` | All BD-* scenarios |
| `smoke` | BD-01, BD-04, RT-01, RT-05 |
| `cost_onprem_smoke` | BD-01, RT-01 |
| `cost_price_list_enhancements` | All RT-* scenarios |

### Execution commands

```bash
# Smoke tests only
ENV_FOR_DYNACONF=local iqe tests plugin cost_management \
  -k "test_api_breakdown or test_api_price_list_rates" -m smoke -vv

# Full breakdown suite
ENV_FOR_DYNACONF=local iqe tests plugin cost_management \
  -k test_api_breakdown -m cost_ocp_on_prem -vv

# Full rate filtering suite
ENV_FOR_DYNACONF=local iqe tests plugin cost_management \
  -k test_api_price_list_rates -m cost_required -vv

# On-prem smoke
iqe tests plugin cost_management \
  -m "cost_onprem_smoke and not cost_onprem_blocked" -vv
```

---

## 7. Exit Criteria

- All P0 scenarios pass
- No P1 scenario fails without documented risk acceptance
- Existing `cost_required` and `cost_ocp_on_prem` test suites remain green
- Cost conservation invariant holds at every tree depth (tolerance 1e-10)
- Recipes reproducible by a second QE using documented steps

---

## 8. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Backend PRs not merged | Cannot execute BD-* scenarios | Execute RT-* (COST-7439) first; breakdown deferred to Phase 4 merge |
| Ephemeral env instability | Flaky IQE timeouts | Retry policy; separate infra failures from test failures |
| Cost conservation rounding | Floating-point sums may not match exactly | Use `tolerance_value()` from `helpers.py` with appropriate tolerance |
| GPU flag dependency | GPU scenarios only testable with flag on | Document BD-34 as conditional P1 |
| Breakdown endpoint path TBD | URL may change before merge | Define `BREAKDOWN_PATH` constant; update in one place |

---

## 9. References

- IQE plugin: `iqe-cost-management-plugin`
- Existing OCP cost report tests: `test__ocp_cost_reports.py` (2,028 lines)
- Existing bucketing tests: `test__ocp_all_bucketing.py`
- Cost model tests: `test__cost_model.py` (8,052 lines, 58 tests)
- Rate constants: `cost_model_constants.py` (RATES_TYPE_0, RATES_TYPE_1)
- API helpers: `call_api()`, `report_line_items()`, `tolerance_value()` in `fixtures/helpers.py`
- Architecture docs: `docs/architecture/cost-breakdown/`
