# HUF App Builder — Agent Instructions

This file is read directly by AI coding agents (Codex, Cursor, OpenCode,
Kimi, Claude Code, etc.) when working in this repo, or can be pasted as a
system/task prompt into any of them. It's a plain set of instructions — no
tool-specific syntax — so any agent that can read files, run shell commands,
and write files can follow it.

If you're setting this up as a **Claude Code skill** instead, use `SKILL.md`
in this same repo (same content, with the YAML frontmatter Claude Code's
skill loader expects). Everything else in this repo (`templates/`) is
shared between both.

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

If the user is working in a Frappe bench directory, suggest "This looks like you have a bench. Are you seeding this app inside it?" — but still ask; never assume.

---

## Step 2: Plan

### Target 1 (Launched from HUF)

Present the plan explicitly and wait for go-ahead before executing.

**DocTypes to seed:**
- Agent — the main agent record
- Agent Prompt — system prompt and conversation instructions
- Agent Tool Function — any custom tools the agent needs
- Knowledge Source — documents, FAQs, or data the agent will reference
- Agent Trigger — optional; how the agent is invoked (manual, scheduled, webhook, etc.)

**Agent capabilities:** List only the non-default fields Step 1's capability answer requires (e.g. `stt_model`+`tts_model` for voice, `image_generation_model` for image gen, `enable_memory`+`memory_policy` for memory). Look them up in `templates/target1/AGENT_CONFIG_REFERENCE.md` — a single indexed table of every relevant `Agent` field, grouped by capability, with type/default/purpose. Do not set fields the plan doesn't call for.

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
- **SPA deep-link tile (default, recommended)** — The app appears as a tile in HUF's dashboard; clicking it opens the agent in a chat interface. Works today. No gaps.
- **Portal page** — The app appears as a page in the HUF portal. Flag two known gaps:
  - Missing per-app `www/` template registry — requires manual setup or a workaround.
  - The `alias`, `is_public`, and `agent` fields are not in `ALLOWED_FIELDS`, so guest access requires a System Manager to manually edit the HUF App record after creation. Emit exact field values as a hand-off note.
- **Desk page** — NOT currently supported. The page.js pattern does not exist. Do not offer this without flagging it as unsupported.

If the user chooses **Portal page** or **Desk page**, this skill's HUF-specific plan only decides
*that* delivery — it does not teach the Frappe implementation. Load the matching subset of
`/Users/safwan/Code/Huf/workspace/doc/reference/frappe-framework/` (a tagged, categorized Frappe
framework reference; see its README for the full index) before writing any Frappe code:
- Portal page → `portal/*.md` (start with `overview.md` + `context.md`), plus
  `server-api/server-calls.md` and `server-api/jinja.md`.
- Desk page (once actually implemented — currently unsupported, see above) → `desk/page-api.md` +
  `desk/vue-inside-desk-page.md` + `assets/asset-bundling.md` + `server-api/server-calls.md`.
Load only the files relevant to the chosen path — not the whole reference directory.

**Show the plan and get explicit go-ahead before proceeding to Step 3.**

### Target 2 (Calls HUF API)

Present the plan explicitly and wait for go-ahead before executing.

**API scopes the app needs:**
- `agents:read` — list/fetch agent definitions
- `agents:run` — execute an agent
- `conversations:read` — fetch conversation history
- `conversations:write` — create or update conversations
- `files:read` — download files from conversations
- `files:write` — upload files for the agent to reference
- `voice:use` — make voice/audio API calls
- `ocr:use` — use OCR/vision capabilities

List only the scopes the app actually needs.

**API key scope restriction:**
- Ask: "Should this key be restricted to a specific agent, or should it work with all agents the key holder can access?"
- Agent-restricted keys are narrower and safer for production.

**Client code outline:**
- Sketch which endpoints the app will call (e.g., `POST /huf/api/v1/agents/:agent_id/run` for synchronous execution, `POST /huf/api/v1/conversations` for managing state, etc.).
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
   Do not invent manifest fields; see `manifest.md` for the authoritative field list.

2. **Seed JSON files** — Create one JSON file per seeded DocType under the seed directory
   (`apps/<myapp>/<myapp>/huf/`), in these flat subdirectories:
   - `agents/<agent_id>.json` — Agent record (`templates/target1/agent.json.template`, plus any capability fields planned in Step 2 — see `templates/target1/AGENT_CONFIG_REFERENCE.md`)
   - `prompts/<prompt_id>.json` — Agent Prompt record (`templates/target1/prompt.json.template`)
   - `tools/<tool_id>.json` — Tool definitions, if any (`templates/target1/tool.json.template`)
   - `knowledge/<knowledge_id>.json` — Knowledge sources, if any (`templates/target1/knowledge.json.template`)
   - `triggers/<trigger_id>.json` — Triggers, if any (`templates/target1/trigger.json.template`)

   Reference the app-pattern.md checklist and the templates in `templates/target1/` for the structure of each file.

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
2. **Test the agent** — Run one test turn with the agent (via the chat interface or API call). Confirm it responds correctly.
3. **Summarize what was created**:
   - App ID and delivery method
   - List of seeded DocTypes and their IDs
   - Whether knowledge was seeded (and from what source), or left empty for the installer to add
   - Where the seed files are located
   - Link to the app in the HUF dashboard (if SPA tile) or portal/desk (if those methods)

### Target 2

1. **Verify API connectivity** — Perform two sequential tests:
   - **Step 1: Router connectivity** — Call `GET /huf/api/v1/ping` (no authentication required, `requires_auth=False`). A successful response means the API endpoint is reachable. This does NOT validate the API key.
   - **Step 2: Key authentication** — Call `GET /huf/api/v1/me` with the `X-Huf-Api-Key` header set to `$HUF_API_KEY`. A successful response returns the key's granted scopes and proves the key authenticates. Only this call is a real key test.
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
- **Do not seed fabricated knowledge content.** A Knowledge Source seed file must come from real material the user supplied (a file, URL, or DocType/Data Table). If they have none yet, ship without a knowledge seed rather than inventing plausible-sounding facts.
- **If audience = shipping to others, do not seed the builder's private material.** No personal/internal docs, credentials, org-specific references, or site-specific data in an app meant to be installed on someone else's site. The system prompt must read as generic install instructions, not "you, the builder."

---

## Reference Templates

Starting-point JSON schemas and code templates are located in this skill's `templates/` directory:

- **templates/target1/** — JSON templates for the app manifest and seeded DocTypes
  - `README.md` — seed directory layout, sync commands, placeholder conventions
  - `AGENT_CONFIG_REFERENCE.md` — indexed table of every capability-relevant `Agent` field (vision, image gen, STT/TTS, context/summarization, reasoning, caching, memory, permissions, etc.)
  - `manifest.json.template` — HUF App manifest
  - `agent.json.template` — Agent record
  - `prompt.json.template` — Agent Prompt record
  - `tool.json.template` — Agent Tool Function definition
  - `knowledge.json.template` — Knowledge Source definition
  - `trigger.json.template` — Agent Trigger definition

- **templates/target2/** — Client stubs for external apps
  - `client.py` — Python HTTP client (ping/me/agents/conversations/responses/runs)
  - `example_usage.sh` — curl examples, all using `$HUF_API_KEY`
  - `SCOPES.md` — scope reference and key-handling notes
  - `.env.example` — environment variable template (empty value)
  - `.gitignore.snippet` — the `.env` line to add to the app's `.gitignore`

Reference these when scaffolding; do not invent structures.
