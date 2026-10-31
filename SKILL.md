---
name: huf-app-builder
description: Use when the user wants to build a new app/agent on the HUF platform — either a HUF App seeded inside a Frappe bench (desk/portal delivery) or an external service that calls HUF over the /huf/api/v1/* REST API with a developer API key. Triggers on requests like "build a HUF app", "create an agent app for HUF", "scaffold a HUF integration", "make an app that talks to HUF API".
---

# HUF App Builder Skill

## Overview

This skill guides building one of two HUF app architectures:

1. **Target 1 (Launched from HUF)**: A HUF App seeded inside a Frappe bench, with an Agent, Agent Prompt, Knowledge Sources, and Tools. Delivered via SPA deep-link tile (default, works today) or portal page (has gaps).
2. **Target 2 (Calls HUF API)**: An external service (web app, CLI, chatbot, etc.) that makes REST calls to `/huf/api/v1/*` with a developer API key.

The flow is always the same: **Discover → Plan → Execute → Verify**.

---

## Step 1: Discover

Ask the user the following questions. Use bench detection only to pre-fill a suggested answer; never skip the question.

1. **What is this app about?** — What problem does it solve? Who will use it?
2. **UI requirements** — Does this app need its own user interface, or is it agent-only (background worker, API service)?
3. **Launch model** — This is the fork question: **"Does this app need to be *launched from* HUF, or does it just need to *call* HUF?"**
   - *Launched from HUF* → seeded inside the bench, appears as a tile or page in HUF, Agent runs inside HUF (Target 1)
   - *Calls HUF* → external service, runs somewhere else, calls HUF's API as a client (Target 2)
4. **Audience** — **"Is this for your own use (personal/internal), or are you building it to ship as an app for other people to install?"**
   - *Personal/internal* → single tenant, one team/site. The system prompt and knowledge sources can be specific and even reference this user's own data, docs, or workflow. No need to generalize.
   - *Shipping to others* → the app will be installed on sites you don't control. The system prompt must read as instructions for a generic install, not "you, the builder." Knowledge sources must be either generic reference material the user actually supplies (and confirms is safe to distribute), or no seeded knowledge at all, with instructions for each installer to add their own — never the builder's own private docs, credentials, or site-specific data, and never generic-sounding content you wrote yourself.
   This answer changes how Step 2 drafts the prompt and the knowledge plan.
5. **Knowledge sources** — If the agent needs grounding (FAQs, product docs, a wiki, past tickets, a schema, etc.), ask what the source material actually is: files the user has locally, URLs, existing Frappe DocTypes/Data Tables, or "none yet." Don't invent knowledge content — either the user supplies real source material to seed, or the app ships with no seeded knowledge and a note that the installer adds their own.
6. **Capabilities (Target 1 only)** — Ask, as one bundled question, which of these the agent needs: **vision/document upload, image generation, voice (STT/TTS), custom context/summarization strategy, reasoning control, prompt caching, memory, or code execution/SSH tools.** Don't assume "just a chat prompt" — these are real, common Agent fields (see `templates/target1/AGENT_CONFIG_REFERENCE.md`), not add-ons. Skip any group the user doesn't need; every field in that reference defaults to off/unset if you never touch it.
7. **Other installed apps (Target 1 only)** — Ask: **"Does this agent need to read or write data in another installed app — CRM, ERPNext, HR, etc.?"** If yes, run App & DocType Discovery (below) before planning tools, rather than guessing DocType/field names from general Frappe/ERPNext knowledge.

8. **Which HUF capabilities does the app use?** — Ask as one bundled question: **gateways/messaging channel, decision runtime (JEV), skills, data tables, knowledge, flows, approvals, external API.** For each "yes", read the matching reference before planning and respect its availability tags:
   - gateways / WhatsApp / Telegram / Slack / Email → `references/gateways-and-whatsapp.md`
   - decision runtime (JEV) → `references/decision-runtime-jev.md`
   - skills, data tables, knowledge, flows, approvals, memory, MCP, artifacts → `references/platform-surfaces.md`
   - external API (Target 2) → `references/api-v1.md` (endpoints and scopes that exist today; the Target 2 plan steps stay in this file's Target 2 section)

   Ask each reference's own "decision questions" only for the capabilities the user said yes to.
9. **Flows, voice and media depth (Target 1 only)** — Ask: **"Should the agent talk to people on a messaging channel (WhatsApp), do any steps need to be deterministic (keyword routing, canned replies, no LLM), and does it handle voice/audio/images/documents?"** If yes to any, read the matching reference in "Reference Templates" below (WhatsApp operations -> `references/whatsapp-gateway.md`, after `references/gateways-and-whatsapp.md`; outside the 24h window -> `references/whatsapp-templates.md`; non-LLM and building, testing and publishing any flow -> `references/flows-authoring.md` (`references/flows.md` is pre-develop only; do not use it on builds that have `huf/ai/flow/`); voice/media -> `references/audio-and-media.md`; worked builds -> `references/end-to-end-recipes.md`).

10. **Users, keys and spend (Target 1 only)** — Ask as one bundled question: **"Which roles will use this app, who enters the provider keys (the site owner, in the UI), and what spend limit should it run under?"** The answers go into the plan and the app README as owner decisions; you do not act on them yourself. Read `references/users-roles-permissions.md`, `references/usage-and-limits.md` and (if the agent needs grounding) `references/knowledge-and-skills.md` before planning.

### Availability tags

Every capability in `references/` carries a tag. **[available]** works today on the released branch; **[pending: PR]** exists only in an unmerged PR/branch (e.g. the WhatsApp bridge, `tridz-dev/huf` PR #806); **[experimental/shadow]** built but off by default or unmerged; **[planned]** designed, not built.

- Never plan on a **[planned]**, **[pending]** or **[experimental]** capability without telling the user, and offer the supported alternative the reference gives (e.g. a normal Agent with structured output instead of JEV).
- Never seed gateways, `Integration Settings`, credentials, secrets, sender ids or phone numbers. The app ships the target Agent/Flow; the installer creates and enables the Gateway.

If the user is working in a Frappe bench directory, suggest "This looks like you have a bench. Are you seeding this app inside it?" — but still ask; never assume.

### App & DocType Discovery (only if Q7 = yes)

1. **List installed apps** — `bench --site <site> list-apps` (or, no bench access: ask the user which apps are installed).
2. **List an app's DocTypes** — Its modules: `bench --site <site> execute frappe.get_all --kwargs '{"doctype": "Module Def", "filters": {"app_name": "<app>"}, "pluck": "name"}'`; then its DocTypes: same call with `{"doctype": "DocType", "filters": {"module": ["in", [<those modules>]]}, "pluck": "name"}` (or `GET /api/method/frappe.client.get_list`). Ask the user which specific DocTypes matter (e.g. CRM → `CRM Lead`, `CRM Deal`; ERPNext → `Sales Invoice`, `Customer`, `Item`) rather than enumerating everything.
3. **Get real field names** — Before seeding any tool referencing a DocType, check its meta (`GET /api/resource/DocType/<name>` or `frappe.get_meta("<name>")`) for actual fieldnames. Do not guess ERPNext/CRM field names from general knowledge — schemas vary by version and customization.
4. **No live bench/site reachable** — Don't guess. Ask the user to name the exact app, DocType(s), and fields to target.

---

## Step 2: Plan

### Target 1 (Launched from HUF)

Present the plan explicitly and wait for go-ahead before executing.

**DocTypes to seed:**
- Agent — the main agent record
- Agent Prompt — system prompt and conversation instructions
- Agent Tool Function — any custom tools the agent needs, including one per DocType operation confirmed in App & DocType Discovery (real `reference_doctype`, a `types` value like `Get List`/`Create Document`/`Update Document`, and `required_permission`)
- Knowledge Source — documents, FAQs, or data the agent will reference
- Agent Trigger — optional; how the agent is invoked (manual, scheduled, webhook, etc.)

**Agent capabilities:** List only the non-default fields Step 1's capability answer requires (e.g. `stt_model`+`tts_model` for voice, `image_generation_model` for image gen, `enable_memory`+`memory_policy` for memory). Look them up in `templates/target1/AGENT_CONFIG_REFERENCE.md` — a single indexed table of every relevant `Agent` field, grouped by capability, with type/default/purpose. Do not set fields the plan doesn't call for.

**Messaging, flows and media (only if Step 1 Q8 or Q9 = yes)** — add these rows to the plan; none of them is seedable:
- Gateway (+ WhatsApp Account, credentials entered by the user) — `references/whatsapp-gateway.md`
- WhatsApp templates (Meta approval needed outside the 24h window) — `references/whatsapp-templates.md`
- Flow Definition(s) for deterministic routing — `references/flows-authoring.md`, shape in `templates/target1/flow_definition.json.template`
- Models and provider keys for STT/TTS/image (`stt_model`, `tts_model`, `image_generation_model`, voice reply mode) — `references/models-and-keys.md`, `references/audio-and-media.md`

**Model & Provider selection:**
- Call the live endpoints to list available AI Providers and AI Models from the user's site (see Model & Provider Suggestion section below).
- Present a pick-list of what's actually configured on their instance, rather than blind recommendations.
- Do not assume or hardcode defaults that may not exist.

**System prompt & knowledge sources — draft the real content, not an outline:**
- Write the actual system prompt text (Agent + Agent Prompt content) the seed file will ship with — full instructions, tone, constraints, what the agent should and shouldn't do — based on Step 1's answers. The user refines it, but hand them a finished draft, not a placeholder like "add your instructions here."
- Wording depends on the audience answer from Step 1:
  - *Personal/internal* → can reference the user's own team, tools, or workflow by name.
  - *Shipping to others* → must read as generic install instructions ("you are an assistant for this workspace's support tickets"), no references to the builder's own org, people, or private systems.
- For knowledge sources: if the user supplied real source material (files/URLs/DocTypes) in Step 1, plan exactly which Knowledge Source records to seed and what each should point at or contain. If they said "none yet," plan the app with no knowledge seed file at all and a clear note for whoever installs it to add their own — do not fabricate placeholder facts as if they were real knowledge content.
- *Shipping to others*: only seed knowledge content that is safe to distribute (generic docs, public reference material, or nothing). Never seed the builder's private/internal documents into an app meant to be installed elsewhere.

**Delivery method — pick one:**
- **SPA deep-link tile (default, recommended)** — The app appears as a tile in HUF's dashboard; clicking it opens the agent in a chat interface. Works today. No gaps. Facts to respect (see `references/platform-surfaces.md` section 4): only `launch_mode: route` is accepted; SPA routes are hard-coded in the host frontend, so a manifest adds a tile but cannot add a page; `permission_method` hides the tile for users it denies but is not an authority check; first-party HUF apps are not manifests (install code seeds their `HUF App` records), so do not model a third-party app on them.
- **Portal page** — The app appears as a page in the HUF portal. Flag two known gaps:
  - Missing per-app `www/` template registry — requires manual setup or a workaround.
  - The manifest accepts `alias`, `is_public`, `agent`, `www_template` and `delivery` (see `ALLOWED_FIELDS`), so put the guest-access and portal values in the manifest. Per-app `www/` template registration still needs manual setup. Emit that step, with the exact values, as a hand-off note.
- **Desk page** — NOT currently supported. The page.js pattern does not exist. Do not offer this without flagging it as unsupported.

If the user chooses **Portal page** or **Desk page**, this skill's HUF-specific plan only decides
*that* delivery — it does not teach the Frappe implementation. Before writing any Frappe code for
that path (portal page templates and routing, or the desk `page.js` pattern once it exists), ask the
user whether their project has its own Frappe framework reference docs to load; this skill does not
ship one. If not, work from the official Frappe framework documentation instead of guessing at
portal/desk API shapes.

**Show the plan and get explicit go-ahead before proceeding to Step 3.**

### Target 2 (Calls HUF API)

Present the plan explicitly and wait for go-ahead before executing.

**API scopes the app needs** (full table and routes in `references/api-v1.md`). Enforced today:
- `agents:read` — `GET /agents`, `GET /agents/{id}`
- `agents:run` — `POST /responses` (queue-first; poll `GET /runs/{id}`, or `stream: true` for Run Immediately agents)
- `conversations:read` — conversations, messages, and `GET /runs/{id}`
- `conversations:write` — `POST /conversations`

Reserved (can be minted, but **no endpoints enforce or serve them yet**): `files:read`, `files:write`, `voice:use`, `ocr:use`. Do not plan a Target 2 app around file, voice or OCR calls; say so and offer an in-HUF (Target 1) agent that handles them. Everything else (gateway routes, tables, skills, knowledge, flows, decisions, approvals, events, new scopes) is **[planned]** — not callable.

List only the scopes the app actually needs. Approvals: `approvals:decide` for keys is **[planned]**; an external app cannot resume a paused run today.

**Auth facts:** send `X-Huf-Api-Key` (never `Authorization: Bearer`). Key auth is implemented; a key acts as its owner and can only reduce, never extend, the owner's authority. An invalid key is not rejected on its own: it falls through to session auth and returns `401` if there is no session.

**API key scope restriction:**
- Ask: "Should this key be restricted to a specific agent, or should it work with all agents the key holder can access?"
- Agent-restricted keys are narrower and safer for production.

**Client code outline:**
- Sketch which real endpoints the app will call, from `references/api-v1.md` (e.g. `POST /huf/api/v1/responses` with `agent_id` and `input`, then `GET /huf/api/v1/runs/{response_id}`; `POST /huf/api/v1/conversations`). Do not invent routes.
- Note the technology stack; `templates/target2/client.py` is the reference implementation.

**Show the plan and get explicit go-ahead before proceeding to Step 3.**

---

## Step 3: Execute — Target 1

### Pre-flight checks

Before writing any files:

1. **Seed directory location** — The seed directory MUST be placed at `apps/<myapp>/<myapp>/huf/`. This is the location `find_seed_dirs()` expects. Never create subdirectories under `prompts/`, `tools/`, `agents/`, etc. Scanning is flat and non-recursive; nested files are silently ignored with no error.

2. **Check app_id uniqueness** — Call `huf.ai.apps_api.get_huf_apps()` with the chosen `app_id` to verify it is not already in use. Note: app_id is globally unique across provider apps. A collision does NOT fail loudly; it just leaves a note in the existing app's `sync_error` and the new manifest is dropped. Warn the user if a collision is detected and ask them to choose a different app_id.

### Scaffold files

1. **App manifest** — Create `apps/<myapp>/<myapp>/huf/apps/<app_id>.json` using
   `templates/target1/manifest.json.template` (fields: `manifest_version`, `app_id`, `title`,
   `route`, `description`, `version`, `icon`, `category`, `launch_mode`,
   `required_huf_version`, `permission_method`, `sort_order`, `enabled`, `exposed_tables`).
   Do not invent manifest fields beyond the ones listed above and in `templates/target1/manifest.json.template`.

2. **Seed JSON files** — Create one JSON file per seeded DocType under the seed directory
   (`apps/<myapp>/<myapp>/huf/`), in these flat subdirectories:
   - `agents/<agent_id>.json` — Agent record (`templates/target1/agent.json.template`, plus any capability fields planned in Step 2 — see `templates/target1/AGENT_CONFIG_REFERENCE.md`)
   - `prompts/<prompt_id>.json` — Agent Prompt record (`templates/target1/prompt.json.template`)
   - `tools/<tool_id>.json` — Tool definitions, if any (`templates/target1/tool.json.template`)
   - `knowledge/<knowledge_id>.json` — Knowledge sources, if any (`templates/target1/knowledge.json.template`)
   - `triggers/<trigger_id>.json` — Triggers, if any (`templates/target1/trigger.json.template`)

   Use the templates in `templates/target1/` for the exact structure of each file.

3. **Populate with real content, not placeholders** — the templates give you the field shape; fill
   them with the content drafted and approved in Step 2:
   - `prompts/<prompt_id>.json` gets the actual, finished system prompt text from Step 2 — not
     `"TODO: add instructions"`.
   - `knowledge/<knowledge_id>.json` gets seeded only from real source material the user provided
     (a file, URL, or DocType/Data Table reference confirmed in Step 1). If the user said "none
     yet," skip creating a knowledge seed file rather than inventing one with fabricated content,
     and say so explicitly in the hand-off summary (Step 4).
   - If audience = *shipping to others*, re-check every knowledge source and prompt reference for
     anything that identifies the builder's own org, private docs, or credentials before writing
     the file — that content must not ship inside an installable app.

### Sync with HUF

1. **Run sync** — Execute `bench --site <site> execute huf.ai.app_seeding.apps_loader.sync_huf_apps` (or point the user to `POST /api/method/huf.ai.apps_api.sync_huf_apps` if no bench is reachable).
2. **Check sync_status** — Verify that the app and its DocTypes synced successfully. If there are errors, surface them and help the user fix them.
3. **Graceful degradation** — If no live bench is reachable, provide a summary of the files created and tell the user: "Here are the seed files. You can install and migrate them manually using `bench install` and `bench migrate`, or copy them into your app and run the sync yourself."

### Post-sync setup (not seedable)

The app seeder imports only prompts, tools, knowledge, agents and triggers. **Gateway, WhatsApp Account, WhatsApp templates and Flow Definitions are NOT seeded**: create them after sync through the desk or the REST API, using the exact DocType/field/function names in the references (`references/whatsapp-gateway.md`, `references/whatsapp-templates.md`, `references/flows-authoring.md`; example flow: `templates/target1/examples/whatsapp_triage_flow.json`). Never invent a seed folder for them. Credentials (Meta tokens, app secrets) are entered by the user in the desk, never written to files or echoed. For a full worked build see `references/end-to-end-recipes.md`; for known limits see its "Known gaps" section.

**Flow tooling notes.** The offline validator `scripts/validate_flow_examples.py` needs `pip install jsonschema` in a clean venv; pip's `frappe` package breaks it. Flow facts in the references are indicative: verify against the target build (`graph_ir.schema.json`, `validate_flow`) at build time. To ship a flow with an app, deliver the JSON in the app and save it after sync with a post-sync script calling `huf.ai.flow.api.save_flow_definition` (secret generated per site, approval roles checked with `get_approver_roles`, left as Draft): `references/flows-authoring.md` section 7b. Discovery helpers (`get_trigger_doctypes`, `get_trigger_doctype_info`, `get_site_timezone`, `get_approver_roles`, `get_flow_step_labels`, `get_document_sample`, `list_recent_documents`): section 7a.

### Do NOT

- Run `bench new-app <name>`. Assume the Frappe app already exists. If it doesn't, tell the user to run that command themselves as a prerequisite.

---

## Step 3: Execute — Target 2

### API key provisioning

1. **Point the user to Developer Settings** — Do NOT mint keys yourself. Instead, direct the user to Settings → Developer Settings (or the equivalent path on their HUF instance) to create a new HUF API Key.
2. **Specify scopes** — Tell the user which scopes to grant (from Step 2's plan).
3. **Optionally: agent-restrict** — If the plan called for it, tell the user to restrict the key to a specific agent in the key settings.
4. **Key is user-visible-once secret** — The user will see the key once after creation; they must save it immediately. The skill never sees or stores it.

### Scaffold client code

1. **Choose template** — `templates/target2/client.py` is the shipped reference client; for another stack (Node.js, Go, etc.) port it rather than inventing new endpoint shapes.
2. **Replace placeholders** — Fill in:
   - HUF instance URL (e.g., `https://huf.example.com`)
   - Agent ID (if known)
   - API method calls matching the app's planned workflow
3. **Environment variable setup**:
   - Client code MUST read the key from the environment variable `HUF_API_KEY`, never from a literal string or committed config file.
   - Emit `.env.example` with `HUF_API_KEY=` (empty placeholder).
   - Ensure `.env` is in `.gitignore`.

### Never

- Echo a key back into the transcript, even in "here's your curl command" examples.
- Include key material in code snippets or commit history.
- Use a literal or hardcoded key anywhere.

---

## Step 4: Verify & Hand Off

### Target 1

1. **Confirm sync** — Verify the app manifest synced and appears in the HUF App list.
1a. **Check the seed files (after writing seeds, before sync)** — run `scripts/validate_agent_seed.py --huf-repo <huf checkout> <myapp>/huf` (read-only; stdlib only). Without `--huf-repo` only the secret, link and access checks run and the script says so. Fix every `ERROR`; surface `WARN` lines (e.g. `allow_guest`, unresolved model placeholders) to the owner.
2. **Test the agent** — Run one test turn with the agent (via the chat interface or API call). Confirm it responds correctly.
2a. **If a Flow is part of the plan** — before saving it, run `scripts/validate_flow_examples.py --huf-repo <huf checkout> <flow.json>` (needs `pip install jsonschema` in a clean venv; do not install pip's `frappe` package, it breaks the script; indicative: verify against the target build, `graph_ir.schema.json` and `validate_flow`, at build time); then follow `references/flows-authoring.md` (save as Draft, validate in publish mode, TEST run, ask the owner before publish or any real run). Never put secrets in a flow.
2b. **If a Gateway/flow was set up** — check gateway health (see `references/whatsapp-gateway.md`), dry-run each Flow Definition with a sample event, then do a live check following `references/testing-and-pitfalls.md` (fake graph, then `tools/wa_live_smoke.py` on an isolated site). Confirm exactly one reply per inbound event.
3. **Summarize what was created**:
   - App ID and delivery method
   - List of seeded DocTypes and their IDs
   - Whether knowledge was seeded (and from what source), or left empty for the installer to add
   - Where the seed files are located
   - Link to the app in the HUF dashboard (if SPA tile) or portal/desk (if those methods)

### Target 2

1. **Verify API connectivity** — Perform two sequential tests:
   - **Step 1: Router connectivity** — Call `GET /huf/api/v1/ping` (no authentication required, `requires_auth=False`). A successful response means the API endpoint is reachable. This does NOT validate the API key.
   - **Step 2: Key authentication** — Call `GET /huf/api/v1/me` with the `X-Huf-Api-Key` header set to `$HUF_API_KEY`. A successful response (with `auth_type: api_key`) proves the key authenticates; it does not list scopes. Only this call is a real key test. If `/me` reports `auth_type: session` or a `401` appears, the key was not accepted (bad keys fall through to session auth).
2. **Summarize what was created**:
   - Technology stack and framework used
   - Where the client code lives
   - Which API scopes the key has
   - Environment variable setup (HUF_API_KEY from .env)
   - Next steps for deployment or integration

---

## Model & Provider Suggestion (v1)

Do not recommend blind. Instead:

1. **Call live endpoints** — Query the user's HUF instance:
   - `GET /api/resource/AI Provider` — list available providers
   - `GET /api/resource/AI Model` — list available models (filter by provider if desired)

2. **Present a pick-list** — Show the user what's actually configured on their site, with enough detail (provider name, model name, context window, cost per token if available) for them to make an informed choice.

3. **Do not hardcode defaults** — Do not assume "use Claude" or "use GPT-4" or "use Llama". A model that doesn't exist on their site will only cause the agent to fail on its first turn.

4. **Do not build opinionated suggestions** — Do not attempt to recommend "use Model X for this kind of app" or "use Provider Y for production". That's deferred to v2. Keep this v1 simple: show what exists, let the user choose.

---

## Hard Constraints (Must NOT Do)

- **Do not silently choose Desk-page delivery.** If the user asks for a Desk page, flag it as not currently supported and ask them to choose SPA tile or portal page instead. Never seed a Desk page without their explicit acknowledgment that it's unsupported.
- **Do not write API keys or secrets to disk** after creation. Never echo back a key in the transcript, logs, or client code. The user generates the key in Developer Settings; the skill references it via `$HUF_API_KEY` environment variable only.
- **Do not assume bench access.** The app may be seeded outside a bench (e.g., user clones the app repo to a different machine). Provide graceful degradation: "If you have a bench, run [command]. Otherwise, here are the files; copy them to your bench and run migrate yourself."
- **Target 2 client code must never contain a literal key.** Every code example must use `$HUF_API_KEY` or `process.env.HUF_API_KEY` or the language equivalent. Do not provide a curl snippet like `curl -H "X-Huf-Api-Key: sk-..." ...`. Use `curl -H "X-Huf-Api-Key: $HUF_API_KEY" ...` instead.
- **Do not plan on unavailable capabilities silently.** Anything tagged [planned], [pending: PR] or [experimental/shadow] in `references/` must be disclosed to the user with the supported alternative. The Decision Runtime (JEV) is not safely usable by apps today.
- **Do not seed gateways, `Integration Settings`, credentials, tokens, sender ids or phone numbers.** The installer creates and enables the Gateway; its `execution_user` is never Administrator or a real person.
- **Do not seed fabricated knowledge content.** A Knowledge Source seed file must come from real material the user supplied (a file, URL, or DocType/Data Table). If they have none yet, ship without a knowledge seed rather than inventing plausible-sounding facts.
- **Do not guess another app's DocType or field names.** For a tool that reads/writes CRM, ERPNext, HR, etc., confirm the real DocType and field names via App & DocType Discovery (its live meta) before seeding — schemas vary by version/customization, and "well-known" ERPNext field names are not a substitute for checking the actual site.
- **If audience = shipping to others, do not seed the builder's private material.** No personal/internal docs, credentials, org-specific references, or site-specific data in an app meant to be installed on someone else's site. The system prompt must read as generic install instructions, not "you, the builder."

- **Never, without explicit owner approval in chat (per action):** write or print an AI Provider `api_key` (Password field), a pgvector password, or any gateway/WhatsApp/Telegram secret; call `stash_secret` (gateway credential entry only, `huf/ai/secrets/__init__.py:55`); create or change a User, Huf User Role or Frappe User Permission; create or update a Huf Role or grant any capability; grant System Manager or Huf Admin, or the capabilities `roles.manage`, `users.*`, `developer.keys.manage`, `execution.*`, `code_execution.run`, `ssh.*`, `docker.run`, `system.*`; change Agent Settings spend cap or limits, or Execution Profiles; set `allow_guest` to 1. Keys and passwords are a human step in the UI: never ask for one in chat and never unmask a Password field with `get_password`. Details: `references/users-roles-permissions.md`, `references/models-and-keys.md`, `references/usage-and-limits.md`, `references/knowledge-and-skills.md`.
---

## Reference Templates

Starting-point JSON schemas and code templates are located in this skill's `templates/` directory:

- **templates/target1/** — JSON templates for the app manifest and seeded DocTypes
  - `README.md` — seed directory layout, sync commands, placeholder conventions
  - `AGENT_CONFIG_REFERENCE.md` — indexed table of every capability-relevant `Agent` field (vision, image gen, STT/TTS, context/summarization, reasoning, caching, memory, permissions, etc.)
  - `manifest.json.template` — HUF App manifest
  - `agent.json.template` — Agent record (model fields are `<AI_PROVIDER>` / `<AI_MODEL_NAME>` placeholders; `allow_guest` is 0)
  - `prompt.json.template` — Agent Prompt record
  - `tool.json.template` — Agent Tool Function definition
  - `knowledge.json.template` — Knowledge Source definition
  - `trigger.json.template` — Agent Trigger definition

- **references/** — Read-on-demand capability references (each opens with the availability tags)
  - `gateways-and-whatsapp.md` — channels, admission policies, `execution_user`, WhatsApp modes, what not to seed
  - `decision-runtime-jev.md` — Decision Runtime / JEV status and the supported alternative
  - `platform-surfaces.md` — every platform surface (skills, tables, knowledge, flows, approvals, ...) per target, plus manifest rules
  - `api-v1.md` — the real `/huf/api/v1` routes, scopes, auth and errors

- **templates/target2/** — Client stubs for external apps
  - `client.py` — Python HTTP client (ping/me/agents/conversations/responses/runs)
  - `example_usage.sh` — curl examples, all using `$HUF_API_KEY`
  - `SCOPES.md` — scope reference and key-handling notes
  - `.env.example` — environment variable template (empty value)
  - `.gitignore.snippet` — the `.env` line to add to the app's `.gitignore`

- **templates/target1/** (additions)
  - `flow_definition.json.template` — Flow Definition record; read when creating a flow post-sync
  - `examples/whatsapp_triage_flow.json` — working non-LLM triage flow; read when building keyword routing
  - `examples/flows/*.json` — six validated flows (CRM follow-up with approval, ERP order routing, webhook to Sheets, scheduled digest, doc-event reaction, gateway reply)
  - `scripts/validate_agent_seed.py [--huf-repo <huf checkout>] <seed dir or files>` — read-only check of agent/prompt/tool/knowledge/trigger seeds: keys vs doctype JSON, linked seed names, key-like strings, `allow_guest`
  - `scripts/validate_flow_examples.py --huf-repo <huf checkout> <file>` — validate any flow JSON offline against the Huf schema and validator before saving

- **references/** — read only the file the Step 1 answers need
  - `whatsapp-gateway.md` — read when the agent/flow talks on WhatsApp (gateway setup, tokens, access/pairing, 24h window, send actions, health)
  - `whatsapp-templates.md` — read when sending outside the 24h window, creating templates, or using Meta's MCP
  - `flows.md` — PRE-DEVELOP ONLY: does not apply to builds that have `huf/ai/flow/`; use `flows-authoring.md`
  - `flows-authoring.md` — read BEFORE creating any Flow Definition: triggers, all node types, value forms, draft vs publish validation, whitelisted API, test-run simulation, debugging, safety rules, checklist
  - `end-to-end-recipes.md` — read for full worked builds (triage flow, agent with voice replies, template notification) and known gaps
  - `audio-and-media.md` — read when handling voice, audio, images or documents inbound/outbound
  - `models-and-keys.md` — read when choosing STT/TTS/image models and provider keys; which AI Model fields you may read and who writes what
  - `users-roles-permissions.md` — read when the app needs users, roles or capabilities: default roles, owner-run commands, what an agent may and may not do
  - `usage-and-limits.md` — read when the owner cares about cost: run budget, per-agent limits, Agent Run cost, analytics
  - `knowledge-and-skills.md` — read when the agent needs knowledge or skills: SQLite FTS seed, verifying with `test_search`, uploads, prompt versioning
  - `testing-and-pitfalls.md` — read before verifying or when something misbehaves (fake graph, live smoke, pitfall list)

Reference these when scaffolding; do not invent structures.
