"""
HUF Platform REST API Client

Minimal Python client stub for calling HUF platform endpoints.
Requires HUF_API_KEY environment variable (obtained from Developer Settings).

Note: /huf/api/v1/ping does NOT validate the API key (no authentication required).
Only /huf/api/v1/me requires authentication and actually tests whether the key is valid.
/me returns identity and capabilities of the key owner (not the key's scopes).
Scopes enforced today: agents:read, agents:run, conversations:read, conversations:write.
See references/api-v1.md. Beta API: no backward-compatibility guarantees.
"""

import os
import requests


class HufClient:
    def __init__(self, base_url: str = "http://localhost:8104"):
        self.base_url = base_url
        self.api_key = os.environ.get("HUF_API_KEY")
        self.session = requests.Session()

    def _get_headers(self, authenticated: bool = True) -> dict:
        """Build request headers."""
        headers = {"Content-Type": "application/json"}
        if authenticated and self.api_key:
            headers["X-Huf-Api-Key"] = self.api_key
        return headers

    def ping(self) -> dict:
        """
        GET /huf/api/v1/ping
        Router reachability check (no authentication required).
        Does NOT validate the API key.
        """
        url = f"{self.base_url}/huf/api/v1/ping"
        response = self.session.get(url, headers=self._get_headers(authenticated=False))
        response.raise_for_status()
        return response.json()

    def me(self) -> dict:
        """
        GET /huf/api/v1/me
        Authenticate and retrieve granted scopes.
        This endpoint requires X-Huf-Api-Key header and is the real key validation.
        """
        url = f"{self.base_url}/huf/api/v1/me"
        response = self.session.get(url, headers=self._get_headers(authenticated=True))
        response.raise_for_status()
        return response.json()

    def list_agents(self, limit: int = 50, offset: int = 0) -> dict:
        """GET /huf/api/v1/agents - List agents (scope agents:read)."""
        url = f"{self.base_url}/huf/api/v1/agents"
        response = self.session.get(
            url, headers=self._get_headers(), params={"limit": limit, "offset": offset}
        )
        response.raise_for_status()
        return response.json()

    def create_conversation(self, agent_id: str, title: str | None = None) -> dict:
        """POST /huf/api/v1/conversations - Start a conversation (scope conversations:write)."""
        url = f"{self.base_url}/huf/api/v1/conversations"
        body = {"agent_id": agent_id}
        if title:
            body["title"] = title
        response = self.session.post(url, headers=self._get_headers(), json=body)
        response.raise_for_status()
        return response.json()

    def send_message(
        self, agent_id: str, message: str, conversation_id: str | None = None
    ) -> dict:
        """POST /huf/api/v1/responses - Run an agent turn (scope agents:run).

        Queue-first: usually returns status "queued" with output null.
        Poll get_run(data.response_id) for the result.
        """
        url = f"{self.base_url}/huf/api/v1/responses"
        body = {"agent_id": agent_id, "input": message}
        if conversation_id:
            body["conversation_id"] = conversation_id
        response = self.session.post(url, headers=self._get_headers(), json=body)
        response.raise_for_status()
        return response.json()

    def get_run(self, run_id: str) -> dict:
        """GET /huf/api/v1/runs/{run_id} - Run status/output (scope conversations:read)."""
        url = f"{self.base_url}/huf/api/v1/runs/{run_id}"
        response = self.session.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response.json()
