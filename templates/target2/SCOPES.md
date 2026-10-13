# HUF API Scopes

A key can be minted with any of the 8 scopes below, but only some are enforced by an endpoint today. See `references/api-v1.md`.

## Enforceable today

- `agents:read` — `GET /agents`, `GET /agents/{id}`.
- `agents:run` — `POST /responses` (sync and streaming).
- `conversations:read` — `GET /conversations`, `GET /conversations/{id}`, `GET /conversations/{id}/messages`, `GET /runs/{id}`.
- `conversations:write` — `POST /conversations`.

## Reserved (no endpoints yet; granting them has no effect)

- `files:read`, `files:write` — planned file upload/download.
- `voice:use` — planned speech-to-text / text-to-speech.
- `ocr:use` — planned OCR.

`/ping` and `/me` need no scope. A key can only reduce its owner's authority, never extend it.

## API Key Management

API keys are created and managed in Developer Settings within the HUF platform. When you create a key, it will display a one-time secret value that you must copy and save — this secret is never shown again.

Keys can optionally be restricted to specific agents (`selected` mode). Unrestricted keys (`all`) can access any agent that the key owner has permission to use.

The skill does not mint, create, or store API keys. Keys are created by the user directly in Developer Settings and their secret value is handled entirely by your application.
