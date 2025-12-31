# Add SOURCES_CRUD flag for independent Sources API CRUD control

## Summary

This PR adds a new `SOURCES_CRUD` environment variable flag that allows enabling Sources API CRUD operations (create, update, delete) independently from the `DEVELOPMENT` mode. Previously, these operations were only available when `DEVELOPMENT=True`, which could be too permissive for certain environments.

Additionally, this PR adds Kafka event publishing for source deletion operations to ensure ros-ocp-backend compatibility when sources are deleted through the API.

## Changes

### 1. Added `SOURCES_CRUD` setting (`koku/koku/settings.py`)

Added a new boolean setting that reads from the `SOURCES_CRUD` environment variable:

```python
SOURCES_CRUD = ENVIRONMENT.bool("SOURCES_CRUD", default=False)
```

### 2. Updated Sources API view condition (`koku/sources/api/view.py`)

Modified the condition that enables CRUD mixins and HTTP methods to check for either `SOURCES_CRUD` or `DEVELOPMENT`:

```python
if settings.SOURCES_CRUD or settings.DEVELOPMENT:
    MIXIN_LIST.extend([mixins.CreateModelMixin, mixins.UpdateModelMixin, DestroySourceMixin])
    HTTP_METHOD_LIST.extend(["post", "patch", "delete"])
```

### 3. Added Kafka event publishing for source deletion

Source deletion operations now publish `Application.destroy` events to Kafka for ros-ocp-backend compatibility. The publish functionality is implemented in `koku/sources/storage.py` via the `destroy_source_event()` function, which:

- Fetches source data before deletion
- Deletes the source from the database
- Publishes the destroy event to Kafka after successful deletion
- Ensures events are only published if deletion succeeds

This ensures that ros-ocp-backend and other consumers are notified when sources are deleted through the Sources API.

## Behavior

- **Before**: Sources CRUD operations were only enabled when `DEVELOPMENT=True`
- **After**: Sources CRUD operations are enabled when either `SOURCES_CRUD=True` OR `DEVELOPMENT=True`

This provides more granular control:
- Production environments can enable Sources CRUD without enabling all development features
- Development environments continue to work as before (backward compatible)
- The flag defaults to `False` for security

## Usage

To enable Sources CRUD operations, set the environment variable:

```bash
export SOURCES_CRUD=True
```

Or in docker-compose:

```yaml
environment:
  - SOURCES_CRUD=True
```

## Impact

- **Backward Compatible**: Existing behavior is preserved - `DEVELOPMENT=True` still enables Sources CRUD
- **Security**: Defaults to `False`, requiring explicit opt-in
- **Flexibility**: Allows enabling Sources CRUD in production-like environments without full development mode
- **Event Publishing**: Source deletions now publish Kafka events for downstream consumers (ros-ocp-backend), ensuring proper synchronization across services

## Testing

- Verify Sources API CRUD endpoints (POST, PATCH, DELETE) are available when `SOURCES_CRUD=True`
- Verify Sources API CRUD endpoints remain available when `DEVELOPMENT=True`
- Verify Sources API CRUD endpoints are disabled when both flags are `False`
- Verify read-only endpoints (GET, HEAD) remain available regardless of flag settings
- Verify that source deletion publishes `Application.destroy` events to Kafka
- Verify that Kafka events are only published after successful source deletion
- Verify ros-ocp-backend receives and processes deletion events correctly
