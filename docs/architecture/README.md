# Architecture documentation

This directory holds **long-lived architecture documentation** for the Koku backend and related pipelines. It complements code and tests: explain *why* and *how systems connect*, and **link into the codebase** for *what exactly* the implementation does.

---

## What lives here

| Style | Purpose | Examples |
|-------|---------|----------|
| **Reference docs** | Stable maps of subsystems, tasks, and processing paths. Update when behavior or entry points change. | [`sources-and-data-ingestion.md`](sources-and-data-ingestion.md), [`celery-tasks.md`](celery-tasks.md), [`cost-models.md`](cost-models.md), provider CSV docs |
| **Feature design hubs** | PRD-driven technical design for a specific initiative: decisions, phased delivery, risks, and deep dives split across multiple files. | [`data-retention/`](data-retention/README.md), [`cost-breakdown/`](cost-breakdown/README.md) |
| **Feature narrative** | Single large doc when a folder split is not needed yet. | [`mig-gpu-support.md`](mig-gpu-support.md) |

**Convention:** Large features usually get a subdirectory with a `README.md` hub plus focused documents (data model, API, pipeline, phased delivery, risk register). Smaller or cross-cutting topics can stay as one top-level `.md` file.

---

## How to turn a PRD into architecture docs (with Cursor)

Use this flow when product gives you a PRD (or equivalent: epic, RFC, Google Doc, Jira description) and you want engineering-ready design material in this repo.

### 1. Gather inputs

- **PRD or feature brief** — goals, user stories, acceptance criteria, explicit out-of-scope items.
- **Tracking links** — Jira epic/story, PRD id or URL (even if internal).
- **Constraints** — on-prem vs SaaS, timeline, compliance, performance budgets.

### 2. Ground the design in the codebase (non-negotiable)

Before writing “how we will build it,” trace **today’s behavior** in `koku/`:

- Find the orchestration path (Celery tasks, views, Kafka handlers).
- Note **tenant vs public** data: tenant models live under `reporting/` and `cost_models/` and require `schema_context` / `tenant_context` (see `.cursor/rules/multi-tenancy.mdc` and `AGENTS.md`).
- If the feature touches SQL templates, check **dual paths**: `masu/database/sql/`, `masu/database/trino_sql/`, and `masu/database/self_hosted_sql/` (on-prem mirrors Trino where applicable).

Architecture docs should **cite real modules, tasks, and tables** discovered in this step—not only the PRD’s assumptions.

### 3. Choose shape: new folder vs update existing

- **New subdirectory** under `docs/architecture/<feature-slug>/` when the PRD implies multiple workstreams (schema, API, pipeline, rollout) or long-lived review material (IQ/OQ tables, risk register).
- **Update an existing reference doc** when the PRD only extends a documented subsystem (for example, a new Celery task belongs in [`celery-tasks.md`](celery-tasks.md)).
- **Single new `.md` at this level** only if the design is cohesive and unlikely to sprawl past ~400–500 lines; split early if you add heavy SQL/API sections.

### 4. Write the hub `README.md` first

Mirror the proven pattern in [`data-retention/README.md`](data-retention/README.md) and [`cost-breakdown/README.md`](cost-breakdown/README.md):

1. **Title and one-paragraph summary** — what changes for operators and developers.
2. **Links** — PRD reference, Jira epic, prerequisite reading (existing architecture docs).
3. **Open questions / decisions** — table with ids (e.g. `IQ-1`), status, owner, short proposal. Resolve over time; keep history honest.
4. **Document catalog** — table of sibling `.md` files with role (DD, reference, risk) and **reading order**.
5. **Diagrams** — one or two high-level diagrams (Mermaid is fine): current vs proposed, or request/queue/datastore flow.
6. **Key design decisions** — short table: decision, rationale, link to detail section or file.
7. **Changelog** — version rows (date + summary) so reviewers see doc evolution.

**Hub depth (pick a tier; do not copy cost-breakdown wholesale for small features):**

| Element | Lean hub (single `README`, mostly API/ORM) | Standard hub (+1–2 siblings) | Full hub (multi-phase, SQL, high risk) |
|---------|-------------------------------------------|------------------------------|----------------------------------------|
| **Tracking** — Jira epic, PRD URL | Fill in when known (placeholders until then) | Same | Same; add related epics if split delivery |
| **Prerequisite reading** | 1–2 links | 2–4 links | As needed |
| **Current vs proposed** — Mermaid or prose | One diagram or “already implemented” section | Current + proposed if behavior changes | Two diagrams (today vs target) like [cost-breakdown](./cost-breakdown/README.md#architecture-at-a-glance) |
| **Implementation inventory** — code links, formulas, guards | **Required** | **Required** | **Required** + SQL file inventory in a sibling doc |
| **IQ / decision table** | Short table (owner, status, notes) | Same; link to anchored sections when answers get long | Wide table: blocking phase, PoC artifact, link to detail § |
| **OQ / resolved write-ups** | Optional; fold into IQ when few items | Brief “resolved” subsection | Dedicated **Open Questions** + long **Implementation questions** sections |
| **PoC / spikes** | Omit unless spiking | `poc/` + one table of artifacts | Spikes table + residual risks + [risk-register.md](./cost-breakdown/risk-register.md)-style file if R1+ tracking is useful |
| **Quick start + reading order** | Optional one-liner (“Implementers: § Current implementation”) | **Reading order** for roles | **Quick start** table + **Reading order** for backend vs frontend |
| **Document catalog** | Single row OK (“this README only”) | Catalog sibling files + role | Full catalog (DD vs Ref) |
| **Gaps / backlog vs PRD** | Recommended for agent-led work | Same | Same; tie to phased delivery |
| **Phased delivery + rollback** | Omit if one PR | Short bullets or `phased-delivery.md` | Dedicated doc + validation per phase |
| **Key design decisions** | Short table | Same | Same + “resolution” column when decided |

Example lean hub: [`efficiency-scores/README.md`](efficiency-scores/README.md) (inventory, formulas, IQ table, gaps — no PoC, no multi-doc catalog yet).
Example full hub: [`cost-breakdown/README.md`](cost-breakdown/README.md).

### 5. Split detail by concern

Typical filenames (pick what applies):

| File | Contents |
|------|------------|
| `data-model.md` | Models, migrations, partitioning, retention, indexes |
| `api.md` | Endpoints, serializers, permissions, validation, error cases |
| `*-pipeline.md` | Ingestion, summarization, SQL file inventory, accessor changes |
| `phased-delivery.md` | Phases, validation per phase, rollback, flags, operational checklist |
| `risk-register.md` | Risks, mitigations, severity (optional if small) |

Use a `poc/` subfolder only for **spike artifacts** (SQL sketches, scripts) that inform decisions—not for production code.

### 6. Maintenance rule

Per `.cursorrules`: **link to code instead of pasting large blocks** that will drift. When implementation merges, update or add links to the canonical files. If a workflow documented here changes (tasks, serializers, Kafka, cost model SQL), update the relevant architecture doc in the same PR when practical.

---

## Instructions for AI agents (Cursor, PRD → design)

Use this section as **system or user context** when asking an agent to draft or revise architecture docs from a PRD.

### Cursor slash command: Architecture Architect

For a **dedicated architect workflow** (analyze PRD, map codebase, draft API/system design, **no implementation**—output is documentation for a builder agent), use the repo command:

- **Invoke:** In Cursor chat, type `/` and choose **`architect`**, then paste or attach the PRD and supply the feature slug, epic key, and hub depth (lean / standard / full).
- **Definition:** [`.cursor/commands/architect.md`](../../.cursor/commands/architect.md) — boundaries, prime context, workflow, and required **Builder handoff** output.
- **Also documented:** [`.cursor/commands/README.md`](../../.cursor/commands/README.md) (command index).

The command follows the same principles as the subsections below; it is a single entry point for teams that want a repeatable **PRD → `docs/architecture/<feature-slug>/`** pass.

### Prime context (attach or `@` mention)

- `AGENTS.md` — repo layout, multi-tenancy, dual SQL paths, testing commands.
- `.cursor/rules/multi-tenancy.mdc` and `.cursor/rules/onprem-vs-saas.mdc` — schema and deployment constraints.
- Relevant **existing** files under `docs/architecture/` so the agent matches tone and structure.

### Agent workflow

1. **Restate scope** from the PRD in your own words; list in-scope and out-of-scope bullets.
2. **Inventory current state** by searching and reading code (tasks, accessors, models, SQL callers). Do not invent filenames or task names.
3. **Identify touch points**: Django apps, Celery queues, Kafka topics, SQL directories, API routes, UI contract if specified.
4. **Produce or update** the hub `README.md` plus focused docs following the templates above.
5. **Surface decisions** as numbered questions with options and a recommended default; mark what only a human tech lead can approve.
6. **Risks and blast radius** — data migrations, backfill, ordering with existing jobs, multi-tenant migration patterns.
7. **Linking** — use relative links from the doc you are editing. For code, prefer stable anchors:

   ```markdown
   [update_summary_tables](../../koku/masu/processor/tasks.py#L1-L40)
   ```

   Path from `docs/architecture/` goes up twice to repo root, then into `koku/…`.

8. **Avoid** — pasting huge SQL or Python into docs; duplicating serializer fields line-by-line; stating “Trino does X” without checking `settings.ONPREM` implications.

### Suggested prompt template (paste into Cursor)

```text
You are documenting a Koku feature for docs/architecture/<feature-slug>/.

Inputs:
- PRD: <paste or link>
- Epic: <JIRA-KEY>

Requirements:
1. Follow docs/architecture/README.md “Instructions for AI agents”.
2. Ground every technical claim in code search; cite files with relative links from docs/architecture/.
3. Create README.md hub + split docs as needed; include mermaid for current vs proposed flow.
4. Explicitly cover multi-tenancy (public vs tenant schema) and ONPREM vs SaaS SQL paths if relevant.
5. List open questions (IQ-*), risks, and phased delivery with validation criteria per phase.

Output: proposed new/changed markdown files only (no application code unless asked).
```

### Quality checklist before opening a PR

- [ ] Hub depth matches feature size (see **Hub depth** table under step 4 — lean vs standard vs full).
- [ ] Hub page lists **document catalog** and **reading order** (reading order may be one sentence if the hub is a single file).
- [ ] PRD requirements trace to **concrete code or schema** touch points.
- [ ] Tenant vs public models are correct; no “query tenant table without context” patterns proposed.
- [ ] SQL changes note **sql/ vs trino_sql/ vs self_hosted_sql/** as appropriate.
- [ ] Celery/task additions or changes cross-check [`celery-tasks.md`](celery-tasks.md) for update.
- [ ] Large code blocks avoided; **links** to implementation instead.
- [ ] Changelog entry on the hub (and subdocs if they carry independent versions).

---

## Catalog (existing documents)

### Reference and subsystem maps

| Document | Summary |
|----------|---------|
| [`sources-and-data-ingestion.md`](sources-and-data-ingestion.md) | Platform Sources, Kafka listener, provider creation, ingestion triggers |
| [`celery-tasks.md`](celery-tasks.md) | Task inventory, queues, workflows, Beat schedules |
| [`cost-models.md`](cost-models.md) | Cost model JSON, metrics, distribution, OCP updater and SQL stages |
| [`api-serializers-provider-maps.md`](api-serializers-provider-maps.md) | Report API patterns, provider maps, query handlers |
| [`api-settings-endpoints.md`](api-settings-endpoints.md) | Settings-related API surface |
| [`csv-processing-aws.md`](csv-processing-aws.md) | AWS CUR processing architecture |
| [`csv-processing-azure.md`](csv-processing-azure.md) | Azure cost export processing |
| [`csv-processing-gcp.md`](csv-processing-gcp.md) | GCP billing export processing |
| [`csv-processing-ocp.md`](csv-processing-ocp.md) | OpenShift report processing |

### Feature hubs (subdirectories)

| Directory | Summary |
|-----------|---------|
| [`data-retention/`](data-retention/README.md) | Configurable retention (tenant settings, API, purge pipeline, phased delivery) |
| [`cost-breakdown/`](cost-breakdown/README.md) | OCP cost breakdown / price list technical design and PoC artifacts |
| [`efficiency-scores/`](efficiency-scores/README.md) | OCP CPU/memory usage efficiency, wasted cost, Optimizations Summary tab alignment |

### Standalone feature architecture

| Document | Summary |
|----------|---------|
| [`mig-gpu-support.md`](mig-gpu-support.md) | MIG GPU cost tracking, allocation, distribution, API, testing |

---

## Related project rules

- **Architecture doc policy** (link vs duplicate, when to update): `.cursorrules` section “Architecture Documentation.”
- **Multi-tenancy** and **on-prem vs SaaS**: `.cursor/rules/multi-tenancy.mdc`, `.cursor/rules/onprem-vs-saas.mdc`.

If you add a major new workflow or task, update [`celery-tasks.md`](celery-tasks.md) or the relevant CSV/architecture doc in the same change set when that remains the canonical map.
