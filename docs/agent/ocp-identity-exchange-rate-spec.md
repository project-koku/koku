# SPEC — OCP identity exchange-rate optimization

- Tier: 3 — monetary report calculation and public API response path.
- Setup plan:
  - Isolation: the `mpovolny/ocp-identity-exchange-rate` worktree, so the
    user's main Koku checkout and its unrelated untracked work remain untouched.
  - Tools to install: none.
  - Git: commit this approved specification before implementation; commit the
    implementation and tests after the final validation run.
  - Files the gauntlet will add: this spec and an evidence report under
    `docs/agent/`; no test harness or dependency is expected.
  - New dependencies: none.

## Scenarios

```gherkin
Feature: OCP report source-currency identity optimization
  Scenario: Enable the cheaper source-rate annotation for an identity conversion
    Given an OCP report request whose target currency is BRL
    And every explicit source-to-cost-model mapping has currency BRL
    And the identity-rate feature flag is enabled for the tenant schema
    When the OCP query handler builds exchange-rate annotations
    Then exchange_rate is a decimal constant 1
    And infra_exchange_rate retains its existing raw-currency expression

  Scenario: Preserve the legacy path while the experiment is disabled
    Given the same identity-conversion request
    And the identity-rate feature flag is disabled
    When the OCP query handler builds exchange-rate annotations
    Then exchange_rate remains the legacy source_uuid CASE expression

  Scenario: Do not remove a required source-currency conversion
    Given an OCP report request whose source mapping includes a currency other
    than the requested currency
    And the identity-rate feature flag is enabled
    When the OCP query handler builds exchange-rate annotations
    Then exchange_rate remains the legacy source_uuid CASE expression

  Scenario: Preserve report values for an identity-conversion tenant
    Given OCP report fixture data with target-currency source mappings
    When the same report is executed with the feature flag disabled and enabled
    Then data and total values are identical
```

## Must NOT

- Do not alter `infra_exchange_rate`, raw-currency conversion, or the existing
  constant-currency flag.
- Do not change the response schema, query parameters, rate semantics, tenant
  context, mappings, migrations, or on-prem defaults.
- Keep the new Unleash enablement flag OFF by default and preserve the legacy
  path until a controlled, schema-sticky production rollout has completed.
- Do not add dependencies or change unrelated providers.

## Failure model and checks

| Failure mode | Check |
| --- | --- |
| A required conversion is replaced with 1 | Flag-on non-identity unit test |
| Flag state is ignored | Separate flag-off and flag-on tests |
| Raw-currency conversion is accidentally changed | Annotation assertion plus response-parity test |
| Monetary output changes for the optimized path | Full response parity test with seeded tenant data |
| New path is enabled unintentionally | Default-off flag constant and mocked flag tests |

## Revisions

- Initial scope: source/cost-model `exchange_rate` only. The raw-currency
  expression remains intentionally out of scope even though the measured Banco
  window had NULL raw currencies.
