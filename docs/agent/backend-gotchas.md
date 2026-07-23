# Backend Gotchas

Compact reference for common Django/ORM and utility patterns. See also the
**Task Router** in [`AGENTS.md`](../../AGENTS.md).

## Mixed-Type Aggregation

`Sum`, `Value(0)`, and `Coalesce` with `DecimalField` columns raise
`FieldError: Expression contains mixed types` when `IntegerField` and
`DecimalField` are mixed. Always set `output_field`:

```python
_decimal = DecimalField(max_digits=33, decimal_places=15)
qs.annotate(
    total=Sum(
        Coalesce(F("cost_model_cpu_cost"), Value(0, output_field=_decimal)),
        output_field=_decimal,
    )
)
```

Provider-map cost aggregations follow the same pattern — see
[`.cursor/rules/provider-maps.mdc`](../../.cursor/rules/provider-maps.mdc).

## TenantAPIProvider FK

Some tenant models FK to `TenantAPIProvider`, not public `Provider`. Filter by
UUID, not the public provider instance — full detail in
[`.cursor/rules/multi-tenancy.mdc`](../../.cursor/rules/multi-tenancy.mdc).

## DateHelper

`api.utils.DateHelper` — available as `self.dh` on `IamTestCase` / `MasuTestCase`:

```python
dh.now, dh.now_utc, dh.today, dh.yesterday, dh.tomorrow
dh.this_month_start, dh.this_month_end
dh.last_month_start, dh.last_month_end
dh.days_in_month(date), dh.list_days(start, end)
dh.parse_to_date(input)  # string or datetime → date
```

## SummaryRangeConfig

`masu.util.common.SummaryRangeConfig` — Pydantic date-range helper (accepts
`datetime` or `str`):

```python
summary_range = SummaryRangeConfig(start_date=self.dh.this_month_start, end_date=self.dh.today)
```

Properties: `start_of_month`, `end_of_month`, `is_current_month`, `summary_start`,
`summary_end`, `iter_summary_range_by_month()`.

## Structured Logging

```python
from api.common import log_json
LOG.info(log_json(msg="doing something", schema=self.schema, provider_uuid=uuid))
```

See [`.cursor/rules/logging-patterns.mdc`](../../.cursor/rules/logging-patterns.mdc).

## DB Accessor Pattern

```python
with OCPReportDBAccessor(self.schema) as accessor:
    accessor.populate_usage_costs_by_name(...)
```

For cost-model pipeline order and SQL locations, see
[`docs/architecture/cost-models.md`](../architecture/cost-models.md).
