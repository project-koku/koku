"""
Prototype for _price_list_from_rate_table() — Phase 1 compatibility proof.

This module demonstrates that reading from the Rate table produces the
exact same dict structure as the existing JSON-based price_list property
on CostModelDBAccessor.

Since the PriceList and Rate models don't exist yet, this uses
dataclasses to simulate Rate rows. The test creates a known JSON blob,
runs it through the EXISTING price_list logic, then creates matching
Rate objects and verifies the new method produces identical output.

Usage:
    python -m pytest docs/architecture/cost-breakdown/poc/price_list_compat.py -v

Or standalone:
    python docs/architecture/cost-breakdown/poc/price_list_compat.py
"""
import copy
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal


# ---------------------------------------------------------------------------
# Simulated Rate model (mirrors data-model.md § Rate)
# ---------------------------------------------------------------------------
@dataclass
class RateRow:
    """Simulates a cost_model_rate table row."""
    uuid: str
    price_list_id: str
    custom_name: str
    description: str
    metric: str              # e.g. "cpu_core_usage_per_hour"
    metric_type: str         # cpu, memory, storage, gpu
    cost_type: str           # Infrastructure, Supplementary
    default_rate: Decimal
    tag_key: str = ""
    tag_values: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Implementation: _price_list_from_rate_table
# ---------------------------------------------------------------------------
def price_list_from_rate_table(rate_rows: list[RateRow]) -> dict:
    """
    Build the same dict structure as CostModelDBAccessor.price_list,
    but reading from Rate table rows instead of the JSON blob.

    The output format must match exactly:
    {
        "cpu_core_usage_per_hour": {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "cost_type": <first cost_type seen>,
            "tiered_rates": {
                "Infrastructure": [{"value": <float>, "unit": "USD"}],
                "Supplementary": [{"value": <float>, "unit": "USD"}],
            },
            "description": "...",
        },
        ...
    }

    When multiple Rate rows share (metric, cost_type), their
    default_rate values are summed — matching the JSON path behavior.
    """
    metric_rate_map: dict = {}

    for rate in rate_rows:
        if rate.tag_key:
            continue

        metric_name = rate.metric
        cost_type = rate.cost_type
        value = float(rate.default_rate)

        if metric_name in metric_rate_map:
            existing = metric_rate_map[metric_name]
            tiered = existing["tiered_rates"]
            if cost_type in tiered:
                tiered[cost_type][0]["value"] += value
            else:
                tiered[cost_type] = [{"value": value, "unit": "USD"}]
        else:
            metric_rate_map[metric_name] = {
                "metric": {"name": metric_name},
                "cost_type": cost_type,
                "description": rate.description,
                "tiered_rates": {
                    cost_type: [{"value": value, "unit": "USD"}],
                },
            }

    return metric_rate_map


# ---------------------------------------------------------------------------
# Reference: existing JSON-based price_list logic (extracted from accessor)
# ---------------------------------------------------------------------------
def price_list_from_json(rates_json: list[dict]) -> dict:
    """
    Exact replica of CostModelDBAccessor.price_list logic,
    extracted as a standalone function for testing.
    """
    metric_rate_map = {}
    price_list = copy.deepcopy(rates_json)
    if not price_list:
        return {}
    for rate in price_list:
        if not rate.get("tiered_rates"):
            continue
        metric_name = rate.get("metric", {}).get("name")
        metric_cost_type = rate["cost_type"]
        if metric_name in metric_rate_map:
            metric_mapping = metric_rate_map[metric_name]
            if metric_cost_type in metric_mapping.get("tiered_rates", {}):
                current_tiered_mapping = metric_mapping["tiered_rates"][metric_cost_type]
                new_tiered_rate = rate.get("tiered_rates")
                current_value = float(current_tiered_mapping[0].get("value"))
                value_to_add = float(new_tiered_rate[0].get("value"))
                current_tiered_mapping[0]["value"] = current_value + value_to_add
                metric_rate_map[metric_name] = metric_mapping
            else:
                new_tiered_rate = rate.get("tiered_rates")
                metric_mapping["tiered_rates"][metric_cost_type] = new_tiered_rate
        else:
            format_tiered_rates = {metric_cost_type: rate.get("tiered_rates")}
            rate["tiered_rates"] = format_tiered_rates
            metric_rate_map[metric_name] = rate
    return metric_rate_map


def infrastructure_rates_from_price_list(price_list: dict) -> dict:
    """Extract infra rates — same as CostModelDBAccessor.infrastructure_rates."""
    return {
        key: value["tiered_rates"]["Infrastructure"][0]["value"]
        for key, value in price_list.items()
        if "Infrastructure" in value.get("tiered_rates", {})
    }


def supplementary_rates_from_price_list(price_list: dict) -> dict:
    """Extract supplementary rates — same as CostModelDBAccessor.supplementary_rates."""
    return {
        key: value["tiered_rates"]["Supplementary"][0]["value"]
        for key, value in price_list.items()
        if "Supplementary" in value.get("tiered_rates", {})
    }


# ---------------------------------------------------------------------------
# Helper: convert JSON rates to simulated Rate rows
# ---------------------------------------------------------------------------
def json_rates_to_rate_rows(rates_json: list[dict]) -> list[RateRow]:
    """
    Convert a CostModel.rates JSON blob into simulated RateRow objects.
    This mirrors what migration M3 would do.
    """
    rows = []
    used_names: set[str] = set()
    counter = 0

    for rate_json in rates_json:
        metric_name = rate_json.get("metric", {}).get("name", "unknown")
        cost_type = rate_json.get("cost_type", "Infrastructure")
        description = rate_json.get("description", "")
        tiered_rates = rate_json.get("tiered_rates", [])
        tag_rates = rate_json.get("tag_rates", {})

        default_rate = Decimal(str(tiered_rates[0].get("value", 0))) if tiered_rates else Decimal("0")

        candidate = description[:50] if description else metric_name[:50]
        if candidate in used_names:
            base = candidate[:47]
            for i in range(1000):
                suffixed = f"{base}_{i:03d}"
                if suffixed not in used_names:
                    candidate = suffixed
                    break
        used_names.add(candidate)

        counter += 1
        rows.append(RateRow(
            uuid=f"rate-{counter:04d}",
            price_list_id="pl-0001",
            custom_name=candidate,
            description=description,
            metric=metric_name,
            metric_type=_derive_metric_type(metric_name),
            cost_type=cost_type,
            default_rate=default_rate,
            tag_key=tag_rates.get("tag_key", ""),
            tag_values=tag_rates.get("tag_values", {}),
        ))

    return rows


USAGE_METRIC_MAP = {
    "cpu_core_usage_per_hour": "cpu",
    "cpu_core_request_per_hour": "cpu",
    "cpu_core_effective_usage_per_hour": "cpu",
    "memory_gb_usage_per_hour": "memory",
    "memory_gb_request_per_hour": "memory",
    "memory_gb_effective_usage_per_hour": "memory",
    "storage_gb_usage_per_month": "storage",
    "storage_gb_request_per_month": "storage",
    "cluster_core_cost_per_hour": "cpu",
}


def _derive_metric_type(metric_name: str) -> str:
    if metric_name in USAGE_METRIC_MAP:
        return USAGE_METRIC_MAP[metric_name]
    if "gpu" in metric_name:
        return "gpu"
    if metric_name in ("node_cost_per_month", "node_core_cost_per_month",
                       "cluster_cost_per_month"):
        return "cpu"
    if metric_name == "pvc_cost_per_month":
        return "storage"
    if metric_name.startswith("vm_"):
        return "cpu"
    return "cpu"


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

# Fixture 1: Simple case — one rate per metric, both cost types
SIMPLE_RATES_JSON = [
    {
        "metric": {"name": "cpu_core_usage_per_hour"},
        "cost_type": "Infrastructure",
        "description": "CPU usage charge",
        "tiered_rates": [{"value": 0.22, "unit": "USD"}],
    },
    {
        "metric": {"name": "cpu_core_usage_per_hour"},
        "cost_type": "Supplementary",
        "description": "CPU usage supplementary",
        "tiered_rates": [{"value": 0.05, "unit": "USD"}],
    },
    {
        "metric": {"name": "memory_gb_usage_per_hour"},
        "cost_type": "Infrastructure",
        "description": "Memory usage charge",
        "tiered_rates": [{"value": 0.01, "unit": "USD"}],
    },
    {
        "metric": {"name": "storage_gb_usage_per_month"},
        "cost_type": "Infrastructure",
        "description": "Storage usage charge",
        "tiered_rates": [{"value": 0.03, "unit": "USD"}],
    },
]

# Fixture 2: Duplicate metrics (same metric+cost_type, values should sum)
DUPLICATE_RATES_JSON = [
    {
        "metric": {"name": "cpu_core_usage_per_hour"},
        "cost_type": "Infrastructure",
        "description": "CPU charge A",
        "tiered_rates": [{"value": 0.10, "unit": "USD"}],
    },
    {
        "metric": {"name": "cpu_core_usage_per_hour"},
        "cost_type": "Infrastructure",
        "description": "CPU charge B",
        "tiered_rates": [{"value": 0.12, "unit": "USD"}],
    },
    {
        "metric": {"name": "cpu_core_usage_per_hour"},
        "cost_type": "Supplementary",
        "description": "CPU supp",
        "tiered_rates": [{"value": 0.05, "unit": "USD"}],
    },
    {
        "metric": {"name": "memory_gb_usage_per_hour"},
        "cost_type": "Infrastructure",
        "description": "",
        "tiered_rates": [{"value": 0.008, "unit": "USD"}],
    },
]

# Fixture 3: Mixed tiered + tag rates (tag rates should be skipped in price_list)
MIXED_RATES_JSON = [
    {
        "metric": {"name": "cpu_core_usage_per_hour"},
        "cost_type": "Infrastructure",
        "description": "CPU usage",
        "tiered_rates": [{"value": 0.22, "unit": "USD"}],
    },
    {
        "metric": {"name": "node_cost_per_month"},
        "cost_type": "Infrastructure",
        "description": "",
        "tag_rates": {
            "tag_key": "app",
            "tag_values": [
                {"tag_value": "smoke", "value": 123, "unit": "USD", "default": True}
            ],
        },
    },
    {
        "metric": {"name": "memory_gb_usage_per_hour"},
        "cost_type": "Supplementary",
        "description": "Mem supp",
        "tiered_rates": [{"value": 0.015, "unit": "USD"}],
    },
]

# Fixture 4: Empty rates
EMPTY_RATES_JSON: list = []

# Fixture 5: Full realistic cost model (mirrors OCP_ON_PREM_COST_MODEL pattern)
FULL_RATES_JSON = [
    {"metric": {"name": "cpu_core_usage_per_hour"}, "cost_type": "Infrastructure",
     "description": "CPU usage", "tiered_rates": [{"value": 0.22, "unit": "USD"}]},
    {"metric": {"name": "cpu_core_request_per_hour"}, "cost_type": "Infrastructure",
     "description": "CPU request", "tiered_rates": [{"value": 0.10, "unit": "USD"}]},
    {"metric": {"name": "cpu_core_effective_usage_per_hour"}, "cost_type": "Infrastructure",
     "description": "CPU effective", "tiered_rates": [{"value": 0.15, "unit": "USD"}]},
    {"metric": {"name": "memory_gb_usage_per_hour"}, "cost_type": "Infrastructure",
     "description": "Memory usage", "tiered_rates": [{"value": 0.01, "unit": "USD"}]},
    {"metric": {"name": "memory_gb_request_per_hour"}, "cost_type": "Infrastructure",
     "description": "Memory request", "tiered_rates": [{"value": 0.008, "unit": "USD"}]},
    {"metric": {"name": "memory_gb_effective_usage_per_hour"}, "cost_type": "Infrastructure",
     "description": "Memory effective", "tiered_rates": [{"value": 0.012, "unit": "USD"}]},
    {"metric": {"name": "storage_gb_usage_per_month"}, "cost_type": "Infrastructure",
     "description": "Storage usage", "tiered_rates": [{"value": 0.03, "unit": "USD"}]},
    {"metric": {"name": "storage_gb_request_per_month"}, "cost_type": "Infrastructure",
     "description": "Storage request", "tiered_rates": [{"value": 0.02, "unit": "USD"}]},
    {"metric": {"name": "node_cost_per_month"}, "cost_type": "Supplementary",
     "description": "Node monthly", "tiered_rates": [{"value": 100.0, "unit": "USD"}]},
    {"metric": {"name": "cluster_cost_per_month"}, "cost_type": "Supplementary",
     "description": "Cluster monthly", "tiered_rates": [{"value": 500.0, "unit": "USD"}]},
    {"metric": {"name": "pvc_cost_per_month"}, "cost_type": "Infrastructure",
     "description": "PVC monthly", "tiered_rates": [{"value": 10.0, "unit": "USD"}]},
]


# ---------------------------------------------------------------------------
# Comparison utilities
# ---------------------------------------------------------------------------

def normalize_price_list(pl: dict) -> dict:
    """
    Normalize a price_list dict for comparison.
    The JSON-based path preserves extra keys (description, metric, cost_type)
    on the outer dict; the Rate-table path only produces the keys we control.
    We compare only the structural keys that matter for downstream consumers:
    - metric.name
    - tiered_rates (nested by cost_type, with float values)
    """
    normalized = {}
    for metric_name, entry in sorted(pl.items()):
        tiered = {}
        for cost_type, rate_list in sorted(entry.get("tiered_rates", {}).items()):
            tiered[cost_type] = [{"value": round(float(r["value"]), 10), "unit": r["unit"]} for r in rate_list]
        normalized[metric_name] = {
            "metric": {"name": metric_name},
            "tiered_rates": tiered,
        }
    return normalized


def compare_price_lists(json_pl: dict, rate_pl: dict) -> list[str]:
    """Return list of difference descriptions. Empty = match."""
    diffs = []
    n_json = normalize_price_list(json_pl)
    n_rate = normalize_price_list(rate_pl)

    all_keys = set(n_json.keys()) | set(n_rate.keys())
    for key in sorted(all_keys):
        if key not in n_json:
            diffs.append(f"metric '{key}' in Rate path but not JSON path")
            continue
        if key not in n_rate:
            diffs.append(f"metric '{key}' in JSON path but not Rate path")
            continue

        j_tiered = n_json[key]["tiered_rates"]
        r_tiered = n_rate[key]["tiered_rates"]

        all_ct = set(j_tiered.keys()) | set(r_tiered.keys())
        for ct in sorted(all_ct):
            if ct not in j_tiered:
                diffs.append(f"'{key}' cost_type '{ct}' in Rate path but not JSON path")
                continue
            if ct not in r_tiered:
                diffs.append(f"'{key}' cost_type '{ct}' in JSON path but not Rate path")
                continue

            j_val = j_tiered[ct][0]["value"]
            r_val = r_tiered[ct][0]["value"]
            if abs(j_val - r_val) > 1e-9:
                diffs.append(f"'{key}' {ct}: JSON={j_val} vs Rate={r_val}")

    return diffs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_simple_rates():
    """Simple case: one rate per metric per cost_type."""
    json_pl = price_list_from_json(SIMPLE_RATES_JSON)
    rate_rows = json_rates_to_rate_rows(SIMPLE_RATES_JSON)
    rate_pl = price_list_from_rate_table(rate_rows)

    diffs = compare_price_lists(json_pl, rate_pl)
    assert not diffs, f"Differences found: {diffs}"

    infra_json = infrastructure_rates_from_price_list(json_pl)
    infra_rate = infrastructure_rates_from_price_list(rate_pl)
    assert infra_json == infra_rate, f"infra rates differ: {infra_json} vs {infra_rate}"

    supp_json = supplementary_rates_from_price_list(json_pl)
    supp_rate = supplementary_rates_from_price_list(rate_pl)
    assert supp_json == supp_rate, f"supp rates differ: {supp_json} vs {supp_rate}"


def test_duplicate_rates():
    """Multiple rates with same metric+cost_type should sum."""
    json_pl = price_list_from_json(DUPLICATE_RATES_JSON)
    rate_rows = json_rates_to_rate_rows(DUPLICATE_RATES_JSON)
    rate_pl = price_list_from_rate_table(rate_rows)

    diffs = compare_price_lists(json_pl, rate_pl)
    assert not diffs, f"Differences found: {diffs}"

    expected_cpu_infra = 0.10 + 0.12
    actual_json = json_pl["cpu_core_usage_per_hour"]["tiered_rates"]["Infrastructure"][0]["value"]
    actual_rate = rate_pl["cpu_core_usage_per_hour"]["tiered_rates"]["Infrastructure"][0]["value"]
    assert abs(actual_json - expected_cpu_infra) < 1e-9, f"JSON sum wrong: {actual_json}"
    assert abs(actual_rate - expected_cpu_infra) < 1e-9, f"Rate sum wrong: {actual_rate}"


def test_mixed_tiered_and_tag():
    """Tag rates are skipped in price_list (only tiered rates appear)."""
    json_pl = price_list_from_json(MIXED_RATES_JSON)
    rate_rows = json_rates_to_rate_rows(MIXED_RATES_JSON)
    rate_pl = price_list_from_rate_table(rate_rows)

    diffs = compare_price_lists(json_pl, rate_pl)
    assert not diffs, f"Differences found: {diffs}"

    assert "node_cost_per_month" not in json_pl, "tag-only metric should not appear in JSON price_list"
    assert "node_cost_per_month" not in rate_pl, "tag-only metric should not appear in Rate price_list"


def test_empty_rates():
    """Empty rates JSON produces empty price_list."""
    json_pl = price_list_from_json(EMPTY_RATES_JSON)
    rate_rows = json_rates_to_rate_rows(EMPTY_RATES_JSON)
    rate_pl = price_list_from_rate_table(rate_rows)

    assert json_pl == {}
    assert rate_pl == {}


def test_full_realistic():
    """Full realistic cost model with all metric types."""
    json_pl = price_list_from_json(FULL_RATES_JSON)
    rate_rows = json_rates_to_rate_rows(FULL_RATES_JSON)
    rate_pl = price_list_from_rate_table(rate_rows)

    diffs = compare_price_lists(json_pl, rate_pl)
    assert not diffs, f"Differences found: {diffs}"

    infra_json = infrastructure_rates_from_price_list(json_pl)
    infra_rate = infrastructure_rates_from_price_list(rate_pl)
    assert infra_json == infra_rate, f"infra rates differ: {infra_json} vs {infra_rate}"

    supp_json = supplementary_rates_from_price_list(json_pl)
    supp_rate = supplementary_rates_from_price_list(rate_pl)
    assert supp_json == supp_rate, f"supp rates differ: {supp_json} vs {supp_rate}"

    assert len(infra_json) == 9, f"Expected 9 infra metrics, got {len(infra_json)}"
    assert len(supp_json) == 2, f"Expected 2 supp metrics, got {len(supp_json)}"


def test_infrastructure_rates_values():
    """Verify specific rate values propagate correctly."""
    rate_rows = json_rates_to_rate_rows(FULL_RATES_JSON)
    rate_pl = price_list_from_rate_table(rate_rows)
    infra = infrastructure_rates_from_price_list(rate_pl)

    assert abs(infra["cpu_core_usage_per_hour"] - 0.22) < 1e-9
    assert abs(infra["memory_gb_usage_per_hour"] - 0.01) < 1e-9
    assert abs(infra["storage_gb_usage_per_month"] - 0.03) < 1e-9
    assert abs(infra["pvc_cost_per_month"] - 10.0) < 1e-9


# ---------------------------------------------------------------------------
# Main: run all tests standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_simple_rates,
        test_duplicate_rates,
        test_mixed_tiered_and_tag,
        test_empty_rates,
        test_full_realistic,
        test_infrastructure_rates_values,
    ]
    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"  PASS  {test_fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {test_fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {test_fn.__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)}")
    if failed:
        raise SystemExit(1)
