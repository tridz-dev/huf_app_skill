#!/bin/bash

# HUF Platform REST API Usage Examples (see references/api-v1.md)
# HUF_API_KEY must be set in your environment (never hard-code a key).
# Replace the base URL with your Huf site.
BASE="${HUF_BASE:-http://localhost:8104}"

# Example 1: Router reachability (no auth; does NOT validate the key)
curl -s "$BASE/huf/api/v1/ping"

# Example 2: Validate the key; returns the owner's identity and capabilities
curl -s "$BASE/huf/api/v1/me" -H "X-Huf-Api-Key: $HUF_API_KEY"

# Example 3: List agents (scope agents:read)
curl -s "$BASE/huf/api/v1/agents?limit=20" -H "X-Huf-Api-Key: $HUF_API_KEY"

# Example 4: Create a conversation (scope conversations:write)
curl -s -X POST "$BASE/huf/api/v1/conversations" \
  -H "X-Huf-Api-Key: $HUF_API_KEY" -H "Content-Type: application/json" \
  -d '{"agent_id":"<agent_id>"}'

# Example 5: Run an agent turn (scope agents:run). Queue-first: returns response_id.
curl -s -X POST "$BASE/huf/api/v1/responses" \
  -H "X-Huf-Api-Key: $HUF_API_KEY" -H "Content-Type: application/json" \
  -d '{"agent_id":"<agent_id>","conversation_id":"<conversation_id>","input":"hello world"}'

# Example 6: Poll the run (scope conversations:read)
curl -s "$BASE/huf/api/v1/runs/<response_id>" -H "X-Huf-Api-Key: $HUF_API_KEY"
