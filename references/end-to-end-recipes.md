# End-to-end recipes (WhatsApp)

Three worked builds. Placeholders in angle brackets: `<SITE_URL>`, `<KEY>:<SECRET>` (API key and secret of a System Manager
or Huf Manager), `<GATEWAY>`, `<EXEC_USER>`, `<FLOW_ID>`, `<AGENT>`. Gateways, WhatsApp accounts, templates and flows are NOT
seed folders: create them after sync. Concepts: `references/flows.md`; Gateway setup: `references/whatsapp-gateway.md`;
templates: `references/whatsapp-templates.md`; voice: `references/audio-and-media.md`.

Source: huf/ai/app_seeding/seeder.py

## Recipe 1: non-LLM WhatsApp support triage
Goal: reply to keywords `order`, `refund`, `hours`, `human` and numeric options 1 to 4 without any LLM; remember a pending refund
across two messages; log hand-offs as ToDo rows; reply with the extracted order number. Graph:
`templates/target1/examples/whatsapp_triage_flow.json` (28 nodes, validated with the real Huf validator).

How it branches: `input.message` -> `trim` -> `lower` -> `state.get` key `wa:<sender_id>`.
- State found (a refund is pending): `regex_extract` digits; digits found -> `doc.create` ToDo, `state.delete`, reply
  "Refund logged for order #4521. Reference <ToDo name>"; no digits -> fall through to the normal keyword chain.
- Not pending: `contains` order -> (or text "1") -> digits ? "checking order #N" : "which order?"; `contains` refund (or "2") ->
  `state.set` `{"awaiting":"order_number"}` with TTL 600 s, reply "Please send your order number"; `contains` hours (or "3") -> hours
  text; `contains` human (or "4") -> `doc.create` ToDo "WhatsApp hand-off from <sender>: <message>", reply with the reference;
  anything else (including "menu") -> menu text "1 order status, 2 refund, 3 opening hours, 4 talk to a person".
- Branch order is fixed: order, refund, hours, human, menu. A pending refund captures digits, so "4" while pending logs order #4.
- Every branch ends in an `output` node, so exactly one reply is sent.

### Steps
1. Allow the doctype (ToDo is the default, so nothing to do). For another doctype:
   `bench --site <SITE> set-config huf_flow_create_doc_doctypes '["ToDo"]' --parse`.
2. Validate offline before touching a site (no bench, no frappe; `R` = a Huf checkout; stubs the two frappe imports):
   ```
   python3 -I - /path/to/huf-repo <<'PY'
   import sys,types,json; from unittest.mock import MagicMock
   R=sys.argv[1]; sys.modules["frappe"]=MagicMock()
   for n,s in (("huf","huf"),("huf.ai","huf/ai")):
       m=types.ModuleType(n); m.__path__=[f"{R}/{s}"]; sys.modules[n]=m
   t=types.ModuleType("huf.ai.tool_registry")
   class PermissionAwareToolRegistry: TOOL_PERMISSIONS={}
   t.PermissionAwareToolRegistry=PermissionAwareToolRegistry; sys.modules["huf.ai.tool_registry"]=t
   from huf.ai.graph.validator import validate_flow_graph
   from huf.ai.graph.permissions import ToolPermission
   r=validate_flow_graph(json.load(open("templates/target1/examples/whatsapp_triage_flow.json")),
       classify_tool=lambda i: ToolPermission(ptype=None,doctype=None,http=False,code=False))
   print(r.ok, [str(e) for e in r.errors])
   PY
   ```
   Expected `True []`. Needs `jsonschema` installed.
3. Create the Draft (the save runs the same validator):
   ```
   curl -sS -X POST "<SITE_URL>/api/method/huf.ai.flow_api.save_flow_definition" \
     -H "Authorization: token <KEY>:<SECRET>" -H "Content-Type: application/json" \
     -d "$(jq -n --slurpfile d templates/target1/examples/whatsapp_triage_flow.json '{flow_id:"<FLOW_ID>",definition_json:$d[0]}')"
   ```
4. Activate: `curl -sS -X PUT "<SITE_URL>/api/resource/Flow%20Definition/<FLOW_ID>" -H "Authorization: token <KEY>:<SECRET>" -H "Content-Type: application/json" -d '{"status":"Active"}'`
   (errors list every activation problem at once).
5. Smoke-run without WhatsApp (synchronous, trigger Manual; the caller needs ToDo create rights):
   ```
   curl -sS -X POST "<SITE_URL>/api/method/huf.ai.flow_api.run_flow" -H "Authorization: token <KEY>:<SECRET>" \
     -H "Content-Type: application/json" \
     -d '{"flow_id":"<FLOW_ID>","payload":{"message":"  REFUND please ","sender_id":"15550001111"}}'
   ```
   Expect `"status":"Success"`. Send the second message `Order 4521` with the same `sender_id`, then check:
   - `GET <SITE_URL>/api/resource/ToDo?filters=[["description","like","Refund request for order #4521%"]]` returns one row;
   - `GET <SITE_URL>/api/resource/Flow State?filters=[["flow_id","=","<FLOW_ID>"]]` is empty after message 2 (and has a row
     `wa:15550001111` after message 1);
   - `GET <SITE_URL>/api/method/huf.ai.flow_api.get_flow_run?flow_run_id=<RUN>` shows `status` and `last_error`.
   The reply text itself is not stored (node outputs are in memory); it is only observable on a real Gateway run, or in a Huf test
   that spies `GraphContext.record_output` (`huf/ai/tests/test_flow_triage_e2e.py`).
6. Route the Gateway: set `default_target_type` = Flow and `default_flow` = `<FLOW_ID>` on Gateway `<GATEWAY>`, or add a Gateway
   Binding (`target_type` Flow, `flow`, `match_type`). Check the route without sending:
   `POST /api/method/huf.ai.gateway_service.preview_gateway_route` with `{"gateway_name":"<GATEWAY>","context":{...}}`.
7. Grant `<EXEC_USER>` (Gateway "Run as user") create permission on ToDo; otherwise `doc.create` fails with `permission denied`.
8. Live check: send "refund" from a real or test phone; expect "Please send your order number."; then "order 4521"; expect
   "Refund logged for order #4521. Reference <ToDo name>". Confirm in Desk: Gateway Event `status` Succeeded, `flow_run` linked;
   Flow Run `trigger_type` Gateway, `status` Success; ToDo created.

### Pitfalls
- `human` creates a row only; nobody is notified. Add an Assignment/Notification rule on ToDo in Frappe if someone must act.
- One run per message; no per-sender lock, so two fast messages can race on the state key.
- State key is per sender and per flow; TTL 600 s on `remember_refund` means the pending refund silently expires after 10 minutes.

Source: huf/ai/tests/test_flow_triage_e2e.py, huf/ai/gateway_service.py, templates/target1/examples/whatsapp_triage_flow.json

## Recipe 2: an Agent answering on WhatsApp with voice replies
Goal: an LLM Agent behind a WhatsApp Gateway; if the customer sends a voice note the agent answers with a voice note.
No Flow is needed: the Gateway default target is an Agent.

### Steps
1. Seed the agent as usual (`templates/target1/agent.json.template`, plus prompt/tools/knowledge). In the Agent set `stt_model`
   (speech to text, AI Model link) and `tts_model` (text to speech, AI Model link); if unset the provider default is used.
   Model keys and options: `references/models-and-keys.md`; voice and media behaviour: `references/audio-and-media.md`.
2. After sync create the Gateway (WhatsApp provider, credentials, webhook) per `references/whatsapp-gateway.md`. Set:
   `default_target_type` = Agent, `default_agent` = `<AGENT>`, `execution_user` = `<EXEC_USER>` (least-privileged, with access to
   the agent), `voice_reply_mode` in `Off` | `Voice only` | `Text and voice`.
   Per the field help: `voice_reply_mode` answers a customer's voice note with the agent's TTS model, needs ffmpeg on the server,
   and replies over 1500 characters (or any failure) fall back to text.
3. Check readiness and routing before testing: Gateway form checklist (route target, execution user, credentials), and
   `POST /api/method/huf.ai.gateway_service.preview_gateway_route` `{"gateway_name":"<GATEWAY>","context":{...}}`.
4. Verify: send a text; expect a text answer. Send a voice note; expect a voice note (mode `Voice only`) or text + voice
   (`Text and voice`). In Desk, the Gateway Event shows `status` Succeeded, `agent_run` linked, `reply_status` and `delivery_error`
   (empty on success). A text answer to a voice note means TTS/ffmpeg failed: read `references/audio-and-media.md`
   and `references/testing-and-pitfalls.md`.
5. If the agent must send media or templates itself, give it the `whatsapp` tool; the gateway is bound from the conversation and
   the recipient defaults to the current contact.

### Pitfalls
- `voice_reply_mode` applies when the customer wrote a voice note; a text question still gets text.
- The execution user must be able to run the agent, or `Gateway` validation refuses to enable it.
- Do not set a flow and an agent as the same default route: one `default_target_type` only.

Source: huf/huf/doctype/gateway/gateway.json, huf/huf/doctype/agent/agent.json, huf/ai/gateway_service.py

## Recipe 3: template-based outbound notification
Goal: send an approved WhatsApp template (e.g. "refund received, order {{1}}") from a Flow.

What works in R (pre-develop): a Gateway-triggered Flow sending a template to the sender who just wrote in.
What does NOT work in R: a template sent from a doc event or schedule (e.g. Sales Order submitted -> notify customer). Reasons,
all confirmed in code: (1) the WhatsApp tool takes its gateway only from a Gateway Event of the run or a trusted node binding;
doc-event / schedule runs (via `set_flow_trigger`, an Automation) have neither, so the tool returns `gateway_context_required`;
(2) `tool.call.config.gateway` is rejected by the graph schema, so the node-level binding cannot be saved; (3) Automation
`target_type` is Agent or Agent Procedure only. Do not promise proactive doc-event messaging with a Flow; say so in the plan.

### Steps (supported variant, template after the reply)
1. Create and get the template approved first (`references/whatsapp-templates.md`); note its exact `template_name`, language and
   number of body placeholders. `send_template` is not limited by the 24 h window, but opt-out and recipient scope still apply.
2. Add to the triage graph, between `clear_state` and `reply_refund_logged`, a node (the validator derives the envelope from the tool's
   registered permission on your site; re-save and read any `ENVELOPE_UNDER_DECLARED` error):
   ```
   { "id": "notify_template", "type": "tool.call",
     "config": { "tool_id": "<WHATSAPP_TOOL_NAME>",
       "input": { "action": "send_template", "template_name": "<TEMPLATE_NAME>", "language_code": "en",
                  "parameters": [ { "$from": "extract_refund_num" } ] } },
     "next": "reply_refund_logged" }
   ```
   and point `clear_state.next` at `notify_template`. `<WHATSAPP_TOOL_NAME>` is the Agent Tool Function name of
   `huf.ai.tools.whatsapp.handle_action` (the built-in registry name is `whatsapp`; confirm it exists on the site). Omit `to`: the
   recipient defaults to the sender. `parameters` is a list of strings filling `{{1}}`, `{{2}}` in order (a `{name: value}` map is
   also accepted).
3. Save, activate, then run a real gateway conversation (the Manual smoke run has no Gateway Event, so the tool refuses with
   `gateway_context_required`; that refusal is itself the proof of the binding rule).
4. Verify: Meta delivers the template (Gateway Event `Succeeded`, the phone shows the template); then the text reply
   follows. A recipient who opted out is suppressed.
5. To prove the doc-event limitation on your build before promising anything: save a flow `trigger.doc-event` -> `tool.call`
   (`send_template`), call `huf.ai.flow_api.set_flow_trigger` (`flow_id`, `trigger_type="doc_event"`, `reference_doctype`,
   `doc_event`), fire the event, read the run output: expect `gateway_context_required`. If a newer Huf adds a gateway binding for
   doc-event runs, re-check `references/flows.md` first.

### Pitfalls
- Two messages (template then text reply) can look like a duplicate; use one or the other unless both are intended.
- Template parameters are strings; format dates and amounts before (`concat`, `replace`).
- Not confirmed: Meta-side delivery receipts feeding back into the Flow Run (none stored on the run).

Source: huf/ai/tools/whatsapp.py, huf/ai/flow_engine.py, huf/ai/graph/graph_ir.schema.json, huf/huf/doctype/automation/automation.json
