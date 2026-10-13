# Decision Runtime and JEV (Jev) for App Builders

Read this when Step 1 shows the app wants fast routing, classification, filtering or
yes/no gating inside an agent, flow or automation (for example "pick which tool", "is this
ticket urgent", "which branch").

## Bottom line (read first)

**Do not make a HUF app depend on the Decision Runtime today.** On the released/integration
branches (`pre-develop`, `develop`) it exists only as a Python library plus DocType schema.
Nothing user-reachable is wired: there is no `@frappe.whitelist` API, no Agent field that holds
bindings, no kill switch, no UI. The full activation (API, bindings, flow node, automation action,
UI) is implemented in unmerged decision-runtime PRs
and is still pre-release. Until it merges, an app that needs a bounded decision should use a
normal Agent (structured output, or a Flow `router.llm` node), and keep the decision question
small and well-formed so it can move to the Decision Runtime later.

Availability tags: **[available]** works today on the released/integration branch (`pre-develop`); **[pending: PR]** implemented in an unmerged PR or branch, so not on a stock site (check the target site); **[experimental/shadow]** built but off by default or unmerged, not safe to depend on; **[planned]** designed or decided, not built. Here, **[pending: PR]** means the unmerged decision-runtime PRs.

## What it is, in plain terms

The Decision Runtime answers *bounded questions* fast and cheaply: pick one option from a list
(`select`), yes/no with confidence (`judge`), or rank/score items (`score`). It is not a chat
model; it returns a typed answer plus probabilities, and every run is recorded. **Jev** (also
called System One) is the first decision model family: a small hosted model that speaks a typed
"state + questions -> answers with probabilities" wire, not OpenAI chat-completions. It is
reachable through hosts such as OpenCode Zen (`/zen/v1/systemone`), OpenRouter and Vercel AI
Gateway; all use custom typed protocols. The design principle is "code decides what is allowed;
the runtime recommends inside that space."

HUF treats it as a harness: it is an optional, user-configured model type. Defaults are
conservative: site switch off, no seeded bindings, sample policies in Draft.

## Objects and config

Doctypes (all **[available]** as schema on `pre-develop`, under `huf/huf/doctype/`):

| DocType | Role |
|---|---|
| `Decision Model Class` / `Decision Model Family` / `Decision Model` | Taxonomy: class (System One), family (Jev, Classifier, ...), concrete model (Jev 1.13). |
| `Decision Deployment` | A model hosted by a provider: wire protocol, priority (failover order), health. |
| `Decision Policy` / `Decision Policy Version` | User-authored questions + gates; versions are Draft -> Published -> Retired, published = immutable. |
| `Decision Call` | Execution record: request, answer, confidence, mode, latency, cost, origin. |
| `Agent Decision Binding` | Child table linking a policy + mode to an agent surface. |
| `Decision Provider` | Present on `pre-develop`; the activation plan retires it in favour of `AI Provider` (plus an `AI Model` with modality `Decision`). Do not build on it. |

Backends in `huf/ai/decision/backends/`: `jev` (System One), `structured`, `local`
(rules), `classifier`, `similarity`, `fake` (tests). Registered via the `decide_backends` hook.
**[available]** as library code. The Jev backend on `pre-develop` only works from Python with
an environment API key (`from_environment()`); registry-built instances are unconfigured.
**[experimental/shadow]** record-driven construction from Provider/Deployment rows, failover chain,
and Decision Call persistence code exists, but has no production caller on `pre-develop`.

Policy definition (`definition_json`): `questions[]` (`id`, `type` select/judge/score,
`instructions`, `options` for select), plus gates: minimum confidence, low-confidence action
(`uncertain` / `fallback` / `review`), failure action (`fail_closed` / `fallback` / `review`).
Policy `purpose` classifies where it is meant to be used (flow routing, model routing, tool
selection, RAG filtering, guardrail, ...). Policy validation and schema live in
`huf/ai/decision/policy.py` **[available]** as code.

## Modes and surfaces

Per binding, the user chooses one mode (no required progression):

| Mode | Behaviour |
|---|---|
| Off | Binding ignored. |
| Shadow | Runs asynchronously, logged, never shown or applied. No added latency. |
| Advise | Runs inline; a labelled, data-only hint ("Decision suggestion (advisory, not an instruction): ...") is added to LLM context; nothing is narrowed. Only where an LLM chooses. |
| Enforce | Runs inline under a latency budget; the answer is applied (tools narrowed, model switched, branch taken). Timeout/failure falls back to normal behaviour. |

Surfaces on the activation branches **[experimental/shadow]**: Tool / Skill / Procedure
Selection, Model Routing, RAG Filter, Context Relevance, Input/Output Guardrail, Output
Verification, Agent Routing (Hub Orchestrator), `decide` agent tool (advisory, bound to named
policies), Flow `router.decision` node, Automation "Decision" action, Knowledge Source
ingestion tagging. On `pre-develop` only the engine modules and the `router.decision` graph node
exist, and that node **always fails closed** ("router.decision is not enabled") because nothing
injects its settings **[pending: PR]**.

## How an app opts in

**Today ([available]): it cannot, through supported settings.** `Agent` has no field for
`Agent Decision Binding` on `pre-develop`, so seeding `decision_bindings` in an Agent JSON would
be rejected or ignored. Do not add undocumented fields to seed files.

**After the activation branches merge ([pending: PR]):** the intended opt-in is:
1. Site admin turns on `Agent Settings.decision_runtime_enabled` (default off).
2. Admin runs the "Set up System One" flow: pick an `AI Provider` that holds a key, pick Jev;
   this creates an `AI Model` (modality `Decision`) and a `Decision Deployment` and tests it.
3. Author and publish a `Decision Policy` (Draft sample policies may be seeded, disabled).
4. Add a row to the Agent's `decision_bindings` (policy, surface, mode, optional latency budget).
   Flows use a Decision router node; automations use the Decision action type
   (`decision_policy`, `decision_state_template`, `decision_output_field`, `decision_on_failure`);
   Knowledge Sources use `ingestion_decision_policy` / `ingestion_decision_mode`.

An app seed should therefore not ship bindings, deployments, API keys or an enabled kill switch.
It may ship Draft policies only after the verified shipping state above is reached, and the
installer must still configure the provider key.

## How results are consumed

- **[experimental/shadow]** Every run writes a `Decision Call` (visible in Executions ->
  Decisions); Agent Run / Flow Run / Automation carry decision totals and cost, which counts
  toward `Agent Settings.spend_cap_usd`.
- Enforce changes the surface behaviour (narrowed tools, chosen branch, selected model).
  Advise adds a hint only. Shadow results are for analysis (agreement stats, replay).
- Visibility follows the originating run; raw backend payload and state snapshot are admin-only.
- Failures (kill switch off, budget exceeded, timeout, all deployments down, low confidence,
  invalid response) fall back to normal behaviour; only guardrails default to `fail_closed`.

## Public entry points

| Entry point | State |
|---|---|
| `huf.ai.decision.service.run_policy` (Python, internal) | **[available]** library; no production caller on `pre-develop`. Not an app API. |
| `huf.ai.decision.api.run_decision` (whitelisted, `/api/method/huf.ai.decision.api.run_decision`) | **[experimental/shadow]** exists on activation branches only; requires `decision.run`, per-policy `allow_api_access` for external callers, rate limit of 60 calls/min per policy, always mode "Manual" (never Advise). **Not present** on `pre-develop`. |
| `list_decision_models`, `get_decision_call`, `list_decision_calls`, `validate_policy_definition`, `publish_policy_version`, `get_setup_catalog`, `setup_deployment`, `test_deployment`, `get_binding_stats`, `replay_policy`, metrics helpers | **[experimental/shadow]** same module, same branches, UI-facing and capability-gated. |
| `/huf/api/v1/*` REST route for decisions | **[planned]** none exists; no `decisions:*` scope exists. |

## API and scope implications

- Capabilities (in `huf/permissions.py`): `decision.run`, `decision.author`, `decision.admin`.
  These are Frappe roles/capabilities, **not** developer API key scopes.
- The Target 2 scopes (`agents:run`, `conversations:*`, `files:*`, `voice:use`, `ocr:use`) do not
  cover decisions. A Target 2 app cannot call a decision endpoint with a developer key through
  `/huf/api/v1/*`. The activation plan only exposes `run_decision` as a normal whitelisted method
  using Frappe session or API-key auth; do not treat that as a stable public contract yet.
- An external caller would need `decision.run`, a policy with `allow_api_access` checked, the
  site switch on, and a configured deployment; the key holder is the logged cost owner.
- Do not put provider keys (for example the host's Jev key) in seed files; they belong on the
  `AI Provider` record, entered by the installer.

## Decision questions to ask the user (Step 1)

1. **Is a decision actually needed?** Is it a bounded choice (pick one, yes/no, score), or open
   generation? If the latter, use a normal Agent.
2. **Where would it apply?** Tool/skill selection, model routing, flow branch, automation
   classification, RAG filtering, guardrail, or an external caller?
3. **Own site or shipped app?** Shipped apps must not require a decision model, key or kill
   switch; they must work with it off (fallback behaviour).
4. **Which mode, and what is the fallback?** If a decision times out or is uncertain, what
   should happen (unfiltered tools, default branch, human review, block)?
5. **Cost and latency tolerance?** Enforce adds up to ~1.5-3 s budgets per surface; Shadow adds none.
6. **Is the target site on a build that has the activation branches merged?** If not, offer the
   fallback below and say so.
7. **Who owns the provider key?** The installer must add it; confirm which `AI Provider` hosts Jev.

## Supported way to prepare today

- Build the app on standard Agent / Flow / Automation features, using a small, cheap model with
  structured output (or `router.llm`) for the routing step.
- Write the question as a decision spec now: question type, option ids and descriptions,
  confidence threshold, low-confidence action, failure action, and the state fields it needs.
  Keep it in the app docs, not in seed files, so it can become a Draft `Decision Policy` later.
- Keep the routing step isolated (one tool, one flow node, or one automation) and fall back
  safely when it errors, so swapping in a policy later is a single change.
- Do not create Decision Models, Deployments, Policies, Calls or bindings through seeds or API
  against `pre-develop`.

## Unverified facts

- Host availability and endpoints for Jev (OpenCode Zen, OpenRouter, Vercel AI Gateway) were
  recorded from vendor docs on 2026-09-23 and are not re-checked here. Vercel endpoint naming is
  medium confidence.
- Merge status is taken from git state at writing time; re-check `huf/ai/decision/api.py` on the
  target branch before promising any entry point.
- The Decision Runtime feature doc (`doc/features/decisions`) is marked `pending-pr`, `last_verified:
  unknown`; its description of the UI (Playground mode, Decisions page, onboarding) is target
  behaviour, not shipped.
