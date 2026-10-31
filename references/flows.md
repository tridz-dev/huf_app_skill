# Flows: deterministic (non-LLM) workflows

> **PRE-DEVELOP ONLY. This file does not apply to builds that have `huf/ai/flow/`; use `references/flows-authoring.md`.**
> It describes the older `pre-develop` engine (`huf.ai.flow_api`, `flow_engine`). On any current build the module names, API
> paths, condition syntax, statuses, approval and cancel behaviour below are wrong or incomplete. Only read on if the target
> Huf checkout has no `huf/ai/flow/` directory.

Read when Step 1 says "a WhatsApp/webhook/doc-event workflow with fixed rules" (menus, keyword triage, hand-off rows,
templated replies) and an LLM is not needed. Flows are NOT seedable: the app seeder only takes
`prompts, tools, knowledge, agents, triggers`. Create flows after sync through REST or Desk (see "Creating a flow").
`R` below = Huf `pre-develop` code. Worked builds: `references/end-to-end-recipes.md`. Gateway setup: `references/whatsapp-gateway.md`.

Source: huf/ai/app_seeding/seeder.py, huf/ai/flow_api.py

## Graph IR shape
A Flow Definition holds one JSON document (`definition_json`), validated on every save against the Flow profile
(`FlowGraph` in graph_ir.schema.json). There is NO `edges` array; each node carries its own successor.

- Top level, all required, no extra keys: `schema_version` (const `"1.0.0"`), `profile` (const `"flow"`),
  `fingerprint` (64 hex chars; `"0"*64` is accepted), `entry` (node id, or array of trigger node ids), `nodes[]`, `contract`.
- Node: `{id, type, config, next?, on_error?}`. `next` = default successor; absent = chain ends. `on_error` = node to route to
  if this node raises; absent = run fails.
- Self-routing nodes (`condition`, `router.*`, `human.approval`) must NOT have `next`; they name targets inside `config`.
  `output` is terminal (no `next`).
- `contract` (required): `input_schema`, `output_schema`, `applies_when` (array of expressions), `permission_envelope`
  `{read:[{doctype,fields?}], write:[{doctype,fields?}], http:"none"|[hosts], code:"none"|[ids]}` and `limits`.
- `limits` (all required, `fail_closed` must be `true`): `max_nodes, max_rows, max_output_bytes, max_parallel_calls,
  max_foreach_iterations, max_external_calls, max_writes, max_wall_time_ms`. Policy ceilings: nodes 500, rows 50,000,
  output bytes 5,000,000, parallel 16, foreach 5,000, external calls 2,000, writes 500, wall time 15 min.
  `max_writes` 0 means `doc.create` is refused at run time; `permission_envelope.write` must list the doctype too.
- Validator also rejects: duplicate ids, dangling `next`/targets, unreachable nodes, cycles, a `$from` pointing at a node that
  does not precede it (`FORWARD_REFERENCE`), bad expressions, unknown transform ops, non-literal `tool_id`.

Source: huf/ai/graph/graph_ir.schema.json, huf/ai/graph/validator.py

## Node catalogue (type: config -> output)
Allowed Flow types = `FLOW_NODE_TYPES` (validator.py). Every config is `additionalProperties:false`: unknown keys fail the save.
Values (`Value`) may be a literal, `{"$from": ...}`, `{"$template": ..., "vars": {...}}`, or arrays/objects of those.

| type | config | output / routing |
|---|---|---|
| `trigger.webhook` | `method`: GET or POST | entry marker. Also the entry used by every gateway-triggered test flow. |
| `trigger.schedule` | `cron` (string) | entry marker; schedule and doc-event are trigger nodes, nothing else is needed to fire them |
| `trigger.doc-event` | `doctype`, `event` in after_insert, on_update, on_submit, on_cancel, on_trash | entry marker |
| `trigger.unset` | `{}` | placeholder; a Flow with an unset trigger cannot be Active |
| `tool.call` | `tool_id` (literal Agent Tool Function name), `input` (object of Values), `timeout_ms?`, `approved?` | tool result |
| `transform` | `op` (20 ops below), `input` (object of Values) | op result (string, bool, list...) |
| `condition` | `expression`, `on_true`, `on_false` (node ids); no `next` | routes; see Conditions |
| `foreach` | `items` ($from ref), `body` (node ids), `max_iterations`, `on_item_error` fail/skip, `collect` ($from ref), `item_var?`, `index_var?` | list |
| `parallel` (pre-develop only; not a Flow node type on current builds) | `branches` (arrays of node ids), `join` const "all", `max_parallel_calls?` | after all branches |
| `validate` | `assertions[]` each `{expression, code, message}` | passes or fails run |
| `output` | `value` (Value); no `next` | final value; for a gateway run this is the reply text |
| `agent.run` | `agent`, `prompt`, `prompt_bindings?` | agent response (LLM; not deterministic) |
| `router.llm` | `prompt`, `options[{label,node_id}]`, `default` | LLM picks a branch |
| `router.decision` | `policy`, `options[{label,node_id}]`, `default` | policy picks a branch |
| `human.approval` | `message`, `approve_next`, `reject_next`, `timeout_next?`, `timeout_ms?` | sets run to Waiting Approval |
| `state.get` | `key` (Value), `default?` | `{found: bool, value}` |
| `state.set` | `key`, `value`, `ttl_seconds?` (1..2,592,000, or a Value) | stored |
| `state.delete` | `key` | `{deleted}` |
| `doc.create` | `doctype` (literal string), `fields` (object of Values) | `{doctype, name}` |

Notes confirmed in code:
- `http_request`, `loop`, `end` are NOT in `FLOW_NODE_TYPES`; a definition containing them cannot be saved. They survive in the
  engine only for old pinned runs. Use `tool.call` for HTTP-like needs, `foreach` for loops, and just omit `next` to end.
- `agent.run` / `router.llm`: the schema asks for `agent`/`prompt` and `prompt`/`options`/`default`, but the engine executors
  read `agent_name` and `router_agent_name` (flow_engine.py:884, :1137). A schema-valid node and the engine disagree. UNVERIFIED
  live; do not ship these nodes without running them on a test site. Prefer an Agent as the Gateway target instead.
- `human.approval` engine code reads extra keys (`approver_role`, `title`...) the schema forbids; only the schema keys are saveable.
- `tool.call` `config.gateway` is rejected by the schema (`Additional properties`), although `_bound_gateway` reads it. See Gateway.
- Flow Definition must be `status: Active` to run; Active needs a real trigger node (not `trigger.unset`), non-blank required
  config, no dangling targets and every node reachable. Draft/Archived saves are permissive about completeness.

Source: huf/ai/graph/validator.py, huf/ai/flow_engine.py, huf/huf/doctype/flow_definition/activation_rules.py

## Transform ops (exactly 20)
Row ops: `select, filter, sort, limit, group_by, aggregate, join, lookup, batch, distinct, coalesce`.
Text ops (inputs capped at 10,000 chars; null -> "", numbers/bools stringified; anything else is an error):

| op | input keys | result |
|---|---|---|
| `lower`, `upper`, `trim` | `text` | string |
| `replace` | `text`, `find` (non-empty), `with`, `count?` (int >= 0) | string |
| `contains` | `text`, `needle`, `ignore_case?` (true only) | bool; empty needle is true |
| `starts_with` | `text`, `prefix`, `ignore_case?` | bool |
| `split_first` | `text`, `separator?` (default whitespace) | first part |
| `regex_extract` | `text`, `pattern`, `group?` (default 0), `default?` (default null) | first match or `default` |
| `concat` | `parts` (list of scalars), `separator?` | string |

`regex_extract` subset limits: pattern 1..200 chars; only plain `(...)` and `(?:...)` groups (no lookaround, named or
conditional groups); no backreferences; no quantified group like `(ab)+`; `group` must not exceed the pattern's group count.
Text joining is `concat` (the row op `join` is a different thing).

Source: huf/ai/graph/transforms.py

## References and templates
- `{"$from": "<root>.<path>"}`: roots are `input` (the run's trigger payload/context), `trigger`, `row`, `foreach.item`,
  `foreach.index`, or an earlier node id (`lower`, `create_todo.name`, `list[0]`). Path grammar:
  `^(input|trigger|row|foreach.(item|index)|id)(.key|[n])*$`, max 256 chars.
- Missing path, missing key or out-of-range index resolves to null (never an error).
- `{"$template": "Refund for #{order}", "vars": {"order": {"$from": "extract.x"}}}`: `{name}` placeholders; `{{` and `}}` are
  literal braces. A placeholder not declared in `vars` fails the node; a declared var that resolves to null renders as `""`
  (so a missing number renders `#`); bool -> true/false; list/dict -> compact JSON; template <= 4,000, rendered <= 10,000 chars.
  Placeholders are identifiers only (no `{a.b}`): resolve the path in `vars`.

Source: huf/ai/graph/templates.py, huf/ai/graph/expressions.py, huf/ai/graph/graph_ir.schema.json

## Conditions
Superseded. Expression syntax (subscripts such as `input['amount'] > 100`, only `number/lower/startswith/endswith` calls, 500 chars)
is defined in `references/flows-authoring.md` section 4. The older `context["outputs"][...]` form described for pre-develop
is not valid on current builds.

## State (remember something between messages)
`state.get/set/delete` use the `Flow State` doctype (`flow_id, state_key, value_json, expires_at`), keyed to the running flow only
(config cannot name another flow). Key 1..140 chars (string or int); value JSON <= 16 KB; TTL default 24 h, max 30 days
(`ttl_seconds` 1..2,592,000). Expired rows read as missing and are purged lazily.
Doctype roles: System Manager, Huf Manager; nodes access it internally. Key per sender: `{"$template":"wa:{s}","vars":{"s":{"$from":"input.sender_id"}}}`.

Source: huf/ai/flow_state.py, huf/huf/doctype/flow_state/flow_state.json

## doc.create
`{doctype, fields}`; `doctype` must be a literal in site config `huf_flow_create_doc_doctypes` (list; default `["ToDo"]`).
Add more with `bench --site <site> set-config huf_flow_create_doc_doctypes '["ToDo","Lead"]' --parse`. Rules: the graph's
`permission_envelope.write` must list the doctype; each insert counts against `limits.max_writes`; the insert runs as the run's
session user with normal permission checks (no `ignore_permissions`); at most 30 fields; values scalar and <= 5,000 chars;
the field must exist, be writable, and not be a system, Table, Attach, layout or Geolocation field. A data-table-row hand-off
is not a Flow node: confirm the table's doctype first and add it to the allow-list (not confirmed for Huf Data Table).

Source: huf/ai/flow_create_doc.py, huf/ai/flow_engine.py (`_exec_doc_create`)

## Gateway-triggered flows and replies
- Route: Gateway `default_target_type = Flow` + `default_flow`, or a Gateway Binding (`target_type` Flow, `flow` link, `match_type`).
  Gateway Events with a Flow target call `create_flow_run(..., trigger_type="Gateway", ignore_permissions=True)` and enqueue
  `huf.ai.flow_engine.run_flow` (one run per event; redelivery does not start a second).
- Payload (read as `input.<field>`): `gateway_event, gateway, provider, sender_id, wa_id, conversation_id, thread_id, message_id,
  message, text, message_type, attachments[], reply_to_message_id, interactive_reply{id,title}`.
- Entry node: use `trigger.webhook` (there is no gateway trigger node type).
- Reply: when a Gateway run succeeds the engine takes the final `output` node's value (or `context.reply`; for a dict its
  `reply`, `text` or `message`) and sends ONE reply through the normal WhatsApp pipeline (formatting, split, opt-out check,
  `voice_reply_mode`). Empty text or the `<NO_REPLY>` sentinel sends nothing. A failed run marks the Gateway Event Failed; on current builds a plain "Something went wrong. Ref <event>." notice is
  also sent (see `flows-authoring.md` section 11). A run that ends in a non-output node replies with nothing unless `context.reply` is set.
- Extra messages mid-flow: send them with a `tool.call` to the `whatsapp` tool (e.g. `send_template`, `send_buttons`); the gateway
  is bound from the run's own Gateway Event, never from tool input; free-form sends obey the 24 h window and recipient scope.
- Doc-event and schedule runs have no Gateway Event, so a `tool.call` to the WhatsApp tool there fails closed with
  `gateway_context_required`; and `tool.call.config.gateway` cannot be saved. Outbound-from-doc-event is NOT possible in R. See recipe 3.

Source: huf/ai/gateway_service.py (`_flow_trigger_payload`, `_start_flow_for_event`, `finish_flow_event`), huf/ai/flow_engine.py (`_flow_reply_text`, `_bound_gateway`), huf/ai/tools/whatsapp.py, huf/huf/doctype/gateway_binding/gateway_binding.json

## Run-as user and permissions
- Gateway runs: Gateway `execution_user` (least-privileged, never Administrator) is the session user. The Flow Run is created on the
  gateway's behalf, so that user needs no Huf User role to start it, but `doc.create` and `tool.call` then run as it:
  grant it create rights on the target doctype (e.g. ToDo) or the node fails with `permission denied`.
- REST: `save_flow_definition` (current path `huf.ai.flow.api.save_flow_definition`) needs Flow Definition write; `run_flow` needs Flow Run create; Flow Definition and
  Flow Run roles are System Manager, Huf Manager, Huf User (Flow Definition also Huf Viewer).
- Builder tools (`huf/ai/tools/builder.py`) require System Manager or Huf Manager; an agent run as a lower user cannot author flows.
- Schedule and doc-event firing are `trigger.schedule` / `trigger.doc-event` nodes on current builds; there is no `set_flow_trigger`.

Source: huf/ai/gateway_service.py, huf/ai/flow_api.py, huf/ai/tools/builder.py

## Creating a flow (post-sync)
Superseded. Use `references/flows-authoring.md` sections 6 and 7 (`save_flow_definition`, `validate_flow_definition`,
`publish_flow`, `run_flow` with `mode="test"`, `get_flow_run`) under `huf.ai.flow.api.*`. Do not set `status` through
`PUT /api/resource`.
Template: `templates/target1/flow_definition.json.template`; example graph: `templates/target1/examples/whatsapp_triage_flow.json`.

## Known limits
- No multi-turn without state nodes: each inbound message is a new run; carry context with `state.set` keyed by sender.
- `context["outputs"]` / node outputs live in memory for one execution pass; they are not written to `context_json`, so they are
  not kept across a pause/resume (`Waiting Approval`, `Waiting User`). Re-derive or `state.set` what you need after a pause.
- Pre-develop only: no wait-for-reply node and no per-sender run lock; two quick messages can run in parallel. Current builds add
  Waiting Code and Cancelled statuses, approval timeouts (`timeout_next`) and `cancel_flow_run`; see `flows-authoring.md` sections 1, 7 and 10.
- Interactive taps arrive as new events (`interactive_reply`) that start a new run, not a resume of an old one.
- Pre-develop run status values: Queued, Running, Waiting Approval, Waiting User, Success, Failed (current builds also have Waiting Code and Cancelled).
- No flow seed directory: apps cannot ship flows through `app_seeding`.
- `max_wall_time_ms` and hop budget (default 100) bound runs; the enqueue timeout for gateway runs is 300 s.

Source: huf/ai/graph/executor.py, huf/ai/flow_engine.py, huf/huf/doctype/flow_run/flow_run.json
