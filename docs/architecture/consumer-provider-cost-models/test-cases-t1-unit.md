# Test Case Specifications — Tier 1: Unit Tests

**IEEE 829-2008 Test Case Specification**

| Field | Value |
|-------|-------|
| Parent Plan | [test-plan.md](./test-plan.md) (COST-3920-TP-001) |
| Tier | T1 — Unit |
| Base Class | `IamTestCase`, `TestCase` |
| Coverage Target | ≥85% |
| Test Count | 25 |

---

## Module: `cost_models/test/test_cost_model_context.py`

### Class: `CostModelContextModelTest`

---

### TC-01: Context creation with valid data

| Field | Value |
|-------|-------|
| Identifier | TC-01 |
| Test Items | `CostModelContext` model (C1) |
| BAC | BAC-1 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: Valid context creation persists all fields correctly.

**Given**
- A tenant schema with no existing `CostModelContext` rows
- `setUp` has cleared all contexts via `CostModelContext.objects.all().delete()`

**When**
- `baker.make("CostModelContext", name="provider", display_name="Provider", position=2, is_default=False)` is called
- The instance is refreshed from DB via `ctx.refresh_from_db()`

**Then**
- `ctx.name == "provider"`
- `ctx.display_name == "Provider"`
- `ctx.is_default` is `False`
- `ctx.position == 2`
- `ctx.uuid` is not `None` (auto-generated UUID)
- `ctx.created_timestamp` is not `None` (auto-set by DB)

---

### TC-02: Max 3 contexts enforced by DB CHECK

| Field | Value |
|-------|-------|
| Identifier | TC-02 |
| Test Items | `CostModelContext` model (C1) — position CHECK constraint |
| BAC | BAC-2 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: Fourth context per tenant is rejected by DB constraint.

**Given**
- 3 contexts already exist with positions 1, 2, 3:
  - `baker.make("CostModelContext", name="c1", position=1, is_default=True)`
  - `baker.make("CostModelContext", name="c2", position=2, is_default=False)`
  - `baker.make("CostModelContext", name="c3", position=3, is_default=False)`

**When**
- Inside `transaction.atomic()`:
  `baker.make("CostModelContext", name="c4", display_name="C4", position=4, is_default=False)`

**Then**
- `IntegrityError` is raised
- The DB CHECK constraint on `position` rejects values outside 1–3

---

### TC-03: One default context enforced by partial unique index

| Field | Value |
|-------|-------|
| Identifier | TC-03 |
| Test Items | `CostModelContext` model (C1) — partial unique index on `is_default` |
| BAC | BAC-3 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: Second `is_default=True` context is rejected.

**Given**
- One context with `is_default=True` already exists:
  `baker.make("CostModelContext", name="default", display_name="Consumer", position=1, is_default=True)`

**When**
- Inside `transaction.atomic()`:
  `baker.make("CostModelContext", name="also_default", display_name="Also Default", position=2, is_default=True)`

**Then**
- `IntegrityError` is raised
- The partial unique index `WHERE is_default = TRUE` blocks the second default

---

### TC-04a: Valid positions (1, 2, 3) accepted

| Field | Value |
|-------|-------|
| Identifier | TC-04a |
| Test Items | `CostModelContext` model (C1) — position CHECK constraint |
| BAC | BAC-2 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: Positions 1, 2, 3 are all accepted by the DB.

**Given**
- An empty tenant schema with no contexts

**When**
- Create contexts with positions 1, 2, 3 sequentially:
  ```python
  for pos in (1, 2, 3):
      ctx = baker.make("CostModelContext", name=f"ctx_{pos}",
                        display_name=f"Context {pos}", position=pos,
                        is_default=(pos == 1))
      ctx.refresh_from_db()
  ```

**Then**
- All 3 contexts persist successfully
- Each `ctx.position` matches the value provided

---

### TC-04b: Invalid positions (0, 4, -1) rejected

| Field | Value |
|-------|-------|
| Identifier | TC-04b |
| Test Items | `CostModelContext` model (C1) — position CHECK constraint |
| BAC | BAC-2 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: Out-of-range positions are rejected by DB constraint.

**Given**
- An empty tenant schema with no contexts

**When**
- For each invalid position `(0, 4, -1)`, inside `transaction.atomic()`:
  `baker.make("CostModelContext", name=f"bad_{pos}", position=pos, is_default=False)`

**Then**
- `IntegrityError` is raised for each invalid position (via `subTest`)
- No row is persisted for any invalid position

---

### TC-05a: Default context deletion is blocked

| Field | Value |
|-------|-------|
| Identifier | TC-05a |
| Test Items | `CostModelContext` model (C1) — delete guard |
| BAC | BAC-4 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: Attempting to delete the default context raises an error.

**Given**
- A context with `is_default=True` exists:
  `baker.make("CostModelContext", name="default", display_name="Consumer", position=1, is_default=True)`

**When**
- `default_ctx.delete()` is called

**Then**
- `ValidationError` or `IntegrityError` is raised
- The default context row still exists in the database

---

### TC-05b: Non-default context deletion is allowed

| Field | Value |
|-------|-------|
| Identifier | TC-05b |
| Test Items | `CostModelContext` model (C1) — delete guard |
| BAC | BAC-4 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: Non-default context can be deleted.

**Given**
- A non-default context exists:
  `baker.make("CostModelContext", name="provider", display_name="Provider", position=2, is_default=False)`

**When**
- `ctx.delete()` is called

**Then**
- No exception is raised
- `CostModelContext.objects.filter(uuid=ctx_uuid).exists()` returns `False`

---

### Class: `CostModelMapContextTest`

---

### TC-09: Same provider with different contexts allowed

| Field | Value |
|-------|-------|
| Identifier | TC-09 |
| Test Items | `CostModelMap` + `cost_model_context` FK (C2) |
| BAC | BAC-5 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: CostModelMap accepts two rows for the same provider when contexts differ.

**Given**
- Two contexts exist: `ctx_consumer` (default, position=1) and `ctx_provider` (position=2)
- One cost model exists: `baker.make("CostModel", source_type="OCP")`
- A `provider_uuid` is generated via `uuid4()`

**When**
- `CostModelMap.objects.create(provider_uuid=uuid, cost_model=cm, cost_model_context=ctx_consumer)`
- `CostModelMap.objects.create(provider_uuid=uuid, cost_model=cm, cost_model_context=ctx_provider)`

**Then**
- Both rows persist without error
- `CostModelMap.objects.filter(provider_uuid=uuid).count() == 2`

---

### TC-10: Duplicate provider + context rejected

| Field | Value |
|-------|-------|
| Identifier | TC-10 |
| Test Items | `CostModelMap` + `cost_model_context` FK (C2) — unique constraint |
| BAC | BAC-6 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: CostModelMap rejects duplicate (provider_uuid, cost_model_context).

**Given**
- One context exists: `ctx` (default)
- One `CostModelMap` row exists for `(provider_uuid, ctx)`

**When**
- Inside `transaction.atomic()`:
  `CostModelMap.objects.create(provider_uuid=uuid, cost_model=cm, cost_model_context=ctx)`

**Then**
- `IntegrityError` is raised (unique constraint violation)
- Only one row exists for `(provider_uuid, ctx)`

---

### Class: `CostModelManagerContextTest`

---

### TC-06: Manager allows same provider in different contexts

| Field | Value |
|-------|-------|
| Identifier | TC-06 |
| Test Items | `CostModelManager.update_provider_uuids` (C3) |
| BAC | BAC-7 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: update_provider_uuids succeeds when same provider is assigned to different contexts.

**Given**
- Two contexts exist: `ctx_consumer` (default) and `ctx_provider`
- Two cost models exist: `cm1` and `cm2`
- A `provider_uuid` string

**When**
- `CostModelManager(cm1.uuid).update_provider_uuids([provider_uuid], cost_model_context=ctx_consumer)`
- `CostModelManager(cm2.uuid).update_provider_uuids([provider_uuid], cost_model_context=ctx_provider)`

**Then**
- Both calls succeed without error
- `CostModelMap.objects.filter(provider_uuid=provider_uuid).count() == 2`

---

### TC-07: Manager rejects same provider + same context

| Field | Value |
|-------|-------|
| Identifier | TC-07 |
| Test Items | `CostModelManager.update_provider_uuids` (C3) |
| BAC | BAC-8 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: update_provider_uuids raises CostModelException when same provider+context already assigned.

**Given**
- One context exists: `ctx` (default)
- Cost model 1 already assigned to `(provider_uuid, ctx)` via the manager

**When**
- `CostModelManager(cm2.uuid).update_provider_uuids([provider_uuid], cost_model_context=ctx)`

**Then**
- `CostModelException` is raised with a descriptive error message

---

### TC-08: Manager defaults to tenant's default context when None

| Field | Value |
|-------|-------|
| Identifier | TC-08 |
| Test Items | `CostModelManager.update_provider_uuids` (C3) |
| BAC | BAC-7 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: When cost_model_context is not passed, manager resolves to tenant's default.

**Given**
- A default context exists: `baker.make("CostModelContext", name="default", is_default=True)`

**When**
- `CostModelManager(cm.uuid).update_provider_uuids([provider_uuid])`
  (no `cost_model_context` argument)

**Then**
- `CostModelMap` row is created
- `mapping.cost_model_context` is not `None`
- `mapping.cost_model_context.name == "default"`

---

### Class: `CostModelContextSerializerTest`

---

### TC-11: Serializer accepts valid context data

| Field | Value |
|-------|-------|
| Identifier | TC-11 |
| Test Items | `CostModelContextSerializer` (C4) |
| BAC | BAC-1 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: Serializer validates valid name and display_name.

**Given**
- A default context exists (required for serializer count logic)

**When**
- `CostModelContextSerializer(data={"name": "provider", "display_name": "Provider"}).is_valid(raise_exception=True)`

**Then**
- Returns `True` — data is valid

---

### TC-12: Serializer rejects 4th context

| Field | Value |
|-------|-------|
| Identifier | TC-12 |
| Test Items | `CostModelContextSerializer` (C4) |
| BAC | BAC-2 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: Serializer enforces max 3 contexts per tenant.

**Given**
- 3 contexts already exist: `c1` (default), `c2`, `c3`

**When**
- `CostModelContextSerializer(data={"name": "c4", "display_name": "C4"}).is_valid()`

**Then**
- Returns `False` — 4th context rejected at the serializer level

---

### TC-13: Default context not deletable via serializer/model guard

| Field | Value |
|-------|-------|
| Identifier | TC-13 |
| Test Items | `CostModelContextSerializer` (C4) — delete guard |
| BAC | BAC-4 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: Default context cannot be deleted.

**Given**
- A default context exists: `baker.make("CostModelContext", is_default=True)`

**When**
- `default_ctx.delete()` is called

**Then**
- `ValidationError` or `IntegrityError` is raised

---

### TC-14: CostModelSerializer accepts context UUID

| Field | Value |
|-------|-------|
| Identifier | TC-14 |
| Test Items | `CostModelSerializer` (C5) — context field |
| BAC | BAC-5 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: CostModelSerializer accepts source_uuids + cost_model_context.

**Given**
- A default context exists with known UUID

**When**
- `CostModelSerializer(data={..., "cost_model_context": str(ctx.uuid)}, context=request_context).is_valid(raise_exception=True)`

**Then**
- Returns `True` — context UUID is accepted as valid input

---

### TC-15: CostModelSerializer defaults context when absent

| Field | Value |
|-------|-------|
| Identifier | TC-15 |
| Test Items | `CostModelSerializer` (C5) — default context resolution |
| BAC | BAC-7 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | None |

**Scenario**: Missing cost_model_context defaults to tenant's default.

**Given**
- A default context exists
- Serializer data does not include `cost_model_context` field

**When**
- `CostModelSerializer(data={name, description, source_type, rates, source_uuids}, context=request_context).is_valid(raise_exception=True)`

**Then**
- Returns `True` — validation passes without explicit context

---

### TC-XX: Backward-compatible cost model creation without context

| Field | Value |
|-------|-------|
| Identifier | TC-XX |
| Test Items | `CostModelSerializer` (C5) — backward compatibility |
| BAC | BAC-7 |
| Module | `cost_models/test/test_cost_model_context.py` |
| Dependencies | TC-15 |

**Scenario**: POST/PUT without cost_model_context field succeeds (backward-compat).

**Given**
- A default context exists
- Serializer data has no `cost_model_context` field

**When**
- `serializer.is_valid()` followed by `serializer.save()`

**Then**
- `valid` is `True`
- `instance` is not `None` — cost model created successfully
- The instance is implicitly associated with the default context

---

## Module: `api/common/permissions/test/test_context_permission.py`

### Class: `CostModelContextPermissionTest`

---

### TC-16: Admin user bypasses context check

| Field | Value |
|-------|-------|
| Identifier | TC-16 |
| Test Items | `CostModelContextPermission` (C12) |
| BAC | BAC-28 |
| Module | `api/common/permissions/test/test_context_permission.py` |
| Dependencies | None |
| Special Requirements | `@override_settings(ENHANCED_ORG_ADMIN=True)` |

**Scenario**: Admin user with ENHANCED_ORG_ADMIN bypasses context permission.

**Given**
- `ENHANCED_ORG_ADMIN` setting is `True`
- User mock: `admin=True`, `access={"cost_model": {"read": ["*"], "write": ["*"]}}`
- Request mock: `method="GET"`, `query_params={"cost_model_context": "provider"}`

**When**
- `perm.has_permission(request, None)` is called

**Then**
- Returns `True` — admin bypass grants access

---

### TC-17: Unpermitted user denied

| Field | Value |
|-------|-------|
| Identifier | TC-17 |
| Test Items | `CostModelContextPermission` (C12) |
| BAC | BAC-29 |
| Module | `api/common/permissions/test/test_context_permission.py` |
| Dependencies | None |

**Scenario**: User without cost_model read access is denied when context is requested.

**Given**
- User mock: `access={"cost_model": {"read": [], "write": []}}`
- Request mock: `method="GET"`, `query_params={"cost_model_context": "consumer"}`

**When**
- `perm.has_permission(request, None)` is called

**Then**
- Returns `False` — access denied

---

### TC-18: Permitted user allowed (no context param)

| Field | Value |
|-------|-------|
| Identifier | TC-18 |
| Test Items | `CostModelContextPermission` (C12) |
| BAC | BAC-33 |
| Module | `api/common/permissions/test/test_context_permission.py` |
| Dependencies | None |

**Scenario**: User with cost_model read access passes when no context param is present.

**Given**
- User mock: `access={"cost_model": {"read": ["*"], "write": []}}`
- Request mock: `method="GET"`, `query_params={}` (no `cost_model_context`)

**When**
- `perm.has_permission(request, None)` is called

**Then**
- Returns `True` — pass-through when no context is explicitly requested

---

### TC-19a: Missing customer attribute returns False

| Field | Value |
|-------|-------|
| Identifier | TC-19a |
| Test Items | `CostModelContextPermission` (C12) |
| BAC | BAC-29 |
| Module | `api/common/permissions/test/test_context_permission.py` |
| Dependencies | None |

**Scenario**: User with no customer attribute is denied when context is requested.

**Given**
- User mock: `access=None`, `customer=None`
- Request mock: `method="GET"`, `query_params={"cost_model_context": "consumer"}`

**When**
- `perm.has_permission(request, None)` is called

**Then**
- Returns `False` — no customer means no tenant, no permission

---

### TC-19b: No context param allows access regardless

| Field | Value |
|-------|-------|
| Identifier | TC-19b |
| Test Items | `CostModelContextPermission` (C12) |
| BAC | BAC-33 |
| Module | `api/common/permissions/test/test_context_permission.py` |
| Dependencies | None |

**Scenario**: Without cost_model_context in query params, permission passes regardless of user state.

**Given**
- User mock: `access=None`, `customer=None`
- Request mock: `method="GET"`, `query_params={}` (no `cost_model_context`)

**When**
- `perm.has_permission(request, None)` is called

**Then**
- Returns `True` — permission is a pass-through when context is not requested

---

### TC-20: Empty access dict returns False

| Field | Value |
|-------|-------|
| Identifier | TC-20 |
| Test Items | `CostModelContextPermission` (C12) |
| BAC | BAC-29 |
| Module | `api/common/permissions/test/test_context_permission.py` |
| Dependencies | None |

**Scenario**: User with empty access dict is denied when context is requested.

**Given**
- User mock: `access={}` (empty dict)
- Request mock: `method="GET"`, `query_params={"cost_model_context": "consumer"}`

**When**
- `perm.has_permission(request, None)` is called

**Then**
- Returns `False` — empty access means no permissions

---

### TC-21: Missing cost_model key does not raise KeyError

| Field | Value |
|-------|-------|
| Identifier | TC-21 |
| Test Items | `CostModelContextPermission` (C12) |
| BAC | BAC-29 |
| Module | `api/common/permissions/test/test_context_permission.py` |
| Dependencies | None |

**Scenario**: Access dict without 'cost_model' key returns False gracefully (no KeyError).

**Given**
- User mock: `access={"aws.account": {"read": ["*"]}}` (has access, but not to cost_model)
- Request mock: `method="GET"`, `query_params={"cost_model_context": "consumer"}`

**When**
- `perm.has_permission(request, None)` is called

**Then**
- Returns `False`
- No `KeyError` is raised — the missing key is handled gracefully
