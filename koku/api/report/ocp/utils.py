from decimal import Decimal


def calculate_unused(row, finalized_mapping={}):
    """Calculates the unused portions of the capacity & request."""
    # Populate unused request and capacity
    for key, value in finalized_mapping.items():
        row[key] = value
    capacity = row.get("capacity", Decimal(0))
    if not capacity:
        capacity = Decimal(0)
    usage = row.get("usage") if row.get("usage") else Decimal(0)
    request = row.get("request") if row.get("request") else Decimal(0)
    effective_usage = max(usage, request)
    unused_capacity = max(capacity - effective_usage, 0)
    capacity_unused_percent = (unused_capacity / max(capacity, Decimal(1))) * 100
    row["capacity_unused"] = unused_capacity
    row["capacity_unused_percent"] = capacity_unused_percent
    unused_request = max(request - usage, 0)
    row["request_unused"] = unused_request
    if request <= 0:
        request = 1
    row["request_unused_percent"] = (unused_request / max(capacity, Decimal(1))) * 100
