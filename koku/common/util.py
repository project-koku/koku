import typing as t


def extract_context_from_sql_params(sql_params: dict[str, t.Any]) -> dict[str, t.Any]:
    ctx = {}
    if sql_params is None:
        return ctx
    if schema := sql_params.get("schema"):
        ctx["schema"] = schema
    if (start := sql_params.get("start")) or (start := sql_params.get("start_date")):
        ctx["start_date"] = start
    if (end := sql_params.get("end")) or (end := sql_params.get("end_date")):
        ctx["end_date"] = end
    if invoice_month := sql_params.get("invoice_month"):
        ctx["invoice_month"] = invoice_month
    if provider_uuid := sql_params.get("source_uuid"):
        ctx["provider_uuid"] = provider_uuid
    if cluster_id := sql_params.get("cluster_id"):
        ctx["cluster_id"] = cluster_id

    return ctx
