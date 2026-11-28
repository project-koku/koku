"""Monthly cost totals per cluster from koku's OCP costs report API (run inside the rtu-toolbox pod)."""
import sys

sys.path.insert(0, "/tmp/rtu")
import rtu_setup  # noqa: E402

for cluster in ("rtu-cluster-a", "rtu-cluster-b"):
    for month in ("2026-10", "2026-11"):
        start = f"{month}-01"
        end = "2026-10-31" if month == "2026-10" else "2026-11-28"
        report = rtu_setup.call(
            "GET",
            f"{rtu_setup.KOKU_API}/reports/openshift/costs/",
            params={"filter[cluster]": cluster, "start_date": start, "end_date": end, "filter[resolution]": "monthly"},
        )
        total = report["meta"]["total"]["cost"]
        print(
            cluster,
            month,
            "total",
            total["total"]["value"],
            "| raw",
            total["raw"]["value"],
            "| usage",
            total["usage"]["value"],
            "| markup",
            total["markup"]["value"],
            "| distributed",
            total.get("distributed", {}).get("value"),
        )
