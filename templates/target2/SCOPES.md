# HUF API Scopes

Available scopes that can be granted to an API key:

- `agents:read` — Read agent definitions and list available agents.
- `agents:run` — Execute agents and trigger agent runs.
- `conversations:read` — Read conversation history and metadata.
- `conversations:write` — Create and modify conversations.
- `files:read` — Read uploaded files and attachments.
- `files:write` — Upload and store files.
- `voice:use` — Access text-to-speech and speech-to-text capabilities.
- `ocr:use` — Extract text from images and documents via OCR.

## API Key Management

API keys are created and managed in Developer Settings within the HUF platform. When you create a key, it will display a one-time secret value that you must copy and save — this secret is never shown again.

Keys can optionally be restricted to specific agents. Unrestricted keys can access any agent that your user account has permission to use.

The skill does not mint, create, or store API keys. Keys are created by the user directly in Developer Settings and their secret value is handled entirely by your application.
