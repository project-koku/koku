# API — Global Settings Endpoint

**Parent**: [README.md](README.md) · **Status**: Draft

---

## Overview

A new REST endpoint exposes the `TenantSettings` data retention
configuration to the frontend. The endpoint is registered only when
`settings.ONPREM` is `True` and requires org-admin access for writes.

---

## Endpoint

### `GET /api/cost-management/v1/account-settings/data-retention/`

Returns the current data retention setting.

**Permission**: `SettingsAccessPermission` (org-admin or `settings.read`).

**Response** `200 OK`:

```json
{
    "data_retention_months": 12,
    "env_override": false
}
```

When `RETAIN_NUM_MONTHS` env var is set:

```json
{
    "data_retention_months": 4,
    "env_override": true
}
```

The `env_override` flag tells the frontend to disable the input
control and display a notice that the setting is controlled by the
environment.

### `PUT /api/cost-management/v1/account-settings/data-retention/`

Updates the data retention period.

**Permission**: Org-admin only (`settings.write` with `["*"]`).

**Request body**:

```json
{
    "data_retention_months": 24
}
```

**Response** `204 No Content` on success.

**Error responses**:

| Code | Condition |
|------|-----------|
| `400` | Value out of range (< 3 or > 120) |
| `403` | `RETAIN_NUM_MONTHS` env var is set (settings locked) |
| `403` | User is not org-admin |

---

## Serializer

```python
# api/settings/serializers.py (new)

class TenantSettingsSerializer(serializers.Serializer):
    data_retention_months = serializers.IntegerField(
        min_value=TenantSettings.MIN_RETENTION_MONTHS,
        max_value=TenantSettings.MAX_RETENTION_MONTHS,
    )
```

---

## View

```python
# api/settings/views.py (new class)

class GlobalSettingsView(APIView):
    """Global operational settings (on-prem only)."""

    permission_classes = [SettingsAccessPermission]

    def get(self, request):
        schema = request.user.customer.schema_name
        env_override = os.environ.get("RETAIN_NUM_MONTHS") is not None

        with schema_context(schema):
            settings_row, _ = TenantSettings.objects.get_or_create(
                defaults={
                    "data_retention_months": TenantSettings.DEFAULT_RETENTION_MONTHS,
                }
            )

        data = {
            "data_retention_months": (
                int(os.environ["RETAIN_NUM_MONTHS"])
                if env_override
                else settings_row.data_retention_months
            ),
            "env_override": env_override,
        }
        return Response(data)

    def put(self, request):
        if os.environ.get("RETAIN_NUM_MONTHS") is not None:
            return Response(
                {"error": "Data retention is controlled by the "
                          "RETAIN_NUM_MONTHS environment variable "
                          "and cannot be modified via the API."},
                status=status.HTTP_403_FORBIDDEN,
            )

        schema = request.user.customer.schema_name
        with schema_context(schema):
            settings_row, _ = TenantSettings.objects.get_or_create(
                defaults={
                    "data_retention_months": TenantSettings.DEFAULT_RETENTION_MONTHS,
                }
            )
            serializer = TenantSettingsSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            settings_row.data_retention_months = serializer.validated_data[
                "data_retention_months"
            ]
            settings_row.full_clean()
            settings_row.save()

        return Response(status=status.HTTP_204_NO_CONTENT)
```

---

## URL Registration

```python
# api/urls.py (modified)

if settings.ONPREM:
    urlpatterns += [
        path(
            "account-settings/data-retention/",
            GlobalSettingsView.as_view(),
            name="global-settings-data-retention",
        ),
    ]
```

The endpoint is registered **only** when `settings.ONPREM = True`.
SaaS deployments do not expose it.

---

## Permission Model

The existing `SettingsAccessPermission` is reused:

- **GET**: org-admin, or any user with `settings.read` access.
- **PUT**: org-admin, or user with `settings.write = ["*"]`.

This matches the PRD requirement: "Only Organization Administrators
will be able to view and change these settings."

---

## Shortening Retention — Warning

When the new `data_retention_months` is shorter than the current value,
the PRD requires a warning: *"This will permanently delete data from
MMDDYYYY to MMDDYYYY. Are you sure?"*

This is a **frontend concern**. The backend PUT does not require
confirmation. The frontend should:

1. `GET` the current setting to know the old retention.
2. If the user reduces retention, show a confirmation dialog with the
   date range that will be purged.
3. On confirmation, `PUT` the new value.

The backend stores the new value. The next scheduled purge cycle
deletes data that falls outside the new retention window.

---

## Cache Invalidation

When retention is updated, invalidate the view cache for the tenant
so that subsequent report queries use the correct
`materialized_view_month_start`. Call
`invalidate_view_cache_for_tenant_and_all_source_types()` after a
successful PUT (same pattern as currency update).

---

## Files Changed

| File | Change |
|------|--------|
| `api/settings/serializers.py` | New `TenantSettingsSerializer` |
| `api/settings/views.py` | New `GlobalSettingsView` class |
| `api/urls.py` | New route (on-prem gated) |

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-11 | Initial draft |
