from abc import ABC, abstractmethod
from typing import Dict, Optional

class OAuthBase(ABC):
    @abstractmethod
    def generate_oauth_link(self, state: Optional[Dict[str, str]] = None) -> str:
        """Generate the OAuth authorization URL with an optional state parameter."""
        pass

    @abstractmethod
    def handle_callback(self, code: str) -> Dict[str, str]:
        """Handle the OAuth callback to retrieve access and refresh tokens."""
        pass

    @abstractmethod
    def refresh_access_token(self, access_token: str, refresh_token: str) -> Dict[str, str]:
        """Refresh the access token using the provided refresh token."""
        pass
