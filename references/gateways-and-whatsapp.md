# Gateways and WhatsApp (reference)

Read this when the app needs an external messaging channel (WhatsApp, Telegram, Slack, Email, ...) to reach an Agent or Flow, or to send messages out. Apply only to Target 1 (seeded inside a bench); a Target 2 app talks to HUF over REST and does not configure Gateways.

Availability tags: **[available]** works today on the released/integration branch (`pre-develop`); **[pending: PR]** implemented in an unmerged PR or branch, so not on a stock site (check the target site); **[experimental/shadow]** built but off by default or unmerged, not safe to depend on; **[planned]** designed or decided, not built. In this file, **[pending: tridz-dev/huf PR #806]** is the WhatsApp bridge, templates, management API and drafts.

## 1. What a Gateway is  **[available]**

A Gateway is one configured inbound/outbound channel with admission rules and a service identity. Four DocTypes:

| DocType | Role |
| --- | --- |
| `Gateway` | One channel: `provider`, `is_enabled`, `integration_settings` (credentials live there), `execution_user`, admission policies, default target |
| `Gateway Binding` | Routing rule: match (any / direct / room / thread / sender) to an Agent or Flow; lowest `priority` number wins |
| `Gateway Event` | Immutable audit record of each inbound event (status, target, run link, redacted payload) |
| `Gateway Access Entry` | Approved / pending / revoked sender or room (used by Pairing and Allow list) |

Registered providers: WhatsApp, Messenger, Instagram, Telegram, Slack, Email, Google Chat, Microsoft Teams. Discord, SMS, VK and WeCom are not selectable.

Admission policies on `Gateway`:

| Field | Values | Notes |
| --- | --- | --- |
| `direct_policy` | Disabled, Pairing, Allow list, Open | `Open` is rejected at save. Use Pairing or Allow list. |
| `room_policy` | Disabled, Allow list, Open | Group/channel admission |
| `room_sender_policy` | Allow list, Open | Senders inside admitted rooms |
| `mention_required` | check | Room messages must mention the gateway |

Pairing: an unapproved DM creates a Pending `Gateway Access Entry` and a `PAIR-XXXX` code; a user with write permission approves it (`huf.ai.gateway_service.approve_gateway_pairing`). No agent runs before approval.

### execution_user (hard rule)

All work triggered by an inbound event runs as the Gateway's `execution_user`.

- Required when the gateway is enabled.
- Must hold a role from the `huf_gateway_execution_roles` hook (default `Huf Gateway User`).
- Must have execution access to the default Agent.
- **Never Administrator.** Never a real person's account. Use a dedicated low-privilege service user and grant it only what the target Agent/Flow needs.

## 2. What an app can and cannot seed

Gateways need credentials (tokens, app secrets, verify tokens). An app must never ship them.

| Seed it in the app | Do NOT seed |
| --- | --- |
| The Agent and/or Flow the channel will route to (and its prompt, tools, knowledge) | `Gateway` records (need `Integration Settings` credentials and an `execution_user`) |
| `Gateway Binding` rows, only if they can reference a Gateway by a name you document (see below) | `Integration Settings` credentials, tokens, app secrets, verify tokens |
| A "Gateway setup" section in the app README / hand-off | `Gateway Access Entry` rows (they hold real sender ids) |
| A suggested `execution_user` role and permission list | An enabled Gateway of any kind |

Rule of thumb: the app ships the target; the installer creates and enables the Gateway.

Hand-off text to give the installer (adapt per app):

1. Create `Integration Settings` for the provider and enter credentials yourself.
2. Create a `Gateway` (provider, linked settings, a dedicated `execution_user`, `direct_policy` Pairing or Allow list).
3. Set `default_target_type` to the shipped Agent or Flow, or add Bindings.
4. Enable the Gateway, then register the callback URL with the provider.

A Binding cannot exist without its parent Gateway, so do not seed Bindings unless the user explicitly agrees on a fixed `gateway_name` and the installer is told to create it first. Safer default: use the Gateway's `default_agent` / `default_flow`, set by the installer.

## 3. Routing and conversations  **[available]**

Resolution order for an admitted inbound event: matching enabled `Gateway Binding` (by `priority`, lowest first), else the Gateway default target (`default_target_type` = Agent or Flow), else the event is `Unrouted`.

- Targets are Agent or Flow. **Routing to a Hub target is not confirmed in the gateway code reviewed; treat as [planned] unless the target site proves otherwise.**
- Preview a route without running work: `huf.ai.gateway_service.preview_gateway_route`.
- Event states: Received, Rejected, Unrouted, Queued, Running, Succeeded, Failed. Inspect `Gateway Event` for errors; `Gateway.last_error` shows the latest problem.
- Dedupe is on the provider event id, so retries from the provider do not run the agent twice.

Conversation continuity: the agent run uses `channel_id = gateway:<gateway_name>` and `external_id` = the normalised sender/conversation id (for WhatsApp, the normalised wa_id). The same contact keeps the same conversation across messages; design prompts and memory with that in mind.

Reply policy: after the agent finishes, the reply is sent back through the same Gateway to the same conversation. Text-only for most adapters today; media and interactive messages are not part of the shared contract (WhatsApp has its own media-by-link path, see section 5).

## 4. Provider notes  **[available]**

- Inbound requests are signature-verified and fail closed (HMAC or provider token). A gateway without its secret cannot be enabled.
- Email inbound uses a document hook, not the webhook route; its signature check is not on the real path. Do not rely on it for authentication.
- Teams and Google Chat verification is incomplete; avoid promising them in a shipped app without checking current status.
- Callback URL pattern: `/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=<Gateway>`.

## 5. WhatsApp specifics

### Modes

| | Direct mode **[available]** | Bridge mode **[pending: tridz-dev/huf PR #806]** |
| --- | --- | --- |
| Requires | WhatsApp Gateway + Integration Settings | Optional `frappe_whatsapp` app installed and `Gateway.whatsapp_account` set |
| Inbound | Signed Huf webhook, Gateway Event, agent | Same, plus mirrored into `WhatsApp Message` |
| Outbound | Huf calls Meta Graph directly | Huf inserts an Outgoing `WhatsApp Message`; `frappe_whatsapp` sends |
| Templates, message history, drafts | Not available (`bridge_unavailable`) | Available |

HUF core must work without `frappe_whatsapp`. Never make an app depend on it unless the user wants templates/management; if they do, state that dependency in the hand-off and keep the base flow working without it.

If bridge mode is used, block the unsigned `frappe_whatsapp` webhook (`/api/method/frappe_whatsapp.utils.webhook.webhook`) at the proxy so only HUF's signed endpoint accepts Meta callbacks.

### 24-hour window and fallback template  **[pending: tridz-dev/huf PR #806]**

- Window = 24h from the user's last signed inbound message timestamp (computed from Gateway Events).
- Window open: free-form text or media.
- Window closed: send the Gateway's `fallback_template` (+ `fallback_template_language`), or the event fails with a readable error.
- Only text inbound opens the window. Location, contact and reaction messages do not.
- If the app needs to message people first (reminders, notifications), it needs an approved template and a fallback template configured by the installer.

### Templates  **[pending: tridz-dev/huf PR #806]**

- Create (header text/media, body variables, footer, buttons), edit/resubmit, delete, sync (imports templates that exist on Meta), send with parameters.
- Meta rules: sample values required; a variable cannot start or end the body; Meta may reclassify the category (for example UTILITY to MARKETING); approved templates allow limited edits (1 per 24h, 10 per 30 days); name and language are immutable.
- Approval workflow: an agent or user creates a `WhatsApp Template Draft`; a human approves or rejects it in HUF; on approval it is submitted to Meta once. Meta then reviews it (APPROVED / REJECTED / PAUSED).
- Template status and quality updates arrive only on the Meta app's default callback; route by WABA id.

### Server-side flags (Integration Settings, never LLM arguments)

| Flag | Effect |
| --- | --- |
| `allow_proactive` | Agent may send free-form messages to numbers with no open window |
| `allow_whatsapp_management` | Agent may create templates (as drafts); also allows proactive free-form sends |
| `auto_submit_templates` | With `allow_whatsapp_management`, agent-created templates go straight to Meta instead of a draft |

These are set by the installer/admin, default off, and are stripped if an LLM passes them as tool arguments. An app must not seed them on; list them in the hand-off as opt-in.

### Agent tool actions  **[pending: tridz-dev/huf PR #806]**

One consolidated WhatsApp tool with an `action` parameter: `send_message`, `send_media`, `send_template`, `list_messages`, `get_account_info`, `list_templates`, `create_template`, `get_template_status`. Credentials are never tool parameters. Check which actions exist on the target site before writing prompts that call them.

### Management API  **[pending: tridz-dev/huf PR #806]**

Python/whitelisted methods under `huf.ai.whatsapp_management`: `get_setup_status`, `list_templates`, `get_template`, `create_template`, `edit_template`, `delete_template`, `sync_templates`, `create_template_draft`, `list_template_drafts`, `approve_template_draft`, `reject_template_draft`, `send_template_message`, `send_text_message`, `send_media_message`, `list_messages`, `list_conversations`. Mutating calls are POST and permission-gated; the account is always derived from the Gateway. Realtime event: `whatsapp_template_status`.

### Multiple gateways  **[pending: tridz-dev/huf PR #806]**

- Several WhatsApp Gateways may exist; each has its own callback URL (`?gateway_name=`), settings, execution user, policies and default target.
- One enabled Gateway per `phone_number_id`.
- Several numbers under one Meta app: use Meta's per-number or per-WABA callback override so each number posts to its own Gateway URL (check Meta's current docs for the request body).
- Templates, windows and conversations are scoped per gateway and contact.

### Not supported

- Inbox, assignment, shared conversations, CRM features (use a CRM app).
- Interactive messages (lists, buttons), WhatsApp Flows, bulk sends, notification campaigns.
- Authentication templates and video headers.
- Outbound media except by public link.
- Routing by `phone_number_id` with a shared app credential **[planned]**.
- First-party "Manage WhatsApp" app tile gated on an enabled WhatsApp Gateway **[planned]**.
- Live inbound verification was not complete when this was written; treat inbound as unconfirmed on the bridge branch until the target site is tested.

## 6. Decision questions to ask the user (Step 1)

Ask as one bundled question when the app involves messaging:

1. Does the app need an external channel at all (users messaging the agent from WhatsApp, Telegram, Slack, Email), or is HUF's own chat enough?
2. Which gateway kind(s)? Do they already have a provider account and credentials, or will the installer create them?
3. Inbound only, or should the agent send messages out too (replies only, or proactive)?
4. WhatsApp: direct mode, or bridge mode (adds templates, history, drafts, requires `frappe_whatsapp` and PR #806 on the site)?
5. Proactive sends allowed (`allow_proactive`)? If yes, which approved template is the fallback outside the 24h window?
6. Who approves templates: a human in HUF (drafts, default) or auto-submit (`auto_submit_templates`)? Who owns the Meta side?
7. Who is allowed to message the agent: Pairing, Allow list, groups with mentions? (`Open` direct is not allowed.)
8. Which low-privilege user will be the `execution_user`, and what may it touch?
9. One number or several (one Gateway per number)? Is the app for personal use or to ship to other sites? (Shipping: never include credentials, numbers or sender ids.)

## 7. Hand-off checklist

- [ ] No credentials, phone numbers, sender ids or Gateway records in the seed.
- [ ] Target Agent/Flow seeded and works from HUF chat before any gateway is attached.
- [ ] README tells the installer: create Integration Settings, create Gateway, set `execution_user` (not Administrator), pick policy, set default target, enable, register callback URL.
- [ ] WhatsApp-only: window/fallback template, flags, and `frappe_whatsapp` dependency stated explicitly with their status tags.
