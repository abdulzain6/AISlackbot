from datetime import datetime
from google_auth_oauthlib.flow import Flow
from typing import Dict, Optional
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
import requests

class GoogleOAuth:
    def __init__(
        self,
        client_secrets_file: str, 
        redirect_uri: str, 
        client_id: str,
        client_secret: str,
        scopes: Optional[list] = None, 
        **kwargs
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.client_secrets_file = client_secrets_file
        self.redirect_uri = redirect_uri
        self.scopes = scopes if scopes else [
            "https://www.googleapis.com/auth/meetings.space.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar"
        ]
        self.flow = Flow.from_client_secrets_file(
            self.client_secrets_file,
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )

    def generate_oauth_link(self, state: str = None) -> str:
        """
        Generate the OAuth authorization URL for Google Drive with an optional state parameter.
        """
        auth_url, _ = self.flow.authorization_url(prompt='consent', state=state)
        return auth_url

    def handle_callback(self, code: str) -> Dict[str, str]:
        """
        Handle the OAuth callback to retrieve access and refresh tokens, user email, and username.
        """
        self.flow.fetch_token(code=code)

        # Retrieve the credentials.
        credentials = self.flow.credentials

        # Use Gmail API to fetch user info
        try:
            gmail_service = build('gmail', 'v1', credentials=credentials)
            profile = gmail_service.users().getProfile(userId='me').execute()
            
            email = profile['emailAddress']
            # Extract username from email address
            username = email.split('@')[0]
        except Exception as e:
            raise Exception(f"Error retrieving user info: {str(e)}")

        # Store the access and refresh tokens, user email, and username.
        tokens = {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expires_in": int((credentials.expiry - datetime.utcnow()).total_seconds()),
            "expires_at": credentials.expiry.timestamp(),
            "email": email,
            "username": username
        }
        return tokens
    
    def refresh_access_token(self, access_token: str, refresh_token: str) -> Dict[str, str]:
        """
        Refresh the access token using the provided refresh token.
        """
        # Initialize credentials using the provided access token and refresh token
        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.flow.client_config["client_id"],
            client_secret=self.flow.client_config["client_secret"]
        )

        # Refresh the credentials
        credentials.refresh(GoogleRequest())

        # Return the new access token and expiry
        tokens = {
            "access_token": credentials.token,
            "expires_in": credentials.expiry.isoformat()
        }
        return tokens
    