#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Seed a tenant schema with synthetic rates_to_usage (RTU) rows for the RTU hardening work.

Tier 1 test data: database only, no nise, no pipeline. Creates one price list with
RTU_SEED_RATES rates, two cost models attached to it (the "shared price list" blast
radius of Finding E), and RTU_SEED_ROWS_PER_RATE_MONTH rows per rate per month for
RTU_SEED_MONTHS months, all on an existing OCP provider and report period.

Everything it creates is tagged with the "rtu-seed" prefix (price list, cost model
names, RTU custom_name), so --cleanup removes exactly that.

Run from the koku repository root with the dev database environment, e.g.:

    RTU_SEED_ROWS_PER_RATE_MONTH=20000 python koku/manage.py shell < dev/rtu-hardening/testdata/seed_rtu.py
    RTU_SEED_CLEANUP=1 python koku/manage.py shell < dev/rtu-hardening/testdata/seed_rtu.py

Environment (all optional):
    RTU_SEED_SCHEMA               tenant schema, default org1234567
    RTU_SEED_PROVIDER_UUID        OCP provider, default the first OCP provider of the schema's customer
    RTU_SEED_RATES                rates in the price list, default 30
    RTU_SEED_MONTHS               months of RTU rows ending with the current month, default 3
    RTU_SEED_ROWS_PER_RATE_MONTH  RTU rows per rate per month, default 10000
    RTU_SEED_CLEANUP              set to 1 to delete everything the seed created and exit
"""
import os
import time
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import connection
from django.db import transaction
from django_tenants.utils import schema_context

from api.provider.models import Provider
from cost_models.models import CostModel
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from koku.pg_partition import PartitionHandlerMixin
from reporting.provider.ocp.models import OCPUsageReportPeriod

PREFIX = "rtu-seed"
SCHEMA = os.environ.get("RTU_SEED_SCHEMA", "org1234567")
N_RATES = int(os.environ.get("RTU_SEED_RATES", "30"))
N_MONTHS = int(os.environ.get("RTU_SEED_MONTHS", "3"))
ROWS_PER_RATE_MONTH = int(os.environ.get("RTU_SEED_ROWS_PER_RATE_MONTH", "10000"))
METRICS = [
    ("cpu_core_usage_per_hour", "cpu"),
    ("memory_gb_usage_per_hour", "memory"),
    ("storage_gb_usage_per_month", "storage"),
    ("node_cost_per_month", "node"),
    ("cluster_cost_per_month", "cluster"),
]

INSERT_RTU_SQL = """
INSERT INTO rates_to_usage (
    uuid, rate_id, cost_model_id, source_uuid, report_period_id,
    usage_start, usage_end, cluster_id, namespace, node,
    custom_name, metric_type, cost_model_rate_type, calculated_cost
)
SELECT
    gen_random_uuid(), %(rate_id)s, %(cost_model_id)s, %(source_uuid)s, %(report_period_id)s,
    d.day, d.day, %(cluster_id)s, 'rtu-seed-ns-' || (g %% 50), 'rtu-seed-node-' || (g %% 10),
    %(custom_name)s, %(metric_type)s, %(cost_type)s, round((random() * 10)::numeric, 6)
FROM generate_series(1, %(rows)s) AS g
CROSS JOIN LATERAL (
    SELECT (%(month_start)s::date + ((g %% %(days)s) * interval '1 day'))::date AS day
) AS d
"""


def cleanup():
    with schema_context(SCHEMA), connection.cursor() as cursor:
        cursor.execute("DELETE FROM rates_to_usage WHERE custom_name LIKE %s", [f"{PREFIX}%"])
        rtu_deleted = cursor.rowcount
        cost_models = CostModel.objects.filter(name__startswith=PREFIX)
        price_lists = PriceList.objects.filter(name__startswith=PREFIX)
        rates_deleted = Rate.objects.filter(price_list__in=price_lists)._raw_delete(connection.alias)
        PriceListCostModelMap.objects.filter(price_list__in=price_lists).delete()
        n_cm = cost_models.count()
        cost_models._raw_delete(connection.alias)
        n_pl = price_lists.count()
        price_lists._raw_delete(connection.alias)
    print(f"cleanup: {rtu_deleted} RTU rows, {rates_deleted} rates, {n_cm} cost models, {n_pl} price lists")


def seed():
    with schema_context(SCHEMA):
        provider_uuid = os.environ.get("RTU_SEED_PROVIDER_UUID")
        if not provider_uuid:
            provider = Provider.objects.filter(customer__schema_name=SCHEMA, type=Provider.PROVIDER_OCP).first()
            if not provider:
                raise SystemExit(f"no OCP provider in {SCHEMA}; set RTU_SEED_PROVIDER_UUID")
            provider_uuid = str(provider.uuid)
        report_period = OCPUsageReportPeriod.objects.filter(provider_id=provider_uuid).order_by("-id").first()
        if not report_period:
            raise SystemExit(f"provider {provider_uuid} has no report period in {SCHEMA}")

        this_month = date.today().replace(day=1)
        months = [this_month - relativedelta(months=i) for i in range(N_MONTHS)]
        PartitionHandlerMixin()._handle_partitions(
            SCHEMA, ["rates_to_usage"], months[-1], this_month + relativedelta(months=1, days=-1)
        )

        with transaction.atomic():
            price_list = PriceList.objects.create(
                name=f"{PREFIX} prices",
                description="RTU hardening synthetic data",
                currency="USD",
                effective_start_date=months[-1],
                effective_end_date=date(2099, 12, 31),
                enabled=True,
                version=1,
                rates=[],
            )
            cost_models = []
            for suffix in ("A", "B"):
                cost_model = CostModel.objects.create(
                    name=f"{PREFIX} cost model {suffix}", description="RTU hardening", source_type="OCP", rates=[]
                )
                PriceListCostModelMap.objects.create(price_list=price_list, cost_model=cost_model, priority=1)
                cost_models.append(cost_model)
            rates = [
                Rate.objects.create(
                    price_list=price_list,
                    custom_name=f"{PREFIX} rate {i:03d}",
                    metric=METRICS[i % len(METRICS)][0],
                    metric_type=METRICS[i % len(METRICS)][1],
                    cost_type="Infrastructure" if i % 2 else "Supplementary",
                    default_rate=Decimal("0.01"),
                )
                for i in range(N_RATES)
            ]

        started = time.monotonic()
        with connection.cursor() as cursor:
            for month_start in months:
                days = ((month_start + relativedelta(months=1)) - month_start).days
                for i, rate in enumerate(rates):
                    cursor.execute(
                        INSERT_RTU_SQL,
                        {
                            "rate_id": rate.uuid,
                            "cost_model_id": cost_models[i % 2].uuid,
                            "source_uuid": provider_uuid,
                            "report_period_id": report_period.id,
                            "cluster_id": report_period.cluster_id,
                            "custom_name": rate.custom_name,
                            "metric_type": rate.metric_type,
                            "cost_type": rate.cost_type,
                            "rows": ROWS_PER_RATE_MONTH,
                            "month_start": month_start,
                            "days": days,
                        },
                    )
            cursor.execute("ANALYZE rates_to_usage")
        total = N_RATES * N_MONTHS * ROWS_PER_RATE_MONTH
        print(
            f"seeded {SCHEMA}: price list {price_list.uuid}, cost models {[str(c.uuid) for c in cost_models]}, "
            f"{N_RATES} rates, {total} RTU rows over {N_MONTHS} months in {time.monotonic() - started:.1f}s"
        )
        print(f"sample rate for measurements: {rates[0].uuid}")


if os.environ.get("RTU_SEED_CLEANUP") == "1":
    cleanup()
else:
    seed()
