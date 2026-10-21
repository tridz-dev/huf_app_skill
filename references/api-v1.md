# Huf external API v1 (`/huf/api/v1`)

Status: **beta**. Verified against the Huf source (router, auth, scopes, endpoint handlers, `Huf API Key` doctype). Only the routes in "Implemented routes" exist today. Everything under "Planned platform API" is **[planned]** and not callable. There are no backward-compatibility guarantees while Huf is in beta.

Availability tags: **[available]** works today; **[planned]** designed or decided, not built (see `platform-surfaces.md` for the full legend).

Base URL: your Huf site, e.g. `https://huf.example.com`. All routes live under `/huf/api/v1/`.

## Authentication

Two ways, resolved in this order: API key, then session cookie.

- **API key**: send header `X-Huf-Api-Key: huf_sk_...`. Not `Authorization: Bearer` (Frappe intercepts that header before Huf sees it). Keys are created by the user in Developer Settings (needs capability `developer.keys.manage`); the secret is shown once. Store it in an env var (`HUF_API_KEY`), never in code or the repo.
- **Session cookie**: a logged-in Frappe session works too (e.g. an app served from the same site). Session requests carry no scope restriction; normal Huf capability/ownership checks still apply.

Key rules (as implemented):
- A key acts **as its owner** (the router switches to the owner's user). It can only **reduce** authority: effective access = owner's own permissions AND key scopes AND key agent restriction. A key never grants more than its owner has.
- Keys are stored hashed (SHA-256); `last_used_at` is updated on use. Revoked, expired, unknown, or malformed (not starting `huf_sk_`) keys do not verify.
- **Bad key behaviour**: an invalid key is NOT rejected on its own; the resolver falls through to session auth. With no valid session the result is `401 authentication_required`. (If a valid session cookie is also sent, the request succeeds as that session user.) A key that verifies but lacks the needed scope gets `403 authorization_failed`.
- **Agent restriction** on a key: `all` (any agent the owner may use) or `selected` (only the listed agents, at least one required). A request for another agent returns `403`.
- `GET /ping` needs no auth and does not validate a key. Use `GET /me` to test a key.

## Scopes

`ALLOWED_SCOPES` has 8 values. A key may be minted with any of them, but only four are enforced today.

| Scope | Enforced today by |
|---|---|
| `agents:read` | `GET /agents`, `GET /agents/{id}` |
| `agents:run` | `POST /responses` (sync and `stream`) |
| `conversations:read` | `GET /conversations`, `GET /conversations/{id}`, `GET /conversations/{id}/messages`, `GET /runs/{id}` |
| `conversations:write` | `POST /conversations` |
| `files:read`, `files:write`, `voice:use`, `ocr:use` | **Reserved. No endpoints yet**; granting them does nothing. |

`/me` and `/ping` require no scope.

## Response and error envelopes

Success: `{"data": <payload>, "request_id": "<uuid>", "meta": {}}` (all payloads below are the `data` value).
Error: `{"error": {"code": "...", "message": "...", "request_id": "<uuid>"}}`.

| HTTP | code | When |
|---|---|---|
| 400 | `validation_error` | missing/invalid input, streaming not allowed for the agent, conversation has queued runs |
| 401 | `authentication_required` | no valid key or session |
| 403 | `authorization_failed` | missing scope, agent not allowed for key, no access to agent |
| 404 | `not_found` | unknown route/resource; also used for resources you do not own (existence is not leaked) |
| 409 | `conflict` | conversation execution lock held (stream) |
| 500 | `internal_error` | unexpected failure (quote `request_id`) |

`429 rate_limited` exists as an error class but **no rate limiting is implemented** in v1 today; do not rely on `Retry-After`/`X-RateLimit-*` headers. Be conservative with polling.

## Pagination

List routes (`/agents`, `/conversations`) take `limit` (default and max 50) and `offset` (default 0). They return `has_more` and `cursor` (the next offset, or `null`). `has_more` for `/agents` is based on the raw page, so a page can be shorter than `limit` while `has_more` is true. `/conversations/{id}/messages` is not paginated.

## Implemented routes

Parameters may be sent as query string or JSON body. Do not rely on HTTP method for static routes (only `POST` vs `GET` on `/conversations` is distinguished); use the methods shown.

| Method / path | Scope | Params | `data` |
|---|---|---|---|
| `GET /ping` | none | - | `{status, version}` |
| `GET /me` | none | - | `{user, display_name, huf_role, capabilities[], auth_type}` (`auth_type`: `session` or `api_key`). Does not list the key's scopes. |
| `GET /agents` | `agents:read` | `limit`, `offset` | `{agents[], has_more, cursor}`; agent = `{id, name, description, modality, voice_enabled, file_upload_supported, streaming, execution_mode}` (`streaming` true when the agent has Run Immediately; `execution_mode` is `immediate` or `queued`) |
| `GET /agents/{id}` | `agents:read` | - | one agent (same shape); 404 if missing, disabled, or not accessible |
| `POST /conversations` | `conversations:write` | `agent_id` (or `agent`), optional `title` | conversation `{id, agent_id, title, created_at, status}` (+ `host` for desktop-hosted) |
| `GET /conversations` | `conversations:read` | `agent_id`, `limit`, `offset` | `{conversations[], has_more, cursor}`; only the caller's own |
| `GET /conversations/{id}` | `conversations:read` | - | conversation (owner only; System Manager sees any) |
| `GET /conversations/{id}/messages` | `conversations:read` | - | `{messages: [{id, role, content, created_at}]}` |
| `POST /responses` | `agents:run` | `agent_id` (or `agent`), `input` (or `input_text`/`prompt`), optional `conversation_id`, optional `stream` | `{response_id, conversation_id, status, output}` |
| `GET /runs/{id}` | `conversations:read` | - | `{id, agent_id, conversation_id, status, output, created_at}`; status: `queued`, `running`, `completed`, `failed` |

### Running an agent

`POST /responses` is **queue-first**: it normally returns `status: "queued"` with `output: null`. `response_id` is the run id; poll `GET /runs/{response_id}` until `completed` or `failed`, then read `output`. Without `conversation_id` a new conversation is created and its id returned; with one, you must own it.

### Streaming

`POST /responses` with `"stream": true` (also `1`/`yes`) returns `text/event-stream`, only for agents with **Run Immediately** enabled (else `400`). It also fails with `400` if the conversation has queued runs and `409` if it is locked. Each event is one line `data: {json}` with a `type`:
- `response.created` - `{conversation_id, request_id}`
- `response.output_text.delta` - `{delta, output}` (text) or `{tool_call}`
- `response.completed` - `{output}` (final)
- `response.failed` - `{error}`
Stop reading after `response.completed` or `response.failed`. Failures before the stream starts may also arrive as a single `response.failed` event.

## Examples

```bash
export HUF_BASE="https://huf.example.com"   # HUF_API_KEY must already be set in your shell
curl -s "$HUF_BASE/huf/api/v1/me" -H "X-Huf-Api-Key: $HUF_API_KEY"
curl -s "$HUF_BASE/huf/api/v1/agents?limit=20" -H "X-Huf-Api-Key: $HUF_API_KEY"
curl -s -X POST "$HUF_BASE/huf/api/v1/responses" \
  -H "X-Huf-Api-Key: $HUF_API_KEY" -H "Content-Type: application/json" \
  -d '{"agent_id":"<agent id>","input":"Hello"}'
curl -s "$HUF_BASE/huf/api/v1/runs/<response_id>" -H "X-Huf-Api-Key: $HUF_API_KEY"
# stream
curl -N -X POST "$HUF_BASE/huf/api/v1/responses" \
  -H "X-Huf-Api-Key: $HUF_API_KEY" -H "Content-Type: application/json" \
  -d '{"agent_id":"<agent id>","input":"Hello","stream":true}'
```

```python
import os, time, requests
base = os.environ["HUF_BASE"] + "/huf/api/v1"
h = {"X-Huf-Api-Key": os.environ["HUF_API_KEY"]}
r = requests.post(f"{base}/responses", headers=h, json={"agent_id": AGENT_ID, "input": "Hello"})
r.raise_for_status()
run = r.json()["data"]
rid = run["response_id"]
while run["status"] in ("queued", "running"):
    time.sleep(2)
    run = requests.get(f"{base}/runs/{rid}", headers=h).json()["data"]
print(run["output"])
```

---

# Planned platform API (not available yet)

Everything below is **[planned]** (from the platform plan; subject to change). Do not generate code that calls it.

- **[planned] Generic gateway routes** `/gateways/{id}/...` (not per-provider routes like `/whatsapp/*`), driven by adapter capabilities: gateway list/get with capability flags, threads, messages (list/send), templates (only where the adapter supports templates; otherwise `capability_not_supported`). Typed errors such as `window_closed` for provider service windows.
- **[planned] New scopes**: `runs:read` (split from `conversations:read`), `gateways:read`, `gateways:send`, `gateways:templates:write`, `gateways:access`, `gateways:write`, `tables:read/write/schema`, `skills:read`, `knowledge:read/write`, `flows:read/run`, `decisions:read/run`, `memory:read/write`, `automations:*`, `artifacts:read`, `events:subscribe`. `files:*`, `voice:use`, `ocr:use` get endpoints later.
- **[planned] Approvals**: `approvals:read` and `approvals:decide`. Planned: keys may approve, via the separate `approvals:decide` scope (never in defaults or presets, must be minted explicitly), honouring the key's agent restriction and the owner's own authority, and every decision audited with `decided_via = api_key:<key id>`.
- **[planned] Inbound events**: an event stream (SSE with cursor replay) and signed webhook subscriptions for inbound gateway messages and run events.
- **[planned] Per-key gateway restriction**, alongside the existing agent restriction, plus table/other resource restrictions.
- **[planned] Mechanics**: declarative route table with scope enforced by the router, cursor pagination, `Idempotency-Key`, real rate limits (`429` + `Retry-After`), request audit log, generated OpenAPI, error-code taxonomy.

Beta notice: the API may change without notice; no backward-compatibility guarantees until the first stable release.
