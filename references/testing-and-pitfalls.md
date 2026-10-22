# Testing and pitfalls (Huf gateways, WhatsApp first)

Read this before you build or change a Gateway, flow or agent tool and need to prove it works.
`R` = the Huf repo checkout (branch `pre-develop` or later). Never put tokens, app secrets or real
phone numbers in files, chat or logs. Use placeholders: `<site>`, `<gateway>`, `<phone_id>`.

## 1. Test layers (cheapest first)

| Layer | Needs | Use for |
|---|---|---|
| Pure unit test | plain `python3` | helpers with no `frappe` import (e.g. `tools/wa_live_smoke.py`, `FakeGraph`) |
| Frappe `IntegrationTestCase` | a bench + site | anything touching DocTypes, hooks, the gateway pipeline |
| Fake Graph server | bench, test flags | WhatsApp send/media/template calls with strict schema checks |
| Signed webhook replay | bench + HTTP or in-process | ingest, routing, opt-out, dead letters |
| Read-only live smoke | a real token in env | "is my token still valid" (never sends) |
| Live window with a phone | Meta test number + owner | final proof only (section 2) |

### Pure unit tests
Test modules under `R/huf/ai/tests/` import `huf`, which imports `frappe`, so
`python3 -m unittest huf.ai.tests.<mod>` fails without a bench (`No module named 'frappe'`).
Load a frappe-free test by file path instead (verified: 4 tests OK):

```bash
cd R && python3 -c "
import importlib.util, unittest
s = importlib.util.spec_from_file_location('t', 'huf/ai/tests/test_wa_live_smoke.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
unittest.main(module=m, argv=['x'], exit=False)"
```

### Frappe IntegrationTestCase on a bench
The module path must be the FULL dotted name, one `--module` per run:

```bash
bench --site <site> run-tests --module huf.ai.tests.test_whatsapp_ingress
bench --site <site> run-tests --module huf.ai.tests.test_gateway_webhook
```
Existing WhatsApp/gateway modules (all confirmed present in `R/huf/ai/tests/`): `test_whatsapp_contract`,
`test_whatsapp_ingress`, `test_whatsapp_health`, `test_whatsapp_voice_reply`, `test_whatsapp_fake_graph`,
`test_fake_graph`, `test_gateway_webhook`, `test_gateway_webhook_status_codes`, `test_wa_live_smoke`.
Run optional-app cases on a site with `frappe_whatsapp` installed AND on a core-only site: the
`whatsapp_account` link only exists when that app is present. Write new tests next to these and run the
neighbours of every file you changed (gateway_service, tools/whatsapp, bridge) before declaring done.

Source: R/huf/ai/tests/test_wa_live_smoke.py, R/ongoing run_tests.sh (`bench --site $SITE run-tests --module $m`)

## 1b. Fake Graph API (WhatsApp)

Two fakes, both in `R/huf/ai/tests/`:

- `fake_graph.py` - `FakeGraph`, in-process drop-in for `requests` (`post` / `get` / `request`). Pass
  `graph.post` as `http_post` to an adapter; read `graph.sent_messages()`; `graph.reset()` clears.
  Success: `POST .../<phone_id>/messages` -> `{"messages":[{"id":"wamid.FAKE<n>"}]}`.
  Failure switches (constructor kwargs): `window_closed=True` -> error 131047 (400, "Re-engagement
  message"; wins over rate limit); `rate_limited=True` -> 131056 (pair rate limit), with
  `rate_limit_code=130429` for throughput throttling. Also `token_valid`, `token_expires_at`, `health_status`.
  Other endpoints modelled: `GET/POST <waba>/subscribed_apps` (idempotent POST), `POST <phone_id>/register`,
  `GET debug_token` (`is_valid`, `expires_at`), `GET <phone_id>` (`health_status`). Anything else succeeds,
  so it also stands in for media upload and template reads. Verified: `FakeGraph(window_closed=True)`
  returns 400/131047 and `rate_limit_code=130429` returns code 130429.
- `fake_graph_server.py` - `FakeGraphServer().start()`: a real `http.server` on an ephemeral port; code under
  test makes genuine `requests` calls. Implements messages (text/template/media/sticker/location/contacts/
  reaction/interactive/read), `/media` upload and download, `message_templates` CRUD, resumable uploads.
  Every body is checked against Meta's schema; violations are collected, so end each test with
  `self.server.assert_clean()` (a swallowed 400 still fails the test). It does NOT model the 24h window
  (Huf enforces it before sending) and is only reachable under `frappe.flags.in_test`. Constants `TOKEN`,
  `APP_SECRET`, `GRAPH_VERSION` are fake test values.
- Fixtures: `R/huf/ai/tests/fixtures/whatsapp/*.json` are saved webhook payloads (e.g. `audio.json`).
  Prefer extending them to hand-writing payloads.

Gap to remember: fakes are hand-written from docs; they cannot catch drift in Meta's real payloads.
A passing fake is not live proof.

Source: R/huf/ai/tests/fake_graph.py, R/huf/ai/tests/fake_graph_server.py, R/huf/ai/tests/test_whatsapp_fake_graph.py

## 1c. Signed webhook replay

The callback is one whitelisted guest endpoint for all gateways:
`POST https://<site>/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=<gateway>`
(GET answers the Meta verify handshake). The adapter accepts a request only if header
`X-Hub-Signature-256: sha256=<hex>` equals `HMAC-SHA256(app_secret, raw_body)` (constant-time compare). The
secret is the gateway's own app secret (stored in its Integration Settings); read it inside your process
from env, never print it.

```python
# replay.py - re-sign a saved payload under a NEW message id and post it
import hashlib, hmac, json, os, time, urllib.request
body = json.load(open("R/huf/ai/tests/fixtures/whatsapp/audio.json"))
val = body["entry"][0]["changes"][0]["value"]
val["metadata"]["phone_number_id"] = os.environ["WA_PHONE_ID"]       # must be the gateway's number
val["messages"][0]["id"] = f"wamid.REPLAY{int(time.time())}"        # fresh id, else deduped
val["messages"][0]["timestamp"] = str(int(time.time()))
raw = json.dumps(body).encode()
sig = "sha256=" + hmac.new(os.environ["WA_APP_SECRET"].encode(), raw, hashlib.sha256).hexdigest()
req = urllib.request.Request(os.environ["WEBHOOK_URL"], data=raw, method="POST",
      headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig})
print(urllib.request.urlopen(req).status)
```
Notes: edit the SAME body bytes you sign (re-serialising after signing breaks the HMAC). Use a fresh wamid per
replay (idempotency key is gateway + wamid). Point at a local dev site, or at a gateway whose recipient is
the owner's own test number: a replay enqueues a real agent run and a real reply send. To replay a saved
real voice note, keep the `audio` object (media id) from the capture and change only the id/timestamp.
Expected rejections: missing/wrong/`sha1=`/tampered signature -> 401 with no event row.
Rate limit: 100 requests / 60 s per gateway.

Source: R/huf/ai/gateway_adapters/whatsapp.py (signature check), R/huf/ai/gateway_webhook.py (`handle_gateway_webhook`),
ongoing/whatsapp/verify/np_verify.py (`sign`, `post_webhook`)

## 1d. Read-only live smoke script

`R/tools/wa_live_smoke.py`: one call to Meta `debug_token`, prints exactly one of
`token valid until <YYYY-MM-DD>` / `token valid (no expiry)` / `token invalid`. Sends nothing; never prints the
token; transport errors collapse to `token invalid`. It has no argparse, so `--help` is not a mode (it just
runs and, without env, prints `WA_TOKEN is not set`, exit 2). Exit codes: 0 valid, 1 invalid, 2 bad env.

```bash
WA_TOKEN="$(<your secret manager>)" WA_PHONE_ID=<numeric phone id> python3 R/tools/wa_live_smoke.py
```
`WA_PHONE_ID` is an operator guard only (must be numeric; never transmitted). Run it before every live window
(test tokens last about 1-2 hours). Do not paste `WA_TOKEN` inline in shell history; export from a file you
do not commit.

Source: R/tools/wa_live_smoke.py, R/huf/ai/tests/test_wa_live_smoke.py

## 2. Live verification with Meta's test number

What you can prove WITHOUT a phone (the "no-phone" pass, `verify/np_verify.py`, run via
`bench --site <site> execute huf.np_verify.run` after copying the script into the app):
tool authorization and scope/caps, idempotent sends, reaper, dead letters, signature rejects, edit/revoke/echo
handling, BSUID ingest, `account_update` -> Disconnected, user_preferences isolation. Safety model that made
it safe on a bench with live workers: replace `requests.sessions.Session.request` with a recorder (no I/O),
make `socket.getaddrinfo` refuse facebook/whatsapp hosts, replace `frappe.enqueue`/`enqueue_doc` with
recorders, make `frappe.db.commit` a no-op and roll back at the end, drive the webhook in-process with real
werkzeug requests, and scan the report for the secret. Copy that pattern for any script that must not reach
Meta or the live worker.

What needs a phone or WhatsApp Web: real agent run and reply after a replay, delivery to a handset (voice
note bubble, image, PDF), STOP/START round trip, provider-failure fallback delivery, killing a worker.

Rules for a live window:
1. Message ONLY the owner's own Meta test number. Recipient scope/caps on the gateway stay on.
2. Check the token first (section 1d). Test tokens last ~1-2 h. When rotating, update BOTH token stores:
   the gateway Integration Settings `access_token` (agent replies) AND the linked WhatsApp Account `token`
   (bridge: templates, confirmations, management). One stale store gives error 131005 / 190 on only some sends.
3. Callback override: Meta delivers to the app's configured callback unless the phone number has an override.
   Set the phone number's `webhook_configuration.override_callback_uri` to a public https URL that reaches
   the dev bench (tunnel) plus that gateway's verify token, send the test messages, then ALWAYS REVERT the
   override in the same sitting. Log OPEN and CLOSED lines with the time so a crash can be recovered
   (SWARM_STATE does this: "WINDOW n OPEN ... MUST REVERT" / "CLOSED, override REVERTED").
4. Any temporary config change (agent model, `voice_reply_mode`, gateway `default_target_type`/`default_flow`,
   role grants) needs a written restore step. Scripts that do this: `verify/flow_target_on.py` /
   `flow_target_off.py` and `flow_triage_on.py` / `flow_triage_off.py` (back up the original target to a
   file, switch the Gateway to a Flow, restore exactly; triage_on can grant a role with `GRANT_ROLE=1`, and
   triage_off revokes it). Run the matching `*_off` even when the test failed.
5. Never print tokens or app secrets; scan transcripts and reports before saving.
6. Live PASS list from the hardening run (for reference): text round trip, STOP -> confirmation, post-STOP
   rejected, START -> reply, sticker/photo/PDF/m4a/voice-note inbound, reaction recorded without a run,
   transcription (STT), vision, generated image reply, voice-in/voice-out, forced provider failure ->
   fallback delivered, flow-routed reply exactly once, non-LLM triage flow (5 branches).

Source: ongoing/whatsapp/gap2/LIVE_VERIFY_NOPHONE.md, ongoing/whatsapp/gap2/SWARM_STATE.md,
ongoing/whatsapp/verify/np_verify.py, ongoing/whatsapp/verify/flow_triage_on.py, flow_triage_off.py

## 3. Isolation pitfalls (shared bench)

- One shared bench = whichever worktree/branch synced and ran tests last is the code the workers run.
  Symptoms: a helper import that "should exist" is missing; `bench migrate` rewrites DocType JSON back to
  an older shape; a feature passes in unit tests but the live reply behaves like the old code (a voice reply
  fell back to text for exactly this reason); a live window ran against another agent's tree.
- Fix: give each track its own bench/site; if you must share, serialize with a lock around sync + migrate +
  tests + restore (the repo helpers `with_bench_lock.sh` / `bench_test.sh <worktree> <module...>` do:
  mkdir lock, stale after 45 min, rsync worktree into the app, migrate full+core sites, run modules, rsync
  the integration worktree back). Hold the lock for the whole live window too.
- After any code sync, RESTART the workers (and web) - long-lived processes keep old modules in memory. Put
  the right PATH in the restart environment (next point).
- `ffmpeg` with the `libopus` encoder must be on the PATH of the process that runs the agent worker (voice-note
  replies convert TTS to ogg/opus mono). Check: `ffmpeg -hide_banner -encoders | rg libopus`. Gateway health
  shows `voice_reply_ffmpeg_missing`, but that check runs on the site host, so verify on each worker host too.
  If ffmpeg is only inside a venv (e.g. `env/bin/ffmpeg` from `imageio-ffmpeg`), export that PATH when restarting.
- Prefer a scratch site per experiment (`bench new-site`, install apps, drop afterwards) so migrations and
  half-built DocTypes never touch the shared site. Do not stop containers or workers you did not start.

Source: ongoing/whatsapp/with_bench_lock.sh, ongoing/whatsapp/bench_test.sh, ongoing/whatsapp/gap2/SWARM_STATE.md,
R/docs/gateways/whatsapp-runbook.md (section 8)

## 4. Merge hygiene

- Before committing any merge, run `git grep -n -E '^(<<<<<<<|>>>>>>>)'` and fix every hit. A merge commit with
  markers did land once on a branch because the merge output was truncated (`| tail`) and the markers were in
  the cut-off part. Never truncate merge/conflict output; read all of it.
- For hand-resolved JSON (DocType `field_order` etc.): check the list has no duplicates and matches `fields`.
- After a merge, rerun the suites of BOTH sides, not just your own.

Source: ongoing/whatsapp/gap2/SWARM_STATE.md (PR #828 note)

## 5. Pitfalls learned live

1. Two token stores (gateway Integration Settings `access_token` and WhatsApp Account `token`): rotate both.
   Stale one => 131005 "Access denied" while the token itself is valid.
2. Stale conversation context: an agent that failed once (e.g. "I cannot make images") repeats the failure from
   history. Retest on a fresh conversation before blaming code.
3. The agent must have the tools attached (WhatsApp, generate_image, ...). `to` is optional: omitted, it
   defaults to the current contact; recipient scope and send caps still apply.
4. Models need their own provider keys AND the right modality (Transcription / Image / TTS). A Google model
   run with the agent's Anthropic key fails `API_KEY_INVALID`. Set `stt_model` / `tts_model` /
   `image_generation_model` on the agent and check the catalogue row's modality.
5. Gemini TTS is called through completion and returns raw PCM16; it needs conversion before ogg/opus.
6. STOP/START must act on every linked identifier (phone AND BSUID). Fix FX-E: START cleared only one id and
   a linked entry stayed opted out.
7. A Disconnected gateway (`account_update` PARTNER_REMOVED, ban DISABLE) must refuse EVERY send path,
   including agent `send_message` / `send_template`; check `send_refusal` in all of them (defect DEF-2 found
   no-phone: only adapter and typed sends were guarded).
8. The webhook GET verify handshake must answer while a gateway is disabled, or Meta cannot (re)subscribe.
9. The gateway `execution_user` needs permission to use the WhatsApp tool; default Huf Gateway User got
   `permission_denied` (DEF-1). Test with the real execution user, not Administrator.
10. Direct `frappe.db.set_value` (and bench scripts) skips DocType validation and hooks. Use `doc.save()` when
    you want validation; when you must set_value, set every dependent field and re-read to verify.
11. A bench-wide model catalogue row with the wrong modality silently disables STT; fix the row, not the agent.
12. Unsupported attachments (octet-stream audio) once produced two replies; confirm exactly one reply per event.
13. Redis rate-limit counters are outside the DB transaction: a "rolled back" no-phone run still advances them.

Source: ongoing/whatsapp/gap2/SWARM_STATE.md, ongoing/whatsapp/gap2/LIVE_VERIFY_NOPHONE.md,
ongoing/whatsapp/gap2/OPUS_REVIEW_FINAL.md, R/docs/gateways/whatsapp-runbook.md
