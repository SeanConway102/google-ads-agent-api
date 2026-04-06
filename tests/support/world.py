"""
TestWorld — mirrors ClientApp/tests/support/world.js
Holds shared state per test scenario: api_client, response, headers, etc.
"""
from dataclasses import dataclass, field
from typing import Optional, Any
import httpx


@dataclass
class TestWorld:
    """
    Shared state container for each test scenario.
    Analogous to the Cucumber TestWorld class.
    """
    # Configuration
    base_url: str
    admin_api_key: str

    # HTTP state
    api_client: httpx.Client | None = field(default=None)
    response: httpx.Response | None = field(default=None)
    response_body: Any = field(default=None)
    response_headers: dict = field(default_factory=dict)

    # Auth
    token: Optional[str] = None
    custom_headers: dict = field(default_factory=dict)

    # Campaign state (for multi-step scenarios)
    created_campaign_id: Optional[str] = None
    created_campaign_ids: list = field(default_factory=list)

    # Webhook state
    registered_webhook_id: Optional[str] = None

    # Debate state
    current_debate_state: Optional[dict] = None

    def create_api_client(self) -> None:
        """Create the shared HTTP client."""
        self.api_client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def cleanup(self) -> None:
        """Close the HTTP client."""
        if self.api_client:
            self.api_client.close()

    def get_headers(self) -> dict:
        """Build request headers including auth."""
        headers = {"X-API-Key": self.admin_api_key, **self.custom_headers}
        return headers

    def get_authenticated_headers(self) -> dict:
        """Build request headers with API key."""
        return {"X-API-Key": self.admin_api_key}

    def sign_in(self, api_key: str) -> None:
        """
        For this system, authentication is a simple API key.
        Store it for use in subsequent requests.
        """
        self.token = api_key

    def api_get(self, path: str, **kwargs) -> httpx.Response:
        """Make an authenticated GET request."""
        assert self.api_client is not None, "api_client not initialized — call create_api_client() first"
        self.response = self.api_client.get(
            path,
            headers=self.get_headers(),
            **kwargs
        )
        self.response_headers = dict(self.response.headers)
        return self.response

    def api_post(self, path: str, json: dict = None, **kwargs) -> httpx.Response:
        """Make an authenticated POST request."""
        assert self.api_client is not None, "api_client not initialized — call create_api_client() first"
        self.response = self.api_client.post(
            path,
            json=json,
            headers=self.get_headers(),
            **kwargs
        )
        self.response_headers = dict(self.response.headers)
        return self.response

    def api_delete(self, path: str, **kwargs) -> httpx.Response:
        """Make an authenticated DELETE request."""
        assert self.api_client is not None, "api_client not initialized — call create_api_client() first"
        self.response = self.api_client.delete(
            path,
            headers=self.get_headers(),
            **kwargs
        )
        self.response_headers = dict(self.response.headers)
        return self.response
