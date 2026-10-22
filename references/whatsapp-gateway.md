# WhatsApp Gateway on HUF

Read this when the app must receive or send WhatsApp messages. Everything here is a **post-sync setup**: the HUF app seeder only accepts `prompts, tools, knowledge, agents, triggers`, so Gateways, Integration Settings and WhatsApp Accounts are created in Desk/REST after the app is synced, never as seed folders. Never write real tokens into seed files, prompts or chat; use placeholders such as `<ACCESS_TOKEN>`.

Source: huf/ai/app_seeding/seeder.py, docs/gateways/whatsapp-runbook.md

## 1. What a Gateway is

A **Gateway** doc binds one channel (`provider` = `WhatsApp`) and one phone number to HUF. It owns credentials (via `integration_settings`), admission rules, consent, the default route (`default_target_type` Agent or Flow, `default_agent`, `default_flow`), health state and agent send limits. Inbound webhooks become **Gateway Event** rows; each runs the default Agent or Flow as `execution_user` (never `Administrator`).

- One enabled Gateway per `phone_number_id`. Several numbers need several Gateways.
- Two modes: **direct** (Graph API only) and **bridge** (`frappe_whatsapp` installed and `whatsapp_account` set). Template list/create/sync, message history and `list_templates`/`create_template` tool actions need bridge mode (otherwise `bridge_unavailable`). Text/media/template sends work in both.

Source: huf/huf/doctype/gateway/gateway.json, docs/WHATSAPP_INTEGRATION_SETUP.md

## 2. Setup, step by step

1. **Meta**: create a Meta app with the WhatsApp product; note the WhatsApp Business Account id (WABA) and the **Phone Number ID**.
2. Create a **permanent system-user token** (not the 24h test token) with messaging and management scopes. Copy the **App Secret** (App settings > Basic). Choose any **verify token** string.
3. **Integration Settings** record, service `whatsapp`, credential keys: `phone_number_id`, `access_token`, `webhook_verify_token`, `app_secret`. The adapter refuses to start without all four.
4. **Gateway**: `provider` WhatsApp, `integration_settings` = the record above, `execution_user` = least-privilege user, `direct_policy` (section 3), `default_target_type` + `default_agent`/`default_flow`, `is_enabled` checked. `phone_number_id` is derived on save.
5. Optional bridge mode: `bench get-app https://github.com/shridarpatil/frappe_whatsapp`, install on the site, create a **WhatsApp Account** (`phone_id`, `token`, `business_id`, `url`, `version`) and link it in `whatsapp_account`. Its `phone_id` must equal the Gateway phone id.
6. **Meta webhook** (WhatsApp > Configuration):
   - Callback URL: `https://<site>/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=<Gateway name>`
   - Verify token = `webhook_verify_token`; click Verify and save (GET returns `hub.challenge`).
   - Subscribe `messages`; also `message_template_status_update`, `message_template_quality_update`, `template_category_update`, and `account_update`/`user_preferences` if offered.
   - The callback must be HUF's endpoint, not `frappe_whatsapp`'s unsigned webhook route.
7. Verify (admin): `huf.ai.whatsapp_management.get_setup_status` with `gateway_name`; empty `failing_checks` means healthy. Send a test message and confirm a Gateway Event and an Agent Run.
8. Several numbers under one Meta app need Meta's callback override and the same `app_secret` in each Gateway's Integration Settings.

Source: docs/WHATSAPP_INTEGRATION_SETUP.md, huf/ai/gateway_adapters/whatsapp.py

## 3. Two token stores: rotate BOTH

| Store | Used for |
|---|---|
| Integration Settings credential `access_token` (via `Gateway.integration_settings`) | Agent replies, agent tool sends, `get_account_info` |
| `WhatsApp Account.token` (bridge mode, linked by `whatsapp_account`) | Bridge: confirmations, template create/sync, management sends |

Refreshing only one gives "some sends work, others fail" with Meta errors 131005/190. Rotation:
1. Generate a new system-user token in Meta Business settings.
2. Update **both** stores.
3. `POST /api/method/huf.ai.whatsapp_management.check_token` with `gateway_name` and `force=1` (admin only; cached 600 s, one live call per 10 s).
4. Confirm health reason `access_token_invalid` is gone and the next inbound gets a reply.

Source: docs/gateways/whatsapp-runbook.md, huf/ai/whatsapp_management.py

## 4. Access control

`direct_policy` on the Gateway:

| Value | Behaviour |
|---|---|
| `Allow list` (default) | Only senders with an **Approved** Gateway Access Entry are admitted |
| `Pairing` | Unknown sender gets a pairing code; the triggering message is not run until approved |
| `Open` | Everyone admitted |
| `Disabled` | Nobody |

Rooms use `room_policy`, `room_sender_policy`, `mention_required`. Pairing knobs: `pairing_ttl_minutes`, `pairing_reply_enabled`, `pairing_pending_limit`, `pairing_reply_daily_limit`; `inbound_sender_limit` rate-limits senders.

**Gateway Access Entry** fields: `gateway`, `entry_type` (Sender/Room), `external_id` (digits only for WhatsApp), `state` (Pending, Approved, Revoked, Blocked, Opted out, Expired), `pairing_code`, `expires_at`. To allow a number manually, create an entry with `entry_type` Sender, digits-only `external_id`, `state` Approved. Whitelisted calls (`huf.ai.gateway_service`): `approve_gateway_pairing(code_or_entry_name, notes, gateway)`, `approve_gateway_access_entry(entry_name)`, `list_gateway_access_entries(gateway, state)`, `revoke_gateway_access_entry(entry_name)`.

Known gap: an approved entry can keep a stale `expires_at` from the pairing step; clear it if an approved sender is dropped after an hour (docs/GATEWAY_ALLOW_LIST_GAP.md).

Source: huf/ai/gateway_service.py, huf/huf/doctype/gateway_access_entry/gateway_access_entry.json

## 5. STOP / START opt-out and consent

Handled at ingest for WhatsApp (`_handle_consent_event`).
- Defaults STOP: `STOP, UNSUBSCRIBE, CANCEL, END, QUIT`; START: `START, UNSTOP, SUBSCRIBE`. Override with Gateway `opt_out_keywords`, `opt_in_keywords`, `opt_out_reply_text`.
- STOP from an admitted sender: records opt-out, sends confirmation, starts no run. START reverses it. Other messages from an opted-out sender are rejected. STOP from a sender with no access entry is ignored (unless HUF first sent them a template; then a `template_outreach` marker lets their STOP count).
- Every outbound send checks `is_opted_out`; agent tool refusal code is `opted_out`.
- Meta `user_preferences` marketing stop/resume is stored as `Gateway Consent` rows; MARKETING templates are refused for a contact whose latest marketing preference is `stop`. Payload shape is marked UNVERIFIED in code.
- `bsuid_recipient`: a business-scoped user id cannot be a recipient; use the phone number.

Source: huf/ai/gateway_service.py, huf/ai/whatsapp_outbound_policy.py, huf/ai/whatsapp_account_events.py

## 6. The 24h window and proactive sends

- Window = 24h from the sender's last verified inbound Gateway Event (reactions and record-only kinds do not count; redelivered webhooks cannot reopen it).
- Inside: free-form text/media/interactive. Outside: only an **approved template** can go.
- Reply path with window closed: if Gateway `fallback_template` (+ `fallback_template_language`, default `en_US`) is APPROVED, it is sent and the agent reply suppressed; otherwise the event fails (`WhatsAppWindowClosed`, no retry). The fallback template may have body variables but no media/location/variable header or URL-button variable; set `fallback_template_params` (JSON list, or `{name: value}` map; count must match the body variables), otherwise each variable gets the contact name or "there". Meta error 131047 also triggers the fallback.
- Agent tool: a free-form send is *proactive* when no window is open. It is refused (`proactive_send_not_permitted`) unless the Gateway checkbox `agent_allow_proactive` is on. `send_template` is never gated by that flag.
- The LLM cannot flip flags: `allow_proactive`, `allow_whatsapp_management`, `auto_submit_templates`, `gateway_name`, `whatsapp_account`, `access_token`, `phone_number_id` in tool args are discarded.

Source: docs/gateways/whatsapp-runbook.md, huf/ai/tools/whatsapp.py

## 7. The `whatsapp` agent tool

Registered as tool `whatsapp` (function `huf.ai.tools.whatsapp.handle_action`, one `action` param). It is **bound to the Gateway of the current run**; outside a WhatsApp run it returns `gateway_context_required`. The recipient `to` (aliases `recipient`, `phone_number`) is **optional**: omit it to reply to the current contact. Never ask users for their phone number.

| Action | Args |
|---|---|
| `send_message` | `message` (alias `text`) |
| `send_media` | `kind` (image, document, audio, video, sticker) + exactly one source: `link`, `media_id`, `file_url`, or `file_id`; `caption`, `filename`, `voice` |
| `send_image` `send_video` `send_audio` `send_document` `send_sticker` | `send_media` with kind preset; `voice=true` on audio makes a voice note |
| `send_voice_note` | `link`, `media_id`, `file_url` or `file_id` (Ogg/Opus mono, <= 16 MB) |
| `send_location` | `latitude`, `longitude`, `name`, `address` |
| `send_contact` | `contact_name`, `contact_phone`, `contact_email`, `contact_org`, or `contacts` (JSON list) |
| `send_reaction` | `message_id` (customer's wamid), `emoji`, `remove=true` |
| `send_buttons` | `body`, `buttons` `[{id,title}]` up to 3, optional `header`, `footer` |
| `send_list` | `body`, `button_text`, `sections` `[{title, rows:[{id,title,description}]}]`, optional `header`, `footer` |
| `send_cta_url` | `body`, `display_text`, `url`, optional `header`, `footer` |
| `send_template` | `template_name`, `language_code` (default `en`), `parameters`, `header_params`, `button_params` (see whatsapp-templates.md) |
| `list_messages` | `to` (required), `limit` 1-50, `cursor` |
| `get_account_info` | none |
| `list_templates`, `create_template`, `get_template_status` | see whatsapp-templates.md |

Common optional args on every send: `reply_to` (wamid to quote), `idempotency_key`. `file_url`/`file_id` must be a HUF File from this conversation (for example output of `generate_image`/`generate_audio`); do not pass `link`/`media_id` together with them. A caption longer than the first chunk is split: media gets the first part, the rest follows as text.

Source: huf/ai/tools/whatsapp.py, huf/ai/tools/_registry.py

## 8. Recipient scope, caps, idempotency, outbound policy

Gateway fields (server-side only): `agent_recipient_scope` (`Current contact` default, `Allow-list`, `Approved contacts`, `Any number`), `agent_recipient_allowlist` (comma/newline separated numbers), `agent_send_cap_per_run` (default 20), `agent_send_cap_per_day` (default 200, rolling 24h; 0 disables the cap). A flow-triggered run is scoped the same way. Refusals: `recipient_not_permitted`, `send_cap_exceeded` (with `cap`, `limit`, `retry_after`).

Idempotency: a send runs once per key and is stored in `WhatsApp Send Key` (TTL 24h). Key = your `idempotency_key` (max 200 chars; scoped to run, action, recipient) or a hash of run, tool call id, action and payload. A repeat returns the original result with `deduplicated: true`; an unfinished claim returns `send_in_progress`; a timeout/5xx keeps the claim pending so it never double-sends. Failed or refused sends do not count toward caps.

Outbound policy order: connection state (`gateway_disconnected` refusal), recipient scope, idempotency claim, caps, then opt-out/BSUID/template-status checks (`opted_out`, `bsuid_recipient`, `template_not_approved`).

Source: huf/ai/whatsapp_send_scope.py, huf/ai/whatsapp_send_keys.py, huf/ai/whatsapp_outbound_policy.py

## 9. Management REST (after sync)

Call `/api/method/huf.ai.whatsapp_management.<fn>`; most take `gateway_name`. Sends need write authority on the Gateway.

| Function | Method | Notes |
|---|---|---|
| `get_setup_status` | GET | admin; health, checklist, webhook URL |
| `check_token` | POST | admin; `gateway_name`, `force` |
| `send_text_message` | POST | `gateway_name`, `to`, `text`; `window_closed` outside window |
| `send_media_message` | POST | `kind`, `link` or `file_url`, `caption`, `filename`, `media_id` |
| `send_voice_note`, `upload_media_file` | POST | upload returns `media_id` (valid 30 days) |
| `send_sticker_message`, `send_location_message`, `send_contacts_message`, `send_reaction_message`, `send_interactive_message` | POST | typed sends |
| `send_template_message` | POST | allowed outside window |
| `list_messages`, `list_conversations`, `list_message_log`, `list_message_log_filters` | GET | gateway scoped |

Source: huf/ai/whatsapp_management.py

## 10. Health, account events, dead letters, reaper

- **Health** (`blocked`, `degraded`, `healthy`, `not_set_up`, `disabled`) comes from DB facts; reasons include `signature_failed` (wrong App Secret), `no_events_yet`, `access_token_invalid`, `fallback_template_unavailable`, `voice_reply_ffmpeg_missing`.
- **Account events**: `account_update` sets `Gateway.connection_state`: Connected (`ACCOUNT_RECONNECTED`), Degraded (`ACCOUNT_RESTRICTION`, `ACCOUNT_VIOLATION`), Disconnected (`PARTNER_REMOVED`, `ACCOUNT_OFFBOARDED`, `ACCOUNT_DELETED`, ban `DISABLE`). Disconnected refuses all sends. No Gateway Event is created. `user_preferences` feeds consent (section 5).
- **Dead letters**: deterministic ingest failures stay as `Failed` Gateway Events with `error_message` starting `dead_letter:`. After fixing the cause, `POST huf.ai.gateway_service.retry_gateway_event` with `name` (admin; only dead letters; idempotent).
- **Reaper** (cron every 10 min, max 50 events): `Running` > 15 min fails; `Queued` > 10 min re-enqueued; `Received` > 5 min replayed (failure becomes dead letter); max 3 attempts, 60 min deadline. If events stall, check the scheduler is running.
- Triage order: health reasons, forced token check, `connection_state`, Failed events, reaper cron.

Source: docs/gateways/whatsapp-runbook.md, huf/ai/whatsapp_account_events.py, huf/ai/gateway_service.py
