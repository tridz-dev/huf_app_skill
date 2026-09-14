"""
HUF Platform REST API Client

Minimal Python client stub for calling HUF platform endpoints.
Requires HUF_API_KEY environment variable (obtained from Developer Settings).

Note: /huf/api/v1/ping does NOT validate the API key (no authentication required).
Only /huf/api/v1/me requires the key header and actually tests whether the key is valid.
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

    def list_agents(self) -> dict:
        """POST /huf/api/v1/agents - List available agents."""
        url = f"{self.base_url}/huf/api/v1/agents"
        response = self.session.post(url, headers=self._get_headers(), json={})
        response.raise_for_status()
        return response.json()

    def create_conversation(self, agent_name: str) -> dict:
        """POST /huf/api/v1/conversations - Start a new conversation."""
        url = f"{self.base_url}/huf/api/v1/conversations"
        response = self.session.post(
            url, headers=self._get_headers(), json={"agent": agent_name}
        )
        response.raise_for_status()
        return response.json()

    def send_message(self, conversation_id: str, message: str) -> dict:
        """POST /huf/api/v1/responses - Send a message to a conversation."""
        url = f"{self.base_url}/huf/api/v1/responses"
        response = self.session.post(
            url,
            headers=self._get_headers(),
            json={"conversation_id": conversation_id, "message": message},
        )
        response.raise_for_status()
        return response.json()

    def get_run_status(self, run_id: str) -> dict:
        """POST /huf/api/v1/runs - Poll run status."""
        url = f"{self.base_url}/huf/api/v1/runs"
        response = self.session.post(
            url, headers=self._get_headers(), json={"run_id": run_id}
        )
        response.raise_for_status()
        return response.json()
