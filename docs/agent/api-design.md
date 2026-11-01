# API Design

## Serializers & Views

- Use DRF serializers for input validation; return clear field errors
- Prefer appropriate HTTP status codes; paginate large list responses
- Validate/sanitize user input (paths, uploads, sizes) at the API boundary
- Query handlers must use `tenant_context(self.tenant)` for tenant models

## When Changing Endpoints

- Update `docs/specs/openapi.json` (also check `koku/sources/openapi.json`, `koku/masu/openapi.json`)
- See [`docs/agent/provider-maps.md`](provider-maps.md) when touching report `provider_map.py`
- Architecture context: [`docs/architecture/api-serializers-provider-maps.md`](../architecture/api-serializers-provider-maps.md)
