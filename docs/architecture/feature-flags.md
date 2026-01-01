# Feature Flags Architecture

## Overview

Koku uses [Unleash](https://www.getunleash.io/) for feature flag management in SaaS deployments. For on-premise deployments without access to Red Hat's Unleash server, a disabled client is used.

## Table of Contents

- [Deployment Modes](#deployment-modes)
- [Implementation](#implementation)
- [Configuration](#configuration)
- [Testing](#testing)
- [Usage Examples](#usage-examples)
- [Migration from SaaS to On-Prem](#migration-from-saas-to-on-prem)
- [Related Files](#related-files)

---

## Deployment Modes

### SaaS Mode (Default)

- `KOKU_ONPREM_DEPLOYMENT=False` (or unset)
- Uses `UnleashClient` to connect to Red Hat's Unleash server
- Feature flags are dynamically controlled via Unleash dashboard
- Requires network access to Unleash server
- Supports gradual rollouts, A/B testing, and feature toggles

**Configuration**:
```bash
KOKU_ONPREM_DEPLOYMENT=False  # or leave unset
UNLEASH_URL=https://unleash.example.com
UNLEASH_TOKEN=your-token-here
```

### On-Premise Mode

- `KOKU_ONPREM_DEPLOYMENT=True`
- Uses `DisabledUnleashClient` (mock implementation)
- All feature flags return `False` by default
- No external API calls to Unleash server
- No network dependencies on Red Hat SaaS services
- Suitable for air-gapped or restricted network environments

**Configuration**:
```bash
KOKU_ONPREM_DEPLOYMENT=True
# Unleash URL and token are ignored in on-prem mode
```

---

## Implementation

### Client Selection

**File**: [`koku/koku/feature_flags.py`](../../koku/feature_flags.py)

The Unleash client is selected at application startup based on the `KOKU_ONPREM_DEPLOYMENT` setting:

```python
if settings.KOKU_ONPREM_DEPLOYMENT:
    UNLEASH_CLIENT = DisabledUnleashClient()
else:
    UNLEASH_CLIENT = UnleashClient(
        url=settings.UNLEASH_URL,
        app_name="koku",
        instance_id="koku-api",
        custom_headers={"Authorization": settings.UNLEASH_TOKEN},
    )
```

### DisabledUnleashClient

The `DisabledUnleashClient` is a mock implementation that provides a no-op interface compatible with the real Unleash client.

**Key characteristics**:

- **`is_enabled(feature_name, context=None, default=False)`**
  - Always returns `False` (or the provided `default` value)
  - Never makes network calls
  - Logs that feature flag evaluation was skipped

- **`get_variant(feature_name, context=None)`**
  - Always returns `{"name": "disabled", "enabled": False}`
  - Consistent with disabled state

- **Thread-safe**: Safe for concurrent access across multiple threads/workers
- **No initialization errors**: Never fails to initialize, unlike network-dependent clients
- **No cleanup required**: No connections to close or resources to clean up

**Source code reference**: [`koku/koku/feature_flags.py#L15-L45`](../../koku/feature_flags.py#L15-L45)

---

## Configuration

### Environment Variables

| Variable                  | Required | Default | Description                                      |
|---------------------------|----------|---------|--------------------------------------------------|
| `KOKU_ONPREM_DEPLOYMENT`  | No       | `False` | Enable on-premise mode (disables Unleash client) |
| `UNLEASH_URL`             | SaaS only| -       | Unleash server URL (ignored in on-prem mode)     |
| `UNLEASH_TOKEN`           | SaaS only| -       | Unleash API token (ignored in on-prem mode)      |
| `UNLEASH_ADMIN_TOKEN`     | SaaS only| -       | Unleash admin token (ignored in on-prem mode)    |
| `UNLEASH_PAT`             | SaaS only| -       | Unleash personal access token (ignored in on-prem) |

### Setting Configuration

**For development** (`.env` file):
```bash
KOKU_ONPREM_DEPLOYMENT=True
```

**For Docker Compose**:
```bash
export KOKU_ONPREM_DEPLOYMENT=True
make docker-up
```

**For Kubernetes/OpenShift** (via Helm chart):
```yaml
# values.yaml
koku:
  env:
    - name: KOKU_ONPREM_DEPLOYMENT
      value: "True"
```

**Django settings**: [`koku/koku/settings.py`](../../koku/settings.py#L123)
```python
KOKU_ONPREM_DEPLOYMENT = env.bool("KOKU_ONPREM_DEPLOYMENT", default=False)
```

---

## Testing

### Test Suite

**Test File**: [`koku/koku/test_feature_flags.py`](../../koku/test_feature_flags.py)

Comprehensive test suite covering:

1. **Client Initialization**
   - Correct client selected based on `KOKU_ONPREM_DEPLOYMENT`
   - Both SaaS and on-prem modes tested

2. **Feature Flag Evaluation**
   - `is_enabled()` returns `False` for all flags
   - Default values are respected
   - Context parameters are accepted (but ignored)

3. **Variant Retrieval**
   - `get_variant()` returns consistent disabled state
   - Returns expected dictionary structure

4. **Method Signatures**
   - All Unleash client methods are implemented
   - Compatible interface with real Unleash client

5. **No External API Calls**
   - No network requests made in on-prem mode
   - No exceptions raised for missing Unleash server

### Running Tests

```bash
# Run feature flag tests only
python koku/manage.py test koku.koku.test_feature_flags -v 2

# Run with coverage
coverage run --source='koku.koku.feature_flags' koku/manage.py test koku.koku.test_feature_flags
coverage report
```

### Test Coverage

- **11 comprehensive test cases**
- **100% code coverage** of `DisabledUnleashClient`
- Tests for both on-prem and SaaS mode selection

---

## Usage Examples

### Checking Feature Flags

```python
from koku.feature_flags import UNLEASH_CLIENT

# Check if a feature is enabled
if UNLEASH_CLIENT.is_enabled("new_api_endpoint"):
    # Feature is enabled (only in SaaS mode)
    return new_api_endpoint(request)
else:
    # Feature is disabled (always in on-prem mode)
    return legacy_api_endpoint(request)
```

### Using Default Values

```python
# Provide a default value (useful for gradual rollouts)
use_new_feature = UNLEASH_CLIENT.is_enabled(
    "experimental_feature",
    default=False  # Default to disabled in on-prem mode
)

if use_new_feature:
    apply_experimental_logic()
else:
    apply_stable_logic()
```

### Getting Variants (A/B Testing)

```python
# Get feature variant
variant = UNLEASH_CLIENT.get_variant("ui_experiment")

if variant["name"] == "treatment_a":
    render_treatment_a()
elif variant["name"] == "treatment_b":
    render_treatment_b()
else:
    # In on-prem mode, variant["name"] == "disabled"
    render_control()
```

### Context-Aware Feature Flags

```python
# Pass context for targeted feature flags
context = {
    "userId": user.id,
    "properties": {
        "tenant": "org123",
        "region": "us-east-1"
    }
}

if UNLEASH_CLIENT.is_enabled("tenant_specific_feature", context=context):
    enable_tenant_feature()
```

**Note**: In on-prem mode, context is accepted but ignored. All flags return `False`.

---

## Migration from SaaS to On-Prem

### Migration Steps

1. **Set environment variable** in all deployment environments:
   ```bash
   KOKU_ONPREM_DEPLOYMENT=True
   ```

2. **Update Helm chart values** (if using Helm):
   ```yaml
   kokuOnpremDeployment: "True"
   ```

3. **Restart all services**:
   - Koku API pods
   - MASU pods
   - All Celery workers

4. **Verify deployment**:
   - Check logs for "On-prem mode: Using DisabledUnleashClient" message
   - Confirm no Unleash connection errors
   - Verify application behavior with all flags disabled

5. **Test application functionality**:
   - All features should work with feature flags disabled
   - No regression in core functionality

### Rollback Procedure

If migration to on-prem mode causes issues:

1. **Revert environment variable**:
   ```bash
   KOKU_ONPREM_DEPLOYMENT=False
   ```

2. **Restart services** to reconnect to Unleash server

3. **Verify** Unleash connectivity restored

**No code changes required** - the client is selected automatically based on the environment variable.

### What to Expect After Migration

**In on-prem mode**:
- ✅ All core functionality works (data ingestion, reporting, APIs)
- ✅ No external network calls to Unleash
- ✅ No feature flags enabled (all return `False`)
- ⚠️ New features gated behind flags will be disabled
- ⚠️ A/B tests and gradual rollouts not available

**Features unaffected**:
- Data ingestion from cloud providers (AWS, Azure, GCP)
- OpenShift data ingestion
- Cost model calculations
- API queries and reporting
- Database operations
- Celery task processing

**Features that may be disabled**:
- Any features currently behind feature flags in SaaS
- Experimental or beta features
- Gradual rollout features

---

## Related Files

### Implementation Files

- [`koku/koku/feature_flags.py`](../../koku/feature_flags.py) - Client initialization and `DisabledUnleashClient` implementation
- [`koku/koku/settings.py`](../../koku/settings.py#L123) - Environment variable configuration
- [`koku/koku/test_feature_flags.py`](../../koku/test_feature_flags.py) - Test suite

### Documentation Files

- [`docs/install.md`](../install.md) - Installation and deployment configuration
- [`README.md`](../../README.md) - Development setup instructions
- [`.env.example`](../../.env.example) - Example environment configuration

### External Resources

- [Unleash Documentation](https://docs.getunleash.io/)
- [Feature Toggle Best Practices](https://martinfowler.com/articles/feature-toggles.html)

---

## Troubleshooting

### Common Issues

**Issue**: Feature flags not working in development

**Solution**: Check that `KOKU_ONPREM_DEPLOYMENT` is not set to `True` in your `.env` file. For development with real Unleash, either unset it or set it to `False`.

---

**Issue**: Unleash connection errors in logs

**Solution**: If you're seeing Unleash connection errors and want to run in on-prem mode, set `KOKU_ONPREM_DEPLOYMENT=True` to disable Unleash client entirely.

---

**Issue**: New feature not working in on-prem deployment

**Solution**: Check if the feature is behind a feature flag. In on-prem mode, all feature flags are disabled. You may need to remove the feature flag check or implement an on-prem-specific code path.

---

## Best Practices

1. **Default to Disabled**: When checking feature flags, default to `False` to ensure compatibility with on-prem mode:
   ```python
   if UNLEASH_CLIENT.is_enabled("new_feature", default=False):
   ```

2. **Graceful Degradation**: Ensure all code paths work when feature flags are disabled:
   ```python
   if UNLEASH_CLIENT.is_enabled("optimized_query"):
       return optimized_query()
   else:
       return standard_query()  # Must work in on-prem mode
   ```

3. **Document Flag Dependencies**: If a feature requires a flag to be enabled, document this in code comments and user-facing documentation.

4. **Test Both Modes**: When adding feature-flagged code, test with both `KOKU_ONPREM_DEPLOYMENT=True` and `False`.

5. **Monitor Logs**: Check logs for feature flag evaluation to understand which code paths are being executed.

---

## Future Enhancements

Potential improvements to the feature flag system:

1. **Configuration File for On-Prem Flags**: Allow specific flags to be enabled in on-prem mode via configuration file
2. **Flag Override Environment Variables**: Support per-flag environment variables (e.g., `FEATURE_NEW_API=True`)
3. **Telemetry**: Add metrics for feature flag evaluation in both modes
4. **Admin UI**: Create admin interface to view/modify flag states in on-prem deployments

---

*Last Updated: December 2025*
*Related Commit: `6475a00c` (koku-onprem-integration branch)*

