# WhatsApp Templates, Template Guard and MCP Approval


Availability: bridge mode, templates, drafts, management API and agent-tool flags are **[pending: tridz-dev/huf PR #806]** per [gateways-and-whatsapp.md](gateways-and-whatsapp.md); direct-mode Graph sends and Gateway admission are **[available]**. Verified against the `huf-whatsapp-harden` branch, so confirm on the target site. Summary and decision questions: [gateways-and-whatsapp.md](gateways-and-whatsapp.md).

Read this when the app must send outside the 24h window (notifications, re-engagement), create templates, or call Meta's WhatsApp Business Tools MCP. Gateway basics (setup, tokens, window, tool actions) are in `whatsapp-gateway.md`.

Template list/create/edit/sync/draft features need **bridge mode** (`frappe_whatsapp` installed and the Gateway's `whatsapp_account` set). Without it they return `bridge_unavailable`; `send_template` still works through Graph directly. Templates are created post-sync (Desk, REST, or agent draft), never as seed files, because they need a live WABA and Meta review.

Source: docs/WHATSAPP_INTEGRATION_SETUP.md, huf/ai/gateway_adapters/whatsapp_bridge.py

## 1. Lifecycle: draft -> human approval -> submit -> status

```
agent / user   create_template_draft         WhatsApp Template Draft (status Pending Review)
admin          approve_template_draft  ----> validates again, submits to Meta ONCE (Approved & Submitted)
               reject_template_draft         Rejected, Meta never contacted
Meta           review                        webhook / sync_templates update the status
```

- Draft statuses: `Draft`, `Pending Review`, `Submitting`, `Approved & Submitted`, `Rejected`, `Failed`.
- Direct admin path: `create_template` (POST) validates, pushes straight to Meta, mirrors a `WhatsApp Templates` row.
- Meta statuses HUF tracks: APPROVED, PENDING, REJECTED, PAUSED, DISABLED, IN_APPEAL, LIMIT_EXCEEDED, PENDING_DELETION, DELETED. HUF keeps rejection reason, quality (GREEN/YELLOW/RED/UNKNOWN) and a pending category change in `WhatsApp Template State`; each change publishes realtime event `whatsapp_template_status`.
- Run `sync_templates` after creating or after Meta edits; it imports templates that exist only on Meta and refreshes status/category/components. Do not use frappe_whatsapp's "Fetch templates" button in Desk; it bypasses HUF.

Source: huf/huf/doctype/whatsapp_template_draft/whatsapp_template_draft.json, huf/ai/gateway_adapters/whatsapp_bridge.py

## 2. REST (admin unless noted)

Base: `/api/method/huf.ai.whatsapp_management.<fn>`.

| Function | Method | Args |
|---|---|---|
| `list_templates` | GET | `gateway_name` (or `account`), `status` |
| `get_template` | GET | `name` |
| `create_template` | POST | `gateway_name` (or `account`), `payload` (object) |
| `edit_template` | POST | `name`, `payload` |
| `delete_template` | POST | `name` (`template_in_use` if it was ever sent) |
| `sync_templates` | POST | `gateway_name` or `account` |
| `create_template_draft` | POST | `gateway_name`, `payload`, `submit_for_review` (default 1); non-admins need create permission on the draft doctype |
| `list_template_drafts` | GET | `gateway_name` |
| `approve_template_draft` / `reject_template_draft` | POST | `name`, `note` |
| `send_template_message` | POST | `gateway_name`, `to`, `template_name`, `body_params`, `header_params`, `button_params`, `language_code` (needs Gateway write authority; allowed outside window; 60 calls/min) |

"Admin" means System Manager or Huf Admin.

Source: huf/ai/whatsapp_management.py

## 3. Template payload and limits

`payload` keys (validated before anything reaches Meta; errors come back as `{"success": false, "error": "validation_failed", "errors": [{field, code, message}]}`):

| Key | Rules |
|---|---|
| `template_name` | `^[a-z0-9_]+$`; `language_code` required (for example `en_US`) |
| `category` | `UTILITY` or `MARKETING`. `AUTHENTICATION` is rejected (`category_not_supported`) |
| `body` (alias `template`) | required, <= 1024 chars, cannot start or end with a variable; either `{{1}}`, `{{2}}` in order (POSITIONAL) or `{{name}}` lowercase (NAMED); do not mix |
| `parameter_format` | `POSITIONAL` or `NAMED`; inferred when omitted |
| `sample_values` | one example per body variable (list or comma string); `named_samples` for NAMED |
| `header_type` / `header` | TEXT (<= 60 chars, at most one variable), IMAGE, VIDEO, DOCUMENT, LOCATION |
| `sample` | TEXT header with variable: example value. Media header: public https URL or an uploaded File path |
| `footer` | <= 60 chars, no variables |
| `buttons` | `[{type, text, ...}]`; types `QUICK_REPLY`, `URL` (+`url`, trailing `{{1}}` needs `example`), `PHONE_NUMBER` (+`phone_number`), `COPY_CODE`. Button text <= 25 chars |
| `ttl_seconds` | UTILITY only; 30..43200, or -1 for 30 days |

Category guidance: UTILITY for transactional updates (order, appointment, receipt); MARKETING for promotions. Meta may re-classify a template; HUF records `correct_category`/pending change from the `template_category_update` webhook. Marketing sends are refused for contacts who stopped marketing. Meta's own Business Suite "messaging campaigns" have no API; HUF only sends single-recipient templates.

Not supported: AUTHENTICATION templates, carousel, flow and catalog buttons, editing name or language. Edits follow Meta's rules (APPROVED: once per 24h, 10 per 30 days; REJECTED/PAUSED unlimited); HUF checks locally first.

Source: huf/ai/gateway_adapters/whatsapp_templates.py, huf/ai/whatsapp_management.py

## 4. Template guard

HUF-owned rows in `WhatsApp Templates` are protected: Desk saves and deletes are refused ("This template is managed by Huf. Edit it from the WhatsApp page.") unless they come through HUF's own code path (`huf_template_write`). Edit and create through the management API or the HUF WhatsApp page, never by writing the doctype directly or from app code. HUF-side sidecars: `WhatsApp Template Extra` (parameter format, components, ttl) and `WhatsApp Template State`.

Source: huf/ai/gateway_adapters/whatsapp_template_guard.py

## 5. Using templates from an agent

Gateway checkboxes (all off by default, server-side only):

| Field | Effect |
|---|---|
| `agent_allow_template_management` | permits tool action `create_template` (saves a **draft** only) |
| `agent_auto_submit_templates` | with the above, `create_template` submits directly to Meta (skip human approval; avoid unless asked) |
| `agent_allow_proactive` | free-form sends outside the window; **not needed** for `send_template` |

Tool actions on the `whatsapp` tool:
- `list_templates` (`status` filter; rows show status and rejection reason).
- `create_template`: `template_name`, `category`, `language_code`, `body`, `sample_values`, optional `header_type`, `header`, `sample`, `footer`, `buttons`. Returns `status: pending_review` and a draft name. Do not retry; a human approves in the console. Needs the Gateway's write authority for the run user. Refused with `management_not_permitted` if the flag is off.
- `get_template_status`: `template_name` (a template name or the draft name) returns Meta status, rejection reason, quality, draft state.
- `send_template`: `template_name`, `language_code` (default `en`), `parameters`, `header_params`, `button_params`; `to` optional (current contact).
  - `parameters`: list of strings for `{{1}}...`, or `{name: value}` for NAMED templates. Values must not be empty or contain newlines, tabs or 4+ spaces.
  - `header_params`: one text string, or `{"type": "image|document|video", "link": "https://..."}`, or `{"type": "location", "latitude": ..., "longitude": ...}`.
  - `button_params`: `[{"index": 0, "sub_type": "url", "text": "<suffix>"}]` for dynamic URL buttons.
  - Refusals: `opted_out`, `bsuid_recipient`, `template_not_approved`, `recipient_not_permitted`, `send_cap_exceeded`, `gateway_disconnected`.

A template send to a contact with no access entry is remembered so their later STOP is honoured.

Source: huf/ai/tools/whatsapp.py, huf/ai/tools/_registry.py, huf/ai/whatsapp_outbound_policy.py

## 6. Using templates from a flow

A deterministic flow has no LLM. Use a `tool.call` node whose `tool_id` is the HUF Tool named `whatsapp` (function `huf.ai.tools.whatsapp.handle_action`) and whose `input` holds the action args; `{"$from": ...}` references are resolved from flow context.

```json
{"type": "tool.call",
 "config": {"tool_id": "whatsapp",
            "input": {"action": "send_template", "template_name": "order_update",
                      "language_code": "en_US", "parameters": ["Asha", "A-1042"],
                      "idempotency_key": "order-A-1042-shipped"}}}
```

Rules: the saved `tool.call` config schema allows only `tool_id`, `input`, `timeout_ms` and `approved` (anything else is rejected), so the Gateway cannot be named in the node. The `whatsapp` tool uses the Gateway of the Gateway Event that started the flow run (gateway trigger); a flow started any other way (cron, doc event) gets `gateway_context_required`. `to` defaults to the triggering sender; any other number is subject to `agent_recipient_scope` and caps. Always set `idempotency_key` for retried or repeated sends. Node field names are listed in `flows-authoring.md` section 5 (indicative: verify against the target build).

Source: huf/ai/flow/engine.py, huf/ai/tests/test_flow_gw33_gateway_send.py

## 7. Fallback template for closed windows

Gateway `fallback_template` + `fallback_template_language` (+ optional `fallback_template_params`) is what the reply pipeline sends when the agent answers after the 24h window. Pick an APPROVED template with a plain header. Health warns (`fallback_template_unavailable`) when Meta marks it REJECTED, PAUSED or DISABLED.

Source: huf/huf/doctype/gateway/gateway.py, docs/gateways/whatsapp-runbook.md

## 8. MCP approval gate and Meta WhatsApp Business Tools MCP

**Approval gate (PR #823 per the plan; behaviour confirmed in code).** Syncing an MCP Server creates one tool row per remote tool; tools without `readOnlyHint` get `requires_approval = 1` by default, read-only tools 0. An agent calling a `Requires Approval` tool is refused with `approval_required: true` (message: turn off Requires Approval, or call it from a flow `tool.call` node with `approved` set after a `human.approval` node). A flow that needs a mutating MCP tool therefore needs:

`human.approval` node -> `tool.call` node with `"approved": true` (the MCP server is found by tool name, so the name must be unique across servers).

Re-syncing keeps the admin's `requires_approval` choice. Never mark a send/mutate tool as not requiring approval just to make a demo pass.

**Meta WhatsApp Business Tools MCP status (observed 2026-10-22).** The Meta app dashboard shows a "WhatsApp Business Tools MCP" banner. OAuth/consent/token exchange was verified with the real Meta server on 2026-10-22; the WhatsApp Business Tools MCP server returned **401 "restricted to certain users"** for the tested account (beta rollout). Treat it as unavailable until a call succeeds for your account: do not build an app that depends on it, and use HUF's own `whatsapp` tool and management API instead. If it becomes available, add it as an MCP Server, sync, keep approval on for non-read-only tools, and verify with one read-only call first.

Source: huf/ai/mcp_client.py, huf/ai/flow/engine.py
