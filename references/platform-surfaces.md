# HUF Platform Surfaces Reference

Every platform surface a HUF app can use, how to reach it from each app target, and whether it works today.

- **In-bench** = Target 1: app seeded into a Frappe bench; code runs as the logged-in user (session cookie, CSRF token) and may call whitelisted methods at `/api/method/<dotted.path>`.
- **External** = Target 2: service calling `/huf/api/v1/*` with header `X-Huf-Api-Key: <key>` (not `Authorization`). A key has scopes and acts as its owner; it can only reduce the owner's authority, never exceed it.

Availability tags: **[available]** works today on the released/integration branch (`pre-develop`); **[pending: PR]** implemented in an unmerged PR or branch, so not on a stock site (check the target site); **[experimental/shadow]** built but off by default or unmerged, not safe to depend on; **[planned]** designed or decided, not built.

Facts below were read from code and docs, not all executed. Re-verify against the target site before relying on them.

## 1. Quick matrix

| Surface | In-bench (seed / session / whitelisted) | External (API key) | Notes |
|---|---|---|---|
| Agents: list/get | seed `huf/agents/*.json`; session | `GET /agents`, `agents:read` **[available]** | per-agent access check |
| Agents: run sync | whitelisted chat/run methods **[available]** | `POST /responses` `agents:run` **[available]** (queue-first) | see 2.1 |
| Agents: run stream | SSE / realtime **[available]** | `POST /responses` with `stream=true` **[available]** | |
| Run status/result | whitelisted status method **[available]** | `GET /runs/{id}` (needs `conversations:read`) **[available]** | no `runs:read` scope yet **[planned]** |
| Conversations | session **[available]** | `conversations:read/write` **[available]**, owner-only | |
| Triggers/automations | seed `huf/triggers/*.json` **[available]**; automation API whitelisted | none **[planned]** | |
| Skills | `huf_skills` hook **[available]** | list only, none today **[planned]** | |
| Data tables | `exposed_tables`, `set_table_agent_access` **[available]** | none **[planned]** (`tables:*` planned) | |
| Knowledge | seed `huf/knowledge/*.json`; `knowledge_search` **[available]** | none **[planned]** | |
| Flows | whitelisted `run_flow` etc. **[available]** | none **[planned]** | |
| Memory | agent tools only **[planned]** user-level API | none **[planned]** | |
| MCP | via Skill only | never exposed | not app-seedable |
| Tools | seed `huf/tools/*.json`, `huf_tools` hook **[available]** | n/a | |
| Approvals | whitelisted approve/reject **[available]** | `approvals:decide` **[planned]** | see 2.10 |
| Files / voice / OCR | whitelisted methods (OCR not whitelisted) | scopes exist, no endpoints **[planned]** | dead scopes |
| Artifacts | whitelisted list/get **[available]** | none **[planned]** | |
| Execution profiles | admin config, tool-level **[available]** | not exposed | |
| Gateways | seed target Agent/Flow only; installer creates the Gateway **[available]**; WhatsApp bridge/templates **[pending: tridz-dev/huf PR #806]** | none **[planned]** | see `gateways-and-whatsapp.md`; generic `/gateways` family planned |
| Decisions (JEV) | none **[experimental/shadow]** (unmerged branches only) | none **[planned]** | not safely usable by apps today; see `decision-runtime-jev.md` |

## 2. Surfaces

### 2.1 Agents (sync / stream / queue-first runs)

- **What**: `Agent` records (model, prompt, tools, skills, knowledge) run as conversations.
- **Seed**: `<app>/huf/agents/<id>.json`, keyed on `agent_name`; applied on `after_app_install`. See `templates/target1/agent.json.template`.
- **External**:
```bash
curl -s -H "X-Huf-Api-Key: $HUF_API_KEY" -H "Content-Type: application/json" \
  -d '{"agent_id":"my_agent","input":"hello"}' "$HUF_URL/huf/api/v1/responses"
# -> {"data":{"response_id":"..","conversation_id":"..","status":"queued","output":null},"request_id":..}
curl -s -H "X-Huf-Api-Key: $HUF_API_KEY" "$HUF_URL/huf/api/v1/runs/<response_id>"   # poll
```
- **Gotchas**
  - `POST /responses` is **queue-first**: it returns `status=queued` with `output=null`. Poll `GET /runs/{id}` or use `stream=true` (SSE). A `Prefer: wait=N` long-poll is **[planned]**.
  - Run lookup is guarded by the `conversations:read` scope today.
  - Each call spends LLM budget; there is no per-key budget cap.
  - Agent visibility follows the owner's agent access; a key can also be restricted to selected agents.
  - In-bench apps get no scope limit (session actor), but per-method capability checks still apply.

### 2.2 Triggers and automations

- **What**: Agent Triggers (doc events, cron schedule, webhook) start agent runs unattended.
- **Seed**: `huf/triggers/*.json`, keyed on `trigger_name` (`templates/target1/trigger.json.template`). **[available]**
- **Runtime**: automation CRUD and run-now are whitelisted for in-bench use. External `automations:*` scopes are **[planned]**.
- **Gotchas**: triggers are persistent config; seed them disabled unless the installer opts in. Runs execute as the trigger's configured user, so check that user's permissions.

### 2.3 Skills (`huf_skills` shipping)

- **What**: a `Skill` bundles instructions, tools, prompts, knowledge, and MCP servers; agents attach skills (child table `Agent Skill`).
- **Seed**: not a seed folder. Declare a `huf_skills` hook in `hooks.py`; synced on install and every `after_migrate`. **[available]**
```python
# hooks.py
huf_skills = [{"skill_name": "workspace_ops",
               "function_path": "myapp.skills.workspace_ops.manifest"}]
```
`manifest()` returns the skill definition (name, title, instructions, tools, and so on). Skills are marked `source_type: App Provided`.
- **External**: read-only listing is **[planned]** (`skills:read`). Never expose import-from-git to keys.
- **Gotchas**: a skill has no standalone invoke; it works only through an agent that has it attached. Re-sync on migrate overwrites manual edits to provider-owned skills.

### 2.4 Data tables (`exposed_tables`, `set_table_agent_access`)

- **What**: user-defined tables (`Huf Data Table`) backed by Frappe DocTypes, with scaffolded agent tools.
- **Manifest**: `"exposed_tables": ["My DocType"]` on the HUF App record declares which tables the app uses.
- **Provisioning**: no seed folder (API only). Create tables via the data table API in `after_install`, then grant the seeded agent access:
```
POST /api/method/huf.huf.doctype.huf_data_table.api.set_table_agent_access
     table=<name> agent=<Agent> actions=["view","create"]
```
This is declarative: it attaches the missing scaffolded tools and detaches tools for actions no longer listed. It needs the `data.tables.manage` capability.
- **Records**: `get_table_records`, `create`, `get_table_schema` are whitelisted and guarded by `data.records.*` capabilities **[available]** in-bench.
- **External**: `tables:read/write/schema` with a per-table grant list is **[planned]**.
- **Gotchas**: `fields` and `filters` strings pass into `frappe.get_list`, so validate input in your app. Seeding the scaffolded tool names into the agent's `tools` list is the alternative to calling `set_table_agent_access`.

### 2.5 Knowledge sources

- **What**: indexed sources (SQLite FTS or vector) agents retrieve from.
- **Seed**: `huf/knowledge/*.json`, keyed on `source_name`. `storage_mode: "SQLite (FTS)"` maps to Frappe File plus `sqlite_fts`; with no `knowledge_type` it defaults to `sqlite_fts`. **[available]**
- **Runtime**: `huf.ai.knowledge.retriever.knowledge_search` is whitelisted (needs `knowledge.use`). **[available]** in-bench; `knowledge:*` for keys **[planned]**.
- **Gotchas**: ship only distributable content. Ingest is a prompt-injection surface, so treat retrieved text as untrusted.

### 2.6 Flows

- **What**: visual multi-step workflows (agents, tools, conditions, human steps).
- **Runtime**: whitelisted `run_flow`, `get_flow_run`, `list_flow_runs`, `resume`, `approve`, `reject`, webhook entry (needs `flows.use`). **[available]** in-bench.
- **Seed**: flows are not an app seed type today. **[planned]**
- **External**: `flows:run/read` **[planned]**.
- **Gotchas**: flows can invoke tools and agents, so a flow run can spend money and write data.

### 2.7 Memory

- **What**: durable per-agent, per-contact memory records (save, search, archive, promote).
- **Use**: enable on the agent (`enable_memory`, `memory_policy`; see `templates/target1/AGENT_CONFIG_REFERENCE.md`). **[available]** agent-side.
- **Direct app access**: the functions are agent tools bound to conversation context. A user-facing service layer and `memory:*` scopes are **[planned]**.
- **Gotchas**: memory holds PII; scope isolation depends on `scope_type`.

### 2.8 MCP

- **What**: external tool servers (including OAuth ones) attached to agents.
- **Use**: **not app-seedable.** Attach an `MCP Server` to a `Skill` (`Skill MCP Server`) and ship the skill via `huf_skills`. The installer must still create the server record and credentials.
- **External**: never exposed (tokens). Management needs `system.mcp.manage`.

### 2.9 Tools

- **What**: `Agent Tool Function` records agents can call (doc ops, HTTP, custom functions, run agent, client-side).
- **Seed**: `huf/tools/*.json`, keyed on `tool_name`. Unknown `types` become `App Provided`; a missing `tool_type` is created. **[available]**
- **Discovered**: `huf_tools` hook with `function_path` for Python functions. **[available]**
```python
huf_tools = [{"tool_name": "myapp_sync_project", "function_path": "myapp.tools.sync_project", "category": "Workspace"}]
```
- **Gotchas**: set `reference_doctype` and `required_permission` on doc tools. Do not guess ERPNext/CRM fieldnames; read the real meta.

### 2.10 Approvals and ask-user

- **What**: human-in-the-loop primitives. The built-in `ask_user` tool pauses a run for user input. Execution approval (`approve_execution`, `reject_execution`) gates tool calls and sandboxed code. Flows have approve/reject steps.
- **In-bench**: whitelisted approve/reject methods, gated by `execution.approve` and similar capabilities. **[available]**
- **External**: Planned: keys MAY approve through an `approvals:decide` scope, with `approvals:read` to list pending items. **[planned]**
  - Expected shape: `GET /approvals`, `POST /approvals/{id}/approve|reject`.
  - Not grantable by default; prefer allow-listing specific agents. Mint-time check should require the creator to hold the backing capability.
- **Gotchas**: until it ships, an external app cannot resume a paused run; surface the pause to a human in HUF.

### 2.11 Files, voice, OCR

- **Scopes**: `files:read`, `files:write`, `voice:use`, `ocr:use` can be granted to keys but **enforce nothing**; no v1 endpoints exist. **[planned]** (endpoints **[planned]**: `POST /files`, `/audio/transcriptions`, `/ocr/extractions`).
- **In-bench**: upload and transcribe methods are whitelisted. **[available]** OCR extraction is async and not whitelisted. **[planned]**
- **Agent-side**: STT/TTS, vision, and image generation are `Agent` fields (see the agent config reference).
- **Gotchas**: do not tell users a key can do file/voice/OCR work today. Files are private by default.

### 2.12 Artifacts

- **What**: generated documents attached to a conversation.
- **Use**: whitelisted `list_conversation_artifacts`, `get_artifact`, plus export. **[available]** in-bench. `artifacts:read` for keys **[planned]**.

### 2.13 Execution profiles

- **What**: `Execution Profile` sets sandbox limits (wall time, CPU, memory, output), `approval_mode` (`Auto Approve`, `Ask Every Time`, `Never Allow`), filesystem policy, allowed modules, and an optional `Network Access Policy`. Admin-configured; apps do not seed them.
- **Gotcha**: `Ask Every Time` creates approvals (2.10). Code-execution tools do not work without a suitable profile.

### 2.14 Gateways (WhatsApp and others)

- **What**: `Gateway` records bind external channels to agents. Secrets live in Password fields.
- **In-bench**: Gateway, Binding and routing are **[available]**; apps never seed Gateways or credentials. WhatsApp bridge, templates and the management/send methods are **[pending: tridz-dev/huf PR #806]**; template mutation there requires System Manager or Huf Admin. See `gateways-and-whatsapp.md`.
- **External**: generic `/gateways/*` resources with capability-driven sub-routes. **[planned]**
- **Gotchas**: WhatsApp has a 24 hour service window, so free-form sends need a template outside it. Never return gateway credentials to the client.

### 2.15 Decisions (JEV)

- The runtime is a library plus schema only; the public entry (`run_decision`) exists on unmerged branches **[experimental/shadow]** and `decisions:run`/`decisions:read` scopes are **[planned]**. Apps should not depend on it today; see `decision-runtime-jev.md`.

## 3. Permissions and capability model

- **Capabilities** are strings in `huf.permissions.CAPABILITIES` (for example `agent.use`, `data.tables.manage`, `data.records.*`, `knowledge.use`, `flows.use`, `execution.approve`, `system.mcp.manage`, `developer.keys.manage`). They are checked per method, alongside Frappe doctype permissions.
- **Effective authority** = owner capabilities AND key scopes AND key restrictions. A request runs after `frappe.set_user(key.owner)`.
- **API key scopes today (8)**: `agents:read`, `agents:run`, `conversations:read`, `conversations:write`, `files:read`, `files:write`, `voice:use`, `ocr:use`. The last four are reserved: no endpoints enforce them yet.
- **Restrictions**: agents only (`mode all|selected`). None for gateways, tables, flows, or knowledge.
- **Error envelope**: `{data, request_id, meta}` on success, `{error:{code,message,request_id}}` on failure (400/401/403/404/409/500). Offset pagination on list routes; no 429 or `Retry-After`, no idempotency key. Full detail in `api-v1.md`.
- A key cannot mint keys.
- Do not call `frappe.session.user` helpers in code reached by key auth; the ambient user may be Guest outside the router's `set_user`.

## 4. App manifest (`huf/apps/<app_id>.json`)

Template: `templates/target1/manifest.json.template`. Allowed fields: `manifest_version, app_id, title, route, description, version, icon, category, launch_mode, required_huf_version, permission_method, sort_order, enabled, exposed_tables, alias, is_public, agent, www_template, delivery`.

| Field | Behavior |
|---|---|
| `launch_mode` | only `route` is accepted today |
| `route` | in-app SPA route the tile opens |
| `permission_method` | dotted path to a function that returns bool; hides the tile for users it denies. If unset, visibility needs `agent.use`. Controls the tile only, **not** authority. |
| `exposed_tables` | DocTypes the app declares it uses (see 2.4) |
| `required_huf_version` | recorded only, not enforced |
| `required_capabilities`, `required_scopes`, `required_gateway_kinds` | do not exist **[planned]**; unknown fields are not honored |

- **First-party apps** are not manifests: install code seeds their `HUF App` records directly.
- Apps are visible only when sync status is Active and the app is enabled. System Manager and Administrator see all.
- SPA routes are hard-coded in the frontend. A manifest adds a launcher tile; it cannot add a page by itself. A route-launched app is therefore an external deep link or a route the host frontend already serves.

## 5. Delivery methods

| Method | Status | Notes |
|---|---|---|
| SPA tile (route-launched) | **[available]** | default and recommended |
| Portal page | **[available]** with gaps | no per-app `www/` template registry. The manifest accepts `alias`, `is_public`, `agent`, `www_template` and `delivery`, but per-app `www/` template registration still needs manual setup |
| Desk page | unsupported | the page.js pattern does not exist; do not offer |

## 6. Install-time seeding order

1. Seed folders on `after_app_install`: prompts, tools, knowledge, agents, triggers, apps.
2. Hooks: `huf_skills` (also re-synced on `after_migrate`), `huf_tools`.
3. Data tables via API in `after_install`, then `set_table_agent_access` for the seeded agent.
4. Things the installer must do by hand: MCP servers and credentials, gateways, execution profiles, provider keys, and any capability grants to roles.
