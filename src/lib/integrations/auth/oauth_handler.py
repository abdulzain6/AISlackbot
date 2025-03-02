import base64
import os
import jwt
import json
from authlib.integrations.requests_client import OAuth2Session
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from datetime import datetime, timezone
from typing import Dict, Any, Optional


class OAuthClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        auth_url: str,
        token_url: str,
        scope: str,
        secret_key: str,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_url = auth_url
        self.token_url = token_url
        self.scope = scope
        self.secret_key = secret_key[:32]

    def get_authorization_url(self, state: dict = None) -> str:
        client = OAuth2Session(
            client_id=self.client_id, redirect_uri=self.redirect_uri, scope=self.scope
        )
        auth_url, _ = client.create_authorization_url(
            self.auth_url, 
            state=self.generate_jwt_token(state),
            access_type="offline",  # ✅ Requests a refresh token
            prompt="consent",  # ✅ Forces Google to reissue a refresh token
        )
        return auth_url

    def exchange_code_for_token(self, code: str, validate: bool = True) -> Dict[str, Any]:
        """Exchange the authorization code for an access token (Google OAuth)."""
        client = OAuth2Session(
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
        )

        token = client.fetch_token(
            self.token_url,
            code=code,
            client_secret=self.client_secret,  # Required for Google OAuth
            include_client_id=True,  # Ensures client_id is sent in the body
            auth=None,  # Disables Basic Auth to prevent conflicts
        )

        if validate:
            self.validate_scopes(token)
        return token


    def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        client = OAuth2Session(
            client_id=self.client_id, client_secret=self.client_secret
        )
        token = client.refresh_token(self.token_url, refresh_token=refresh_token)
        self.validate_scopes(token)
        return token

    def generate_jwt_token(self, state: Optional[dict] = None) -> str:
        if state is None:
            state = {}

        json_state = json.dumps(state)
        iv = os.urandom(16)

        cipher = Cipher(
            algorithms.AES(self.secret_key.encode("utf-8")), modes.CFB(iv), backend=default_backend()
        )
        encryptor = cipher.encryptor()
        encrypted_json_state = (
            encryptor.update(json_state.encode("utf-8")) + encryptor.finalize()
        )

        # Encode iv and encrypted json state with base64
        iv_b64 = base64.b64encode(iv).decode('utf-8')
        encrypted_json_state_b64 = base64.b64encode(encrypted_json_state).decode('utf-8')

        return jwt.encode(
            {"iv": iv_b64, "token": encrypted_json_state_b64},
            self.secret_key,
            algorithm="HS256",
        )

    def decode_jwt_token(self, token: str) -> dict:
        decoded = jwt.decode(token, self.secret_key, algorithms=["HS256"])

        # Decode base64 encoded iv and token
        iv = base64.b64decode(decoded["iv"])
        encrypted_json_state = base64.b64decode(decoded["token"])

        cipher = Cipher(
            algorithms.AES(self.secret_key.encode("utf-8")), modes.CFB(iv), backend=default_backend()
        )
        decryptor = cipher.decryptor()
        decrypted_json_state = (
            decryptor.update(encrypted_json_state) + decryptor.finalize()
        )

        return json.loads(decrypted_json_state.decode("utf-8"))

    def validate_scopes(self, token_response: Dict[str, Any]) -> None:
        if 'scope' in token_response:
            response_scopes = set(token_response['scope'].split())
            requested_scopes = set(self.scope.split())
            if not requested_scopes.issubset(response_scopes):
                raise ValueError("Requested scopes were not granted")
        else:
            raise ValueError("No scopes were returned in the token response")

    def get_valid_token(
        self, access_token: str, refresh_token: str, expires_at: int
    ) -> dict:
        """Return a valid access token. Refresh if expired."""

        # Check if the token is expired
        if datetime.now(timezone.utc).timestamp() >= expires_at:
            token = self.refresh_token(refresh_token)
            return {
                "access_token": token["access_token"],
                "refresh_token": token.get("refresh_token", refresh_token),
                "expires_at": token["expires_at"],
            }

        # If token is still valid, return existing values
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
        }
