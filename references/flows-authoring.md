# Flows: authoring guide for agents (create, validate, publish, run, debug)

Read this when you must BUILD a Flow Definition, not just describe one. It is written against the Huf integration
code under `huf/ai/flow/` (package `huf.ai.flow.*`, branch `fix/flow-ui-schema-alignment` and later). The older
`references/flows.md` was written against `pre-develop` (`huf.ai.flow_api`, `flow_engine`); where the two differ, this file
wins for any Huf checkout that has the `huf/ai/flow/` package. When unsure, read the source named in "Check" lines.

Source of truth in the huf repo: `huf/ai/graph/graph_ir.schema.json` (`$defs/FlowGraph`), `docs/flow/FIELD_CONTRACT.md`,
`docs/flow/USER_GUIDE.md`, `docs/flow/CONDITION.md`, `docs/flow/DATA_INPUT.md`, `huf/ai/flow/api.py`, `huf/ai/flow/engine.py`.
Examples live in `templates/target1/examples/flows/` and are checked by `scripts/validate_flow_examples.py`.

## 1. What a Flow is
A Flow Definition (doctype, name = `flow_id`) holds one JSON document, `definition_json`: a trigger, then steps (nodes), each
pointing at its successor. Each start creates a Flow Run that pins the definition it started with and runs as the flow's
owner (never Guest). Statuses of a Flow Definition: `Draft`, `Active` (published, triggers fire), `Archived`. Flow Run statuses
include Queued, Running, Waiting Approval, Waiting User, Waiting Code, Success, Failed, Cancelled (Success/Failed/Cancelled are final).

## 2. Triggers (the `entry` node)
| type | config | notes |
|---|---|---|
| `trigger.webhook` | `method` GET or POST, `secret` (32-256 chars) | Caller sends header `X-Huf-Secret`. `?secret=` is NOT accepted. Name the flow with `?flow_id=`, header `X-Huf-Flow-Id` or argument. Endpoints: `/api/method/huf.ai.flow.api.flow_webhook` and `flow_webhook_clean`. Only Active flows answer; unknown flow, draft flow and wrong secret all give the same 403; wrong HTTP method 405; more than 60 calls a minute per caller address gives 429. Runs are queued and always Real. |
| `trigger.schedule` | `cron` (5 parts), `time_zone` optional IANA name | Fires while the flow is Active, one run per due minute. Absent time zone = site time zone. |
| `trigger.doc-event` | `doctype`, `event` one of `after_insert, on_update, on_submit, on_cancel, on_trash` | The run's `input` is the document (fields the flow owner may read; Password fields and fields above the owner's permission level removed) plus `input._trigger` (doctype, docname, event, owner, timestamp). `on_submit`/`on_cancel` only fire for submittable doctypes. |
| `trigger.unset` | `{}` | Placeholder; cannot be Active. |
A Gateway (WhatsApp, Telegram, ...) can route to a Flow; there is no gateway trigger node. Use `trigger.webhook` as the entry (see 11).

## 3. IR shape
Top level (no other keys; there is NO `edges` array): `schema_version` `"1.0.0"`, `profile` `"flow"`, `fingerprint` (64 hex chars,
`"0"*64` is fine), `entry` (node id, or array of ids when there are several triggers), `nodes` (min 1), `contract`.
Node: `{id, type, config, next?, on_error?}`. `id` matches `^[a-zA-Z_][a-zA-Z0-9_]*$` (no `-` or `.`), max 64, unique. `config`
rejects unknown keys. `next` = default successor; `on_error` = node to run if this one raises (else the run fails).
Nodes that route inside `config` (`condition`, `router.llm`, `human.approval`) and `output` must NOT have `next`. A `foreach`
body's last node has no `next`; body nodes must not be reachable any other way. No cycles, no unreachable nodes.
Positions and labels are not part of the definition.

`contract` (required): `input_schema` and `output_schema` (JSON Schema objects, `{}` ok; property `title`/`example` feed the Run
dialog and approval card labels), `applies_when` (array of expressions, may be empty), `permission_envelope`
`{read:[{doctype}], write:[{doctype}], http:"none"|[tool ids], code:"none"|[tool ids]}` and `limits` with ALL of
`max_nodes, max_rows, max_output_bytes, max_parallel_calls, max_foreach_iterations, max_external_calls, max_writes,
max_wall_time_ms` and `fail_closed: true`. Policy ceilings: nodes 500, rows 50,000, output bytes 5,000,000, parallel 16,
foreach iterations 5,000, external calls 2,000, writes 500, wall time 15 minutes. The envelope must cover what the graph calls:
a flow with `http_request` needs `"http": ["http_request"]`; a `doc.create` needs the doctype in `write` AND `max_writes` >= 1.

## 4. Value forms
A `Value` is a literal; a reference `{"$from": "<path>"}`; a template `{"$template": "Hi {name}", "vars": {"name": <Value>}}`;
or an array/object of Values (an object may not itself contain `$from`).
Reference path: `input`, `trigger`, `row`, `foreach.item`, `foreach.index`, or an earlier node id, then `.key` or `[n]`
(`input.customer.name`, `draft`, `lookup.rows[0].id`). The referenced node must precede the reference on every path
(else `FORWARD_REFERENCE`). A missing path resolves to null. Template placeholders are plain identifiers declared in `vars`
(`{a.b}` is not a placeholder; resolve the path in `vars`). `{{` and `}}` are literal braces. `{{var}}` double-brace templating
is not supported. Wording prefixes for whole lists/records inside templates: `table_x`, `joined_x`, `count_x`.
Plain-text fields that are not Values (`human.approval.message` and `title`, `router.llm.prompt`, `output.outcome.label`) fill
`{input.field}`, `{<node_id>.field}`, `{foreach.item}` at run time (also `{table:x}`, `{joined:x}`, `{count:x}`); a placeholder that
does not resolve is left as written.
Expressions (`condition.expression`, `validate.assertions[].expression`): restricted Python subset, 1-500 chars, subscripts not
attributes (`input['amount'] > 100`), operators `== != < <= > >= in not in and or not`, only these calls: `number(x)`, `lower(x)`,
`startswith(x, y)`, `endswith(x, y)`. Missing data: `is not`/`not in` comparisons are true, others false. Never repeat text or
lists (`"ab" * 3` is refused); integers stay below 10**18.

## 5. Node types
| type | config (`*` required) | output / routing |
|---|---|---|
| `agent.run` | `agent`* (Agent name), `prompt`* with `{name}` placeholders, `prompt_bindings` name -> Value | agent reply text. `{{`/`}}` are literal braces. |
| `tool.call` | `tool_id`* (literal tool name, never a reference), `input`* object of Values, `timeout_ms`, `approved` | tool result. `timeout_ms` is enforced for MCP tools only. |
| `router.llm` | `prompt`*, `options`* `[{label, node_id}]` (min 1), `default`*, `model` | `{label, node_id, reason, model, provider}`. Any failure or no match goes to `default`. No `next`. |
| `condition` | `expression`*, `on_true`*, `on_false`* | no `next`. |
| `foreach` | `items`* (`$from` only), `body`* node ids, `max_iterations`*, `on_item_error`* `fail`/`skip`, `collect`* (`$from`), `item_var`, `index_var` | list; `next` is the Done edge. Max iterations also capped by `contract.limits.max_foreach_iterations`. |
| `human.approval` | `message`*, `approver_type`* `role`/`user`, `approver_role` (role) or `approver_users` (user), `approve_next`*, `reject_next`*, `timeout_next`, `timeout_ms`, `title`, `details` (max 6 `{label?, value}`) | `{decision: approved/rejected/timeout, comment, decided_by, decided_at}`. No `next`. Without `timeout_next` an expired approval fails the run. |
| `transform` | `op`* one of `select, filter, sort, limit, group_by, aggregate, join, lookup, batch, distinct, coalesce, lower, upper, trim, replace, contains, starts_with, split_first, regex_extract, concat`, `input`* | op result. Text ops take `text`; row ops take `rows` etc. See FIELD_CONTRACT section 2 for each op's keys. |
| `state.get` / `state.set` / `state.delete` | `key`*, plus `default` / `value`*, `ttl_seconds` (1..2,592,000) | Flow-private memory. Key 1-140 chars, value at most 16 KB. |
| `doc.create` | `doctype`* literal, `fields`* | `{doctype, name}`. Doctype must be in site config `huf_flow_create_doc_doctypes` (default `["ToDo"]`); at most 30 fields; each value at most 5,000 chars; runs with the owner's permissions. |
| `validate` | `assertions`* `[{expression, code, message}]` | fails the run if false. |
| `code.run` | `code`* (Python, max 64 KB), `profile`* (Execution Profile, default `Flow Scratch`), `inputs`, `timeout_s` | `{stdout, result, exit_status, truncated}`. See 8. |
| `output` (End) | `value`*, `outcome` `{label (1-60), tone good/neutral/bad}` | terminal. For a gateway-triggered run, its value is the reply text. |
`router.decision` exists in the schema but always routes to its `default`; do not use it. `http_request`, `loop`, `end`, `parallel`
are not Flow node types: use `tool.call` of `http_request`, `foreach`, and `output`.

### Built-in tools for `tool.call` (check the live list with `list_flow_tools`)
Email `gmail_send_email {to, subject, body}`; Slack `slack_send_message {channel, text}`, `slack_send_thread_reply {channel, text, thread_ts}`;
Sheets `gsheets_read {spreadsheet_id, range}`, `gsheets_update {spreadsheet_id, range, data}` (writes exactly that range; there is no append
tool, so compute the row), `gsheets_create {title}`; Drive `gdrive_list_files`, `gdrive_search_files {query}`, `gdrive_get_file {file_id}`;
web `http_request {url, method, headers, body}` (success only for 2xx, body capped at 64 KB, private addresses blocked);
messaging `whatsapp` and `telegram` (multi-action tools: pass `action`), Discord, Google Chat; Calendar, GitHub, Frappe/ERPNext/CRM record tools,
and tools of enabled MCP servers. Integration tools fail with "<Integration> is not connected" until the user connects them in Integrations;
never try to fill credentials yourself. Code Execution tools (`run_python`) are refused in flows; use `code.run`.

## 6. Draft vs publish validation
- Draft (`save_flow_definition`): only STRUCTURE must be sound (JSON shape, known types, unique ids, links to existing nodes, limits inside policy).
  Missing required settings, loose nodes and a missing trigger are allowed and are reported as `unfinished`.
- Publish (`publish_flow`, any run, an Active save): additionally every step finished and connected, a real trigger present, no blank
  required text, named `approver_users` real enabled users (a run does not re-check people; save and publish do).
- Read what is left at any time: `huf.ai.graph.validation.flow_validation.validate_flow_definition(flow_id, mode)` (whitelisted, mode `draft` or `publish`)
  returns `{ok, structure_ok, finished, errors, issues}` with plain sentences naming the step and field.
- Offline check before you save: `python3 scripts/validate_flow_examples.py --huf-repo <huf checkout> my_flow.json`
  (jsonschema against `$defs/FlowGraph`, then the repo's `validate_flow_graph` in publish mode, no bench needed).

## 7. Create, save, publish via the whitelisted API
All are `POST /api/method/<path>` (or `frappe.call`). Permission is the Frappe permission on Flow Definition / Flow Run (roles System Manager,
Huf Manager; Huf User and Huf Viewer can only read Flow Definitions); Huf Roles can grant it through capabilities `flows.create` / `flows.manage`.
| call | args | does |
|---|---|---|
| `huf.ai.flow.api.save_flow_definition` | `flow_id`, `definition_json` (object or string) | Creates a Draft (name = `flow_id`) or updates and bumps `version`. Returns `{flow_id, version, warnings, unfinished}`. Needs write permission. |
| `huf.ai.flow.api.get_flow_definition` | `flow_id` | definition, version, status. Viewers without write get the webhook secret hidden. |
| `huf.ai.graph.validation.flow_validation.validate_flow_definition` | `flow_id`, `mode` | see 6 |
| `huf.ai.flow.api.publish_flow` / `unpublish_flow` | `flow_id` | set status Active / Draft. Refused with a readable message if not finished or not allowed. |
| `huf.ai.flow.api.run_flow` | `flow_id`, `payload`, `mode` `"real"` or `"test"` | starts a run now (synchronous, trigger type Manual). Needs Flow Run create and read on that flow. |
| `huf.ai.flow.api.get_flow_run` | `flow_run_id` | status, `context_json`, `waiting`, `last_error`, `approval_card`, `outcome`, `run_mode` |
| `huf.ai.flow.api.list_flow_runs` / `list_flow_runs_page` | `flow_id`, `status`, `limit`, `run_mode` | run history |
| `huf.ai.flow.api.get_pending_approvals` | `limit` | approvals the caller may decide |
| `huf.ai.flow.api.approve_flow_run` / `reject_flow_run` | `flow_run_id`, `comment` | decide an approval |
| `huf.ai.flow.api.resume_flow_run` | `flow_run_id`, `input` | continue a run waiting for input |
| `huf.ai.flow.runs.actions.cancel_flow_run`, `huf.ai.flow.api.mark_flow_run_failed` | `flow_run_id` | stop a run; mark a stale one failed (System Manager) |
| `huf.ai.flow.listing.clone.clone_flow`, `create_flow_from_template` | `flow_id`; `name, definition_json, description, category` | new Draft with its own fresh secret and a "needs setup" list |
| `huf.ai.flow.listing.tools.list_flow_tools` | none | tools a step may call, each with `effect` reads/changes/sends |
| `huf.ai.flow.testrun.step_test_api.test_step` | `flow_id`, `node_id`, `sample_input` | run ONE step without creating a run (editors only; 20 a minute) |
| `huf.ai.flow.api.get_node_schemas` | none | config schema per node type |
Agent tools `run_flow`, `get_flow_run`, `resume_flow_run`, `approve_flow_run` (`huf/ai/flow/tools.py`) always start REAL runs: no test mode.
Flow Definition `status` can also be set through the doc API, but prefer `publish_flow`.

Capabilities (checked on top of document permissions):
- `flows.publish_sensitive` (Huf Manager, Huf Admin by default): needed to make a flow Active if it has a `trigger.doc-event`, or a web request
  step (`http_request` or any GET/POST tool). Editing an unrelated step of an already-published flow does not need it; adding or changing a
  sensitive step does. A doc-event flow stops firing while its owner lacks it.
- `flows.execute_code` (System Manager, Huf Admin): needed to save or change a `code.run` step, even as a draft.
If you lack one, tell the owner which; do not look for a way around it.

## 8. `code.run`
Hidden unless BOTH switches are on: the server switch (site config `huf_python_execution_enabled`, set with `bench set-config` by the server admin) and
`Agent Settings.allow_code_in_flows` (only a System Manager can change it). Publishing also needs `flows.publish_sensitive` and `flows.execute_code`, an
enabled Execution Profile that is not `Never Allow` or `Shared Directory`, and `timeout_s` within the profile's wall limit. At run time the flow owner must
still hold `flows.execute_code` and `code_execution.run`. The code is read from the pinned definition, never from run input; `inputs` reach it as data in the
variable `inputs`, and the value of `result` at the end comes back. Built-in profile `Flow Scratch`: scratch folder, no network, 30 s, 256 MB. At most 20
code steps per run; not allowed inside a loop body. Status shows Waiting Code while it queues or waits for an Agent Execution Approval.
Check status with `huf.ai.flow.code_node.get_code_flow_status`. Do not add code steps unless the owner asked and both switches are on.

## 9. Test run: what is simulated
`run_flow(flow_id, payload, mode="test")` starts a Test run. Every tool is classified `reads`, `changes` or `sends` (`huf/ai/flow/testrun/effects.py`):
- `reads` run for real (Slack/GitHub/Sheets/Drive/Gmail reads, record lookups, `http_request` GET and HEAD only).
- `changes` (record create/update, Sheets write/create, calendar, GitHub create, other `http_request` methods) and `sends` (email, Slack/Discord/
  Google Chat posts, WhatsApp, Telegram, Messenger) are SKIPPED: the step succeeds with `{"simulated": true, "summary": "Would send email to ...", ...sample fields}`.
- Unlisted tools (custom, MCP, new) count as `changes` and are skipped. Multi-action tools are classified by their `action`.
- `doc.create`, and `state.set` / `state.delete` in a step test, are skipped; `code.run` runs for real only in the shipped `Flow Scratch` profile.
- Conditions, loops, transforms, routers, `validate`, `output` and agents run for real (an agent makes real model calls and uses your AI key, but its own tools
  follow the same reads/changes/sends rule). `human.approval` pauses for real; in a test the person who started it may decide, and no email or Slack card is sent.
- Webhook, schedule, document-event and gateway runs are always Real. A test run never counts in the card "last run".
Test runs are the default first step for any new flow. They still read real data and cost model tokens.

## 10. Reading and debugging runs
`get_flow_run` -> `status`, `last_error`, `current_node_id`, `context_json.__node_outputs__["<node_id>"]` (a failed node's output is
`{"status": "failed", "error": "<reason>"}`), `waiting`, `approval_card`, `outcome`. Approvals: a run in `Waiting Approval` is decided with
`approve_flow_run` / `reject_flow_run` by someone with the role or in `approver_users` (a System Manager always can). Overdue approvals route along
`timeout_next` (checked at least every minute) or fail the run. Exactly one decision wins; a second gets "already decided".
Stale runs: Queued/Running with no change for 30 minutes and no live lock are failed by a sweeper ("Run did not complete (worker stopped)").
| Message or symptom | Cause and fix |
|---|---|
| Save refused: "This flow cannot be saved yet" + sentence | Structure error. Common: id with `-`, `next` on a `condition`/`output`, unknown config key, `"next": null`, missing `secret`, `edges` array, `schema_version` as number. Fix the named step. |
| `FORWARD_REFERENCE` / reference not provable | A `$from` points at a node that does not precede it on every path (e.g. a node on only one branch). Move the data into a node both paths pass, or `state.set`. |
| "Step '...' is not connected to the start of the flow" | Unreachable node. Connect or delete it. |
| "Disallowed expression element: Call" | Only `number, lower, startswith, endswith` are callable in expressions; use a `transform` first. |
| Publish: "This flow has a document-event trigger and a web request step. Only people who may publish ... Ask an admin" | Lacks `flows.publish_sensitive`. Ask the owner/admin to publish. |
| Webhook 403 | Flow not Active, wrong flow id, missing/wrong `X-Huf-Secret`; all look identical on purpose. 405: wrong method. 429: over 60/min. |
| "<Integration> is not connected. Connect it in Integrations." | Gmail/Slack/Sheets/Drive not connected for the flow owner. A human must connect it. |
| `gateway_context_required` | A messaging/CRM tool used in a run that has no gateway conversation (webhook, schedule, doc-event). Only gateway-triggered runs can send replies with the `whatsapp`/`telegram` tools. |
| doc.create refused | Doctype not in `huf_flow_create_doc_doctypes`, not in `permission_envelope.write`, `max_writes` is 0, or the owner lacks create permission. |
| "This approval has expired" | Decided after `timeout_ms`; the timeout path owns it. |
| Agent step fails naming a provider | The AI provider has no working key; the owner must add it. |
| Run stays Running | Worker stopped or queue backlog; use `mark_flow_run_failed` after 15 minutes (System Manager) and check workers. |

## 11. Messaging (WhatsApp, Telegram) in what exists today
- Tools registered: `whatsapp` (`huf.ai.tools.whatsapp.handle_action`; actions include send_message, send_media, send_buttons, send_list,
  send_template, list_messages ...) and `telegram` (`huf.ai.tools.telegram.handle_action`; send_message, send_photo, send_document ...; text goes in `text`),
  plus `telegram_admin`. Both are `sends` for test runs. They work only inside a gateway conversation (the gateway is bound from the run's Gateway Event,
  never from tool input; WhatsApp free-form sends obey the 24-hour window and opt-outs; Telegram sends are capped per run and per day).
- Gateway to Flow: a Gateway `default_target_type = Flow` with `default_flow`, or a Gateway Binding with target type Flow. One Flow Run per event
  (`trigger_type` Gateway). The payload is read as `input.*`: `gateway_event, gateway, provider, sender_id, wa_id, conversation_id, thread_id, message_id,
  message, text, message_type, attachments, reply_to_message_id, interactive_reply`.
- Reply: when the run succeeds, its final `output` value (or a dict's `reply`/`text`/`message`) is sent once through the gateway's normal pipeline. Empty text or
  `<NO_REPLY>` sends nothing. A failed run sends a plain "Something went wrong. Ref <event>." notice, no internal detail.
- There is no `trigger.whatsapp` / `trigger.telegram` node and no wait-for-reply node: each inbound message is a new run, so keep context with `state.*`
  keyed by `input.sender_id`. For WhatsApp setup see `references/whatsapp-gateway.md`; the Gateway itself is created by a human, not seeded.
Example: `gateway_reply_flow.json` (works for either provider because it only uses the output reply).

## 12. Limits
Webhook 60 calls/minute per caller address. `contract.limits` ceilings in 3. Pinned sample (`_sample`) at most 8 KB, secret-looking keys hidden. Step test: 20 a minute,
30 s per step, 64 KB output. State value 16 KB, key 140 chars. `doc.create` 30 fields, 5,000 chars each. Code 64 KB, at most 20 code steps per run. Condition expression 500
chars. Hop budget per run 100. Web requests: public addresses only (every resolved address and each redirect hop is checked), response body 64 KB.

## 13. Safety rules for agents
1. Never put secrets (API keys, tokens, passwords, OAuth values) in a flow. The only secret a flow holds is the webhook `secret`: generate 32+ random characters
   at creation time (for example `python3 -c "import secrets;print(secrets.token_urlsafe(36))"`), never commit it, never print it in chat, never reuse the placeholder
   `REPLACE-WITH-GENERATED-SECRET-...` in an Active flow. Credentials for Gmail/Slack/Sheets are connected by a human in Integrations.
2. Never run a flow for real, publish it, or approve a run unless the owner asked for exactly that. Default order: validate offline, save as Draft, validate in
   publish mode, TEST run, review the simulated summaries with the owner, then ask before publish.
3. Prefer simulated sends: use `mode="test"`. In a test, point email/chat steps at the owner's own address or a test channel anyway.
4. Do not widen scope: do not add `http_request`, `doc.create`, `code.run` or a document-event trigger the owner did not ask for; these need extra capabilities.
5. Do not bypass refusals (missing capability, switch off, unconnected integration, unknown doctype): report them.
6. Put a `human.approval` before any step that messages customers or changes money-related records, unless the owner says otherwise.
7. Never put real phone numbers, emails of customers or ids from production into examples or committed files.

## 14. Validation checklist
- [ ] Top level has exactly `schema_version "1.0.0"`, `profile "flow"`, 64-hex `fingerprint`, `entry`, `nodes`, `contract`.
- [ ] Every id matches `^[a-zA-Z_][a-zA-Z0-9_]*$` and is unique; every `next`, `on_error`, `on_true`, `on_false`, option `node_id`, `default`, `approve_next`,
      `reject_next`, `timeout_next`, `body` entry points at an existing node.
- [ ] No `next` on `condition`, `router.llm`, `human.approval`, `output`. Last `foreach` body node has no `next`.
- [ ] Every node reachable from `entry`; no cycles; every `$from` points at `input`, `trigger`, a loop variable or a proven predecessor.
- [ ] Webhook has `secret` (32-256 chars, generated, not the placeholder) and `method` GET or POST; schedule cron has 5 parts; doc-event event is one of the five.
- [ ] Every `tool_id` is literal and exists in `list_flow_tools`; its `input` has the tool's required arguments.
- [ ] `permission_envelope` covers http/code tools and `doc.create` doctypes; `max_writes` >= number of record creations; all 9 limits present, under ceilings.
- [ ] `human.approval` has `approver_type` plus the matching `approver_role` or `approver_users`; add `timeout_next` whenever `timeout_ms` is set.
- [ ] Offline: `scripts/validate_flow_examples.py --huf-repo <huf>` passes; on the site `validate_flow_definition(flow_id, "publish")` returns `ok`.
- [ ] Test run succeeded; simulated summaries read correctly; owner approved before publish.

## 15. Examples (all in `templates/target1/examples/flows/`, all validated)
| file | trigger | shows |
|---|---|---|
| `crm_lead_followup.json` | webhook | `agent.run` draft, `human.approval` with details, Gmail send, Slack note, outcomes |
| `erp_order_routing.json` | doc-event Sales Order | `condition` on grand_total, approval for big orders, Slack either way |
| `webhook_to_sheets_row.json` | webhook | `transform` trim, `gsheets_update` to a computed row range |
| `scheduled_digest.json` | schedule, weekdays 09:00 | agent writes a digest, Slack post |
| `doc_event_reaction.json` | doc-event Lead | `condition`, `doc.create` ToDo (envelope and `max_writes` set) |
| `gateway_reply_flow.json` | gateway (webhook entry) | keyword answer, otherwise agent; reply is the `output` value |
Replace `REPLACE-WITH-GENERATED-SECRET-...`, agent names, channels, roles, spreadsheet id before use. Agent names, roles and doctypes must exist on the target site.
