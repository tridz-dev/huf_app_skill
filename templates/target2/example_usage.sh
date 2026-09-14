#!/bin/bash

# HUF Platform REST API Usage Examples
# Load HUF_API_KEY from .env before running these examples

# Example 1: Check router reachability (no auth required)
curl -s -X GET "http://localhost:8104/huf/api/v1/ping"

# Example 2: Authenticate and retrieve granted scopes
# This validates the API key and returns the list of scopes your key can access
curl -s -X GET "http://localhost:8104/huf/api/v1/me" \
  -H "X-Huf-Api-Key: $HUF_API_KEY"

# Example 3: List available agents
curl -s -X POST "http://localhost:8104/huf/api/v1/agents" \
  -H "X-Huf-Api-Key: $HUF_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'

# Example 4: Create a new conversation
curl -s -X POST "http://localhost:8104/huf/api/v1/conversations" \
  -H "X-Huf-Api-Key: $HUF_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"agent":"AUD-Guest"}'

# Example 5: Send a message to a conversation
curl -s -X POST "http://localhost:8104/huf/api/v1/responses" \
  -H "X-Huf-Api-Key: $HUF_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"<conversation_id>","message":"hello world"}'

# Example 6: Poll run status
curl -s -X POST "http://localhost:8104/huf/api/v1/runs" \
  -H "X-Huf-Api-Key: $HUF_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"run_id":"<run_id>"}'
